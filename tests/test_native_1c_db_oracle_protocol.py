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
INVENTORY_PHASES = ('poll','post_exit')
INVENTORY_REGIONS = ('home','tmp','runtime','experiment')
INVENTORY_REASONS = ('unexpected_socket','symlink','hardlink','special','race','access','otherio','link_count')
BOOTSTRAP_INVENTORY_FAILURES = frozenset(f'seed_bootstrap_inventory_{phase}_{region}_{reason}'
    for phase in INVENTORY_PHASES for region in INVENTORY_REGIONS for reason in INVENTORY_REASONS)
ALL_SEED_FAILURES = SEED_FAILURES | BOOTSTRAP_INVENTORY_FAILURES
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
        self.assertEqual({value for value in protocol.FAILURES if value.startswith('seed_')},ALL_SEED_FAILURES)
        self.assertTrue(SEED_FAILURES <= protocol.FAILURES)

    def test_bootstrap_inventory_vocabulary_is_exact_finite_cross_product(self):
        self.assertEqual(protocol.INVENTORY_PHASES,INVENTORY_PHASES)
        self.assertEqual(protocol.INVENTORY_REGIONS,INVENTORY_REGIONS)
        self.assertEqual(protocol.INVENTORY_REASONS,INVENTORY_REASONS)
        self.assertEqual(protocol.BOOTSTRAP_INVENTORY_FAILURES,BOOTSTRAP_INVENTORY_FAILURES)
        self.assertEqual(len(BOOTSTRAP_INVENTORY_FAILURES),64)
        self.assertFalse(SEED_FAILURES & BOOTSTRAP_INVENTORY_FAILURES)
        self.assertTrue(BOOTSTRAP_INVENTORY_FAILURES <= protocol.FAILURES)
        self.assertEqual(protocol.SCHEMA,1)
        self.assertEqual(protocol.MAX_REPORT_BYTES,32768)

    def test_every_seed_failure_roundtrips_only_as_unaccepted_seed_diagnosis(self):
        source,_=fixture_report('seed_v1')
        for kind in sorted(ALL_SEED_FAILURES):
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
        unsupported = (protocol.FAILURES - ALL_SEED_FAILURES - SEED_FAILURE_CATEGORIES)
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

    def test_inventory_rejects_unapproved_axes_operations_and_raw_details(self):
        source,_=fixture_report('seed_v1')
        values = [
            'seed_bootstrap_inventory_unknown_home_symlink',
            'seed_bootstrap_inventory_poll_unknown_symlink',
            'seed_bootstrap_inventory_poll_home_unknown',
            'seed_bootstrap_inventory_poll_home',
            'seed_bootstrap_inventory_poll_home_symlink_'+PRIVATE,
            'seed_bootstrap_inventory_poll_home_symlink\n'+PRIVATE,
            'seed_bootstrap_inventory_poll_/private/'+PRIVATE+'_symlink',
            'seed_bootstrap_inventory_poll_home_'+PRIVATE,
            'seed_bootstrap_inventory_poll_home_True',
            'seed_bootstrap_inventory_post-exit_tmp_special',
            *(f'seed_{operation}_inventory_{phase}_{region}_{reason}'
              for operation in SEED_OPERATIONS if operation!='bootstrap'
              for phase in INVENTORY_PHASES for region in INVENTORY_REGIONS
              for reason in INVENTORY_REASONS),
        ]
        for kind in values:
            with self.subTest(kind=kind):
                value=copy.deepcopy(source); value['failure_kind']=kind
                with self.assertRaises(OracleError) as caught:
                    self.check(value)
                self.assertEqual(caught.exception.kind,'transport_invalid')
                self.assertNotIn(PRIVATE,str(caught.exception))
        source['failure_kind']='seed_bootstrap_inventory_poll_home_symlink'
        for key in ('path','name','native_log','inventory'):
            with self.subTest(extra_key=key):
                value=copy.deepcopy(source); value[key]=PRIVATE
                with self.assertRaises(OracleError) as caught:
                    self.check(value)
                self.assertNotIn(PRIVATE,str(caught.exception))

    def test_failure_kind_requires_exact_string_even_for_decoder_objects(self):
        class StringSubclass(str):
            pass
        source,_=fixture_report('seed_v1')
        for kind in ('process_failed','seed_create_process_failed',
                     'seed_bootstrap_inventory_poll_home_symlink'):
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
            for kind in sorted(ALL_SEED_FAILURES):
                with self.subTest(stage=stage,kind=kind):
                    value=copy.deepcopy(source); value['failure_kind']=kind
                    with self.assertRaises(OracleError): self.check(value)
        for kind in sorted(ALL_SEED_FAILURES):
            with self.subTest(stage='success',kind=kind):
                value=copy.deepcopy(self.good); value['failure_kind']=kind
                with self.assertRaises(OracleError): self.check(value)

    def test_seed_failure_requires_failed_primary_seed_not_just_failed_cleanup(self):
        source=copy.deepcopy(self.good)
        source.update(status='failed',failed_stage='seed_v1',failure_kind='seed_bootstrap_invalid_marker',artifacts=[])
        source['stages'][-1]['status']='failed'
        source['stages'][-1]['checks']['raw_files_removed']=False
        source['cleanup']['raw_files_removed']=False
        for kind in ('seed_bootstrap_invalid_marker',*sorted(BOOTSTRAP_INVENTORY_FAILURES)):
            for state in ('ok','not_started'):
                with self.subTest(kind=kind,seed_state=state):
                    value=copy.deepcopy(source); value['failure_kind']=kind
                    seed=value['stages'][1]
                    seed['status']=state
                    seed['checks']={key:state=='ok' for key in protocol.CHECKS['seed_v1']}
                    with self.assertRaises(OracleError): self.check(value)

    def test_inventory_failure_requires_exact_stage_prefix_and_no_observations(self):
        source,_=fixture_report('seed_v1')
        source['failure_kind']='seed_bootstrap_inventory_post_exit_experiment_link_count'
        edits = [
            lambda r:r['stages'][0].update(status='not_started',
                checks={key:False for key in protocol.CHECKS['preflight']}),
            lambda r:r['stages'][2].update(status='failed'),
            lambda r:r['stages'][3].update(status='ok',
                checks={key:True for key in protocol.CHECKS['create']}),
            lambda r:r.update(snapshots=copy.deepcopy(self.good['snapshots'][:1])),
            lambda r:r.update(artifacts=copy.deepcopy(self.good['artifacts'])),
            lambda r:r.update(comparisons=copy.deepcopy(self.good['comparisons'][:1])),
        ]
        for index,edit in enumerate(edits):
            with self.subTest(edit=index):
                value=copy.deepcopy(source); edit(value)
                with self.assertRaises(OracleError): self.check(value)

    def test_primary_seed_failure_and_independent_cleanup_failure_are_valid(self):
        source,_=fixture_report('seed_v1')
        for kind in sorted(ALL_SEED_FAILURES):
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




