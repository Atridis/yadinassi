"""Pure exact selected stored-byte chain policy controls; no native acceptance."""
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
import config_root_reference as policy
import config_content_decode as content_policy
import config_blob_chain as chain_policy
import config_entry_reference as prerequisite_policy
import config_marker_census as census_policy
import config_zero_marker_filename as filename_policy
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
import test_native_1c_db_oracle_config_entry_reference_reader as prerequisite
from types import SimpleNamespace

# Entirely synthetic literal modern locator; not a captured native key or payload.
GUID = '01234567-89ab-cdef-0123-456789abcdef'
ROOT_BYTES = b'\xef\xbb\xbf{2,' + GUID.encode('ascii') + b'}'
ROOT_STORED = b'\x01\x2b\x00\xd4\xff' + ROOT_BYTES
TARGET_STORED = b'\x01\x01\0\xfe\xff\xa7'

def source(rows=None, **kwargs):
    from test_native_1c_db_oracle_config_blob_chain_reader import source as chains
    rows = [prerequisite.row(marker=1)] if rows is None else rows
    prepared=[rows[0],prerequisite.row('RoOt',start=1,length=len(ROOT_STORED)),
              prerequisite.row(GUID.upper(),start=2,length=len(TARGET_STORED))]
    nodes={1:(0,ROOT_STORED),2:(0,TARGET_STORED)}; selected=2
    for original in rows[1:]:
        raw=bytearray(original)
        if (raw[0] == 0 and 0 < int.from_bytes(raw[1:3],'little') <= 128
                and int.from_bytes(raw[287:291],'little') > 0
                and int.from_bytes(raw[291:295],'little') > 0):
            selected+=1; raw[287:291]=selected.to_bytes(4,'little')
            if int.from_bytes(raw[291:295],'little') == 1:
                raw[291:295]=(6).to_bytes(4,'little')
            nodes[selected]=(0,TARGET_STORED)
        prepared.append(bytes(raw))
    return chains(rows=prepared,nodes=nodes,**kwargs)

synthetic=SimpleNamespace(source=source,row=prerequisite.row,DECLARATIONS=prerequisite.DECLARATIONS)
NONCE, TOKEN = old.NONCE, old.TOKEN
host = old.host


def identity():
    result = fixtures.provenance()
    result['sources'] = {name:'c'*64 for name in inputs.CONFIG_ROOT_REFERENCE_SOURCE_FILES}
    return result


def projection(slots=3, zero=2, one=0, other=0, first='one', *, empty=0,
               nonempty=None, maximum=36, selected=None, references=0, names=None, part_zero=None, part_nonzero=0):
    nonempty=zero-empty if nonempty is None else nonempty
    selected=nonempty if selected is None else selected
    names=empty if names is None else names
    part_zero=selected-part_nonzero if part_zero is None else part_zero
    return {'schema':1, 'target':'CONFIG', 'recipe_id':policy.RECIPE_ID,
        'recipe_sha256':policy.RECIPE_SHA256, 'data_logical_bytes':301*slots,
        'blob_logical_bytes':max(512,256*(selected+1)), 'candidate_stride':301, 'candidate_slots':slots,
        'first_marker_class':first, 'later_zero_count':zero,
        'later_one_count':one, 'later_other_count':other,
        'validated_zero_count':zero, 'empty_filenames':empty,
        'nonempty_filenames':zero-empty if nonempty is None else nonempty,
        'max_filename_units':maximum,
        'selected_reference_count':selected,'reference_excluded_count':references,'empty_name_excluded_count':names,
        'selected_part_zero_count':part_zero,'selected_part_nonzero_count':part_nonzero,
        'locator_validation':'selected_capacity_bounds_only','partno_validation':'selected_canonical_bcd_0_4095',
        'framing_validation':'not_accepted', 'filename_validation':'zero_marker_bounded_utf16le',
        'root_identity':'not_observed', 'completed_chain_count':selected,
        'total_stored_bytes_read':42+6*selected, 'total_chain_blocks':selected,
        'maximum_chain_hops':1, 'multi_block_chain_count':0, 'zero_payload_block_count':0,
        'chain_validation':'selected_zero_terminated_exact_stored_length',
        'transport_validation':'all_selected_stored_bytes_read', 'compression_validation':'selected_singlepart_ascii_name_rule_raw_deflate_v1',
        'file_identity':'not_observed', 'applied_state':'not_observed',
        'plain_entry_count':0,'deflate_entry_count':selected,'positive_decoded_entry_count':selected,
        'plain_content_bytes':0,'inflated_content_bytes':42+selected,'inflate_call_count':selected,
        'parsed_locator_count':1,'resolved_positive_target_count':1,
        'relation_validation':'fixed_key_guid_reference_resolved_v1'}


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


