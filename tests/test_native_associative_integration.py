"""Source-bound v2 host/CLI wiring; raw mismatch evidence is never normalized."""
import copy
import hashlib
import json
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest import mock

import test_native_1c_full_host as fixtures
from test_native_1c_full_host import full, smoke


class AssociativeHostTests(unittest.TestCase):
    def setUp(self):
        case = fixtures.SemanticComparisonTests('test_semantic_acceptance_keeps_raw_mismatch_and_explicit_target')
        case.setUp()
        self.addCleanup(case.doCleanups)
        self.case = case
        self.contract = full.associative_contract()
        case.context['comparison_mode'] = full.ASSOCIATIVE_MODE

    def compare(self, *, verdict=None, equal=False, other_diff=False, context=None):
        case = self.case
        def runner(args, cwd, **limits):
            name = Path(args[-3]).stem
            different = (name == 'collections' and not equal) or (name == 'dates' and other_diff)
            return 0, case.payload + b'x' if different else case.payload, b''
        if verdict is None:
            verdict = dict(profile=full.ASSOCIATIVE_MODE, status='equivalent', records=1023,
                           byte_equal_records=1023 if equal else 1022,
                           accepted_labels=[] if equal else [self.contract.ELIGIBLE_LABELS[0]], reason='none')
        verifier = mock.Mock(return_value=verdict)
        self.contract.compare_collections = verifier
        with mock.patch.object(full, 'associative_contract', return_value=self.contract), \
                mock.patch.object(full, 'validate_tree_load_observations'), \
                mock.patch.object(full, 'validate_tree_move_observations'), \
                mock.patch.object(full, 'validate_tree_total_observations'):
            result = full.compare_outputs(case.root, case.capture, case.stage3, case.inputs,
                runner=runner, native_target=full.LINUX_TARGET, comparison_mode=full.ASSOCIATIVE_MODE,
                runtime_evidence=case.context if context is None else context)
        return result, verifier

    def test_v2_acceptance_retains_raw_mismatch_bytes_and_profile(self):
        result, verifier = self.compare()
        row = result['cases'][0]
        self.assertEqual(result['comparison_mode'], 'associative-order-v2')
        self.assertEqual((result['status'], result['acceptance_status']), ('failed', 'accepted'))
        self.assertEqual((row['status'], row['acceptance_status']), ('mismatched', 'accepted'))
        self.assertEqual(row['mismatch'], full.mismatch_metadata(self.case.payload, self.case.payload + b'x'))
        self.assertNotEqual(row['native_sha256'], row['interpreter_sha256'])
        verifier.assert_called_once_with(self.case.payload, self.case.payload + b'x', full.COLLECTIONS_SOURCE_SHA256)
        self.assertTrue(all(row['semantic'] is None for row in result['cases'][1:]))

    def test_other_records_remain_byte_exact_and_invalid_equal_payload_rejects(self):
        result, _ = self.compare(other_diff=True)
        self.assertEqual(result['acceptance_status'], 'rejected')
        self.assertIsNone(result['cases'][1]['semantic'])
        rejected = dict(profile=full.ASSOCIATIVE_MODE, status='rejected', records=0,
                        byte_equal_records=0, accepted_labels=[], reason='unsupported_payload')
        result, _ = self.compare(verdict=rejected, equal=True)
        self.assertEqual((result['status'], result['acceptance_status']), ('ok', 'rejected'))

    def test_requested_profile_cannot_reuse_v1_context(self):
        context = copy.deepcopy(self.case.context)
        context['comparison_mode'] = full.MAP_MODE
        with self.assertRaisesRegex(full.FullError, 'semantic_context_invalid'):
            self.compare(context=context)

    def test_source_or_image_context_tamper_never_accepts(self):
        for field, value in (('image', 'other'), ('runtime_version', 'unknown'), ('platform', 'linux/arm64')):
            context = copy.deepcopy(self.case.context); context[field] = value
            with self.subTest(field=field), self.assertRaisesRegex(full.FullError, 'semantic_context_invalid'):
                self.compare(context=context)
        path = self.case.root / 'integrational_tests/tests/collections.bsl'
        path.write_bytes(path.read_bytes() + b'// tampered')
        result, verifier = self.compare()
        self.assertEqual(result['cases'][0]['failure_kind'], 'source_changed')
        verifier.assert_not_called()

    def test_cross_profile_and_unknown_label_claims_reject(self):
        valid = dict(profile=full.ASSOCIATIVE_MODE, status='equivalent', records=1023,
                     byte_equal_records=1022, accepted_labels=[self.contract.ELIGIBLE_LABELS[0]], reason='none')
        for change in (dict(profile=full.MAP_MODE), dict(accepted_labels=['unknown']), dict(records=1022)):
            with self.subTest(change=change), self.assertRaisesRegex(full.FullError, 'semantic_result_invalid'):
                self.compare(verdict={**valid, **change})

    def test_v1_and_byte_exact_options_stay_available(self):
        full.validate_comparison_options(full.LINUX_TARGET, full.MAP_MODE)
        full.validate_comparison_options(full.LINUX_TARGET, full.ASSOCIATIVE_MODE)
        full.validate_comparison_options(full.WINDOWS_TARGET, full.BYTE_EXACT)
        for mode in (full.MAP_MODE, full.ASSOCIATIVE_MODE):
            with self.assertRaises(full.FullError):
                full.validate_comparison_options(full.WINDOWS_TARGET, mode)
        self.assertEqual(full.semantic_contract(full.MAP_MODE).PROFILE, 'typed-map-order-v1')

    def test_loader_uses_checked_grammar_not_cached_import(self):
        poison = SimpleNamespace(SOURCE_SHA256='cached poison')
        with mock.patch.dict(sys.modules, {'scripts.native_1c_map_contract': poison}):
            relation = full.associative_contract()
        self.assertEqual(relation.SOURCE_SHA256, full.COLLECTIONS_SOURCE_SHA256)
        self.assertIsNot(relation.grammar, poison)
        self.assertEqual(len(relation.ELIGIBLE_LABELS), 18)

    def test_raw_metadata_or_profile_claim_tamper_rejects(self):
        original, _ = self.compare()
        for change in ('mode', 'raw', 'mismatch'):
            result = copy.deepcopy(original)
            if change == 'mode': result['comparison_mode'] = full.MAP_MODE
            if change == 'raw': result['cases'][0]['status'] = 'matched'
            if change == 'mismatch': result['cases'][0]['mismatch'] = None
            with self.subTest(change=change), self.assertRaises(full.FullError):
                full.validate_comparison(result, self.case.stage3, full.LINUX_TARGET, full.ASSOCIATIVE_MODE)


