"""Closed failure-only diagnostic policy; synthetic inputs, no native acceptance."""
import copy
import hashlib
import json
from pathlib import Path
import sys
import unittest
from unittest import mock
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'scripts/native_1c_db_oracle'),str(ROOT/'yadinassi/storage'),str(ROOT/'scripts'),str(ROOT/'tests')]
import config_root_diagnostic as policy
import inputs
import protocol
from snapshots import OracleError
import test_native_1c_db_oracle_stage as fixtures
import test_native_1c_db_oracle_record_route as old
from test_native_1c_db_oracle_config_root_reference_reader import root_source, ROOT_STORED
from test_native_1c_db_oracle_config_root_diagnostic_reader import RECIPE, RECIPE_SHA256
NONCE=old.NONCE
host=old.host
COMPLETE='config_root_diagnostic_complete'
GATES=('config_root_open_brace','config_root_comma','config_root_close_brace')


def identity():
    value=fixtures.provenance();value['sources']={p:'c'*64 for p in inputs.CONFIG_ROOT_DIAGNOSTIC_SOURCE_FILES}
    return value


class Backend(fixtures.FixtureNative):
    reader_attempted=True
    category='diagnostic_stop'
    code=COMPLETE
    def observe_record_metadata(self, identifier):
        self.event('record_metadata',identifier)
        raise policy.ObservationFailure(self.category,self.code)


def fixture(*, category='diagnostic_stop', code=COMPLETE, cleanup=(True,True), fail=None):
    provenance=identity();report=policy.empty_report(NONCE,provenance)
    backend=Backend(provenance,fail);backend.category=category;backend.code=code;backend.clean=cleanup
    controller=fixtures.stage.Controller(backend,report);backend.controller=controller
    return controller.run(),backend


def final_report(**kwargs):
    report,_=fixture(**kwargs);report['cleanup'].update(container_removed=True,private_staging_removed=True)
    return report


