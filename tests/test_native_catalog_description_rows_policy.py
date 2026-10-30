"""Synthetic source-bound typed rows parity; not fresh native execution."""
import copy
from dataclasses import replace
import hashlib
import json
from pathlib import Path
import sys
import unittest
from uuid import UUID
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'scripts/native_1c_db_oracle'),str(ROOT/'yadinassi/storage')]
import catalog_description_rows as p
import catalog_description_measurement as measurement
import catalog_description_physical as physical_reader
import inputs
import protocol
from snapshots import OracleError
import test_native_1c_db_oracle_stage as lifecycle
import test_native_catalog_description_physical as physical

NONCE='a'*32
NATIVE_UUID='52525252-5252-5252-5252-525252525252'

def provenance():
    value=lifecycle.provenance();value['actual_version']=protocol.VERSION
    value['sources']={name:'c'*64 for name in inputs.CATALOG_DESCRIPTION_ROWS_SOURCE_FILES}
    return value

def witness(case='description8',nonce=NONCE,token='1'*32,value='',present=False,actual_uuid=None):
    raw=json.dumps(dict(schema=3,nonce=nonce,token=token,case=case,operation='observe',
        present=present,actual_description=value,actual_uuid=(NATIVE_UUID if present else '') if actual_uuid is None else actual_uuid),ensure_ascii=True,separators=(',',':')).encode()
    return measurement.validate_witness(raw,nonce=nonce,token=token,case=case,operation='observe',rows=True)

def evidence(report,identifier,index):
    snapshot=next(x for x in report['snapshots'] if x['id']==identifier)
    return dict(snapshot=identifier,token=str(index+1)*32,origin={k:snapshot['physical'][k] for k in ('bytes','sha256')},postimage={'bytes':65536,'sha256':'f'*64},logical=copy.deepcopy(snapshot['logical']))

def observation(length,text,payload=32):
    value=physical.source(length,text,payload)
    return physical_reader.read_description_rows(value.read_at,value.size,catalog_name='NativeOracleItems')

def fixture(case='description8',nonce=NONCE,*,final=True,empty=False):
    report,_=lifecycle.fixture_report();base=p.empty_report(nonce,provenance(),description_case=case)
    for k in ('schema','lane','nonce','provenance',*p.EXTRA_KEYS):report[k]=base[k]
    length,created,updated=measurement.CASES[case]
    for i,identifier in enumerate(p.TARGETS):
        ev=evidence(report,identifier,i);value='' if i==0 or empty else created if i==1 else updated
        w=witness(case,nonce,ev['token'],value,i!=0)
        ob,typed=(None,None) if i==0 else observation(length,value,64 if identifier=='applied' else 32)
        report['description_measurement']['states'].append(p.bind_state(identifier,ev,ob,w,report,typed_uuid=typed))
    if final:report['cleanup'].update(container_removed=True,private_staging_removed=True);report['accepted']=True
    return report

def validate(report,final=True):
    return p.validate_report(protocol.encode(report),nonce=report['nonce'],provenance=provenance(),final=final)