class AssociativeHistoricalSourceTests(unittest.TestCase):
    def test_exact_inverse_preserves_old_pins_and_unknown_bytes(self):
        from test_native_async_fixture import (
            without_associative_order_harness,
            without_direct_host_source_history,
            without_direct_smoke_source_history,
        )
        root = Path(__file__).resolve().parents[1]
        contracts = json.loads((root / 'tests/native_associative_source_inverse.json').read_text(encoding='utf-8'))
        historical = {
            'scripts/native_1c_full_host.py': without_direct_host_source_history,
            'scripts/native_1c_smoke.py': without_direct_smoke_source_history,
        }
        self.assertEqual(set(contracts), set(historical))
        for path, recover_candidate in historical.items():
            with self.subTest(path=path):
                contract = contracts[path]
                current = (root / path).read_text(encoding='utf-8')
                candidate = recover_candidate(current)
                self.assertEqual(hashlib.sha256(candidate.encode('utf-8')).hexdigest(), contract['candidate_sha256'])
                restored = without_associative_order_harness(candidate, path)
                self.assertEqual(hashlib.sha256(restored.encode('utf-8')).hexdigest(), contract['base_sha256'])
                self.assertEqual(without_associative_order_harness(current, path), restored)
                self.assertEqual(without_associative_order_harness(restored, path), restored)
                for source in (current, candidate):
                    drift = source + '# unknown'
                    self.assertEqual(without_associative_order_harness(drift, path), drift)


class ActualComparatorContractTests(unittest.TestCase):
    def test_multiple_permitted_payloads_emit_canonical_evidence_order(self):
        from tests.test_native_associative_order import BoundProfileTests
        from tests.test_native_1c_map_contract import mapping,sequence,string,scalar,STRUCTURE,ARRAY,encode
        case=BoundProfileTests();left=case.records();right=list(left)
        pairs=((string('First'),scalar('N',b'1')),(string('Second'),scalar('U')))
        for ordinal in (295,298):
            right[ordinal-1]=(left[ordinal-1][0],mapping(pairs[::-1],STRUCTURE))
        for ordinal in (303,306):
            left[ordinal-1]=(left[ordinal-1][0],sequence(ARRAY,(mapping(pairs),)))
            right[ordinal-1]=(right[ordinal-1][0],sequence(ARRAY,(mapping(pairs[::-1]),)))
        native,actual=encode(left),encode(right)
        contract=full.associative_contract()
        result=contract.compare_collections(native,actual,contract.SOURCE_SHA256)
        self.assertEqual(result['status'],'equivalent')
        self.assertEqual(result['byte_equal_records'],1019)
        self.assertEqual(result['accepted_labels'],sorted((left[i-1][0] for i in (295,298,303,306))))
        full.validate_semantic_result(result,raw_matched=False,comparison_mode=full.ASSOCIATIVE_MODE)
        self.assertNotEqual(native,actual)
        # Validator remains strict; only the producer's metadata ordering changes.
        bad={**result,'accepted_labels':result['accepted_labels'][::-1]}
        with self.assertRaisesRegex(full.FullError,'semantic_result_invalid'):
            full.validate_semantic_result(bad,raw_matched=False,comparison_mode=full.ASSOCIATIVE_MODE)
        changed=list(right);changed[9]=(changed[9][0],changed[9][1]+b' ')
        refused=contract.compare_collections(native,encode(changed),contract.SOURCE_SHA256)
        self.assertEqual(refused['status'],'rejected')
        full.validate_semantic_result(refused,raw_matched=False,comparison_mode=full.ASSOCIATIVE_MODE)