class ConfigRootDiagnosticPolicyTests(unittest.TestCase):
    def check(self, report, final=True):
        return policy.validate_report(protocol.encode(report),nonce=NONCE,provenance=report['provenance'],final=final)

    def test_independent_literal_recipe_and_guard_before_read(self):
        self.assertEqual(policy.RECIPE_DESCRIPTION,RECIPE);self.assertEqual(policy.RECIPE_SHA256,RECIPE_SHA256)
        self.assertEqual(policy.RECIPE_SHA256,hashlib.sha256(json.dumps(RECIPE,ensure_ascii=True,sort_keys=True,separators=(',',':'),allow_nan=False).encode('ascii')).hexdigest())
        callback=mock.Mock(side_effect=AssertionError('reader used before recipe guard'))
        with mock.patch.object(policy,'RECIPE_SHA256','f'*64),self.assertRaises(OracleError) as error:
            policy.read_projection(callback,8192,limits=policy.reader.CatalogLimits())
        self.assertEqual(error.exception.kind,'provenance_mismatch');callback.assert_not_called()

    def test_no_success_projection_binder_or_observer_return(self):
        for name in ('validate_projection','bind_capture','VERDICT'):self.assertFalse(hasattr(policy,name))
        for value in (None,{}, {'reader':'PRIVATE'}, True):
            with mock.patch.object(policy.framing,'observe_config_root_diagnostic',return_value=value),self.assertRaises(OracleError) as error:
                policy.read_projection(lambda a,n:b'',8192,limits=policy.reader.CatalogLimits())
            self.assertEqual(error.exception.kind,'unexpected_failure')
        source=root_source([('root',ROOT_STORED,0)])
        with self.assertRaises(policy.framing._ConfigRootDiagnosticComplete):
            policy.read_projection(source.read_at,source.size,limits=policy.reader.CatalogLimits())

    def test_exact_completion_class_and_finite_gate_type_mapping(self):
        error=policy.framing._ConfigRootDiagnosticComplete();mapped=policy.reader_failure(error)
        self.assertEqual((mapped.category,mapped.code),('diagnostic_stop',COMPLETE))
        self.assertEqual(error.args,(COMPLETE,));self.assertEqual(vars(error),{'code':COMPLETE})
        with self.assertRaises(TypeError):policy.framing._ConfigRootDiagnosticComplete('PRIVATE')
        class Child(policy.framing._ConfigRootDiagnosticComplete):pass
        class InvalidChild(policy.reader.InvalidStructure):pass
        for error in (Child(),policy.reader.InvalidStructure(COMPLETE),policy.reader.UnsupportedLayout(COMPLETE),InvalidChild(GATES[0]),ValueError('PRIVATE')):
            with self.assertRaises(OracleError):policy.reader_failure(error)
        error=policy.framing._ConfigRootDiagnosticComplete();error.code='PRIVATE'
        with self.assertRaises(OracleError):policy.reader_failure(error)
        for code in GATES:
            self.assertEqual(policy.reader_failure(policy.reader.InvalidStructure(code)).category,'structural_rejection')
            with self.assertRaises(OracleError):policy.reader_failure(policy.reader.UnsupportedLayout(code))
        for code in ('config_root_grammar','config_root_missing_selected_target','config_root_empty_target'):
            for kind in (policy.reader.InvalidStructure,policy.reader.UnsupportedLayout):
                with self.assertRaises(OracleError):policy.reader_failure(kind(code))

    def test_all_137_pairs_are_failed_and_wrong_pairings_reject(self):
        self.assertEqual(sum(map(len,policy.DIAGNOSTICS.values())),137)
        template=final_report()
        for category,codes in policy.DIAGNOSTICS.items():
            for code in codes:
                value=copy.deepcopy(template);value['config_root_diagnostic'].update(category=category,code=code)
                with self.subTest(category=category,code=code):
                    self.check(value);self.assertFalse(value['accepted'])
                    for wrong in set(policy.DIAGNOSTICS)-{category}:
                        if code in policy.DIAGNOSTICS[wrong]:continue
                        value['config_root_diagnostic']['category']=wrong
                        with self.assertRaises(OracleError):self.check(value)
                    value['config_root_diagnostic']['category']=category;value['accepted']=True
                    with self.assertRaises(OracleError):self.check(value)
        for category,code in (('PRIVATE',COMPLETE),('diagnostic_stop','PRIVATE'),('diagnostic_stop',True),('diagnostic_stop',GATES[0])):
            with self.assertRaises(OracleError):policy.ObservationFailure(category,code)

    def test_success_looking_fields_and_wrong_schema_inventory_reject(self):
        report=final_report()
        mutations=(lambda v:v.update(accepted=True),lambda v:v.update(status='ok'),lambda v:v.update(schema=True),
            lambda v:v.update(schema=19),lambda v:v.update(lane='owned_config_root_reference_v1'),
            lambda v:v.update(reader_validation='config_root_reference_observed'),
            lambda v:v.update(observation_validation='config_root_diagnostic_complete'),
            lambda v:v.update(native_compatibility='accepted'),lambda v:v.update(native_byte_equivalence='observed'),
            lambda v:v.update(extraction_validation='observed'),lambda v:v.update(failure_kind='config_root_reference_failed'),
            lambda v:v.update(extra='PRIVATE'),lambda v:v['config_root_diagnostic'].update(schema=True),
            lambda v:v['config_root_diagnostic'].update(status='ok'),lambda v:v['config_root_diagnostic'].update(reader={}),
            lambda v:v['config_root_diagnostic'].update(parsed_locator_count=1),lambda v:v['config_root_diagnostic'].update(resolved_positive_target_count=1),
            lambda v:v['config_root_diagnostic'].update(relation_validation='fixed_key_guid_reference_resolved_v1'),
            lambda v:v['config_root_diagnostic'].update(key='PRIVATE'),lambda v:v['config_root_diagnostic'].pop('code'),
            lambda v:v['provenance']['sources'].pop(policy.MODULE_SOURCE),
            lambda v:v['provenance']['sources'].update({'scripts/native_1c_db_oracle/config_root_reference.py':'c'*64}))
        for mutate in mutations:
            value=copy.deepcopy(report);mutate(value)
            with self.assertRaises(OracleError):self.check(value)

    def test_baseline_stop_and_forged_backend_success_never_continue(self):
        report,backend=fixture();self.check(report,False)
        self.assertEqual((report['status'],report['failed_stage'],report['failure_kind'],report['accepted']),('failed','baseline',policy.FAILURE_KIND,False))
        self.assertEqual([x['id'] for x in report['snapshots']],['baseline'])
        self.assertEqual(report['artifacts'],[]);self.assertEqual(report['comparisons'],[])
        self.assertFalse(any(event[0] in ('mutate','clone','artifact','apply') for event in backend.events))
        provenance=identity();template=policy.empty_report(NONCE,provenance);backend=Backend(provenance)
        backend.observe_record_metadata=mock.Mock(return_value={'PRIVATE':'forged success'})
        control=fixtures.stage.Controller(backend,template);backend.controller=control
        result=control.run();self.check(result,False)
        self.assertEqual(result['failure_kind'],'unexpected_failure');self.assertIsNone(result['config_root_diagnostic'])
        self.assertNotIn('PRIVATE',protocol.encode(result).decode())

    def test_intermediate_two_cleanup_gates_and_final_four_gates(self):
        intermediate,_=fixture();self.check(intermediate,False)
        with self.assertRaises(OracleError):self.check(intermediate,True)
        report=final_report();self.check(report)
        for key in report['cleanup']:
            value=copy.deepcopy(report);value['cleanup'][key]=False
            with self.assertRaises(OracleError):self.check(value)
            policy.discard_capture(value,final=True)
            self.assertIsNone(value['config_root_diagnostic']);self.assertFalse(value['accepted'])
        for cleanup in ((False,True),(True,False),(False,False)):
            report,_=fixture(cleanup=cleanup);self.check(report,False);self.assertIsNone(report['config_root_diagnostic'])

    def test_prebaseline_failures_have_no_diagnostic(self):
        for failed in ('preflight','seed_v1'):
            report,_=fixture(fail=failed);self.check(report,False)
            self.assertIsNone(report['config_root_diagnostic']);self.assertFalse(report['accepted'])

    def test_all_old_policies_reject_schema_and_new_reader_codes(self):
        import comparison,record_observation,record_validation,params_observation,params_extraction,dbnames_identity
        import config_observation,config_framing,config_marker_census,config_zero_marker_filename
        import config_entry_reference,config_blob_chain,config_content_decode,config_root_reference
        modules=(comparison,record_observation,record_validation,params_observation,params_extraction,dbnames_identity,
            config_observation,config_framing,config_marker_census,config_zero_marker_filename,
            config_entry_reference,config_blob_chain,config_content_decode,config_root_reference)
        report=final_report()
        for module in modules:
            with self.subTest(module=module.__name__):
                with self.assertRaises(OracleError):module.validate_report(protocol.encode(report),nonce=NONCE,provenance=report['provenance'],final=True)
                mapper=getattr(module,'reader_failure',None)
                if mapper is not None:
                    for error in (policy.framing._ConfigRootDiagnosticComplete(),*(policy.reader.InvalidStructure(code) for code in GATES)):
                        with self.assertRaises(OracleError):mapper(error)

if __name__=='__main__':unittest.main()
