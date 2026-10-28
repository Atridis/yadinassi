"""Current harness source-input bounds; synthetic gates, not native parity.

Only the source-file allowance changes. The host gate tests deliberately stub
comparison output so that each real secure file read is isolated from runtime
semantics. Existing comparator/runtime tests exercise the actual comparison.
"""
import copy
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from scripts import native_async_comparison as adapter
from test_native_1c_full_host import full as host
from test_native_1c_output_artifact import semantic_report

ROOT = Path(__file__).resolve().parents[1]
SOURCE_PATH = 'scripts/native_1c_bootstrap/full_suite.py'
CAP = 294912
SOURCE = (ROOT / SOURCE_PATH).read_bytes()
NATIVE = json.loads((ROOT / 'tests/fixtures/native_async_comparison_linux_8_3_27_1508.json').read_text())['client_async']
RESULT = dict(profile='async-language-8-v1', status='matched',
              cases=[['matched', 'none'] for _ in range(8)], actual_sha256='a'*64)


def at_cap():
    return SOURCE + b' ' * (CAP - len(SOURCE))


class AsyncSourceInputBudgetTests(unittest.TestCase):
    def test_current_source_and_exact_adapter_boundary(self):
        self.assertGreaterEqual(len(SOURCE.replace(b'\r\n', b'\n')), 277724)
        self.assertLessEqual(len(SOURCE), CAP)
        self.assertEqual(adapter.MAX_SOURCE_BYTES, CAP)
        self.assertEqual(CAP, 288 * 1024)
        expected = adapter.read_pinned_sources(SOURCE)
        # Model a physical Windows checkout even when this test runs on Linux.
        crlf = SOURCE.replace(b"\r\n", b"\n").replace(b"\n", b"\r\n")
        self.assertLessEqual(len(crlf), CAP)
        self.assertEqual(adapter.read_pinned_sources(crlf), expected)
        self.assertEqual(adapter.read_pinned_sources(at_cap()), expected)
        with self.assertRaises(adapter.InvalidComparisonInput):
            adapter.read_pinned_sources(at_cap() + b' ')
        # Source growth never changes the pinned template/body identities.
        identity = host.async_source_identity(SOURCE)
        baseline = json.loads((ROOT / 'integrational_tests/directive_probes/infobase_context_measurement.json').read_text())
        self.assertEqual(identity, baseline['async8_identity'])
        self.assertEqual((adapter.MAX_ACTUAL_BYTES, host.ASYNC_ACTUAL_LIMIT,
                          host.MAX_STAGE_REPORT, host.MAX_REPORT), (8192, 8192, 8192, 32768))


@unittest.skipIf(os.name == 'nt', 'real host secure descriptor reads are POSIX-only')
class AsyncHostSourceReadGateTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(); self.addCleanup(temp.cleanup)
        self.root = Path(temp.name).resolve()
        self.source = self.root / SOURCE_PATH
        self.source.parent.mkdir(parents=True)
        self.private = self.root / 'private'; self.private.mkdir()
        self.report = semantic_report()
        self.report['stage3']['client_async'] = copy.deepcopy(NATIVE)
        self.hashes = self.report['trusted_input_sha256']
        self.write(at_cap())
        self.reader = self.patch(host, 'read_regular', wraps=host.read_regular)
        self.patch(host, 'interpreter_provenance', return_value={'stable': True})
        self.patch(host, 'async_contract', return_value=adapter)
        self.patch(adapter, 'compare_observations', return_value=copy.deepcopy(RESULT))
        self.runner = mock.Mock(return_value=(0, b'[]', b''))

    def patch(self, target, name, **kwargs):
        patcher = mock.patch.object(target, name, **kwargs)
        value = patcher.start(); self.addCleanup(patcher.stop)
        return value

    def write(self, raw):
        self.source.write_bytes(raw)
        self.hashes[SOURCE_PATH] = host.digest(raw)
        self.report['stage3']['input_sha256'] = dict(self.hashes)

    def execute(self):
        return host.compare_async_runtime(self.root, self.private, self.report,
                                          self.hashes, runner=self.runner)

    def assert_reads(self, count):
        self.assertEqual(self.reader.call_args_list,
                         [mock.call(self.source, CAP, nonempty=True)] * count)

    def test_both_host_reads_accept_exact_cap(self):
        self.assertEqual(self.execute(), RESULT)
        self.runner.assert_called_once()
        self.assert_reads(2)

    def test_first_read_rejects_cap_plus_one_before_child(self):
        self.write(at_cap() + b' ')
        with self.assertRaisesRegex(host.FullError, '^invalid_private_file$'):
            self.execute()
        self.runner.assert_not_called(); self.assert_reads(1)

    def test_first_read_rejects_nonregular_before_child(self):
        self.source.unlink(); self.source.mkdir()
        with self.assertRaisesRegex(host.FullError, '^invalid_private_file$'):
            self.execute()
        self.runner.assert_not_called(); self.assert_reads(1)

    def test_first_read_rejects_symlink_before_child(self):
        target = self.root / 'regular.py'; target.write_bytes(at_cap())
        self.source.unlink(); self.source.symlink_to(target)
        with self.assertRaisesRegex(host.FullError, '^invalid_private_file$'):
            self.execute()
        self.runner.assert_not_called(); self.assert_reads(1)

    def test_first_read_source_hash_mismatch_fails_before_child(self):
        self.hashes[SOURCE_PATH] = '0' * 64
        self.report['stage3']['input_sha256'] = dict(self.hashes)
        with self.assertRaisesRegex(host.FullError, '^async_source_changed$'):
            self.execute()
        self.runner.assert_not_called(); self.assert_reads(1)

    def test_post_read_rejects_cap_plus_one(self):
        def grow(*args, **kwargs):
            self.source.write_bytes(at_cap() + b' ')
            return 0, b'[]', b''
        self.runner.side_effect = grow
        with self.assertRaisesRegex(host.FullError, '^invalid_private_file$'):
            self.execute()
        self.runner.assert_called_once(); self.assert_reads(2)

    def test_post_read_rejects_nonregular(self):
        def replace(*args, **kwargs):
            self.source.unlink(); self.source.mkdir()
            return 0, b'[]', b''
        self.runner.side_effect = replace
        with self.assertRaisesRegex(host.FullError, '^invalid_private_file$'):
            self.execute()
        self.runner.assert_called_once(); self.assert_reads(2)

    def test_post_read_rejects_same_length_source_change(self):
        def change(*args, **kwargs):
            self.source.write_bytes(at_cap()[:-1] + b'\n')
            return 0, b'[]', b''
        self.runner.side_effect = change
        with self.assertRaisesRegex(host.FullError, '^execution_provenance_changed$'):
            self.execute()
        self.runner.assert_called_once(); self.assert_reads(2)


if __name__ == '__main__':
    unittest.main()
