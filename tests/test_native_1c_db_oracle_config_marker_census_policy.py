"""Pure diagnostic marker policy evidence; no native or framing acceptance."""
from __future__ import annotations

import copy
from dataclasses import replace
import hashlib
import json
from pathlib import Path
import sys
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT/'scripts/native_1c_db_oracle'), str(ROOT/'yadinassi/storage'),
                str(ROOT/'scripts'), str(ROOT/'tests')]
import comparison
import config_marker_census as policy
import config_framing as strict_policy
import config_observation
import inputs
import protocol
import record_observation as metadata
import record_validation
import snapshots
from snapshots import OracleError
import test_native_1c_db_oracle_stage as fixtures
import test_native_1c_db_oracle_record_route as old
import test_native_1c_db_oracle_config_framing_reader as synthetic

NONCE, TOKEN = old.NONCE, old.TOKEN
host = old.host


def identity():
    result = fixtures.provenance()
    result['sources'] = {name:'c'*64 for name in inputs.CONFIG_MARKER_CENSUS_SOURCE_FILES}
    return result


def projection(slots=2, zero=1, one=0, other=0, first='one'):
    return {'schema':1, 'target':'CONFIG', 'recipe_id':policy.RECIPE_ID,
        'recipe_sha256':policy.RECIPE_SHA256, 'data_logical_bytes':301*slots,
        'blob_logical_bytes':256, 'candidate_stride':301, 'candidate_slots':slots,
        'first_marker_class':first, 'later_zero_count':zero,
        'later_one_count':one, 'later_other_count':other,
        'framing_validation':'not_accepted', 'filename_validation':'not_run',
        'root_identity':'not_observed'}


def evidence(token=TOKEN):
    return {'marker':old.marker(token),
        'origin':{'nonce':NONCE, 'token':token, 'clone':'auditor',
                  **{key:fixtures.physical('baseline')[key] for key in ('bytes','sha256')}},
        'postimage':{'bytes':20*8192,'sha256':'e'*64}, 'reader':projection()}


class Backend(fixtures.FixtureNative):
    def observe_record_metadata(self, identifier):
        self.event('record_metadata',identifier)
        return evidence()


def fixture(fail=None, cleanup=(True,True)):
    provenance=identity(); report=policy.empty_report(NONCE,provenance)
    backend=Backend(provenance,fail); backend.clean=cleanup
    controller=fixtures.stage.Controller(backend,report); backend.controller=controller
    return controller.run(),backend


