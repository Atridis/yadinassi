"""Offline execution orchestration tests, not native 1C evidence."""
import json
import os
import unittest
from pathlib import Path
from unittest import mock

import test_native_client_probe as probe

suite = probe.suite
NONCE = probe.NONCE


class CollectionsMismatchMetadataTests(unittest.TestCase):
    def test_all_messages_differ_caps_ordinals_without_message_text(self):
        server, client = ['server'] * 1023, ['PRIVATE'] * 1023
        data = suite.collections_mismatch(client, server, suite.serialize_messages(server))
        self.assertEqual(data['count'], 1023)
        self.assertEqual(data['first'], 1)
        self.assertEqual(data['ordinals'], list(range(1, 17)))
        self.assertEqual(set(data), {'count', 'first', 'ordinals', 'client_sha256',
                                     'server_sha256', 'client_size', 'server_size'})
        self.assertNotIn('PRIVATE', json.dumps(data))

    def test_multiline_and_unicode_use_serialized_message_not_line_positions(self):
        server = [''] * 1023
        server[400] = 'абв\r\nг\rд'
        client = server.copy()
        client[400] += '😀'
        data = suite.collections_mismatch(client, server, suite.serialize_messages(server))
        self.assertEqual(data['ordinals'], [401])
        self.assertEqual(data['client_size'] - data['server_size'], 4)
        self.assertEqual(data['server_sha256'], suite.digest('абв\nг\nд\n'.encode()))

    def test_existing_newline_serialization_does_not_create_false_differences(self):
        server = ['same'] * 1023
        server[0] = 'a\r\nb'
        client = server.copy()
        client[0] = 'a\nb'
        client[1022] = 'different'
        data = suite.collections_mismatch(client, server, suite.serialize_messages(server))
        self.assertEqual(data['ordinals'], [1023])
        self.assertEqual(data['count'], 1)

    def test_unbound_or_equal_outputs_reject_localization(self):
        server, client = ['same'] * 1023, ['different'] * 1023
        for left, right, output in (
                (server, server, suite.serialize_messages(server)),
                (client, server, b'not this server output'),
                (client[:-1], server, suite.serialize_messages(server)),
                (client, server[:-1], suite.serialize_messages(server[:-1])),
                (client, server, 'not bytes'),
                ([1] * 1023, server, suite.serialize_messages(server)),
                (client, [True] * 1023, b'')):
            with self.subTest(left=type(left), right=type(right)), self.assertRaises(suite.FullError):
                suite.collections_mismatch(left, right, output)


