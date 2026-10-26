"""Pure zero-marker filename-field policy controls; no native or file identities."""
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
import config_zero_marker_filename as policy
import config_marker_census as census_policy
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
    result['sources'] = {name:'c'*64 for name in inputs.CONFIG_ZERO_MARKER_FILENAME_SOURCE_FILES}
    return result


def projection(slots=2, zero=1, one=0, other=0, first='one', *, empty=0,
               nonempty=None, maximum=1):
    return {'schema':1, 'target':'CONFIG', 'recipe_id':policy.RECIPE_ID,
        'recipe_sha256':policy.RECIPE_SHA256, 'data_logical_bytes':301*slots,
        'blob_logical_bytes':256, 'candidate_stride':301, 'candidate_slots':slots,
        'first_marker_class':first, 'later_zero_count':zero,
        'later_one_count':one, 'later_other_count':other,
        'validated_zero_count':zero, 'empty_filenames':empty,
        'nonempty_filenames':zero-empty if nonempty is None else nonempty,
        'max_filename_units':maximum,
        'framing_validation':'not_accepted', 'filename_validation':'zero_marker_bounded_utf16le',
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


class ConfigZeroMarkerFilenamePolicyTests(unittest.TestCase):
    def check(self,report,final=False):
        return policy.validate_report(protocol.encode(report),nonce=NONCE,provenance=identity(),final=final)

    def test_independent_recipe_and_real_reader_only_finite_output(self):
        expected={'identifier':'config_zero_marker_filename_8380_8192_v1',
            'declarations':synthetic.DECLARATIONS, 'recordlock':'0','format_item':0,
            'candidate_stride':301, 'filename_offset':1, 'filename_width':258,
            'first_marker':'one_reserved_opaque_v1',
            'later_selection':'zero_validate_nonzero_opaque_v1',
            'filename':'u16le_units_at_most_128_strict_utf16le_v1',
            'selection':'CONFIG_ascii_case_only_no_fallback_v1',
            'empty_data':'unsupported','nonempty_witness':'required',
            'framing':'not_accepted'}
        digest=hashlib.sha256(json.dumps(expected,ensure_ascii=True,sort_keys=True,
            separators=(',',':'),allow_nan=False).encode('ascii')).hexdigest()
        self.assertEqual(policy.RECIPE_DESCRIPTION,expected)
        self.assertEqual(policy.RECIPE_SHA256,digest)
        self.assertEqual(digest,'8de171031a518dc9ac6446dd9425118be1d1d7151ff87607b93086cd924e8d4b')
        data=synthetic.source([synthetic.row(marker=1),synthetic.row('PRIVATE'),
            synthetic.row(''),synthetic.row(raw=b'\0\xd8',units=65535,marker=1),
            synthetic.row(raw=b'\0\xdc',units=65535,marker=255)])
        result=policy.read_projection(data.read_at,data.size,limits=policy.reader.CatalogLimits())
        self.assertEqual(result,projection(slots=5,zero=2,one=1,other=1,empty=1,maximum=7))
        self.assertNotIn(b'PRIVATE',protocol.encode(result))
        self.assertNotIn('usage',result)
        self.assertNotIn((data.blob_page*8192,8192),data.calls)
        self.assertFalse({'active_slots','free_slots','filename','filename_sha256','index','offset'} & set(result))

    def test_core_recipe_disagreement_rejects_before_source_read(self):
        for key,bad in (('identifier','OTHER'),('recipe_sha256','f'*64),
                        ('candidate_stride',302),('filename_offset',2),('filename_width',256)):
            profile=policy.framing.ConfigZeroMarkerFilenameProfile(synthetic.DECLARATIONS,'0',0)
            object.__setattr__(profile,key,bad)
            data=synthetic.source()
            with mock.patch.object(policy.framing,'ConfigZeroMarkerFilenameProfile',return_value=profile), \
                 mock.patch.object(policy.framing,'observe_config_zero_marker_filenames') as observe:
                with self.subTest(key=key),self.assertRaises(OracleError):
                    policy.read_projection(data.read_at,data.size,limits=policy.reader.CatalogLimits())
                observe.assert_not_called()
            self.assertEqual(data.calls,[])

    def test_core_returned_identity_or_claim_disagreement_rejects(self):
        data=synthetic.source()
        result=policy.framing.observe_config_zero_marker_filenames(data.read_at,data.size,
            profile=policy.framing.ConfigZeroMarkerFilenameProfile(synthetic.DECLARATIONS,'0',0))
        for change in ({'recipe_id':'OTHER'},{'recipe_sha256':'f'*64},{'candidate_slots':3},
                       {'first_marker_class':'free'},{'validated_zero_count':0},
                       {'nonempty_filenames':0},{'max_filename_units':129}):
            with mock.patch.object(policy.framing,'observe_config_zero_marker_filenames',return_value=replace(result,**change)):
                with self.assertRaises(OracleError):
                    policy.read_projection(data.read_at,data.size,limits=policy.reader.CatalogLimits())
        for key,value in (('root_identity','observed'),('native_acceptance','accepted'),
                          ('framing_validation','source_hypothesis_satisfied'),
                          ('filename_validation','bounded_utf16le_validated'),('candidate_stride',302)):
            changed=copy.copy(result); object.__setattr__(changed,key,value)
            with mock.patch.object(policy.framing,'observe_config_zero_marker_filenames',return_value=changed):
                with self.assertRaises(OracleError):
                    policy.read_projection(data.read_at,data.size,limits=policy.reader.CatalogLimits())

    def test_count_conservation_witness_and_no_expected_native_counts(self):
        for slots,zero,one,other,empty,maximum in ((2,1,0,0,0,1),(3,2,0,0,1,128),
                (16,4,5,6,2,9),(4096,1,4093,1,0,128),(4096,4095,0,0,4094,1)):
            value=projection(slots,zero,one,other,empty=empty,maximum=maximum)
            self.assertEqual(policy.validate_projection(value),value)
        for changes in ({'candidate_slots':0},{'candidate_slots':4097},{'candidate_slots':True},
                {'candidate_stride':302},{'data_logical_bytes':603},{'later_zero_count':0},
                {'later_one_count':1},{'later_other_count':4096},{'later_zero_count':-1},
                {'validated_zero_count':2},{'validated_zero_count':0},
                {'empty_filenames':1},{'nonempty_filenames':0},{'max_filename_units':0},
                {'max_filename_units':129},{'blob_logical_bytes':snapshots.MAX_FILE_BYTES+1},
                {'blob_logical_bytes':-1},{'first_marker_class':'zero'},
                {'first_marker_class':'other'},{'first_marker_class':'removed'}):
            value=projection();value.update(changes)
            with self.subTest(changes=changes),self.assertRaises(OracleError):policy.validate_projection(value)
        for value in (projection(1,0,0,0,maximum=0),projection(2,1,0,0,empty=1,maximum=0),
                      projection(2,0,1,0,maximum=0),projection(2,0,0,1,maximum=0)):
            with self.assertRaises(OracleError):policy.validate_projection(value)

    def test_every_projection_field_required_closed_and_exact_primitives(self):
        for key in projection():
            value=projection();del value[key]
            with self.subTest(missing=key),self.assertRaises(OracleError): policy.validate_projection(value)
        for forbidden in ('filename','filenames','filename_sha256','free_slots','active_slots','offset','marker_bytes','free_chain'):
            value=projection();value[forbidden]='PRIVATE'
            with self.assertRaises(OracleError): policy.validate_projection(value)
        for key in ('candidate_slots','candidate_stride','later_zero_count','later_one_count',
                    'later_other_count','data_logical_bytes','blob_logical_bytes','schema',
                    'validated_zero_count','empty_filenames','nonempty_filenames','max_filename_units'):
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

    def test_nonzero_opaque_but_malformed_zero_fails_original_modes_unchanged(self):
        opaque=synthetic.row(raw=b'\0\xd8',units=65535,marker=1)
        data=synthetic.source([synthetic.row(marker=1),opaque,synthetic.row('okay')])
        with self.assertRaises(policy.reader.UnsupportedLayout) as error:
            strict_policy.read_projection(data.read_at,data.size,limits=policy.reader.CatalogLimits())
        self.assertEqual(error.exception.code,'config_nonreserved_slot')
        observed=policy.read_projection(data.read_at,data.size,limits=policy.reader.CatalogLimits())
        self.assertEqual(observed,projection(slots=3,zero=1,one=1,maximum=4))
        self.assertEqual(observed['framing_validation'],'not_accepted')
        self.assertEqual(observed['filename_validation'],'zero_marker_bounded_utf16le')
        malformed=synthetic.source([synthetic.row(marker=1),synthetic.row('good'),
                                   synthetic.row(raw=b'\0\xd8',units=65535)])
        with self.assertRaises(policy.reader.InvalidStructure) as error:
            policy.read_projection(malformed.read_at,malformed.size,limits=policy.reader.CatalogLimits())
        self.assertEqual(error.exception.code,'config_filename_length')
        census=census_policy.read_projection(malformed.read_at,malformed.size,limits=policy.reader.CatalogLimits())
        self.assertEqual(census['later_zero_count'],2)
        self.assertEqual(census['filename_validation'],'not_run')

    def test_complete_bound_capture_and_unchanged_native_lifecycle(self):
        report,backend=fixture(); self.check(report)
        self.assertEqual((report['schema'],report['config_zero_marker_filename']['schema']),(13,14))
        self.assertEqual((len(report['stages']),len(report['snapshots']),len(report['comparisons'])),(13,11,5))
        self.assertEqual(backend.events.count(('record_metadata','baseline')),1)
        self.assertNotIn('record_metadata',report['config_zero_marker_filename'])
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
            value=copy.deepcopy(report); value['config_zero_marker_filename'][key]='f'*64
            with self.subTest(key=key),self.assertRaises(OracleError): self.check(value)
        for path in ((),('config_zero_marker_filename',),('config_zero_marker_filename','reader'),
                     ('config_zero_marker_filename','origin'),('config_zero_marker_filename','postimage')):
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
        for name in ('CONFIG_MARKER_CENSUS_SOURCE_FILES','CONFIG_FRAMING_SOURCE_FILES','CONFIG_SOURCE_FILES','PARAMS_SOURCE_FILES','EXTRACTION_SOURCE_FILES','IDENTITY_SOURCE_FILES'):
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
            value=copy.deepcopy(report); value['config_zero_marker_filename']['postimage'].update(changes)
            with self.assertRaises(OracleError): self.check(value)
        for key in ('framing_validation','extraction_validation','mapping_validation','layout_validation',
                    'native_byte_equivalence','native_compatibility'):
            value=copy.deepcopy(report);value[key]='accepted'
            with self.assertRaises(OracleError): self.check(value)
        value=copy.deepcopy(report)
        value['config_zero_marker_filename']['reader']['blob_logical_bytes']=value['config_zero_marker_filename']['postimage']['bytes']
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
                          record_validation.validate_report,config_observation.validate_report,strict_policy.validate_report,
                          census_policy.validate_report):
            with self.assertRaises(OracleError): validator(protocol.encode(report),nonce=NONCE,provenance=identity())
        for schema in (4,5,6,7,8,9,10,11,12,True):
            value=copy.deepcopy(report); value['schema']=schema
            with self.assertRaises(OracleError): self.check(value)
        for foreign in ('config_marker_census_failed','config_framing_failed','config_observation_failed','dbnames_identity_failed','params_extraction_failed',
                        'params_observation_failed','record_readback_failed','record_observation_failed',
                        'catalog_comparison_failed'):
            value=copy.deepcopy(report);value['failure_kind']=foreign
            with self.assertRaises(OracleError): self.check(value)

    def test_all_later_lifecycle_failures_and_native_cleanup_discard_capture(self):
        for failed in protocol.STAGES[3:-1]:
            report,_=fixture(failed);self.check(report)
            self.assertIsNone(report['config_zero_marker_filename'])
            self.assertEqual(report['observation_validation'],'discarded')
        for cleanup in ((False,True),(True,False),(False,False)):
            report,_=fixture(cleanup=cleanup);self.check(report)
            self.assertIsNone(report['config_zero_marker_filename']);self.assertEqual(report['artifacts'],[])
        for gate in ('container_removed','private_staging_removed'):
            report,_=fixture();report['cleanup'].update(container_removed=True,private_staging_removed=True)
            report['cleanup'][gate]=False
            host.fail_report(report,'cleanup_unverified','cleanup',preserve_primary=True)
            self.check(report,final=True);self.assertIsNone(report['config_zero_marker_filename'])

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
                self.check(late,final=True);self.assertIsNone(late['config_zero_marker_filename'])

    def test_failure_vocabulary_covers_only_finite_exact_core_and_catalog_codes(self):
        for kind,codes in (
            (policy.reader.UnsupportedLayout,('config_table_missing','config_table_ambiguous',
                'config_profile_mismatch','config_empty_data','missing_table_blob_header',
                'config_reserved_slot','config_filename_encoding','config_filename_no_nonempty_witness')),
            (policy.reader.InvalidStructure,('config_record_length','table_blob_header_role','config_filename_length')),
            (policy.reader.ResourceLimit,('config_slots','config_record_bytes'))):
            for code in codes:
                self.assertEqual(policy.reader_failure(kind(code)).code,code)
                with self.assertRaises(OracleError):comparison.reader_failure(kind(code))
        for error in (policy.reader.UnsupportedLayout('PRIVATE'),ValueError('PRIVATE'),
                type('Subclass',(policy.reader.UnsupportedLayout,),{})('config_profile_mismatch'),
                policy.reader.UnsupportedLayout('config_nonreserved_slot'),
                policy.reader.UnsupportedLayout('config_filename_length')):
            with self.assertRaises(OracleError):policy.reader_failure(error)
        for category,code in (('PRIVATE','config_slots'),('resource_limit','PRIVATE'),
                              ('unsupported_layout','config_record_length')):
            with self.assertRaises(OracleError):policy.ObservationFailure(category,code)

    def test_actual_reader_requires_nonempty_witness_without_guessing_marker_counts(self):
        for rows in ([synthetic.row(marker=1)],
                     [synthetic.row(marker=1),synthetic.row('')],
                     [synthetic.row(marker=1),synthetic.row('PRIVATE',marker=255)]):
            value=synthetic.source(rows)
            with self.assertRaises(policy.reader.UnsupportedLayout) as error:
                policy.read_projection(value.read_at,value.size,limits=policy.reader.CatalogLimits())
            self.assertEqual(error.exception.code,'config_filename_no_nonempty_witness')
            self.assertEqual(policy.reader_failure(error.exception).code,'config_filename_no_nonempty_witness')

    def test_zero_marker_structural_strings_are_not_file_identities(self):
        # Empty, NUL and BOM are structural strings, not normalized or selected identities.
        value=synthetic.source([synthetic.row(marker=1),synthetic.row(''),
                               synthetic.row('\0'),synthetic.row('\ufeff')])
        actual=policy.read_projection(value.read_at,value.size,limits=policy.reader.CatalogLimits())
        self.assertEqual(actual,projection(4,3,0,0,empty=1,maximum=1))
        self.assertEqual(actual['root_identity'],'not_observed')

    def test_no_witness_failure_is_finite_and_rejected_by_every_old_lane(self):
        provenance=identity();report=policy.empty_report(NONCE,provenance)
        backend=Backend(provenance);backend.reader_attempted=True
        error=policy.reader_failure(policy.reader.UnsupportedLayout('config_filename_no_nonempty_witness'))
        backend.observe_record_metadata=mock.Mock(side_effect=error)
        controller=fixtures.stage.Controller(backend,report);backend.controller=controller
        result=controller.run();self.check(result)
        self.assertEqual(result['failure_kind'],'config_zero_marker_filename_failed')
        self.assertEqual(result['config_zero_marker_filename'],{'schema':14,'status':'failed',
            'category':'unsupported_layout','code':'config_filename_no_nonempty_witness'})
        for validator in (protocol.validate_report,comparison.validate_report,metadata.validate_report,
                          record_validation.validate_report,config_observation.validate_report,
                          strict_policy.validate_report,census_policy.validate_report):
            with self.assertRaises(OracleError):
                validator(protocol.encode(result),nonce=NONCE,provenance=provenance)


if __name__=='__main__': unittest.main()
