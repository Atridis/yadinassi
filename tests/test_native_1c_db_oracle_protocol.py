"""Hostile synthetic transport tests. A fabricated success is never native proof."""
import copy
import json
import sys
from pathlib import Path
import unittest
from unittest import mock

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts/native_1c_db_oracle'))
sys.path.insert(0,str(Path(__file__).resolve().parent))
import protocol
from snapshots import OracleError
from test_native_1c_db_oracle_stage import NONCE,fixture_report,provenance

SEED_OPERATIONS = ('create','dump_empty','import','apply','redump','bootstrap')
SEED_FAILURE_CATEGORIES = frozenset({
    'invalid_input','permission_mismatch','process_failed','timeout','invalid_dump_result',
    'stale_evidence','artifact_missing','artifact_limit','invalid_marker','logical_mismatch',
    'snapshot_not_quiescent','snapshot_changed','metadata_rejected','version_mismatch',
    'unexpected_failure',
})
SEED_FAILURES = frozenset(f'seed_{operation}_{category}'
    for operation in SEED_OPERATIONS for category in SEED_FAILURE_CATEGORIES)
PRIVATE = 'PRIVATE-SYNTHETIC-NATIVE-DATA'


class ProtocolTests(unittest.TestCase):
    def setUp(self):
        self.good,_=fixture_report(); self.identity=provenance()
    def check(self,value,final=False):
        return protocol.validate_report(protocol.encode(value),nonce=NONCE,provenance=self.identity,final=final)
    def rejected(self,edit):
        value=copy.deepcopy(self.good); edit(value)
        with self.assertRaises((OracleError,ValueError,TypeError)): self.check(value)

    def test_success_requires_host_cleanup_and_cannot_accept_in_container(self):
        self.check(self.good)
        self.rejected(lambda r:r.update(accepted=True))
        value=copy.deepcopy(self.good)
        value['cleanup'].update(container_removed=True,private_staging_removed=True); value['accepted']=True
        self.check(value,True)
        value['cleanup']['private_staging_removed']=False
        with self.assertRaises(OracleError): self.check(value,True)

    def test_rejects_unknown_keys_raw_content_and_wrong_scalar_types(self):
        edits=[lambda r:r.update(raw='SECRET RAW DATABASE'), lambda r:r.update(schema=True),
            lambda r:r.update(nonce='b'*32),lambda r:r.update(status='native error /private/path'),
            lambda r:r['stages'].reverse(),lambda r:r['stages'][0]['checks'].update(extra=True),
            lambda r:r['stages'][0]['checks'].update(inputs_verified=1),
            lambda r:r['snapshots'][0]['physical'].update(bytes=True),
            lambda r:r['snapshots'][0]['physical'].update(sha256='not-a-digest'),
            lambda r:r['snapshots'][0]['physical'].update(header='1CDBMSV8'),
            lambda r:r['snapshots'][0]['physical'].update(page_analysis='4096'),
            lambda r:r['snapshots'][0]['physical'].update(raw_prefix='base64-data'),
            lambda r:r['snapshots'][0]['logical'].update(count=False),
            lambda r:r['snapshots'][0]['logical'].update(amount=0),
            lambda r:r['snapshots'][2]['logical'].update(amount='1.250'),
            lambda r:r['snapshots'][2]['logical'].update(deletion_mark=True),
            lambda r:r['snapshots'][2]['logical'].update(same_reference=False),
            lambda r:r['snapshots'][6]['logical'].update(applied_version=2),
            lambda r:r['snapshots'][-1]['logical'].update(payload='alpha'),
            lambda r:r['snapshots'][9]['logical'].update(count=1),
            lambda r:r['snapshots'][2]['logical'].update(user='NativeOracleSetup'),
            lambda r:r['snapshots'][2]['logical'].update(nonprivileged=False),
            lambda r:r['comparisons'][0]['physical']['control'].update(changed_bytes=2),
            lambda r:r['comparisons'][0]['physical']['byte_windows'].update(overlap_sample=[9999]),
            lambda r:r['comparisons'][0].update(source='updated'),
            lambda r:r['artifacts'][2].update(source='deleted'),
            lambda r:r['provenance'].update(actual_version='guessed-from-image'),
            lambda r:r['provenance'].update(commit='b'*40),
        ]
        for edit in edits:
            with self.subTest(edit=edits.index(edit)): self.rejected(edit)

    def test_duplicate_keys_truncated_nonfinite_and_oversized_rejected(self):
        for raw in (b'{"schema":1,"schema":1}',b'{',b'NaN',b'Infinity',b'{}'*20000,
                    b'{"a":NaN}',b'\xff'):
            with self.subTest(raw=raw[:30]),self.assertRaises(OracleError):
                protocol.validate_report(raw,nonce=NONCE,provenance=self.identity)

    def test_failure_never_exposes_ready_artifact(self):
        failed,_=fixture_report('delete'); failed['artifacts']=copy.deepcopy(self.good['artifacts'])
        with self.assertRaises(OracleError): self.check(failed)

    def test_seed_failure_vocabulary_is_exact_fixed_native_cross_product(self):
        self.assertEqual(protocol.SEED_OPERATIONS,SEED_OPERATIONS)
        self.assertEqual(protocol.SEED_FAILURE_CATEGORIES,SEED_FAILURE_CATEGORIES)
        self.assertEqual(protocol.SEED_FAILURES,SEED_FAILURES)
        self.assertEqual(len(SEED_FAILURES),90)
        self.assertEqual({value for value in protocol.FAILURES if value.startswith('seed_')},SEED_FAILURES)
        self.assertTrue(SEED_FAILURES <= protocol.FAILURES)

    def test_every_seed_failure_roundtrips_only_as_unaccepted_seed_diagnosis(self):
        source,_=fixture_report('seed_v1')
        for kind in sorted(SEED_FAILURES):
            for final in (False,True):
                with self.subTest(kind=kind,final=final):
                    value=copy.deepcopy(source); value['failure_kind']=kind
                    if final:
                        value['cleanup'].update(container_removed=True,private_staging_removed=True)
                    observed=self.check(value,final)
                    self.assertEqual(observed,value)
                    self.assertEqual(observed['failed_stage'],'seed_v1')
                    self.assertEqual(observed['stages'][1]['status'],'failed')
                    self.assertFalse(observed['accepted'])
                    for key in ('artifacts','snapshots','comparisons'):
                        self.assertEqual(observed[key],[])
                    self.assertNotIn(PRIVATE,protocol.encode(observed).decode())

    def test_seed_failure_rejects_unknown_and_nonstring_values_without_echo(self):
        source,_=fixture_report('seed_v1')
        unsupported = (protocol.FAILURES - SEED_FAILURES - SEED_FAILURE_CATEGORIES)
        values = [None,True,False,0,1,1.5,[],{},[PRIVATE],{'raw':PRIVATE},
            '',PRIVATE,'seed_unknown_process_failed','seed_create_process_failed_'+PRIVATE,
            'seed_create_process_failed\n'+PRIVATE,'seed_create_'+PRIVATE,
            'seed_create_seed_create_process_failed',
            *(f'seed_{operation}_{category}' for operation in SEED_OPERATIONS
              for category in sorted(unsupported))]
        for kind in values:
            with self.subTest(kind=kind):
                value=copy.deepcopy(source); value['failure_kind']=kind
                with self.assertRaises(OracleError) as caught:
                    self.check(value)
                self.assertEqual(caught.exception.kind,'transport_invalid')
                self.assertNotIn(PRIVATE,str(caught.exception))

    def test_failure_kind_requires_exact_string_even_for_decoder_objects(self):
        class StringSubclass(str):
            pass
        source,_=fixture_report('seed_v1')
        for kind in ('process_failed','seed_create_process_failed'):
            with self.subTest(kind=kind):
                source['failure_kind']=StringSubclass(kind)
                with mock.patch.object(protocol,'decode',return_value=source),self.assertRaises(OracleError):
                    self.check(source)

    def test_seed_composites_cannot_appear_in_success_or_other_failed_stages(self):
        for stage in protocol.STAGES:
            if stage=='seed_v1':
                continue
            if stage=='cleanup':
                source=copy.deepcopy(self.good)
                source.update(status='failed',failed_stage='cleanup',failure_kind='cleanup_unverified',artifacts=[])
                source['stages'][-1]['status']='failed'
                source['stages'][-1]['checks']['raw_files_removed']=False
                source['cleanup']['raw_files_removed']=False
            else:
                source,_=fixture_report(stage)
            self.check(source)
            for kind in sorted(SEED_FAILURES):
                with self.subTest(stage=stage,kind=kind):
                    value=copy.deepcopy(source); value['failure_kind']=kind
                    with self.assertRaises(OracleError): self.check(value)
        for kind in sorted(SEED_FAILURES):
            with self.subTest(stage='success',kind=kind):
                value=copy.deepcopy(self.good); value['failure_kind']=kind
                with self.assertRaises(OracleError): self.check(value)

    def test_seed_failure_requires_failed_primary_seed_not_just_failed_cleanup(self):
        source=copy.deepcopy(self.good)
        source.update(status='failed',failed_stage='seed_v1',failure_kind='seed_bootstrap_invalid_marker',artifacts=[])
        source['stages'][-1]['status']='failed'
        source['stages'][-1]['checks']['raw_files_removed']=False
        source['cleanup']['raw_files_removed']=False
        for state in ('ok','not_started'):
            with self.subTest(seed_state=state):
                value=copy.deepcopy(source); seed=value['stages'][1]
                seed['status']=state
                seed['checks']={key:state=='ok' for key in protocol.CHECKS['seed_v1']}
                with self.assertRaises(OracleError): self.check(value)

    def test_primary_seed_failure_and_independent_cleanup_failure_are_valid(self):
        source,_=fixture_report('seed_v1')
        for kind in sorted(SEED_FAILURES):
            with self.subTest(kind=kind):
                value=copy.deepcopy(source); value['failure_kind']=kind
                value['stages'][-1]['status']='failed'
                value['stages'][-1]['checks']['raw_files_removed']=False
                value['cleanup'].update(raw_files_removed=False,container_removed=False,
                                        private_staging_removed=False)
                observed=self.check(value,True)
                self.assertEqual(observed['failure_kind'],kind)
                self.assertEqual(observed['failed_stage'],'seed_v1')
                self.assertFalse(observed['accepted'])
                self.assertEqual(observed['artifacts'],[])

    def test_no_observations_for_unexecuted_stages(self):
        failed,_=fixture_report('preflight')
        failed['snapshots']=copy.deepcopy(self.good['snapshots'])
        failed['comparisons']=copy.deepcopy(self.good['comparisons'])
        with self.assertRaises(OracleError): self.check(failed)

    def test_ok_stage_must_include_required_snapshot_and_comparison(self):
        failed,_=fixture_report('update'); failed['snapshots']=[]; failed['comparisons']=[]
        with self.assertRaises(OracleError): self.check(failed)

    def test_snapshot_ids_are_exact_prefix_not_arbitrary_subset(self):
        failed,_=fixture_report('update')
        failed['snapshots']=failed['snapshots'][1:]
        with self.assertRaises(OracleError): self.check(failed)

    def test_same_state_control_can_have_physical_churn_without_causation_claim(self):
        value=copy.deepcopy(self.good); item=value['comparisons'][0]['physical']
        for side in ('control','treatment'):
            item[side].update(changed_bytes=1,unchanged_bytes=3,changed_windows=1)
        item['byte_windows'].update(overlap_count=1,overlap_sample=[0])
        self.check(value)
        self.assertEqual(item['interpretation'],'physical_byte_differences_not_causation')

    def test_raw_binaries_are_not_schema_artifacts(self):
        self.rejected(lambda r:r['artifacts'].append({'id':'1Cv8.1CD'}))


if __name__=='__main__': unittest.main()
