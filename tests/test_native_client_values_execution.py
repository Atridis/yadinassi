"""Offline execution orchestration tests, not native 1C evidence."""
import json
import os
import unittest
from pathlib import Path
from unittest import mock

import test_native_client_probe as probe

suite = probe.suite
NONCE = probe.NONCE


class ValuesExecutionTests(unittest.TestCase):
    argument = staticmethod(probe.ClientProbeHarness.argument)
    reset = probe.ClientProbeHarness.reset

    def setUp(self):
        probe.ClientProbeHarness.setUp(self)
        if os.name == 'nt':
            # Only private offline copies model Linux checkout bytes.
            for name in ('scenarios/values.bsl', suite.CLIENT_TARGET):
                path = self.inputs / name
                path.write_bytes(path.read_bytes().replace(b'\r\n', b'\n'))
            self.hashes = suite.input_hashes(self.inputs, client_probe=True)
        self.messages = [f'case-{i}: [value\\nline]\n' for i in range(402)]
        self.messages[4] = 'multiline: [a\nb\r\nc]\n'
        self.output = self.root / 'values.out'
        self.output.write_bytes(suite.serialize_messages(self.messages))
        self.transform = None

    def fake_native(self, command, directory, log, timeout, *, require_clean_tree=False):
        hook, self.hook = self.hook, None
        try:
            probe.ClientProbeHarness.fake_native(self, command, directory, log, timeout,
                                                require_clean_tree=require_clean_tree)
        finally:
            self.hook = hook
            if self.events[-1] == 'enterprise' and self.request:
                completed = Path(self.request['completed'])
                if completed.exists():
                    marker = probe.marker('completed')
                    marker['values'] = self.messages.copy()
                    if self.transform:
                        self.transform(marker)
                    completed.write_bytes(json.dumps(marker, ensure_ascii=False).encode())
            if hook:
                hook(self.events[-1])

    def run_values(self, **kwargs):
        return suite.run_client_probe(self.platform, self.work, self.inputs, NONCE,
                                      self.hashes, values_output=self.output, **kwargs)

    def test_full_exact_output_and_multiline_preserved(self):
        result = self.run_values()
        self.assertEqual(result['status'], 'ok', result)
        self.assertEqual(result['message_count'], 402)
        self.assertEqual(result['output_sha256'], suite.digest(self.output.read_bytes()))
        self.assertEqual(result['output_size'], len(self.output.read_bytes()))
        self.assertEqual(result['source_sha256'], self.hashes['integrational_tests/tests/values.bsl'])
        module = suite.client_values_module((self.inputs / 'scenarios/values.bsl').read_bytes(),
                                          (self.inputs / suite.CLIENT_TARGET).read_bytes())
        self.assertEqual(result['module_sha256'], suite.digest(module))
        self.assertEqual(result['roundtrip_sha256'], suite.digest(module))
        self.assertEqual(self.events, ['build', 'dump', 'enterprise'])
        self.assertEqual(list(self.work.glob('*.out')), [])

    def test_missing_extra_reordered_and_altered_messages_fail(self):
        mutations = [lambda m: m['values'].pop(),
                     lambda m: m['values'].append('extra'),
                     lambda m: m['values'].reverse(),
                     lambda m: m['values'].__setitem__(4, 'multiline: [a\nbCHANGED\nc]\n')]
        for transform in mutations:
            self.transform = transform
            result = self.run_values()
            self.assertEqual(result['status'], 'failed')
            self.assertIn(result['failure_kind'], {'invalid_result', 'output_mismatch'})
            self.assertIsNone(result['output_sha256'])
            self.reset()

    def test_every_new_chars_record_is_mandatory_not_an_ignored_suffix(self):
        # Synthetic wire records test the strict comparator, not native semantics.
        # Original 261 records retain their order; every appended record matters.
        for index in range(261, 402):
            self.transform = lambda marker, index=index: marker['values'].__setitem__(index, 'changed')
            with self.subTest(index=index):
                result = self.run_values()
                self.assertEqual(result['status'], 'failed')
                self.assertEqual(result['failure_kind'], 'output_mismatch')
            self.reset()

    def test_server_trailing_bytes_fail_without_rewriting_oracle(self):
        original = self.output.read_bytes() + b'\n'
        self.output.write_bytes(original)
        result = self.run_values()
        self.assertEqual(result['failure_kind'], 'output_mismatch')
        self.assertEqual(self.output.read_bytes(), original)

    def test_wrong_nonce_phase_witness_and_false_completion_fail(self):
        for key, value in [('nonce', '0'*32), ('phase', 'error'), ('witness', 'server'),
                           ('values', [42, 'client-probe', 3, 6])]:
            self.transform = lambda marker: marker.update({key: value})
            self.assertEqual(self.run_values()['failure_kind'], 'invalid_result')
            self.reset()

    def test_timeout_even_with_completed_output_never_succeeds(self):
        for phases in [(), ('entered',), ('entered', 'completed')]:
            self.run_markers = phases
            self.run_error = 'timeout'
            result = self.run_values()
            self.assertEqual(result['failure_kind'], 'timeout')
            self.assertFalse(result['witness_verified'])
            self.assertIsNone(result['output_sha256'])
            self.reset()

    def test_survivor_fails_after_fresh_output(self):
        with mock.patch.object(suite, 'client_process_snapshot', return_value={(999999, '1')}):
            result = self.run_values()
        self.assertEqual(result['failure_kind'], 'process_failed')
        self.assertFalse(result['quiet'])

    def test_roundtrip_directive_and_server_substitution_fail_before_run(self):
        def tamper(mode):
            if mode == 'dump':
                path = self.work / 'roundtrip' / suite.CLIENT_MODULE
                path.write_bytes(path.read_bytes().replace('&НаКлиенте'.encode(), '&НаСервере'.encode(), 1))
        self.hook = tamper
        self.assertEqual(self.run_values()['failure_kind'], 'module_mismatch')
        self.assertEqual(self.events, ['build', 'dump'])

    def test_source_tamper_rejected_before_compile_even_with_matching_input_hash(self):
        path = self.inputs / 'scenarios/values.bsl'
        path.write_bytes(path.read_bytes() + b'\n')
        self.hashes['integrational_tests/tests/values.bsl'] = suite.digest(path.read_bytes())
        self.assertEqual(self.run_values()['failure_kind'], 'invalid_input')
        self.assertEqual(self.events, [])

    def test_final_census_clears_values_success_and_output_metadata(self):
        record = suite.empty_report(NONCE, client_probe=True, client_values=True)
        record['client_values'] = self.run_values()
        suite.fail_client_process_checkpoint(record, False)
        self.assertEqual(record['client_values']['status'], 'failed')
        self.assertIsNone(record['client_values']['output_sha256'])
        self.assertFalse(record['client_values']['witness_verified'])

    def test_conflicting_parity_options_rejected_before_execution(self):
        self.assertEqual(self.run_values(dates_output=self.output)['failure_kind'], 'invalid_input')
        self.assertEqual(self.events, [])

    def test_fresh_server_must_be_present_bounded_and_exact(self):
        self.output.unlink()
        result = self.run_values()
        self.assertEqual(result['failure_kind'], 'artifact_missing')
        self.assertIsNone(result['output_sha256'])
        self.assertFalse(result['witness_verified'])

    def test_client_roundtrip_body_tamper_fails_before_enterprise(self):
        def tamper(mode):
            if mode == 'dump':
                path = self.work / 'roundtrip' / suite.CLIENT_MODULE
                path.write_bytes(path.read_bytes().replace(b'Null', b'Undefined', 1))
        self.hook = tamper
        self.assertEqual(self.run_values()['failure_kind'], 'module_mismatch')
        self.assertEqual(self.events, ['build', 'dump'])

    def test_values_stall_option_rejected_before_execution(self):
        self.assertEqual(self.run_values(stall=True)['failure_kind'], 'invalid_input')
        self.assertEqual(self.events, [])