class ConfigRootReferencePolicyTests(unittest.TestCase):
    def check(self,report,final=False):
        return policy.validate_report(protocol.encode(report),nonce=NONCE,provenance=identity(),final=final)

    def test_core_recipe_disagreement_rejects_before_source_read(self):
        for key,bad in (('identifier','OTHER'),('recipe_sha256','f'*64),
                        ('candidate_stride',302),('filename_offset',2),('filename_width',256),
                        ('binarydata_offset',286),('binarydata_width',7),('partno_offset',294),('partno_width',5)):
            profile=policy.framing.ConfigRootReferenceProfile(synthetic.DECLARATIONS,'0',0)
            object.__setattr__(profile,key,bad)
            data=synthetic.source()
            with mock.patch.object(policy.framing,'ConfigRootReferenceProfile',return_value=profile), \
                 mock.patch.object(policy.framing,'observe_config_root_reference') as observe:
                with self.subTest(key=key),self.assertRaises(OracleError):
                    policy.read_projection(data.read_at,data.size,limits=policy.reader.CatalogLimits())
                observe.assert_not_called()
            self.assertEqual(data.calls,[])

    def test_complete_bound_capture_and_unchanged_native_lifecycle(self):
        report,backend=fixture(); self.check(report)
        self.assertEqual((report['schema'],report['config_root_reference']['schema']),(19,20))
        self.assertEqual((len(report['stages']),len(report['snapshots']),len(report['comparisons'])),(13,11,5))
        self.assertEqual(backend.events.count(('record_metadata','baseline')),1)
        self.assertNotIn('record_metadata',report['config_root_reference'])
        self.assertNotIn(b'Uninterpreted',protocol.encode(report))
        self.assertEqual(report['reader_validation'],policy.VERDICT)
        for key in ('extraction_validation','mapping_validation','layout_validation'):
            self.assertEqual(report[key],'not_run')
        self.assertEqual(report['decompression_validation'],policy.DECOMPRESSION_VERDICT)
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
            value=copy.deepcopy(report); value['config_root_reference'][key]='f'*64
            with self.subTest(key=key),self.assertRaises(OracleError): self.check(value)
        for path in ((),('config_root_reference',),('config_root_reference','reader'),
                     ('config_root_reference','origin'),('config_root_reference','postimage')):
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
        for name in ('CONFIG_CONTENT_DECODE_SOURCE_FILES','CONFIG_BLOB_CHAIN_SOURCE_FILES','CONFIG_ENTRY_REFERENCE_SOURCE_FILES','CONFIG_ZERO_MARKER_FILENAME_SOURCE_FILES','CONFIG_MARKER_CENSUS_SOURCE_FILES','CONFIG_FRAMING_SOURCE_FILES','CONFIG_SOURCE_FILES','PARAMS_SOURCE_FILES','EXTRACTION_SOURCE_FILES','IDENTITY_SOURCE_FILES'):
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
            value=copy.deepcopy(report); value['config_root_reference']['postimage'].update(changes)
            with self.assertRaises(OracleError): self.check(value)
        for key in ('framing_validation','extraction_validation','mapping_validation','layout_validation',
                    'native_byte_equivalence','native_compatibility','decompression_validation'):
            value=copy.deepcopy(report);value[key]='accepted'
            with self.assertRaises(OracleError): self.check(value)
        value=copy.deepcopy(report)
        value['config_root_reference']['reader']['blob_logical_bytes']=value['config_root_reference']['postimage']['bytes']
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
                          record_validation.validate_report,content_policy.validate_report,config_observation.validate_report,strict_policy.validate_report,
                          census_policy.validate_report,filename_policy.validate_report,prerequisite_policy.validate_report,chain_policy.validate_report):
            with self.assertRaises(OracleError): validator(protocol.encode(report),nonce=NONCE,provenance=identity())
        for schema in (4,5,6,7,8,9,10,11,12,13,14,15,16,17,18,20,True):
            value=copy.deepcopy(report); value['schema']=schema
            with self.assertRaises(OracleError): self.check(value)
        for foreign in ('config_content_decode_failed','config_blob_chain_failed','config_entry_reference_failed','config_zero_marker_filename_failed','config_marker_census_failed','config_framing_failed','config_observation_failed','dbnames_identity_failed','params_extraction_failed',
                        'params_observation_failed','record_readback_failed','record_observation_failed',
                        'catalog_comparison_failed'):
            value=copy.deepcopy(report);value['failure_kind']=foreign
            with self.assertRaises(OracleError): self.check(value)

    def test_all_later_lifecycle_failures_and_native_cleanup_discard_capture(self):
        for failed in protocol.STAGES[3:-1]:
            report,_=fixture(failed);self.check(report)
            self.assertIsNone(report['config_root_reference'])
            self.assertEqual(report['observation_validation'],'discarded')
        for cleanup in ((False,True),(True,False),(False,False)):
            report,_=fixture(cleanup=cleanup);self.check(report)
            self.assertIsNone(report['config_root_reference']);self.assertEqual(report['artifacts'],[])
        for gate in ('container_removed','private_staging_removed'):
            report,_=fixture();report['cleanup'].update(container_removed=True,private_staging_removed=True)
            report['cleanup'][gate]=False
            host.fail_report(report,'cleanup_unverified','cleanup',preserve_primary=True)
            self.check(report,final=True);self.assertIsNone(report['config_root_reference'])

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
                self.check(late,final=True);self.assertIsNone(late['config_root_reference'])

    def test_failure_vocabulary_covers_only_finite_exact_core_and_catalog_codes(self):
        for kind,codes in (
            (policy.reader.UnsupportedLayout,('config_table_missing','config_table_ambiguous',
                'config_profile_mismatch','config_empty_data','missing_table_blob_header',
                'config_reserved_slot','config_filename_encoding','config_reference_no_part_zero_witness',
                'config_blob_capacity','config_partno_encoding','config_chain_no_part_zero_witness')),
            (policy.reader.InvalidStructure,('config_record_length','table_blob_header_role','config_filename_length','config_blob_alignment','config_reference_bounds',
                'config_chain_failed_attempt','config_chain_reference','config_chain_cycle','config_chain_used',
                'config_chain_next','config_chain_length')),
            (policy.reader.ResourceLimit,('config_slots','config_record_bytes','config_partno_limit',
                'config_chain_bytes','config_chain_total_bytes','config_chain_hops','config_chain_total_hops','config_chain_image_bytes')),
            (policy.reader.UnsupportedSharing,('config_chain_overlap',))):
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

    def test_no_witness_failure_is_finite_and_rejected_by_every_old_lane(self):
        provenance=identity();report=policy.empty_report(NONCE,provenance)
        backend=Backend(provenance);backend.reader_attempted=True
        error=policy.reader_failure(policy.reader.UnsupportedLayout('config_reference_no_part_zero_witness'))
        backend.observe_record_metadata=mock.Mock(side_effect=error)
        controller=fixtures.stage.Controller(backend,report);backend.controller=controller
        result=controller.run();self.check(result)
        self.assertEqual(result['failure_kind'],'config_root_reference_failed')
        self.assertEqual(result['config_root_reference'],{'schema':20,'status':'failed',
            'category':'unsupported_layout','code':'config_reference_no_part_zero_witness'})
        for validator in (protocol.validate_report,comparison.validate_report,metadata.validate_report,
                          record_validation.validate_report,content_policy.validate_report,config_observation.validate_report,
                          strict_policy.validate_report,census_policy.validate_report,filename_policy.validate_report,prerequisite_policy.validate_report,chain_policy.validate_report):
            with self.assertRaises(OracleError):
                validator(protocol.encode(result),nonce=NONCE,provenance=provenance)

    def test_independent_recipe_private_producer_and_finite_success(self):
        self.assertEqual(policy.RECIPE_SHA256,
            'df07907176f55bb17c3ed086173da9549f05a0d44a63a934faee12e3829467c5')
        expected=policy.framing.ConfigRootReferenceProfile(synthetic.DECLARATIONS,'0',0).recipe()
        self.assertEqual(policy.RECIPE_DESCRIPTION,expected)
        self.assertEqual(policy.RECIPE_SHA256,hashlib.sha256(json.dumps(expected,
            ensure_ascii=True,sort_keys=True,separators=(',',':')).encode()).hexdigest())
        data=source([prerequisite.row(marker=1),prerequisite.row('PRIVATE'),
            prerequisite.row(''),prerequisite.row(raw=b'\0\xd8',units=65535,marker=255)])
        with mock.patch.object(policy.framing,'observe_config_content_decode',side_effect=AssertionError('reread forbidden')):
            observed=policy.read_projection(data.read_at,data.size,limits=policy.reader.CatalogLimits())
        self.assertEqual(observed,projection(6,4,0,1,empty=1))
        wire=protocol.encode(observed)
        for private in (b'PRIVATE',GUID.encode(),GUID.upper().encode(),ROOT_BYTES):
            self.assertNotIn(private,wire)
        self.assertEqual((observed['parsed_locator_count'],observed['resolved_positive_target_count']),(1,1))

    def test_every_projection_field_required_closed_exact_and_type_strict(self):
        base=projection();policy.validate_projection(base)
        for key,old_value in base.items():
            value=dict(base);del value[key]
            with self.subTest(missing=key),self.assertRaises(OracleError):policy.validate_projection(value)
            bads=(True,False,1.0,'1',None,-1,10**20) if type(old_value) is int else (True,None,{},'PRIVATE')
            for bad in bads:
                value=dict(base);value[key]=bad
                with self.subTest(key=key,bad=bad),self.assertRaises(OracleError):policy.validate_projection(value)
        for key in ('filename','filenames','target_key','guid','root_bytes','target_bytes','payload',
                    'payload_sha256','offset','usage','root_length','target_length','entry_lengths'):
            value=dict(base);value[key]='PRIVATE'
            with self.subTest(extra=key),self.assertRaises(OracleError):policy.validate_projection(value)

    def test_narrow_relation_arithmetic_and_all_counter_conservation(self):
        for changes in ({'parsed_locator_count':0},{'parsed_locator_count':2},
                {'resolved_positive_target_count':0},{'resolved_positive_target_count':2},
                {'inflated_content_bytes':43},{'positive_decoded_entry_count':1},
                {'deflate_entry_count':1},{'selected_reference_count':1},
                {'candidate_stride':302},{'candidate_slots':2},{'data_logical_bytes':902},
                {'blob_logical_bytes':513},{'validated_zero_count':3},{'empty_filenames':1},
                {'nonempty_filenames':3},{'selected_part_nonzero_count':1},
                {'later_zero_count':1},{'later_one_count':1},{'later_other_count':1},
                {'reference_excluded_count':1},{'empty_name_excluded_count':1},
                {'completed_chain_count':3},{'selected_part_zero_count':3},
                {'total_chain_blocks':1},{'maximum_chain_hops':2},{'multi_block_chain_count':1},
                {'zero_payload_block_count':1},{'total_stored_bytes_read':501},
                {'inflate_call_count':1},{'plain_entry_count':1},{'plain_content_bytes':1}):
            value=projection();value.update(changes)
            with self.subTest(changes=changes),self.assertRaises(OracleError):policy.validate_projection(value)
        # Count ranges, not a preferred fixture census; two relation participants
        # may coexist with plain, empty decoded, excluded and opaque rows.
        for empty in range(3):
            for nonempty in range(2,6):
                for selected in range(2,nonempty+1):
                    for names in range(empty+1):
                        zero=empty+nonempty
                        value=projection(zero+2,zero,0,1,empty=empty,selected=selected,
                            references=zero-selected-names,names=names)
                        policy.validate_projection(value)
        value=projection(5,4)
        value.update(plain_entry_count=1,deflate_entry_count=3,positive_decoded_entry_count=2,
            plain_content_bytes=1,inflated_content_bytes=44,inflate_call_count=3)
        policy.validate_projection(value)
        for key in ('root_identity','file_identity','applied_state'):
            value=projection();value[key]='observed'
            with self.assertRaises(OracleError):policy.validate_projection(value)

    def test_guid_name_minimum_bound_at_projection_capture_and_report_boundaries(self):
        report,_=fixture()
        for minimum in (0,1,4,35):
            changed=projection();changed['max_filename_units']=minimum
            with self.subTest(boundary='projection',minimum=minimum),self.assertRaises(OracleError):
                policy.validate_projection(changed)
            changed=evidence();changed['reader']['max_filename_units']=minimum
            with self.subTest(boundary='capture',minimum=minimum),self.assertRaises(OracleError):
                policy.bind_capture(changed,report)
            changed=copy.deepcopy(report);changed['config_root_reference']['reader']['max_filename_units']=minimum
            with self.subTest(boundary='report',minimum=minimum),self.assertRaises(OracleError):
                self.check(changed)
        for maximum in (36,128):
            changed=projection();changed['max_filename_units']=maximum
            policy.validate_projection(changed)

    def test_locator_contribution_bounds_use_positive_entries_not_raw_entries(self):
        report,_=fixture()
        def check_all(value, valid):
            capture_input=evidence();capture_input['reader']=value
            capture_input['postimage']['bytes']=snapshots.MAX_FILE_BYTES
            whole=copy.deepcopy(report);whole['config_root_reference']['reader']=value
            whole['config_root_reference']['postimage']['bytes']=snapshots.MAX_FILE_BYTES
            actions=(lambda:policy.validate_projection(value),
                lambda:policy.bind_capture(capture_input,report),lambda:self.check(whole))
            for action in actions:
                if valid:action()
                else:
                    with self.assertRaises(OracleError):action()
        for positive in (2,3,4,4095):
            value=projection(positive+1,positive)
            low=positive+42
            high=min(8*1024*1024,1024+(positive-1)*4*1024*1024)
            for total in (low,high):
                changed=dict(value);changed['inflated_content_bytes']=total
                with self.subTest(positive=positive,total=total):check_all(changed,True)
            for total in (low-1,high+1):
                changed=dict(value);changed['inflated_content_bytes']=total
                with self.subTest(positive=positive,total=total):check_all(changed,False)
        # An empty third raw stream does not increase either bound: V=2, R=3.
        value=projection(4,3);value.update(positive_decoded_entry_count=2,inflated_content_bytes=44)
        check_all(value,True)
        value['inflated_content_bytes']=1024+4*1024*1024
        check_all(value,True)
        value['inflated_content_bytes']+=1
        check_all(value,False)

    def test_new_diagnostics_are_closed_categorized_and_discarded_on_cleanup(self):
        expected={'unsupported_layout':{'config_root_missing_selected_root',
            'config_root_missing_selected_target','config_root_bom','config_root_tag','config_root_empty_target'},
            'structural_rejection':{'config_root_grammar','config_root_guid','config_root_trailing',
                'config_root_input','config_root_failed_attempt'},
            'resource_limit':{'config_root_input_bytes'}}
        kinds={'unsupported_layout':policy.reader.UnsupportedLayout,
            'structural_rejection':policy.reader.InvalidStructure,'resource_limit':policy.reader.ResourceLimit}
        self.assertEqual({code for codes in policy.DIAGNOSTICS.values() for code in codes if code.startswith('config_root_')},
                         set().union(*expected.values()))
        for category,codes in expected.items():
            for code in codes:
                self.assertEqual(policy.reader_failure(kinds[category](code)).code,code)
                for wrong in set(policy.DIAGNOSTICS)-{category}:
                    with self.assertRaises(OracleError):policy.ObservationFailure(wrong,code)
                for old_policy in (content_policy,chain_policy,prerequisite_policy,filename_policy,census_policy,strict_policy):
                    with self.assertRaises(OracleError):old_policy.reader_failure(kinds[category](code))
                provenance=identity();report=policy.empty_report(NONCE,provenance)
                backend=Backend(provenance);backend.reader_attempted=True
                backend.observe_record_metadata=mock.Mock(side_effect=policy.ObservationFailure(category,code))
                controller=fixtures.stage.Controller(backend,report);backend.controller=controller
                result=controller.run();self.check(result)
                self.assertEqual(result['config_root_reference'],{'schema':20,'status':'failed','category':category,'code':code})
                for gate in result['cleanup']:
                    bad=copy.deepcopy(result);bad['cleanup'].update({k:True for k in bad['cleanup']});bad['cleanup'][gate]=False
                    policy.discard_capture(bad,final=True)
                    self.assertIsNone(bad['config_root_reference'])
        for error in (ValueError('PRIVATE'),policy.reader.InvalidStructure('PRIVATE'),
                      type('Subclass',(policy.reader.InvalidStructure,),{})('config_root_guid')):
            with self.assertRaises(OracleError):policy.reader_failure(error)

    def test_producer_identity_and_immutable_claims_are_rechecked(self):
        data=source()
        result=policy.framing.observe_config_root_reference(data.read_at,data.size,
            profile=policy.framing.ConfigRootReferenceProfile(synthetic.DECLARATIONS,'0',0))
        for key,bad in (('recipe_id','OTHER'),('recipe_sha256','f'*64),('parsed_locator_count',0),
                ('resolved_positive_target_count',True),('relation_validation','header_only'),
                ('root_identity','observed'),('native_acceptance','accepted'),
                ('capability','experimental_config_content_decode'),('file_identity','observed'),
                ('applied_state','observed'),('candidate_stride',302)):
            changed=copy.copy(result);object.__setattr__(changed,key,bad)
            with mock.patch.object(policy.framing,'observe_config_root_reference',return_value=changed):
                with self.subTest(key=key),self.assertRaises(OracleError):
                    policy.read_projection(data.read_at,data.size,limits=policy.reader.CatalogLimits())

if __name__=='__main__': unittest.main()
