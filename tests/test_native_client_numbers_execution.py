"""Offline execution orchestration tests, not native 1C evidence."""
import json
import os
import shutil
import unittest
from pathlib import Path
from unittest import mock

import test_native_client_probe as probe

suite = probe.suite
NONCE = probe.NONCE


class NumbersExecutionTests(unittest.TestCase):
    argument = staticmethod(probe.ClientProbeHarness.argument)
    reset = probe.ClientProbeHarness.reset

    def setUp(self):
        probe.ClientProbeHarness.setUp(self)
        if os.name == 'nt':
            # Only private offline copies model Linux checkout bytes.
            for name in ('scenarios/numbers.bsl', suite.CLIENT_TARGET):
                path = self.inputs / name
                path.write_bytes(path.read_bytes().replace(b'\r\n', b'\n'))
            self.hashes = suite.input_hashes(self.inputs, client_probe=True)
        self.messages = [f'case-{i}: [value\\nline]\n' for i in range(421)]
        self.messages[4] = 'multiline: [a\nb\r\nc]\n'
        self.messages[27:32] = ['present.string: [native-text]', 'present.concat: [native-text]',
                                'present.direct.next:', 'native-text', 'numbers.complete: [ok]']
        (self.root / 'numbers-case').mkdir()
        (self.root / 'numbers-case/result.json').write_text(json.dumps({'messages': self.messages, 'error': ''}))
        self.output = self.root / 'numbers.out'
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

    def run_numbers(self, **kwargs):
        return suite.run_client_probe(self.platform, self.work, self.inputs, NONCE,
                                      self.hashes, numbers_output=self.output, **kwargs)

    def test_full_exact_output_and_multiline_preserved(self):
        result = self.run_numbers()
        self.assertEqual(result['status'], 'ok', result)
        self.assertEqual(result['message_count'], 421)
        self.assertTrue(result['conversion_verified'])
        self.assertEqual(result['output_sha256'], suite.digest(self.output.read_bytes()))
        self.assertEqual(result['output_size'], len(self.output.read_bytes()))
        self.assertEqual(result['source_sha256'], self.hashes['integrational_tests/tests/numbers.bsl'])
        module = suite.client_numbers_module((self.inputs / 'scenarios/numbers.bsl').read_bytes(),
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
            result = self.run_numbers()
            self.assertEqual(result['status'], 'failed')
            self.assertIn(result['failure_kind'], {'invalid_result', 'output_mismatch'})
            self.assertIsNone(result['output_sha256'])
            self.reset()

    def test_server_trailing_bytes_fail_without_rewriting_oracle(self):
        original = self.output.read_bytes() + b'\n'
        self.output.write_bytes(original)
        result = self.run_numbers()
        self.assertEqual(result['failure_kind'], 'output_mismatch')
        self.assertEqual(self.output.read_bytes(), original)

    def test_wrong_nonce_phase_witness_and_false_completion_fail(self):
        for key, value in [('nonce', '0'*32), ('phase', 'error'), ('witness', 'server'),
                           ('values', [42, 'client-probe', 3, 6])]:
            self.transform = lambda marker: marker.update({key: value})
            self.assertEqual(self.run_numbers()['failure_kind'], 'invalid_result')
            self.reset()

    def test_timeout_even_with_completed_output_never_succeeds(self):
        for phases in [(), ('entered',), ('entered', 'completed')]:
            self.run_markers = phases
            self.run_error = 'timeout'
            result = self.run_numbers()
            self.assertEqual(result['failure_kind'], 'timeout')
            self.assertFalse(result['witness_verified'])
            self.assertIsNone(result['output_sha256'])
            self.reset()

    def test_survivor_fails_after_fresh_output(self):
        with mock.patch.object(suite, 'client_process_snapshot', return_value={(999999, '1')}):
            result = self.run_numbers()
        self.assertEqual(result['failure_kind'], 'process_failed')
        self.assertFalse(result['quiet'])

    def test_roundtrip_directive_and_server_substitution_fail_before_run(self):
        def tamper(mode):
            if mode == 'dump':
                path = self.work / 'roundtrip' / suite.CLIENT_MODULE
                path.write_bytes(path.read_bytes().replace('&НаКлиенте'.encode(), '&НаСервере'.encode(), 1))
        self.hook = tamper
        self.assertEqual(self.run_numbers()['failure_kind'], 'module_mismatch')
        self.assertEqual(self.events, ['build', 'dump'])

    def test_source_tamper_rejected_before_compile_even_with_matching_input_hash(self):
        path = self.inputs / 'scenarios/numbers.bsl'
        path.write_bytes(path.read_bytes() + b'\n')
        self.hashes['integrational_tests/tests/numbers.bsl'] = suite.digest(path.read_bytes())
        self.assertEqual(self.run_numbers()['failure_kind'], 'invalid_input')
        self.assertEqual(self.events, [])

    def test_final_census_clears_numbers_success_and_output_metadata(self):
        record = suite.empty_report(NONCE, client_probe=True, client_numbers=True)
        record['client_numbers'] = self.run_numbers()
        suite.fail_client_process_checkpoint(record, False)
        self.assertEqual(record['client_numbers']['status'], 'failed')
        self.assertIsNone(record['client_numbers']['output_sha256'])
        self.assertFalse(record['client_numbers']['witness_verified'])

    def test_conflicting_parity_options_rejected_before_execution(self):
        self.assertEqual(self.run_numbers(dates_output=self.output)['failure_kind'], 'invalid_input')
        self.assertEqual(self.events, [])

    def test_fresh_server_must_be_present_bounded_and_exact(self):
        self.output.unlink()
        result = self.run_numbers()
        self.assertEqual(result['failure_kind'], 'artifact_missing')
        self.assertIsNone(result['output_sha256'])
        self.assertFalse(result['witness_verified'])

    def test_client_roundtrip_body_tamper_fails_before_enterprise(self):
        def tamper(mode):
            if mode == 'dump':
                path = self.work / 'roundtrip' / suite.CLIENT_MODULE
                path.write_bytes(path.read_bytes().replace(b'1234.5', b'1234.6', 1))
        self.hook = tamper
        self.assertEqual(self.run_numbers()['failure_kind'], 'module_mismatch')
        self.assertEqual(self.events, ['build', 'dump'])

    def test_numbers_stall_option_rejected_before_execution(self):
        self.assertEqual(self.run_numbers(stall=True)['failure_kind'], 'invalid_input')
        self.assertEqual(self.events, [])

    def test_same_bytes_without_raw_number_calibration_still_fail(self):
        for ordinal in (27, 28, 29, 31):
            original = self.messages.copy()
            self.messages[ordinal] = 'wrong metadata'
            self.output.write_bytes(suite.serialize_messages(self.messages))
            (self.root / 'numbers-case/result.json').write_text(json.dumps({'messages': self.messages, 'error': ''}))
            result = self.run_numbers()
            self.assertEqual(result['failure_kind'], 'output_mismatch')
            self.assertFalse(result['conversion_verified'])
            self.messages = original
            self.reset()

    def test_missing_or_changed_independent_server_result_fails(self):
        path = self.root / 'numbers-case/result.json'
        path.unlink()
        self.assertEqual(self.run_numbers()['failure_kind'], 'artifact_missing')
        self.reset()
        different = self.messages.copy()
        different[30] = 'different native result'
        path.write_text(json.dumps({'messages': different, 'error': ''}))
        self.assertEqual(self.run_numbers()['failure_kind'], 'invalid_result')



class NumbersSuiteOrderTests(unittest.TestCase):
    def test_six_cases_then_probe_numbers_watchdog_and_private_oracle(self):
        harness = probe.stage_fixture.FullSuiteHarness()
        harness.setUp()
        self.addCleanup(harness.doCleanups)
        shutil.copyfile(probe.ROOT / suite.CLIENT_SOURCE, harness.inputs / suite.CLIENT_TARGET)
        calls = []
        def client(platform, root, inputs, nonce, hashes, **kwargs):
            calls.append(root.name)
            self.assertEqual(len(harness.events), 12)
            if 'dates_output' in kwargs:
                return dict(suite.empty_dates_report(), status='ok', failure_kind='none')
            if 'numbers_output' in kwargs:
                self.assertEqual(kwargs['numbers_output'], harness.work / 'numbers.out')
                self.assertEqual(kwargs['numbers_output'].read_bytes(),
                                 suite.serialize_messages(probe.stage_fixture.MESSAGES))
                return dict(suite.empty_numbers_report(), status='ok', failure_kind='none')
            return dict(suite.empty_client_report(), status='ok', failure_kind='none')
        def watchdog(*args):
            calls.append('watchdog')
            return dict(suite.empty_watchdog_report(), status='ok', failure_kind='none')
        with mock.patch.object(suite, 'run_client_probe', side_effect=client), \
                mock.patch.object(suite, 'run_client_watchdog', side_effect=watchdog):
            result = suite.run_suite(harness.launcher, harness.platform, harness.epf,
                harness.work, harness.inputs, NONCE, client_probe=True, client_dates=True, client_numbers=True,
                watchdog_check=True)
        self.assertEqual(result['status'], 'ok', result)
        self.assertEqual(calls, ['client-probe', 'client-dates', 'client-numbers', 'watchdog'])
        self.assertEqual(len(result['input_sha256']), 24)
        self.assertEqual(sorted(p.name for p in harness.work.glob('*.out')),
                         sorted(name + '.out' for name in suite.SCENARIOS))


class NumbersFinalEmitterTests(unittest.TestCase):
    emitter = probe.ClientFinalReportEmitterTests.emitter

    def test_six_client_teardown_clears_conversion_and_preserves_prior_proofs(self):
        for watchdog in (False, True):
            for cleanup_failed in (False, True):
                with self.subTest(watchdog=watchdog, cleanup_failed=cleanup_failed):
                    report = self.emitter(watchdog=watchdog, dates=True, values=True,
                                          collections=True, numbers=True, cleanup_failed=cleanup_failed)
                    stage = report['stage3']
                    self.assertEqual(stage['schema'], 1)
                    for name in ('client_probe', 'client_dates', 'client_values', 'client_collections'):
                        self.assertEqual(stage[name]['status'], 'ok')
                    record = stage['client_numbers']
                    if watchdog:
                        self.assertEqual(record['status'], 'ok')
                        self.assertTrue(record['conversion_verified'])
                    else:
                        self.assertEqual(record['status'], 'failed')
                        self.assertFalse(record['conversion_verified'])
                        for key in ('output_sha256', 'output_size', 'message_count'):
                            self.assertIsNone(record[key])


if __name__ == '__main__':
    unittest.main()
