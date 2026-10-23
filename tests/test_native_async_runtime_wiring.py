"""Offline bounded actual-only child contract; not fresh native parity."""
import copy
from pathlib import Path
import tempfile
import unittest
from unittest import mock
from scripts import native_1c_full_host as host
from test_native_async_comparison import NATIVE, ROOT
from test_native_1c_output_artifact import semantic_report

class AsyncRuntimeWiringTests(unittest.TestCase):
    def setUp(self):
        self.report = semantic_report()
        self.report['stage3']['client_async'] = copy.deepcopy(NATIVE)
        versions = mock.patch.object(host.importlib.metadata, 'version', side_effect=lambda key: host.DEPENDENCIES[key])
        versions.start()
        self.addCleanup(versions.stop)
        self.path = 'scripts/native_1c_bootstrap/full_suite.py'
        self.hashes = self.report['trusted_input_sha256']
        self.hashes[self.path] = host.digest((ROOT / self.path).read_bytes())
        self.report['stage3']['input_sha256'] = dict(self.hashes)
    def execute(self, runner=None):
        with tempfile.TemporaryDirectory() as private:
            kwargs = {} if runner is None else {'runner': runner}
            return host.compare_async_runtime(ROOT, Path(private), self.report, self.hashes, **kwargs)
    def test_real_child(self):
        result = self.execute()
        self.assertEqual(result['status'], 'matched')
        self.assertEqual(result['actual_sha256'], 'a576aa7f01fc6b14b1bf695e3a41e7cbd5ab87d21b385045a0a2eb33e95955f7')
    def test_isolation(self):
        def runner(args, cwd, **limits):
            self.assertEqual(args[1:3], ['-I', '-B'])
            self.assertEqual(args[-1], str(ROOT))
            self.assertNotIn('continuity_sha256', args[-2])
            self.assertEqual(limits['stdout_limit'], 8192)
            self.assertEqual(limits['stderr_limit'], host.MAX_STDERR)
            self.assertTrue(Path(args[4].split('=', 1)[1]).is_dir())
            return host.bounded_child(args, cwd, **limits)
        self.assertEqual(self.execute(runner)['status'], 'matched')
    def test_early_gates(self):
        for key in ('native_evidence_accepted', 'container_cleanup_verified', 'native_transport_validated'):
            self.report[key] = False
            runner = mock.Mock()
            with self.assertRaisesRegex(host.FullError, '^semantic_context_invalid$'): self.execute(runner)
            runner.assert_not_called()
            self.report[key] = True
    def test_source_change(self):
        self.hashes[self.path] = '0' * 64
        self.report['stage3']['input_sha256'] = dict(self.hashes)
        runner = mock.Mock()
        with self.assertRaisesRegex(host.FullError, '^async_source_changed$'): self.execute(runner)
        runner.assert_not_called()
    def test_untrusted_output(self):
        for response in [(0, b'{}', b''), (0, b'[]', b''), (0, b'NaN', b''),
                         (1, b'SECRET', b''), (0, b'[]', b'SECRET')]:
            runner = mock.Mock(return_value=response)
            with self.assertRaisesRegex(host.FullError, '^async_(execution_failed|comparison_invalid)$') as error:
                self.execute(runner)
            runner.assert_called_once()
            self.assertNotIn('SECRET', str(error.exception))
    def test_provenance_change(self):
        with mock.patch.object(host, 'interpreter_provenance', side_effect=[{'source': 'old'}, {'source': 'new'}]):
            with self.assertRaisesRegex(host.FullError, 'execution_provenance_changed'): self.execute()
    def test_schema(self):
        valid = {'profile': 'async-language-8-v1', 'status': 'matched',
                 'cases': [['matched', 'none'] for _ in range(8)], 'actual_sha256': 'a' * 64}
        self.assertEqual(host.validate_async_comparison(valid), valid)
        for change in ({'status': 'mismatched'}, {'cases': valid['cases'][:7]},
                       {'actual_sha256': 'secret'}, {'extra': 'value'}):
            with self.assertRaises(host.FullError): host.validate_async_comparison({**valid, **change})

    def test_native_mutation_is_compared_not_replaced(self):
        self.report['stage3']['client_async']['cases'][0][6][0] = [4, 18]
        self.assertEqual(self.execute()['status'], 'mismatched')

    def test_wrong_target_and_nonce_rejected_before_child(self):
        for section, key, value in ((self.report, 'native_target', host.WINDOWS_TARGET),
                                   (self.report['stage3'], 'nonce', '0' * 32)):
            old = section[key]
            section[key] = value
            runner = mock.Mock()
            with self.assertRaisesRegex(host.FullError, '^semantic_context_invalid$'): self.execute(runner)
            runner.assert_not_called()
            section[key] = old


class AsyncParityPublicationContextTests(unittest.TestCase):
    """A matched compact result cannot authorize parity in another context."""

    @staticmethod
    def with_async(report):
        report['stage3']['client_async'] = copy.deepcopy(NATIVE)
        report['async_comparison'] = {
            'profile': 'async-language-8-v1', 'status': 'matched',
            'cases': [['matched', 'none'] for _ in range(8)],
            'actual_sha256': 'a' * 64,
        }
        return report

    def test_artifact_rejects_windows_context_even_with_matched_comparator(self):
        import json
        from test_native_1c_output_artifact import accepted_report, artifact_files, full
        baseline = json.loads(artifact_files(self.with_async(semantic_report()))['provenance.json'])
        self.assertTrue(baseline['client_async_parity_claimed'])
        with self.assertRaisesRegex(full.FullError, '^native_artifact_evidence_invalid$'):
            artifact_files(self.with_async(accepted_report()))

    def test_artifact_rejects_changed_nonce_even_with_matched_comparator(self):
        from test_native_1c_output_artifact import artifact_files, full
        report = self.with_async(semantic_report())
        artifact_files(report)  # Prove all unrelated artifact gates accept this fixture.
        report['stage3']['nonce'] = '0' * 32
        with self.assertRaisesRegex(full.FullError, '^native_artifact_evidence_invalid$'):
            artifact_files(report)

    def run_main(self, report):
        import contextlib
        import io
        import json
        from test_native_1c_output_artifact import smoke
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / 'summary.json'
            # Match requested target/mode to the report, so rejection cannot be
            # explained by an unrelated command-line/report mismatch.
            args = ['--execute-approved-image', '--full-suite', '--client-probe',
                    '--client-async-measurement', '--native-target', report['native_target'],
                    '--comparison-mode', report['comparison_mode'], '--output', str(output)]
            with mock.patch.object(smoke, 'run_smoke', return_value=report), contextlib.redirect_stdout(io.StringIO()):
                code = smoke.main(args)
            return code, json.loads(output.read_text())

    def test_final_main_requires_linux_context_and_bound_nonce(self):
        from test_native_1c_output_artifact import accepted_report
        code, public = self.run_main(self.with_async(semantic_report()))
        self.assertEqual(code, 0)
        self.assertTrue(public['client_async_parity_claimed'])
        windows = self.with_async(accepted_report())
        nonce = self.with_async(semantic_report())
        nonce['stage3']['nonce'] = '0' * 32
        for report in (windows, nonce):
            with self.subTest(target=report['native_target']):
                code, public = self.run_main(report)
                self.assertEqual(code, 1)
                self.assertFalse(public['client_async_parity_claimed'])
                self.assertFalse(public['smoke_completed'])
