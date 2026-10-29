"""Independent synthetic policy facts; no native acceptance or emitted raw values."""
import copy
import dataclasses
from decimal import Decimal
import unittest
import test_catalog_binding_integration as integrated
import test_native_1c_db_oracle_record_observation as old
import test_native_1c_db_oracle_catalog_attribute_binding as attrs
import test_native_1c_db_oracle_stage as lifecycle_fixture
import catalog_readonly_binding as p
import catalog_binding_reader as reader
import inputs
import protocol

NONCE=old.NONCE
DECLARATIONS=(('_IDRREF','B',0,16,0,'CS'),('_VERSION','RV',0,0,0,'CS'),
 ('_MARKED','L',0,0,0,'CS'),('_PREDEFINEDID','B',0,16,0,'CS'),('_CODE','NVC',0,2,0,'CI'),
 ('_FLD62','NVC',0,32,0,'CI'),('_FLD741','N',0,9,2,'CS'))


def provenance():
    value=old.identity();value['sources']={key:'c'*64 for key in inputs.CATALOG_BINDING_SOURCE_FILES};return value


def evidence():
    result=old.evidence();marker=result['marker']
    marker['record_metadata']={'schema':1,'target':p.metadata.TARGET,'table':{
        'storage_name':'_Reference19','logical_name':p.metadata.TARGET,'metadata_name':p.metadata.TARGET,
        'fields':[{'storage_name':decl[0],'logical_name':logical,'metadata_name':path,'type_text':''}
                  for decl,(_,logical,path) in zip(DECLARATIONS,p.ROLE_LABELS)]}}
    result['reader']={'schema':1,'target':p.metadata.TARGET,'table':{
        'name':'_Reference19','record_lock_token':'0',
        'fields':[dict(zip(('name','type_token','nullability','length','precision','case_token'),decl)) for decl in DECLARATIONS]}}
    result['identity_manifest']=attrs.manifest()
    return result


def result():
    source=integrated.source()
    return reader.read_catalog_binding(source.read_at,source.size,catalog_name='NativeOracleItems')


def fixture():
    report,_=lifecycle_fixture.fixture_report()
    empty=p.empty_report(NONCE,provenance())
    report.update({key:empty[key] for key in p.EXTRA_KEYS|{'schema','lane','provenance'}})
    def resize(value):
        if isinstance(value,dict):return {k:resize(v) for k,v in value.items()}
        if isinstance(value,list):return [resize(v) for v in value]
        return 65536 if type(value) is int and value==12288 else value
    report=resize(report)
    for snapshot in report['snapshots']:
        if isinstance(snapshot['physical']['header'],dict):
            snapshot['physical']['header'].update(page_size=8192,page_count=8)
    ev=evidence();ev['origin']['bytes']=65536
    capture,oracle,selector=p.begin_capture(ev,report,reader)
    for i,identifier in enumerate(p.TARGETS):
        snapshot=next(x for x in report['snapshots'] if x['id']==identifier)
        ev={'snapshot':identifier,'token':str(i+1)*32,'origin':{k:snapshot['physical'][k] for k in ('bytes','sha256')},
            'postimage':{'bytes':64*8192,'sha256':'f'*64},'logical':snapshot['logical']}
        framing='empty_zero_length' if identifier=='baseline' else 'reserved_and_active'
        capture['states'].append(p.bind_state(identifier,ev,report,framing,framing))
    report.update(record_readback=capture,reader_validation=p.metadata.VERDICT,
        metadata_validation=p.metadata.METADATA_VERDICT,mapping_validation=p.MAPPING_VERDICT,
        layout_validation=p.LAYOUT_VERDICT,record_validation=p.VERDICT)
    report['cleanup'].update(container_removed=True,private_staging_removed=True);report['accepted']=True
    return report,oracle