class BaselineProtocolTests(unittest.TestCase):
    OPERATIONS=('freeze','observe','audit')
    ENTRIES=('database','cfl_database','cfl_temp_database','cfl_lock','cfl_temp_lock',
             'base_1cl','temp_1cd','temp_1cl','session_history','event_log','other')
    SHAPES=('owned_regular_zero','owned_regular_nonzero','unowned_regular_zero',
            'unowned_regular_nonzero','symlink','hardlink','link_count','directory',
            'special','invalid_size')

    def report(self,operation):
        value,_=fixture_report('baseline')
        if operation=='audit': value['snapshots']=copy.deepcopy(fixture_report()[0]['snapshots'][:1])
        return value

    def check(self,value):
        return protocol.validate_report(protocol.encode(value),nonce=NONCE,provenance=provenance())

    def test_exact_baseline_vocabulary_and_every_combination_roundtrips(self):
        generic=frozenset('baseline_'+op+'_invalid_input' for op in self.OPERATIONS)
        entries=frozenset('baseline_'+op+'_entry_'+entry+'_'+shape
            for op in self.OPERATIONS for entry in self.ENTRIES for shape in self.SHAPES)
        self.assertEqual(protocol.BASELINE_OPERATIONS,self.OPERATIONS)
        self.assertEqual(protocol.ENTRY_CLASSES,self.ENTRIES)
        self.assertEqual(protocol.ENTRY_SHAPES,self.SHAPES)
        self.assertEqual(protocol.BASELINE_INPUT_FAILURES,generic)
        self.assertEqual(protocol.BASELINE_ENTRY_FAILURES,entries)
        self.assertEqual(protocol.BASELINE_FAILURES,generic|entries)
        self.assertEqual(len(protocol.BASELINE_FAILURES),333)
        self.assertEqual({kind for kind in protocol.FAILURES if kind.startswith('baseline_')},generic|entries)
        for operation in self.OPERATIONS:
            value=self.report(operation)
            for kind in generic|entries:
                if kind.startswith('baseline_'+operation+'_'):
                    with self.subTest(kind=kind):
                        value['failure_kind']=kind
                        checked=self.check(value)
                        self.assertFalse(checked['accepted'])
                        self.assertLess(len(protocol.encode(value)),protocol.MAX_REPORT_BYTES)

    def test_baseline_diagnostics_reject_unknown_axes_scalars_and_extra_keys(self):
        for kind in (True,False,None,1,[],{},PRIVATE,'baseline_unknown_invalid_input',
                     'baseline_freeze_process_failed','baseline_freeze_entry_unknown_special',
                     'baseline_freeze_entry_other_unknown','baseline_freeze_entry_other_True',
                     'baseline_freeze_entry_other_special_'+PRIVATE,
                     'baseline_freeze_entry_/private/path_special'):
            value=self.report('freeze'); value['failure_kind']=kind
            with self.subTest(kind=kind),self.assertRaises(OracleError):self.check(value)
        for key in ('path','entry_name','owner','size','native_log','operation'):
            value=self.report('freeze');value['failure_kind']='baseline_freeze_invalid_input';value[key]=PRIVATE
            with self.subTest(key=key),self.assertRaises(OracleError):self.check(value)

    def test_baseline_diagnostics_reject_success_and_every_other_stage(self):
        for operation in self.OPERATIONS:
            kinds=('baseline_'+operation+'_invalid_input',
                   'baseline_'+operation+'_entry_other_owned_regular_zero')
            for kind in kinds:
                value,_=fixture_report();value['failure_kind']=kind
                with self.assertRaises(OracleError):self.check(value)
                for failed in protocol.STAGES:
                    if failed=='baseline':continue
                    value,_=fixture_report(failed if failed!='cleanup' else None)
                    if failed=='cleanup':
                        value.update(status='failed',failed_stage='cleanup',artifacts=[])
                        value['cleanup']['raw_files_removed']=False
                        value['stages'][-1].update(status='failed',checks={'native_processes_stopped':True,'raw_files_removed':False})
                    value['failure_kind']=kind
                    with self.subTest(operation=operation,stage=failed),self.assertRaises(OracleError):self.check(value)

    def test_baseline_operation_requires_exact_snapshot_prefix(self):
        for operation in self.OPERATIONS:
            value=self.report(operation);value['failure_kind']='baseline_'+operation+'_invalid_input'
            value['snapshots']=[] if operation=='audit' else copy.deepcopy(fixture_report()[0]['snapshots'][:1])
            with self.subTest(operation=operation),self.assertRaises(OracleError):self.check(value)

    def test_baseline_label_cannot_be_only_a_cleanup_failure(self):
        value,_=fixture_report()
        value.update(status='failed',failed_stage='baseline',failure_kind='baseline_audit_invalid_input',artifacts=[])
        value['stages'][-1].update(status='failed',checks={'native_processes_stopped':False,'raw_files_removed':True})
        value['cleanup']['native_processes_stopped']=False
        with self.assertRaises(OracleError):self.check(value)



