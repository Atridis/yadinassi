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
import config_blob_chain as policy
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

def source(rows=None, **kwargs):
    # Independent healthy table-BLOB fixture: one positive byte per selected
    # reference, distinct logical blocks sharing the same physical backing page.
    if rows is None: rows=[prerequisite.row(marker=1),prerequisite.row('private_filename_Ω')]
    selected=0; prepared=[]
    for original in rows:
        raw=bytearray(original)
        if (raw[0] == 0 and 0 < int.from_bytes(raw[1:3],'little') <= 128
                and int.from_bytes(raw[287:291],'little') > 0
                and int.from_bytes(raw[291:295],'little') > 0):
            selected+=1; raw[287:291]=selected.to_bytes(4,'little')
        prepared.append(bytes(raw))
    kwargs.setdefault('blob_length',max(512,256*(selected+1)))
    result=prerequisite.source(prepared,**kwargs)
    for block in range(1,selected+1):
        at=block*256; result.page(result.blob_page)[at:at+7]=bytes(4)+b'\x01\0\xa7'
    return result


synthetic=SimpleNamespace(source=source,row=prerequisite.row,DECLARATIONS=prerequisite.DECLARATIONS)
NONCE, TOKEN = old.NONCE, old.TOKEN
host = old.host


def identity():
    result = fixtures.provenance()
    result['sources'] = {name:'c'*64 for name in inputs.CONFIG_BLOB_CHAIN_SOURCE_FILES}
    return result


def projection(slots=2, zero=1, one=0, other=0, first='one', *, empty=0,
               nonempty=None, maximum=1, selected=None, references=0, names=None, part_zero=None, part_nonzero=0):
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
        'total_stored_bytes_read':selected, 'total_chain_blocks':selected,
        'maximum_chain_hops':1, 'multi_block_chain_count':0, 'zero_payload_block_count':0,
        'chain_validation':'selected_zero_terminated_exact_stored_length',
        'transport_validation':'all_selected_stored_bytes_read', 'compression_validation':'not_classified',
        'file_identity':'not_observed', 'applied_state':'not_observed'}


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