class ConfigMarkerCensusPolicyTests(unittest.TestCase):
    def check(self,report,final=False):
        return policy.validate_report(protocol.encode(report),nonce=NONCE,provenance=identity(),final=final)

    def test_independent_recipe_and_real_reader_only_finite_output(self):
        expected={'identifier':'config_marker_census_8380_8192_v1',
            'declarations':synthetic.DECLARATIONS, 'recordlock':'0','format_item':0,
            'candidate_stride':301,
            'observation':'first_and_later_zero_one_other_candidate_markers_v1',
            'selection':'CONFIG_ascii_case_only_no_fallback_v1',
            'empty_data':'unsupported','single_candidate':'admitted',
            'framing':'not_accepted','filename':'not_read'}
        digest=hashlib.sha256(json.dumps(expected,ensure_ascii=True,sort_keys=True,
            separators=(',',':'),allow_nan=False).encode('ascii')).hexdigest()
        self.assertEqual(policy.RECIPE_DESCRIPTION,expected)
        self.assertEqual(policy.RECIPE_SHA256,digest)
        data=synthetic.source([synthetic.row(marker=255),synthetic.row('PRIVATE'),
                               synthetic.row(marker=1),synthetic.row(marker=2)])
        result=policy.read_projection(data.read_at,data.size,limits=policy.reader.CatalogLimits())
        self.assertEqual(result,projection(slots=4,zero=1,one=1,other=1,first='other'))
        self.assertNotIn(b'PRIVATE',protocol.encode(result))
        self.assertNotIn('usage',result)
        self.assertNotIn((data.blob_page*8192,8192),data.calls)
        self.assertFalse({'active_slots','free_slots','filename','index','offset'} & set(result))

    def test_core_recipe_disagreement_rejects_before_source_read(self):
        profile=policy.framing.ConfigMarkerCensusProfile(synthetic.DECLARATIONS,'0',0)
        object.__setattr__(profile,'recipe_sha256','f'*64)
        data=synthetic.source()
        with mock.patch.object(policy.framing,'ConfigMarkerCensusProfile',return_value=profile), \
             mock.patch.object(policy.framing,'observe_config_marker_census') as observe:
            with self.assertRaises(OracleError):
                policy.read_projection(data.read_at,data.size,limits=policy.reader.CatalogLimits())
            observe.assert_not_called()
        self.assertEqual(data.calls,[])

    def test_core_returned_identity_or_claim_disagreement_rejects(self):
        data=synthetic.source()
        result=policy.framing.observe_config_marker_census(data.read_at,data.size,
            profile=policy.framing.ConfigMarkerCensusProfile(synthetic.DECLARATIONS,'0',0))
        for change in ({'recipe_id':'OTHER'},{'recipe_sha256':'f'*64},{'candidate_slots':3},
                       {'first_marker_class':'free'}):
            with mock.patch.object(policy.framing,'observe_config_marker_census',return_value=replace(result,**change)):
                with self.assertRaises(OracleError):
                    policy.read_projection(data.read_at,data.size,limits=policy.reader.CatalogLimits())
        for key,value in (('root_identity','observed'),('native_acceptance','accepted'),
                          ('framing_validation','source_hypothesis_satisfied'),
                          ('filename_validation','bounded_utf16le_validated'),('candidate_stride',302)):
            changed=copy.copy(result); object.__setattr__(changed,key,value)
            with mock.patch.object(policy.framing,'observe_config_marker_census',return_value=changed):
                with self.assertRaises(OracleError):
                    policy.read_projection(data.read_at,data.size,limits=policy.reader.CatalogLimits())

    def test_count_conservation_single_candidate_and_no_expected_native_counts(self):
        for slots,zero,one,other in ((1,0,0,0),(2,1,0,0),(2,0,1,0),
                                    (2,0,0,1),(16,4,5,6),(4096,1,4093,1)):
            for first in ('zero','one','other'):
                value=projection(slots,zero,one,other,first)
                self.assertEqual(policy.validate_projection(value),value)
        for changes in ({'candidate_slots':0},{'candidate_slots':4097},{'candidate_slots':True},
                {'candidate_stride':302},{'data_logical_bytes':603},{'later_zero_count':0},
                {'later_one_count':1},{'later_other_count':4096},{'later_zero_count':-1},
                {'blob_logical_bytes':snapshots.MAX_FILE_BYTES+1},{'blob_logical_bytes':-1},
                {'first_marker_class':'removed'}):
            value=projection();value.update(changes)
            with self.subTest(changes=changes),self.assertRaises(OracleError): policy.validate_projection(value)

    def test_every_projection_field_required_closed_and_exact_primitives(self):
        for key in projection():
            value=projection();del value[key]
            with self.subTest(missing=key),self.assertRaises(OracleError): policy.validate_projection(value)
        for forbidden in ('filename','free_slots','active_slots','offset','marker_bytes'):
            value=projection();value[forbidden]='PRIVATE'
            with self.assertRaises(OracleError): policy.validate_projection(value)
        for key in ('candidate_slots','candidate_stride','later_zero_count','later_one_count',
                    'later_other_count','data_logical_bytes','blob_logical_bytes','schema'):
            for replacement in (True,False,1.0,'1',None):
                value=projection();value[key]=replacement
                with self.subTest(key=key,replacement=replacement),self.assertRaises(OracleError):
                    policy.validate_projection(value)
        for key in ('target','recipe_id','recipe_sha256','first_marker_class',
                    'framing_validation','filename_validation','root_identity'):
            for replacement in ('PRIVATE',True,None,{}):
                value=projection();value[key]=replacement
                with self.subTest(key=key,replacement=replacement),self.assertRaises(OracleError):
                    policy.validate_projection(value)

    def test_diagnostic_success_does_not_relax_strict_framing_or_read_filenames(self):
        bad_name=bytearray(synthetic.row(marker=0));bad_name[1:3]=b'\xff\xff'
        data=synthetic.source([synthetic.row(marker=1),synthetic.row(marker=1),bytes(bad_name)])
        with self.assertRaises(policy.reader.UnsupportedLayout) as error:
            strict_policy.read_projection(data.read_at,data.size,limits=policy.reader.CatalogLimits())
        self.assertEqual(error.exception.code,'config_nonreserved_slot')
        observed=policy.read_projection(data.read_at,data.size,limits=policy.reader.CatalogLimits())
        self.assertEqual(observed,projection(slots=3,zero=1,one=1))
        self.assertEqual(observed['framing_validation'],'not_accepted')
        self.assertEqual(observed['filename_validation'],'not_run')

    def test_complete_bound_capture_and_unchanged_native_lifecycle(self):
        report,backend=fixture(); self.check(report)
        self.assertEqual((report['schema'],report['config_marker_census']['schema']),(12,13))
        self.assertEqual((len(report['stages']),len(report['snapshots']),len(report['comparisons'])),(13,11,5))
        self.assertEqual(backend.events.count(('record_metadata','baseline')),1)
        self.assertNotIn('record_metadata',report['config_marker_census'])
        self.assertNotIn(b'Uninterpreted',protocol.encode(report))
        self.assertEqual(report['reader_validation'],policy.VERDICT)
        for key in ('extraction_validation','mapping_validation','layout_validation'):
            self.assertEqual(report[key],'not_run')
        self.assertEqual(report['framing_validation'],'not_accepted')
        self.assertEqual(report['native_byte_equivalence'],'not_observed')
        self.assertEqual(report['native_compatibility'],'not_claimed')
        complete=copy.deepcopy(report)
        complete['cleanup'].update(container_removed=True,private_staging_removed=True)
        complete['accepted']=True
        self.check(complete,final=True)

    def test_complete_capture_bindings_and_inventory_mutations_rejected(self):
        report,_=fixture()
        for key in ('token','nonce','source_manifest_sha256','reader_source_sha256',
                    'policy_source_sha256','framing_reader_source_sha256'):
            value=copy.deepcopy(report); value['config_marker_census'][key]='f'*64
            with self.subTest(key=key),self.assertRaises(OracleError): self.check(value)
        for path in ((),('config_marker_census',),('config_marker_census','reader'),
                     ('config_marker_census','origin'),('config_marker_census','postimage')):
            for extra in (False,True):
                value=copy.deepcopy(report); target=value
                for key in path: target=target[key]
                if extra: target['PRIVATE']='arbitrary'
                else: del target[next(iter(target))]
                with self.subTest(path=path,extra=extra),self.assertRaises(OracleError): self.check(value)
        for mode in ('missing','extra','replace'):
            value=copy.deepcopy(report); sources=value['provenance']['sources']
            if mode!='extra': sources.pop(policy.FRAMING_READER_SOURCE)
            if mode!='missing': sources['scripts/native_1c_db_oracle/config_observation.py']='c'*64
            with self.assertRaises(OracleError):
                policy.validate_report(protocol.encode(value),nonce=NONCE,provenance=value['provenance'])
        for name in ('CONFIG_FRAMING_SOURCE_FILES','CONFIG_SOURCE_FILES','PARAMS_SOURCE_FILES','EXTRACTION_SOURCE_FILES','IDENTITY_SOURCE_FILES'):
            value=copy.deepcopy(report); value['provenance']['sources']={name:'c'*64 for name in getattr(inputs,name)}
            with self.assertRaises(OracleError):
                policy.validate_report(protocol.encode(value),nonce=NONCE,provenance=value['provenance'])

    def test_origin_postimage_and_claim_tampering_rejected(self):
        report,_=fixture()
        for changes in ({'bytes':1},{'sha256':'f'*64}):
            value=evidence();value['origin'].update(changes)
            with self.assertRaises(OracleError): policy.bind_capture(value,report)
        for changes in ({'storage_version':[8,2,14,0]},{'page_size':4096},{'bytes':1},
                        {'copy':'baseline'},{'binding':'before_audit'}):
            value=copy.deepcopy(report); value['config_marker_census']['postimage'].update(changes)
            with self.assertRaises(OracleError): self.check(value)
        for key in ('framing_validation','extraction_validation','mapping_validation','layout_validation',
                    'native_byte_equivalence','native_compatibility'):
            value=copy.deepcopy(report);value[key]='accepted'
            with self.assertRaises(OracleError): self.check(value)
        value=copy.deepcopy(report)
        value['config_marker_census']['reader']['blob_logical_bytes']=value['config_marker_census']['postimage']['bytes']
        with self.assertRaises(OracleError): self.check(value)

    def test_failure_state_pairs_are_closed_without_claiming_unrun_observation(self):
        report,_=fixture('create')
        for pair in (('not_run','failed'),('discarded','failed'),('failed','discarded'),
                     ('not_run','discarded'),('discarded','not_run')):
            changed=copy.deepcopy(report)
            changed['reader_validation'],changed['observation_validation']=pair
            with self.subTest(pair=pair),self.assertRaises(OracleError): self.check(changed)

    def test_older_schema_validators_reject_new_success_and_failure(self):
        report,_=fixture()
        for validator in (protocol.validate_report,comparison.validate_report,metadata.validate_report,
                          record_validation.validate_report,config_observation.validate_report,strict_policy.validate_report):
            with self.assertRaises(OracleError): validator(protocol.encode(report),nonce=NONCE,provenance=identity())
        for schema in (4,5,6,7,8,9,10,11,True):
            value=copy.deepcopy(report); value['schema']=schema
            with self.assertRaises(OracleError): self.check(value)
        for foreign in ('config_framing_failed','config_observation_failed','dbnames_identity_failed','params_extraction_failed',
                        'params_observation_failed','record_readback_failed','record_observation_failed',
                        'catalog_comparison_failed'):
            value=copy.deepcopy(report);value['failure_kind']=foreign
            with self.assertRaises(OracleError): self.check(value)

    def test_all_later_lifecycle_failures_and_native_cleanup_discard_capture(self):
        for failed in protocol.STAGES[3:-1]:
            report,_=fixture(failed);self.check(report)
            self.assertIsNone(report['config_marker_census'])
            self.assertEqual(report['observation_validation'],'discarded')
        for cleanup in ((False,True),(True,False),(False,False)):
            report,_=fixture(cleanup=cleanup);self.check(report)
            self.assertIsNone(report['config_marker_census']);self.assertEqual(report['artifacts'],[])
        for gate in ('container_removed','private_staging_removed'):
            report,_=fixture();report['cleanup'].update(container_removed=True,private_staging_removed=True)
            report['cleanup'][gate]=False
            host.fail_report(report,'cleanup_unverified','cleanup',preserve_primary=True)
            self.check(report,final=True);self.assertIsNone(report['config_marker_census'])

    def test_finite_classified_reader_failure_only_after_cleanup(self):
        for error in (policy.ObservationFailure('unsupported_layout','config_profile_mismatch'),
                      OracleError('timeout'),AssertionError('PRIVATE')):
            provenance=identity();report=policy.empty_report(NONCE,provenance)
            backend=Backend(provenance);backend.reader_attempted=True
            backend.observe_record_metadata=mock.Mock(side_effect=error)
            controller=fixtures.stage.Controller(backend,report);backend.controller=controller
            result=controller.run();self.check(result)
            self.assertEqual(result['reader_validation'],'failed')
            self.assertNotIn(b'PRIVATE',protocol.encode(result))
            for gate in ('container_removed','private_staging_removed'):
                late=copy.deepcopy(result);late['cleanup'].update(container_removed=True,private_staging_removed=True)
                late['cleanup'][gate]=False
                host.fail_report(late,'cleanup_unverified','cleanup',preserve_primary=True)
                self.check(late,final=True);self.assertIsNone(late['config_marker_census'])

    def test_failure_vocabulary_covers_only_finite_exact_core_and_catalog_codes(self):
        for kind,codes in (
            (policy.reader.UnsupportedLayout,('config_table_missing','config_table_ambiguous',
                'config_profile_mismatch','config_empty_data','missing_table_blob_header')),
            (policy.reader.InvalidStructure,('config_record_length','table_blob_header_role')),
            (policy.reader.ResourceLimit,('config_slots','config_record_bytes'))):
            for code in codes:
                self.assertEqual(policy.reader_failure(kind(code)).code,code)
                with self.assertRaises(OracleError): comparison.reader_failure(kind(code))
        for error in (policy.reader.UnsupportedLayout('PRIVATE'), ValueError('PRIVATE'),
                      type('Subclass',(policy.reader.UnsupportedLayout,),{})('config_profile_mismatch')):
            with self.assertRaises(OracleError): policy.reader_failure(error)
        for code in ('config_reserved_slot','config_nonreserved_slot','config_filename_encoding','config_filename_length'):
            with self.assertRaises(OracleError): policy.reader_failure(policy.reader.UnsupportedLayout(code))
        for category,code in (('PRIVATE','config_slots'),('resource_limit','PRIVATE'),
                              ('unsupported_layout','config_record_length')):
            with self.assertRaises(OracleError): policy.ObservationFailure(category,code)


if __name__=='__main__': unittest.main()