class CatalogReadonlyPolicyTests(unittest.TestCase):
    def test_finished_byte_reader_then_independent_oracle(self):
        report,oracle=fixture();actual=result()
        self.assertEqual(p.compare_values(actual,'created',oracle,reader),'reserved_and_active')
        p.validate_report(protocol.encode(report),nonce=NONCE,provenance=provenance(),final=True)

    def test_public_projection_has_no_private_names_uuids_values(self):
        report,_=fixture();raw=protocol.encode(report['record_readback'])
        for secret in ('Payload','Amount','NativeOracleItems','_Reference19','_FLD62','alpha',*attrs.KEYS):
            self.assertNotIn(secret.encode(),raw)
        self.assertLess(len(raw),12288);self.assertLess(len(protocol.encode(report)),32768)

    def test_rows_and_derived_binding_have_distinct_state_verdicts(self):
        report,_=fixture()
        for state in report['record_readback']['states']:
            self.assertEqual(state['binding_verdict'],p.MAPPING_VERDICT)
            self.assertEqual(state['verdict'],p.STATE_VERDICT)
        for key in ('binding_verdict','verdict'):
            changed=copy.deepcopy(report);changed['record_readback']['states'][0][key]='not_run'
            with self.assertRaises(Exception):p.validate_report(protocol.encode(changed),nonce=NONCE,provenance=provenance(),final=True)

    def test_every_config_attribute_fact_matters(self):
        _,oracle=fixture();actual=result();rows=actual.config_observation.private_fields
        for name,value in (('metadata_uuid','cccccccc-cccc-cccc-cccc-cccccccccccc'),('name','Wrong'),('type_token','N'),('qualifiers',(7,1))):
            key,identity,attributes=rows[0]
            changed=dataclasses.replace(attributes,attributes=(dataclasses.replace(attributes.attributes[0],**{name:value}),*attributes.attributes[1:]))
            observation=dataclasses.replace(actual.config_observation,private_fields=((key,identity,changed),*rows[1:]))
            with self.subTest(name=name),self.assertRaises(p.ReadbackFailure):
                p.compare_values(dataclasses.replace(actual,config_observation=observation),'created',oracle,reader)

    def test_native_and_physical_oracle_mismatches_do_not_select_reader(self):
        _,oracle=fixture();actual=result()
        for change in ('table','type','name','role'):
            measured=copy.deepcopy(oracle.metadata)
            if change=='table':measured['reader']['table']['name']='_Reference20'
            elif change=='type':measured['reader']['table']['fields'][5]['length']=31
            elif change=='name':measured['reader']['table']['fields'][5]['name']='_FLD9'
            else:measured['native']['table']['fields'][5]['logical_name']='Wrong'
            with self.subTest(change=change),self.assertRaises((p.ReadbackFailure,p.metadata.ObservationFailure)):
                p.compare_values(actual,'created',dataclasses.replace(oracle,metadata=measured),reader)

    def test_wrong_values_and_count_are_not_binding_success(self):
        _,oracle=fixture();actual=result()
        with self.assertRaises(p.ReadbackFailure):p.compare_values(actual,'baseline',oracle,reader)
        row=actual.records.rows[0];fields=list(row.fields);fields[5]=dataclasses.replace(fields[5],value='wrong')
        changed=dataclasses.replace(actual,records=dataclasses.replace(actual.records,rows=(dataclasses.replace(row,fields=tuple(fields)),)))
        with self.assertRaises(p.ReadbackFailure):p.compare_values(changed,'created',oracle,reader)

    def test_decimal_scale_is_checked(self):
        _,oracle=fixture();actual=result();row=actual.records.rows[0];fields=list(row.fields)
        fields[6]=dataclasses.replace(fields[6],value=Decimal('1.250'))
        changed=dataclasses.replace(actual,records=dataclasses.replace(actual.records,rows=(dataclasses.replace(row,fields=tuple(fields)),)))
        with self.assertRaises(p.ReadbackFailure):p.compare_values(changed,'created',oracle,reader)

    def test_report_identity_inventory_and_cleanup_are_closed(self):
        report,_=fixture()
        changes=(lambda x:x.update(schema=6),lambda x:x.update(lane='owned_record_readback_v1'),
            lambda x:x['cleanup'].update(raw_files_removed=False),
            lambda x:x['record_readback'].update(attribute_count=3),
            lambda x:x['record_readback']['audit'].update(source_manifest_sha256='d'*64),
            lambda x:x['record_readback'].update(identity_manifest_sha256='bad'),
            lambda x:x['record_readback'].update(private=[]))
        for change in changes:
            changed=copy.deepcopy(report);change(changed)
            with self.assertRaises(Exception):p.validate_report(protocol.encode(changed),nonce=NONCE,provenance=provenance(),final=True)
        foreign=provenance();foreign['sources'].pop(next(iter(foreign['sources'])))
        with self.assertRaises(Exception):p.validate_report(protocol.encode(report),nonce=NONCE,provenance=foreign,final=True)

    def test_later_failure_discards_all_success(self):
        report,_=fixture();report.update(status='failed',failure_kind='unexpected_failure',failed_stage='delete',accepted=False)
        p.discard_capture(report,final=True)
        self.assertIsNone(report['record_readback'])
        for key in ('mapping_validation','layout_validation','record_validation'):
            self.assertEqual(report[key],'discarded')

    def test_failure_capture_requires_verified_cleanup(self):
        report,_=fixture();report.update(status='failed',failure_kind=p.FAILURE_KIND,failed_stage='update',accepted=False)
        error=p.ReadbackFailure('record_mismatch','mapped_values')
        p.discard_capture(report,error,final=True)
        self.assertEqual(report['record_readback']['schema'],38)
        report['cleanup']['raw_files_removed']=False;p.discard_capture(report,error,final=True)
        self.assertIsNone(report['record_readback'])

    def test_finite_coordinator_and_decimal_failures_classified(self):
        for kind,category,codes in (
            (p.filedb_catalog.UnsupportedLayout,'unsupported_layout',('binding_catalog_selector','binding_catalog_missing','binding_catalog_ambiguous','binding_dbnames_profile','binding_metadata_profile','decimal_padding')),
            (p.filedb_catalog.InvalidStructure,'structural_rejection',('binding_limits','binding_reader_sources','binding_catalog_identity','binding_dbnames_invalid','binding_graph_state')),
            (p.filedb_catalog.ResourceLimit,'resource_limit',('binding_dbnames_limits',))):
            for code in codes:
                with self.subTest(code=code):
                    error=p.reader_failure(kind(code))
                    self.assertIs(type(error),p.ReadbackFailure)
                    self.assertEqual((error.category,error.code),(category,code))

    def test_unknown_public_stage_and_failure_kind_fail_closed(self):
        report,_=fixture()
        for field,value in (('failed_stage','future_unknown_stage'),('failure_kind','future_unknown_failure')):
            changed=copy.deepcopy(report);changed[field]=value
            with self.assertRaises(Exception):p.validate_report(protocol.encode(changed),nonce=NONCE,provenance=provenance(),final=True)