class CollectionsExecutionTests(unittest.TestCase):
    argument = staticmethod(probe.ClientProbeHarness.argument)
    reset = probe.ClientProbeHarness.reset

    def setUp(self):
        probe.ClientProbeHarness.setUp(self)
        if os.name == 'nt':
            # Only private offline copies model Linux checkout bytes.
            for name in ('scenarios/collections.bsl', suite.CLIENT_TARGET):
                path = self.inputs / name
                path.write_bytes(path.read_bytes().replace(b'\r\n', b'\n'))
            self.hashes = suite.input_hashes(self.inputs, client_probe=True)
        self.messages = [f'case-{i}: [value\\nline]\n' for i in range(1023)]
        self.messages[4] = 'multiline: [a\nb\r\nc]\n'
        self.output = self.root / 'collections.out'
        self.output.write_bytes(suite.serialize_messages(self.messages))
        server_result = self.root / 'collections-case/result.json'
        server_result.parent.mkdir()
        server_result.write_text(json.dumps({'messages': self.messages, 'error': ''}), encoding='utf-8')
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

    def run_collections(self, **kwargs):
        return suite.run_client_probe(self.platform, self.work, self.inputs, NONCE,
                                      self.hashes, collections_output=self.output, **kwargs)

    def test_full_exact_output_and_multiline_preserved(self):
        result = self.run_collections()
        self.assertEqual(result['status'], 'ok', result)
        self.assertEqual(result['message_count'], 1023)
        self.assertEqual(result['output_sha256'], suite.digest(self.output.read_bytes()))
        self.assertEqual(result['output_size'], len(self.output.read_bytes()))
        self.assertEqual(result['source_sha256'], self.hashes['integrational_tests/tests/collections.bsl'])
        module = suite.client_collections_module((self.inputs / 'scenarios/collections.bsl').read_bytes(),
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
            result = self.run_collections()
            self.assertEqual(result['status'], 'failed')
            self.assertIn(result['failure_kind'], {'invalid_result', 'output_mismatch'})
            self.assertIsNone(result['output_sha256'])
            self.reset()

    def test_exact_mismatch_has_only_bounded_ordinals_hashes_and_sizes(self):
        def mutate(marker):
            marker['values'][4] += 'DIFFERENT-PRIVATE-TEXT'
            marker['values'][1022] += 'DIFFERENT-PRIVATE-TEXT'
        self.transform = mutate
        result = self.run_collections()
        self.assertEqual(result['failure_kind'], 'output_mismatch')
        self.assertFalse(result['witness_verified'])
        self.assertIsNone(result['output_sha256'])
        mismatch = result['mismatch']
        self.assertEqual(mismatch['count'], 2)
        self.assertEqual(mismatch['first'], 5)
        self.assertEqual(mismatch['ordinals'], [5, 1023])
        expected = suite.serialize_messages([self.messages[4]])
        self.assertEqual(mismatch['server_sha256'], suite.digest(expected))
        self.assertEqual(mismatch['server_size'], len(expected))
        self.assertNotIn('PRIVATE', json.dumps(result))
        self.assertNotEqual(mismatch['client_sha256'], mismatch['server_sha256'])

    def test_diagnostic_source_not_matching_fresh_output_stays_plain_failure(self):
        (self.root / 'collections-case/result.json').write_text('{}')
        self.transform = lambda marker: marker['values'].__setitem__(4, 'changed')
        result = self.run_collections()
        self.assertEqual(result['failure_kind'], 'output_mismatch')
        self.assertIsNone(result['mismatch'])
        self.assertFalse(result['witness_verified'])

    def test_server_trailing_bytes_fail_without_rewriting_oracle(self):
        original = self.output.read_bytes() + b'\n'
        self.output.write_bytes(original)
        result = self.run_collections()
        self.assertEqual(result['failure_kind'], 'output_mismatch')
        self.assertEqual(self.output.read_bytes(), original)

    def test_wrong_nonce_phase_witness_and_false_completion_fail(self):
        for key, value in [('nonce', '0'*32), ('phase', 'error'), ('witness', 'server'),
                           ('values', [42, 'client-probe', 3, 6])]:
            self.transform = lambda marker: marker.update({key: value})
            self.assertEqual(self.run_collections()['failure_kind'], 'invalid_result')
            self.reset()

    def test_timeout_even_with_completed_output_never_succeeds(self):
        for phases in [(), ('entered',), ('entered', 'completed')]:
            self.run_markers = phases
            self.run_error = 'timeout'
            result = self.run_collections()
            self.assertEqual(result['failure_kind'], 'timeout')
            self.assertFalse(result['witness_verified'])
            self.assertIsNone(result['output_sha256'])
            self.reset()

    def test_survivor_fails_after_fresh_output(self):
        with mock.patch.object(suite, 'client_process_snapshot', return_value={(999999, '1')}):
            result = self.run_collections()
        self.assertEqual(result['failure_kind'], 'process_failed')
        self.assertFalse(result['quiet'])

    def test_roundtrip_directive_and_server_substitution_fail_before_run(self):
        def tamper(mode):
            if mode == 'dump':
                path = self.work / 'roundtrip' / suite.CLIENT_MODULE
                path.write_bytes(path.read_bytes().replace('&НаКлиенте'.encode(), '&НаСервере'.encode(), 1))
        self.hook = tamper
        self.assertEqual(self.run_collections()['failure_kind'], 'module_mismatch')
        self.assertEqual(self.events, ['build', 'dump'])

    def test_source_tamper_rejected_before_compile_even_with_matching_input_hash(self):
        path = self.inputs / 'scenarios/collections.bsl'
        path.write_bytes(path.read_bytes() + b'\n')
        self.hashes['integrational_tests/tests/collections.bsl'] = suite.digest(path.read_bytes())
        self.assertEqual(self.run_collections()['failure_kind'], 'invalid_input')
        self.assertEqual(self.events, [])

    def test_final_census_clears_collections_success_and_output_metadata(self):
        record = suite.empty_report(NONCE, client_probe=True, client_collections=True)
        record['client_collections'] = self.run_collections()
        suite.fail_client_process_checkpoint(record, False)
        self.assertEqual(record['client_collections']['status'], 'failed')
        self.assertIsNone(record['client_collections']['output_sha256'])
        self.assertFalse(record['client_collections']['witness_verified'])

    def test_conflicting_parity_options_rejected_before_execution(self):
        self.assertEqual(self.run_collections(dates_output=self.output)['failure_kind'], 'invalid_input')
        self.assertEqual(self.events, [])

    def test_fresh_server_must_be_present_bounded_and_exact(self):
        self.output.unlink()
        result = self.run_collections()
        self.assertEqual(result['failure_kind'], 'artifact_missing')
        self.assertIsNone(result['output_sha256'])
        self.assertFalse(result['witness_verified'])

    def test_client_roundtrip_body_tamper_fails_before_enterprise(self):
        def tamper(mode):
            if mode == 'dump':
                path = self.work / 'roundtrip' / suite.CLIENT_MODULE
                path.write_bytes(path.read_bytes().replace(b'Null', b'Undefined', 1))
        self.hook = tamper
        self.assertEqual(self.run_collections()['failure_kind'], 'module_mismatch')
        self.assertEqual(self.events, ['build', 'dump'])

    def test_collections_stall_option_rejected_before_execution(self):
        self.assertEqual(self.run_collections(stall=True)['failure_kind'], 'invalid_input')
        self.assertEqual(self.events, [])


class CollectionsSuiteOrderTests(unittest.TestCase):
    def test_six_cases_then_probe_collections_watchdog_and_private_oracle(self):
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
                return dict(suite.empty_values_report(), status='ok', failure_kind='none')
            if 'collections_output' in kwargs:
                self.assertEqual(kwargs['collections_output'], harness.work / 'collections.out')
                self.assertEqual(kwargs['collections_output'].read_bytes(),
                                 suite.serialize_messages(probe.stage_fixture.MESSAGES))
                return dict(suite.empty_collections_report(), status='ok', failure_kind='none')
            return dict(suite.empty_client_report(), status='ok', failure_kind='none')
        def watchdog(*args):
            calls.append('watchdog')
            return dict(suite.empty_watchdog_report(), status='ok', failure_kind='none')
        with mock.patch.object(suite, 'run_client_probe', side_effect=client), \
                mock.patch.object(suite, 'run_client_watchdog', side_effect=watchdog):
            result = suite.run_suite(harness.launcher, harness.platform, harness.epf,
                harness.work, harness.inputs, NONCE, client_probe=True, client_dates=True, client_values=True, client_collections=True,
                watchdog_check=True)
        self.assertEqual(result['status'], 'ok', result)
        self.assertEqual(calls, ['client-probe', 'client-dates', 'client-values', 'client-collections', 'watchdog'])
        self.assertEqual(len(result['input_sha256']), 24)
        self.assertEqual(sorted(p.name for p in harness.work.glob('*.out')),
                         sorted(name + '.out' for name in suite.SCENARIOS))



class CollectionsFinalEmitterTests(unittest.TestCase):
    emitter = probe.ClientFinalReportEmitterTests.emitter
    # Keep only the new concrete contract in this class; use the shared renderer
    # helper without duplicating the prior fixed-probe emitter tests.
    def test_compact_collections_teardown_keeps_all_prior_proofs(self):
        for watchdog in (False, True):
            for cleanup_failed in (False, True):
                with self.subTest(watchdog=watchdog, cleanup_failed=cleanup_failed):
                    report = self.emitter(watchdog=watchdog, dates=True, values=True,
                                          collections=True, cleanup_failed=cleanup_failed)
                    stage = report['stage3']
                    self.assertEqual(stage['schema'], 1)
                    for name in ('client_probe', 'client_dates', 'client_values'):
                        self.assertEqual(stage[name]['status'], 'ok')
                    record = stage['client_collections']
                    if watchdog:
                        self.assertEqual(record['status'], 'ok')
                    else:
                        self.assertEqual(record['status'], 'failed')
                        for key in ('output_sha256', 'output_size', 'message_count'):
                            self.assertIsNone(record[key])


if __name__ == '__main__':
    unittest.main()
