"""Immutable Linux observations, initial mismatch attribution, and exact replay."""
import hashlib
import json
from pathlib import Path
import sys
import unittest

from yadinassi import Interpreter
from yadinassi.native_targets import LINUX_8_3_27_1508

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / 'tests/fixtures/property_transfer'
sys.path.insert(0, str(ROOT / 'scripts'))
import native_1c_property_transfer_contract as wire
import native_1c_tree_profiles as profiles

SOURCE_SHA = '25abcace2821e4d03da731e4cf96a97a33348f21a58ee291399232c51ad5e7c8'
MAPPING_SHA = '63c0aca76891fe56b03d4e53636443c8c3c64c81e0def4d6289f20c07dd75470'
CAPTURE_SHA = '054ace35dbeff0fd2a5d627e731166acb9f8fb37939070b566518bfb37e42174'
PROVENANCE_SHA = 'af5465c3b6ded725a1e4ca8a7db6ce99c7246e6cb1b4b14068fd3ee79d5b5329'
INITIAL_RUNTIME_SHA = '2ce835fad43e70241e95f734b35d5a7ff45ebbb53865514d1b13f758103d58f3'
INITIAL_OUTPUT_SHA = '078b7bca6bfaf4a5c9d103380e278799edd90b2d9530fd97f3cda33de05c50fe'
TREE = '0439b7d8de7d55b4d8acef44706b7ef5efaff3ce'
CHECKOUT = 'a10240123e1c65284ffd4c0b0b9b64e63ac0a7d6'
HEAD = '201b6d9c824e2980932a389e96a3d3bc8dc8d4f9'
ACTION_ERRORS = (17, 18, 21, 22, 24, 27, 28, 31, 32, 34, 42, 43)
INITIAL_DIFFERENCES = (17, 18, 19, 21, 24, 27, 28, 29, 31, 34, 42, 43, 45, 46)


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def records():
    return wire.require_available((FIXTURE / 'original48-linux.out').read_bytes())