class DescriptionRowsPolicyTests(unittest.TestCase):
    def test_four_actual_public_api_states_and_closed_inventory(self):
        self.assertEqual(len(inputs.CATALOG_DESCRIPTION_ROWS_SOURCE_FILES),42)
        self.assertNotIn('scripts/native_1c_db_oracle/catalog_description_policy.py',provenance()['sources'])
        self.assertEqual((p.SCHEMA,p.CAPTURE_SCHEMA,p.AGGREGATE_SCHEMA),(53,54,55))
        self.assertEqual(p.STAGES['applied'],'apply_cf')
        for case in p.CASES:
            r=fixture(case);validate(r);states=r['description_measurement']['states']
            self.assertEqual([s['snapshot'] for s in states],list(p.TARGETS))
            self.assertEqual([s['typed_uuid_verdict'] for s in states],['not_applicable','matches','matches','matches'])
            self.assertEqual([s['comparison']['physical']['payload_length'] for s in states[1:]],[32,32,64])
            self.assertEqual(states[3]['comparison']['physical']['record_size']-states[2]['comparison']['physical']['record_size'],64)
            raw=protocol.encode(r['description_measurement'])
            for secret in (NATIVE_UUID,'actual_uuid','actual_description','NativeOracleItems',*measurement.CASES[case][1:]):self.assertNotIn(secret.encode(),raw)
        validate(fixture(final=False),False)

    def test_present_empty_distinct_from_absent(self):
        r=fixture(empty=True);validate(r)
        self.assertFalse(r['description_measurement']['states'][0]['witness']['present'])
        for s in r['description_measurement']['states'][1:]:
            self.assertTrue(s['witness']['present']);self.assertEqual(s['comparison']['native_utf16_units'],0)

    def test_bind_returns_without_append_and_rejects_old_private_schema(self):
        r=fixture();r['description_measurement']['states']=[];ev=evidence(r,'baseline',0);w=witness(token=ev['token'])
        self.assertEqual(p.bind_state('baseline',ev,None,w,r)['typed_uuid_verdict'],'not_applicable');self.assertEqual(r['description_measurement']['states'],[])
        for change in (dict(schema=2),dict(schema=True),dict(actual_uuid=NATIVE_UUID),dict(nonce='e'*32),dict(token='e'*32),dict(case='description17'),dict(operation='create'),dict(utf16_units=True),dict(present=True)):
            with self.subTest(change=change),self.assertRaises((OracleError,ValueError)):p.bind_state('baseline',ev,None,replace(w,**change),r)
        with self.assertRaises(OracleError):p.bind_state('baseline',ev,None,w,r,typed_uuid=UUID(NATIVE_UUID))

    def test_actual_typed_uuid_not_seed_or_string_and_description_mismatch_fail(self):
        r=fixture();r['description_measurement']['states']=r['description_measurement']['states'][:1]
        ev=evidence(r,'created',1);text=measurement.CASES['description8'][1];w=witness(token=ev['token'],value=text,present=True);ob,typed=observation(8,text)
        self.assertEqual(typed,UUID(NATIVE_UUID))
        for wrong in (None,NATIVE_UUID,UUID(int=0),UUID(int=1)):
            with self.subTest(wrong=wrong),self.assertRaises(OracleError):p.bind_state('created',ev,ob,w,r,typed_uuid=wrong)
        for change in (dict(actual_uuid='bad'),dict(actual_uuid=str(UUID(int=0))),dict(actual_uuid='{'+NATIVE_UUID+'}'),dict(actual_uuid=' '+NATIVE_UUID),dict(actual_uuid='AAAAAAAA-AAAA-AAAA-AAAA-AAAAAAAAAAAA'),dict(actual_description='other',utf16_units=5,scalar_count=5,trailing_spaces=0)):
            with self.subTest(change=change),self.assertRaises((OracleError,ValueError)):p.bind_state('created',ev,ob,replace(w,**change),r,typed_uuid=typed)
        unresolved=replace(ob,status='layout_unresolved',records=None,placements=(),record_size=0)
        with self.assertRaises(OracleError):p.bind_state('created',ev,unresolved,w,r,typed_uuid=typed)
        wrong,typed=observation(17,text)
        with self.assertRaises(OracleError):p.bind_state('created',ev,wrong,w,r,typed_uuid=typed)

    def test_applied_qualifier_and_stale_identity_order_fail_closed(self):
        r=fixture();r['description_measurement']['states']=r['description_measurement']['states'][:3]
        ev=evidence(r,'applied',3);text=measurement.CASES['description8'][2];w=witness(token=ev['token'],value=text,present=True);ob,typed=observation(8,text,32)
        with self.assertRaises(OracleError):p.bind_state('applied',ev,ob,w,r,typed_uuid=typed)
        ob,typed=observation(8,text,64)
        for change in (dict(logical={}),dict(snapshot='updated'),dict(origin={'bytes':65536,'sha256':'e'*64}),dict(extra=True)):
            with self.assertRaises(OracleError):p.bind_state('applied',{**ev,**change},ob,w,r,typed_uuid=typed)
        r['description_measurement']['states']=r['description_measurement']['states'][:2]
        with self.assertRaises(OracleError):p.bind_state('applied',ev,ob,w,r,typed_uuid=typed)

    def test_serialized_closed_types_parity_cleanup_and_full_lifecycle(self):
        source=fixture();mutations=[(('schema',),True),(('extra',),1),(('stages',3,'status'),'not_started'),(('description_measurement','profile_sha256'),'e'*64),(('description_measurement','states'),source['description_measurement']['states'][:3])]
        for i in range(4):
            prefix=('description_measurement','states',i)
            for path,val in [(('witness','nonce'),'e'*32),(('witness','token'),'e'*32),(('origin','sha256'),'e'*64),(('postimage','bytes'),True),(('typed_uuid_verdict',),'differs' if i else 'matches'),(('witness','schema'),3)]:mutations.append((prefix+path,val))
            if i:
                for path,val in [(('status',),'readback_differs'),(('metadata_matches',),False),(('physical','payload_length'),32 if i==3 else 64),(('physical','description_width'),999)]:mutations.append((prefix+('comparison',)+path,val))
        for k in source['cleanup']:mutations.append((('cleanup',k),False))
        for path,value in mutations:
            r=copy.deepcopy(source);node=r
            for k in path[:-1]:node=node[k]
            node[path[-1]]=value
            with self.subTest(path=path),self.assertRaises(OracleError):validate(r)
        r=copy.deepcopy(source);s=r['description_measurement']['states'][3];s['observe_token']=s['witness']['token']='3'*32
        with self.assertRaises(OracleError):validate(r)

    def test_failed_lifecycle_scrubs_capture(self):
        r,_=lifecycle.fixture_report('create');base=p.empty_report(NONCE,provenance(),description_case='description8')
        for k in ('schema','lane','provenance',*p.EXTRA_KEYS):r[k]=base[k]
        with self.assertRaises(OracleError):validate(r,False)
        p.discard_capture(r);self.assertIsNone(r['description_measurement']);validate(r,False)

    def test_wire_and_compact_aggregate_require_actual_final_reports(self):
        r=fixture();raw=protocol.encode(r)
        for bad in (raw[:-1]+b',"schema":53}',b'null',b'[]',b'NaN',b'\xff',b' '*32769):
            with self.assertRaises(OracleError):p.validate_report(bad,nonce=NONCE,provenance=provenance(),final=True)
        reports=[r,fixture('description17','b'*32)];hashes=[hashlib.sha256(protocol.encode(x)+b'\n').hexdigest() for x in reports]
        aggregate=p.build_aggregate(reports,hashes,run_id=123,run_attempt=1)
        self.assertNotIn('reports',aggregate);self.assertEqual([x['outcome'] for x in aggregate['cases']],['readback_matches']*2)
        aggregate['cases'][0]['report_sha256']='e'*64
        with self.assertRaises(OracleError):p.validate_aggregate(protocol.encode(aggregate),provenance=provenance(),run_id=123,run_attempt=1,reports=reports,report_sha256s=hashes)
        reports[1]['description_measurement']['states'][3]['typed_uuid_verdict']='differs'
        with self.assertRaises(OracleError):p.build_aggregate(reports,hashes,run_id=123,run_attempt=1)

if __name__=='__main__':unittest.main()