class ConfigBlobChainPolicyTests(unittest.TestCase):
    def check(self,report,final=False):
        return policy.validate_report(protocol.encode(report),nonce=NONCE,provenance=identity(),final=final)

    def test_independent_recipe_and_real_reader_only_finite_output(self):
        self.assertEqual(policy.RECIPE_SHA256,'e4d826310b61731e380156aaf2dc81e1a1bb342212f5a5f7596b30a51f1e6137')
        expected=policy.framing.ConfigBlobChainProfile(synthetic.DECLARATIONS,'0',0).recipe()
        self.assertEqual(policy.RECIPE_DESCRIPTION,expected)
        self.assertEqual(policy.RECIPE_SHA256,hashlib.sha256(json.dumps(expected,ensure_ascii=True,sort_keys=True,separators=(',',':')).encode()).hexdigest())
        data=synthetic.source([synthetic.row(marker=1),synthetic.row('PRIVATE'),
            synthetic.row(''),synthetic.row(raw=b'\0\xd8',units=65535,marker=1),
            synthetic.row(raw=b'\0\xdc',units=65535,marker=255)])
        result=policy.read_projection(data.read_at,data.size,limits=policy.reader.CatalogLimits())
        self.assertEqual(result,projection(slots=5,zero=2,one=1,other=1,empty=1,maximum=7))
        self.assertNotIn(b'PRIVATE',protocol.encode(result))
        self.assertNotIn('usage',result)
        self.assertNotIn((data.blob_page*8192,8192),data.calls)
        self.assertFalse({'active_slots','free_slots','filename','filename_sha256','index','offset'} & set(result))

    def test_chain_conservation_and_nonvacuous_witnesses(self):
        # Every small positive composition plus optional zero-used blocks must
        # satisfy the independent summary constraints; no preferred chain count.
        import itertools
        for hops in itertools.product(range(1,5),repeat=3):
            value=projection(4,3)
            h=sum(hops);q=sum(n>1 for n in hops);m=max(hops)
            value.update(blob_logical_bytes=256*(h+1),total_chain_blocks=h,
                maximum_chain_hops=m,multi_block_chain_count=q)
            for z in range(h-3+1):
                for d in (h-z,250*(h-z)):
                    value.update(zero_payload_block_count=z,total_stored_bytes_read=d)
                    policy.validate_projection(value)
        mutations=({'completed_chain_count':0},{'completed_chain_count':2},
            {'total_stored_bytes_read':0},{'total_stored_bytes_read':251},
            {'total_stored_bytes_read':4*1024*1024+1},{'total_chain_blocks':0},
            {'total_chain_blocks':2},{'total_chain_blocks':32769},
            {'maximum_chain_hops':0},{'maximum_chain_hops':2},{'maximum_chain_hops':8193},
            {'multi_block_chain_count':1},{'multi_block_chain_count':2},
            {'zero_payload_block_count':1},{'zero_payload_block_count':32769})
        for changes in mutations:
            value=projection();value.update(changes)
            with self.subTest(changes=changes),self.assertRaises(OracleError):policy.validate_projection(value)
        base=projection(4,3);base.update(blob_logical_bytes=4096,total_chain_blocks=8,
            maximum_chain_hops=4,multi_block_chain_count=2,total_stored_bytes_read=7,zero_payload_block_count=1)
        policy.validate_projection(base)
        for changes in ({'total_chain_blocks':6},{'total_chain_blocks':10},
                        {'maximum_chain_hops':1},{'zero_payload_block_count':6},
                        {'total_stored_bytes_read':6},{'total_stored_bytes_read':1751}):
            value=copy.deepcopy(base);value.update(changes)
            with self.subTest(changes=changes),self.assertRaises(OracleError):policy.validate_projection(value)

    def test_core_recipe_disagreement_rejects_before_source_read(self):
        for key,bad in (('identifier','OTHER'),('recipe_sha256','f'*64),
                        ('candidate_stride',302),('filename_offset',2),('filename_width',256),
                        ('binarydata_offset',286),('binarydata_width',7),('partno_offset',294),('partno_width',5)):
            profile=policy.framing.ConfigBlobChainProfile(synthetic.DECLARATIONS,'0',0)
            object.__setattr__(profile,key,bad)
            data=synthetic.source()
            with mock.patch.object(policy.framing,'ConfigBlobChainProfile',return_value=profile), \
                 mock.patch.object(policy.framing,'observe_config_blob_chains') as observe:
                with self.subTest(key=key),self.assertRaises(OracleError):
                    policy.read_projection(data.read_at,data.size,limits=policy.reader.CatalogLimits())
                observe.assert_not_called()
            self.assertEqual(data.calls,[])

    def test_core_returned_identity_or_claim_disagreement_rejects(self):
        data=synthetic.source()
        result=policy.framing.observe_config_blob_chains(data.read_at,data.size,
            profile=policy.framing.ConfigBlobChainProfile(synthetic.DECLARATIONS,'0',0))
        for change in ({'recipe_id':'OTHER'},{'recipe_sha256':'f'*64},{'candidate_slots':3},
                       {'first_marker_class':'free'},{'validated_zero_count':0},
                       {'nonempty_filenames':0},{'max_filename_units':129}):
            with mock.patch.object(policy.framing,'observe_config_blob_chains',return_value=replace(result,**change)):
                with self.assertRaises(OracleError):
                    policy.read_projection(data.read_at,data.size,limits=policy.reader.CatalogLimits())
        for key,value in (('root_identity','observed'),('native_acceptance','accepted'),('capability','experimental_config_entry_reference'),
                          ('chain_validation','all_files_valid'),('transport_validation','partial_success'),
                          ('compression_validation','plain'),('file_identity','observed'),('applied_state','observed'),
                          ('framing_validation','source_hypothesis_satisfied'),
                          ('filename_validation','bounded_utf16le_validated'),('candidate_stride',302),
                          ('locator_validation','chain_validated'),('partno_validation','native_equivalent')):
            changed=copy.copy(result); object.__setattr__(changed,key,value)
            with mock.patch.object(policy.framing,'observe_config_blob_chains',return_value=changed):
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

    def test_selected_partition_and_positive_witness_mutations(self):
        value=projection(8,7,0,0,empty=2,selected=3,references=3,names=1,part_zero=2,part_nonzero=1)
        self.assertEqual(policy.validate_projection(value),value)
        for changes in ({'selected_reference_count':0},{'selected_reference_count':4096},
                {'reference_excluded_count':2},{'empty_name_excluded_count':2},
                {'selected_part_zero_count':0},{'selected_part_zero_count':3},
                {'selected_part_nonzero_count':0},{'selected_part_nonzero_count':4096},
                {'empty_filenames':0,'nonempty_filenames':7},
                {'empty_filenames':5,'nonempty_filenames':2},
                {'blob_logical_bytes':0},{'blob_logical_bytes':256},{'blob_logical_bytes':513}):
            changed=copy.deepcopy(value);changed.update(changes)
            with self.subTest(changes=changes),self.assertRaises(OracleError):policy.validate_projection(changed)
        # Independent low-cardinality enumeration: all feasible cross-partitions
        # are admitted, with no preferred source-specific selected count.
        for empty in range(3):
            for nonempty in range(1,4):
                for selected in range(1,nonempty+1):
                    for names in range(empty+1):
                        for part_zero in range(1,selected+1):
                            zero=empty+nonempty
                            value=projection(1+zero,zero,0,0,empty=empty,
                                selected=selected,references=zero-selected-names,names=names,
                                part_zero=part_zero,part_nonzero=selected-part_zero)
                            policy.validate_projection(value)

    def test_every_projection_field_required_closed_and_exact_primitives(self):
        for key in projection():
            value=projection();del value[key]
            with self.subTest(missing=key),self.assertRaises(OracleError): policy.validate_projection(value)
        for forbidden in ('payload','payload_sha256','block_numbers','stored_bytes','chain_lengths','filename','filenames','filename_sha256','free_slots','active_slots','offset','marker_bytes','free_chain','pointers','lengths','part_numbers','selected_indices'):
            value=projection();value[forbidden]='PRIVATE'
            with self.assertRaises(OracleError): policy.validate_projection(value)
        for key in ('candidate_slots','candidate_stride','later_zero_count','later_one_count',
                    'later_other_count','data_logical_bytes','blob_logical_bytes','schema',
                    'validated_zero_count','empty_filenames','nonempty_filenames','max_filename_units',
                    'selected_reference_count','reference_excluded_count','empty_name_excluded_count',
                    'selected_part_zero_count','selected_part_nonzero_count',
                    'completed_chain_count','total_stored_bytes_read','total_chain_blocks','maximum_chain_hops',
                    'multi_block_chain_count','zero_payload_block_count'):
            for replacement in (True,False,1.0,'1',None):
                value=projection();value[key]=replacement
                with self.subTest(key=key,replacement=replacement),self.assertRaises(OracleError):
                    policy.validate_projection(value)
        for key in ('target','recipe_id','recipe_sha256','first_marker_class',
                    'framing_validation','filename_validation','root_identity','locator_validation','partno_validation',
                    'chain_validation','transport_validation','compression_validation','file_identity','applied_state'):
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
        self.assertEqual((report['schema'],report['config_blob_chain']['schema']),(15,16))
        self.assertEqual((len(report['stages']),len(report['snapshots']),len(report['comparisons'])),(13,11,5))
        self.assertEqual(backend.events.count(('record_metadata','baseline')),1)
        self.assertNotIn('record_metadata',report['config_blob_chain'])
        self.assertNotIn(b'Uninterpreted',protocol.encode(report))
        self.assertEqual(report['reader_validation'],policy.VERDICT)
        for key in ('extraction_validation','mapping_validation','layout_validation','decompression_validation'):
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
            value=copy.deepcopy(report); value['config_blob_chain'][key]='f'*64
            with self.subTest(key=key),self.assertRaises(OracleError): self.check(value)
        for path in ((),('config_blob_chain',),('config_blob_chain','reader'),
                     ('config_blob_chain','origin'),('config_blob_chain','postimage')):
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
        for name in ('CONFIG_ENTRY_REFERENCE_SOURCE_FILES','CONFIG_ZERO_MARKER_FILENAME_SOURCE_FILES','CONFIG_MARKER_CENSUS_SOURCE_FILES','CONFIG_FRAMING_SOURCE_FILES','CONFIG_SOURCE_FILES','PARAMS_SOURCE_FILES','EXTRACTION_SOURCE_FILES','IDENTITY_SOURCE_FILES'):
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
            value=copy.deepcopy(report); value['config_blob_chain']['postimage'].update(changes)
            with self.assertRaises(OracleError): self.check(value)
        for key in ('framing_validation','extraction_validation','mapping_validation','layout_validation',
                    'native_byte_equivalence','native_compatibility','decompression_validation'):
            value=copy.deepcopy(report);value[key]='accepted'
            with self.assertRaises(OracleError): self.check(value)
        value=copy.deepcopy(report)
        value['config_blob_chain']['reader']['blob_logical_bytes']=value['config_blob_chain']['postimage']['bytes']
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
                          census_policy.validate_report,filename_policy.validate_report,prerequisite_policy.validate_report):
            with self.assertRaises(OracleError): validator(protocol.encode(report),nonce=NONCE,provenance=identity())
        for schema in (4,5,6,7,8,9,10,11,12,13,14,True):
            value=copy.deepcopy(report); value['schema']=schema
            with self.assertRaises(OracleError): self.check(value)
        for foreign in ('config_entry_reference_failed','config_zero_marker_filename_failed','config_marker_census_failed','config_framing_failed','config_observation_failed','dbnames_identity_failed','params_extraction_failed',
                        'params_observation_failed','record_readback_failed','record_observation_failed',
                        'catalog_comparison_failed'):
            value=copy.deepcopy(report);value['failure_kind']=foreign
            with self.assertRaises(OracleError): self.check(value)

    def test_all_later_lifecycle_failures_and_native_cleanup_discard_capture(self):
        for failed in protocol.STAGES[3:-1]:
            report,_=fixture(failed);self.check(report)
            self.assertIsNone(report['config_blob_chain'])
            self.assertEqual(report['observation_validation'],'discarded')
        for cleanup in ((False,True),(True,False),(False,False)):
            report,_=fixture(cleanup=cleanup);self.check(report)
            self.assertIsNone(report['config_blob_chain']);self.assertEqual(report['artifacts'],[])
        for gate in ('container_removed','private_staging_removed'):
            report,_=fixture();report['cleanup'].update(container_removed=True,private_staging_removed=True)
            report['cleanup'][gate]=False
            host.fail_report(report,'cleanup_unverified','cleanup',preserve_primary=True)
            self.check(report,final=True);self.assertIsNone(report['config_blob_chain'])

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
                self.check(late,final=True);self.assertIsNone(late['config_blob_chain'])

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

    def test_actual_reader_requires_selected_part_zero_without_guessing_marker_counts(self):
        for rows in ([synthetic.row(marker=1)],
                     [synthetic.row(marker=1),synthetic.row('')],
                     [synthetic.row(marker=1),synthetic.row('PRIVATE',marker=255)]):
            value=synthetic.source(rows)
            with self.assertRaises(policy.reader.UnsupportedLayout) as error:
                policy.read_projection(value.read_at,value.size,limits=policy.reader.CatalogLimits())
            self.assertEqual(error.exception.code,'config_reference_no_part_zero_witness')
            self.assertEqual(policy.reader_failure(error.exception).code,'config_reference_no_part_zero_witness')

    def test_zero_marker_structural_strings_are_not_file_identities(self):
        # Empty, NUL and BOM are structural strings, never normalized identities.
        value=synthetic.source([synthetic.row(marker=1),synthetic.row(''),
                               synthetic.row('\0'),synthetic.row('\ufeff')])
        actual=policy.read_projection(value.read_at,value.size,limits=policy.reader.CatalogLimits())
        self.assertEqual(actual,projection(4,3,0,0,empty=1,maximum=1))
        self.assertEqual(actual['root_identity'],'not_observed')

    def test_no_witness_failure_is_finite_and_rejected_by_every_old_lane(self):
        provenance=identity();report=policy.empty_report(NONCE,provenance)
        backend=Backend(provenance);backend.reader_attempted=True
        error=policy.reader_failure(policy.reader.UnsupportedLayout('config_reference_no_part_zero_witness'))
        backend.observe_record_metadata=mock.Mock(side_effect=error)
        controller=fixtures.stage.Controller(backend,report);backend.controller=controller
        result=controller.run();self.check(result)
        self.assertEqual(result['failure_kind'],'config_blob_chain_failed')
        self.assertEqual(result['config_blob_chain'],{'schema':16,'status':'failed',
            'category':'unsupported_layout','code':'config_reference_no_part_zero_witness'})
        for validator in (protocol.validate_report,comparison.validate_report,metadata.validate_report,
                          record_validation.validate_report,config_observation.validate_report,
                          strict_policy.validate_report,census_policy.validate_report,filename_policy.validate_report,prerequisite_policy.validate_report):
            with self.assertRaises(OracleError):
                validator(protocol.encode(result),nonce=NONCE,provenance=provenance)


if __name__=='__main__': unittest.main()