class PropertyTransferNativeCaptureTests(unittest.TestCase):
    def test_immutable_source_capture_and_input_checkpoint(self):
        source = (FIXTURE / 'original48.bsl').read_bytes()
        mapping_raw = (FIXTURE / 'original48-mapping.json').read_bytes()
        raw = (FIXTURE / 'original48-linux.out').read_bytes()
        self.assertEqual(digest(source), SOURCE_SHA)
        self.assertEqual(source, (ROOT / profiles.PROPERTY_TRANSFER.source).read_bytes())
        self.assertEqual(profiles.PROPERTY_TRANSFER.source_sha256, SOURCE_SHA)
        self.assertEqual(digest(mapping_raw), MAPPING_SHA)
        mapping = json.loads(mapping_raw)
        self.assertEqual(mapping['source_sha256'], SOURCE_SHA)
        self.assertEqual(mapping['evidence_status'], 'not_acquired')
        self.assertFalse(mapping['native_measurement_accepted'])
        self.assertFalse(mapping['runtime_parity_accepted'])
        self.assertEqual([row['case'] for row in mapping['cases']], list(range(1, 49)))
        self.assertEqual(digest(raw), CAPTURE_SHA)
        self.assertEqual((len(raw), len(raw.splitlines())), (6903, 50))
        self.assertEqual((wire.MAX_ENCODED_BYTES, wire.MAX_OUTPUT_BYTES), (6903, 8192))
        self.assertEqual(len(wire.require_available(raw)), 48)
        self.assertEqual(digest((ROOT / 'scripts/native_1c_property_transfer_contract.py').read_bytes()),
                         '7c402802a5e45ca8c06ec9a24bb104d1c1994de3876009602cfc966bdc9de8d5')

    def test_initial_mismatch_provenance_and_exact_acquisition_receipt(self):
        raw = (FIXTURE / 'original48-linux-provenance.json').read_bytes()
        self.assertEqual(digest(raw), PROVENANCE_SHA)
        provenance = json.loads(raw)
        receipt = json.loads((FIXTURE / 'original48-linux-receipt.json').read_text(encoding='utf-8'))
        self.assertEqual(receipt['schema'], 'property-transfer-native-acquisition-v1')
        self.assertEqual(receipt['native_target'], LINUX_8_3_27_1508)
        for value in (provenance, receipt):
            self.assertEqual(value['profile'], 'property-transfer-v1')
            self.assertTrue(value['native_measurement_accepted'])
            self.assertFalse(value['runtime_parity_accepted'])
        self.assertEqual(provenance['repository'], dict(commit=CHECKOUT, tree=TREE,
                         github_run_id='42814632887', github_run_attempt='1'))
        self.assertEqual(receipt['run'], dict(id=42814632887, attempt=1, pull_request=261,
                         url='https://github.com/Atridis/yadinassi/actions/runs/42814632887',
                         head=HEAD, checkout=CHECKOUT, tree=TREE,
                         merge_parents=['397319766c6251f8247c454ebc3f2b20e88ece3c', HEAD]))
        self.assertEqual([(entry['id'], entry['name'], entry['sha256']) for entry in receipt['artifacts']], [
            (13764188665, 'native-1c-property-transfer-outputs',
             '6e9f3afb6f9278677e2d5eef8b28aff79a2e86c2eeb2a5e8401be61f236c3054'),
            (13763189052, 'native-1c-property-transfer-summary',
             'dabe81b58e8287a5bacead5109bf4d0c461a03b8d52c119e6d9812625a1d2429')])
        self.assertEqual({key: entry['path'] for key, entry in receipt['files'].items()}, {
            'source': 'tests/fixtures/property_transfer/original48.bsl',
            'input_mapping': 'tests/fixtures/property_transfer/original48-mapping.json',
            'native_output': 'tests/fixtures/property_transfer/original48-linux.out',
            'native_provenance': 'tests/fixtures/property_transfer/original48-linux-provenance.json'})
        for entry in receipt['files'].values():
            content = (ROOT / entry['path']).read_bytes()
            self.assertEqual((digest(content), len(content)), (entry['sha256'], entry['bytes']))
        self.assertEqual(receipt['initial_interpreter'], provenance['interpreter'])
        self.assertEqual(receipt['initial_comparison'], provenance['comparison'])
        comparison = provenance['comparison']
        self.assertEqual((comparison['status'], comparison['acceptance_status']), ('mismatched', 'rejected'))
        self.assertTrue(comparison['native_property_transfer_available'])
        self.assertEqual((comparison['native_sha256'], comparison['interpreter_sha256']),
                         (CAPTURE_SHA, INITIAL_OUTPUT_SHA))
        self.assertEqual((provenance['interpreter']['source_file_count'],
                          provenance['interpreter']['source_sha256']), (165, INITIAL_RUNTIME_SHA))
        replay = receipt['initial_local_replay']
        self.assertEqual((replay['commit'], replay['tree'], replay['interpreter_sha256'], replay['bytes']),
                         ('a296e12349266e9f2fefeeb9acd48922e18e9836', TREE, INITIAL_OUTPUT_SHA, 6903))
        self.assertTrue(replay['matches_ci_interpreter_digest'])
        self.assertEqual(tuple(replay['differing_cases']), INITIAL_DIFFERENCES)
        self.assertEqual(receipt['observation_counts'], dict(cases=48, calibrations=2,
                         successes=36, action_errors=12, observer_errors=0, bytes=6903))
        self.assertEqual(receipt['verification'], dict(artifact_archive_digests_checked=True,
                         api_merge_commit_binding_checked=True, source_and_generated_module_bindings_checked=True,
                         staged_source_count=22, host_source_count=9, initial_runtime_source_count=165,
                         client_server_equal=True, container_cleanup_verified=True))
        stage = provenance['native_report']['stage3']
        self.assertEqual(stage['input_sha256'], provenance['trusted_input_sha256'])
        self.assertEqual(len(stage['input_sha256']), 22)
        self.assertEqual(len(provenance['host_source_sha256']), 9)
        self.assertEqual(stage['nonce'], provenance['nonce'])
        self.assertEqual(stage['cases'][0]['module_sha256'],
                         'c803d6950319f6d64cf1ac5dabfc5971c3dd2d634891b676ec7e022ef127dbe2')
        client = stage['client_tree']
        self.assertEqual(client['module_sha256'],
                         'ffa6977f7c8a6959fdd7e37a181a5b26d3167e4939f2264e253b057918909681')
        self.assertEqual(client['roundtrip_sha256'], client['module_sha256'])
        for observed in (stage['cases'][0], client):
            self.assertEqual((observed['status'], observed['source_sha256'], observed['output_sha256'],
                              observed['output_size'], observed['message_count']),
                             ('ok', SOURCE_SHA, CAPTURE_SHA, 6903, 50))
        for key in ('completed', 'entered', 'process_exited', 'quiet', 'witness_verified'):
            self.assertTrue(client[key])
        self.assertTrue(provenance['container_cleanup_verified'])
        self.assertTrue(provenance['private_payloads_removed'])
        self.assertEqual(provenance['native_report']['runtime_version'], '8.3.27.1508')
        self.assertEqual((provenance['platform'], provenance['configured_timezone']), ('linux/amd64', 'Etc/UTC'))

    def test_native_controls_cross_row_successes_and_complete_snapshots(self):
        observed = records()
        self.assertEqual([row['case'] for row in observed], list(range(1, 49)))
        self.assertEqual(tuple(row['case'] for row in observed if row['status'] == 'action-error'), ACTION_ERRORS)
        self.assertEqual(sum(row['status'] == 'ok' for row in observed), 36)
        self.assertTrue(all(row['status'] == 'ok' for row in observed[:16]))
        for row in observed:
            self.assertIsNone(row['stage'])
            before, after, shared_after = row['snapshots']
            self.assertEqual((before['shared'], after['shared'], shared_after['shared']), ('A0', 'A0', 'A1'))
            self.assertEqual(before['source'], after['source'])
            self.assertEqual(before['source_shape'], after['source_shape'])
            self.assertEqual(before['setter_values'], after['setter_values'])
        for case in range(1, 17):
            before, after, _ = observed[case - 1]['snapshots']
            self.assertEqual(before['target'][:3], ('N1', 'S1', 'N3'))
            self.assertEqual(after['target'][:3], ('NA', 'S2', 'N3'))

    def test_native_selection_errors_preserve_observed_partial_writes(self):
        observed = records()
        for case in (17, 18, 27, 28, 42, 43):
            self.assertEqual(observed[case - 1]['status'], 'action-error')
            self.assertEqual(observed[case - 1]['snapshots'][1]['target'][:3], ('N1', 'S2', 'N3'))
        for case in (21, 31):
            self.assertEqual(observed[case - 1]['status'], 'action-error')
            self.assertEqual(observed[case - 1]['snapshots'][1]['target'][:3], ('NA', 'S2', 'N3'))
        for case in (19, 29):
            self.assertEqual(observed[case - 1]['status'], 'ok')
            before, after, _ = observed[case - 1]['snapshots']
            self.assertEqual(before, after)
        for case in (22, 24, 32, 34):
            self.assertEqual(observed[case - 1]['status'], 'action-error')
            before, after, _ = observed[case - 1]['snapshots']
            self.assertEqual(before, after)
        for case in (23, 33):
            self.assertEqual(observed[case - 1]['status'], 'ok')
            self.assertEqual(observed[case - 1]['snapshots'][1]['target'][:3], ('NA', 'S1', 'N3'))

    def test_native_typed_setters_indexes_readonly_and_reference_values(self):
        observed = records()
        for case, pair in ((35, ('N9', 'S5')), (36, ('N0', 'S0')), (37, ('N0', 'S5')),
                           (38, ('N9', 'S5')), (39, ('N0', 'S0')), (40, ('N0', 'S5'))):
            self.assertEqual(observed[case - 1]['status'], 'ok')
            for snapshot in observed[case - 1]['snapshots']:
                self.assertEqual((snapshot['setter_status'], snapshot['setter_values']), ('S', pair))
            self.assertEqual(observed[case - 1]['snapshots'][1]['target'][:2], pair)
        for case in (1, 5, 6, 8, 14, 15, 16, 21, 23, 47):
            before, after, _ = observed[case - 1]['snapshots']
            self.assertEqual((before['target_shape'], after['target_shape']), ('T32-1100', 'T32-0201'))
        for case in (35, 36, 37):
            self.assertEqual(observed[case - 1]['snapshots'][1]['target_shape'], 'T32-0100')
        for case in range(41, 45):
            for snapshot in observed[case - 1]['snapshots']:
                self.assertEqual(snapshot['target'][3:], ('R2', 'C0'))
                self.assertEqual(snapshot['target_shape'], 'R3101100')
        for case in (45, 46):
            self.assertEqual(observed[case - 1]['status'], 'ok')
            self.assertEqual(observed[case - 1]['snapshots'][1]['target'], ('NA', 'S2', 'N3', 'R3', 'C1'))
        for case in (47, 48):
            before, after, shared_after = observed[case - 1]['snapshots']
            self.assertEqual((before['target'][1], before['source'][1]), ('S1', 'A0'))
            self.assertEqual((after['target'][1], after['source'][1]), ('A0', 'A0'))
            self.assertEqual((shared_after['target'][1], shared_after['source'][1]), ('A1', 'A1'))

    def test_complete_linux_replay_matches_immutable_native_bytes(self):
        source = (FIXTURE / 'original48.bsl').read_bytes()
        native = (FIXTURE / 'original48-linux.out').read_bytes()
        self.assertEqual(digest(source), SOURCE_SHA)
        self.assertEqual(digest(native), CAPTURE_SHA)
        messages = []
        Interpreter(messages.append, native_target=LINUX_8_3_27_1508).execute(source.decode('utf-8'))
        actual = ('\n'.join(messages) + '\n').encode('ascii')
        self.assertEqual(len(wire.require_available(actual)), 48)
        # No projected records, substitutions, action stubs, or target inference.
        self.assertEqual(actual, native)


if __name__ == '__main__':
    unittest.main()