class ValuesSuiteOrderTests(unittest.TestCase):
    def test_six_cases_then_probe_values_watchdog_and_private_oracle(self):
        harness = probe.stage_fixture.FullSuiteHarness()
        harness.setUp()
        self.addCleanup(harness.doCleanups)
        # Historical 137-value default lane; not current 138-value admission.
        source = (probe.ROOT / suite.CLIENT_SOURCE).read_bytes()
        if os.name == 'nt':
            source = source.replace(b'\r\n', b'\n')
        (harness.inputs / suite.CLIENT_TARGET).write_bytes(suite.preprocessor_shared_source(source))
        calls = []
        def client(platform, root, inputs, nonce, hashes, **kwargs):
            calls.append(root.name)
            self.assertEqual(len(harness.events), 12)
            if 'dates_output' in kwargs:
                return dict(suite.empty_dates_report(), status='ok', failure_kind='none')
            if 'values_output' in kwargs:
                self.assertEqual(kwargs['values_output'], harness.work / 'values.out')
                self.assertEqual(kwargs['values_output'].read_bytes(),
                                 suite.serialize_messages(probe.stage_fixture.MESSAGES))
                return dict(suite.empty_values_report(), status='ok', failure_kind='none')
            return dict(suite.empty_client_report(), status='ok', failure_kind='none')
        def watchdog(*args):
            calls.append('watchdog')
            return dict(suite.empty_watchdog_report(), status='ok', failure_kind='none')
        with mock.patch.object(suite, 'run_client_probe', side_effect=client), \
                mock.patch.object(suite, 'run_client_watchdog', side_effect=watchdog):
            result = suite.run_suite(harness.launcher, harness.platform, harness.epf,
                harness.work, harness.inputs, NONCE, client_probe=True, client_dates=True, client_values=True,
                watchdog_check=True)
        self.assertEqual(result['status'], 'ok', result)
        self.assertEqual(calls, ['client-probe', 'client-dates', 'client-values', 'watchdog'])
        self.assertEqual(len(result['input_sha256']), 24)
        self.assertEqual(sorted(p.name for p in harness.work.glob('*.out')),
                         sorted(name + '.out' for name in suite.SCENARIOS))


if __name__ == '__main__':
    unittest.main()