class BasenameDiagnosticProtocolTests(unittest.TestCase):
    def report(self,name='1Cv8.private-test',final=False):
        value,_=fixture_report('baseline')
        value['failure_kind']='baseline_freeze_entry_'+protocol.diagnostic_entry_class(name)+'_owned_regular_zero'
        value['rejected_basename']=name
        if final:value['cleanup'].update(container_removed=True,private_staging_removed=True)
        return value

    def check(self,value,final=False,**overrides):
        args=dict(nonce=NONCE,provenance=provenance(),final=final);args.update(overrides)
        return protocol.validate_report(protocol.encode(value),**args)

    def test_only_bounded_rejected_names_roundtrip_privately_then_after_all_cleanup(self):
        for name in ('1Cv8','1Cv8'+'A'*48,'1Cv8.1CL','1Cv8tmp.1CD','1Cv8tmp.1CL','1Cv8snc.1CD'):
            with self.subTest(name=name):
                self.assertEqual(self.check(self.report(name))['rejected_basename'],name)
                value=self.check(self.report(name,True),True)
                self.assertEqual(value['rejected_basename'],name);self.assertFalse(value['accepted'])
                self.assertLess(len(protocol.encode(value)),32768)

    def test_rejects_unbounded_nonascii_paths_controls_and_wrong_scalar_types(self):
        names=(True,False,None,1,{},[], '','1Cv','1cv8','X1Cv8','1Cv8'+'A'*49,
               '1Cv8/file','1Cv8\\file','1Cv8\n','1Cv8\r','1Cv8\t','1Cv8\x00',
               '1Cv8é','1Cv8１','1Cv8 native','/tmp/1Cv8.test','1Cv8:'+PRIVATE)
        for name in names:
            value=self.report();value['rejected_basename']=name
            with self.subTest(name=name),self.assertRaises(OracleError):self.check(value)

    def test_success_rejects_diagnostic_even_with_all_cleanup(self):
        for final in (False,True):
            value,_=fixture_report();value['rejected_basename']='1Cv8.test'
            if final:value['cleanup'].update(container_removed=True,private_staging_removed=True);value['accepted']=True
            with self.subTest(final=final),self.assertRaises(OracleError):self.check(value,final)

    def test_field_requires_freeze_exact_class_shape_version_nonce_and_provenance(self):
        edits=(lambda v:v.update(failure_kind='baseline_observe_entry_other_owned_regular_zero'),
               lambda v:v.update(failure_kind='baseline_freeze_entry_other_owned_regular_nonzero'),
               lambda v:v.update(failure_kind='baseline_freeze_entry_other_unowned_regular_zero'),
               lambda v:v.update(failure_kind='baseline_freeze_invalid_input'),
               lambda v:v.update(rejected_basename='1Cv8.1CL'),
               lambda v:v['provenance'].update(actual_version=None),
               lambda v:v.update(nonce='b'*32),
               lambda v:v['provenance'].update(commit='b'*40),
               lambda v:v['provenance'].update(tree='c'*40),
               lambda v:v['provenance']['sources'].update(synthetic='d'*64))
        for index,edit in enumerate(edits):
            value=self.report();edit(value)
            with self.subTest(edit=index),self.assertRaises(OracleError):self.check(value)
        for failed in ('preflight','seed_v1','create','update','delete','cleanup'):
            value,_=fixture_report(failed if failed!='cleanup' else 'delete')
            value['rejected_basename']='1Cv8.test'
            with self.subTest(stage=failed),self.assertRaises(OracleError):self.check(value)

    def test_accepted_known_names_cannot_fabricate_class_consistent_diagnostics(self):
        for name in ('1Cv8.1CD','1Cv8Log','1Cv8.1CD.cfl','1Cv8tmp.1CD.cfl','1Cv8.1CL.cfl','1Cv8tmp.1CL.cfl'):
            with self.subTest(name=name),self.assertRaises(OracleError):self.check(self.report(name))

    def test_each_native_or_final_cleanup_failure_rejects_retained_field(self):
        for final in (False,True):
            for key in ('native_processes_stopped','raw_files_removed','container_removed','private_staging_removed'):
                if not final and key in ('container_removed','private_staging_removed'):continue
                value=self.report(final=final);value['cleanup'][key]=False
                if key in ('native_processes_stopped','raw_files_removed'):
                    value['stages'][-1]['checks'][key]=False;value['stages'][-1]['status']='failed'
                with self.subTest(final=final,key=key),self.assertRaises(OracleError):self.check(value,final)

    def test_no_extra_diagnostic_object_keys_or_raw_error_channels(self):
        for key in ('diagnostic','path','basenames','file_contents','source_directory'):
            value=self.report();value[key]=PRIVATE
            with self.subTest(key=key),self.assertRaises(OracleError):self.check(value)

if __name__=='__main__': unittest.main()
