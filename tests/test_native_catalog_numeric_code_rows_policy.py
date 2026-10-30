"""Synthetic strict public numeric-row policy, not native execution."""
import copy
from dataclasses import replace
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import sys
import unittest
from uuid import UUID
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'scripts/native_1c_db_oracle'),str(ROOT/'yadinassi/storage')]
import catalog_numeric_code_rows_policy as p
import catalog_numeric_code_measurement as measurement
import catalog_numeric_code_physical as physical_reader
import catalog_numeric_code_rows_reader as public_reader
import inputs
import protocol
from snapshots import OracleError
import test_native_1c_db_oracle_stage as lifecycle
import test_native_catalog_numeric_code_physical as physical
NONCE='a'*32

def provenance():
 v=lifecycle.provenance();v['actual_version']=protocol.VERSION
 v['sources']={k:'c'*64 for k in inputs.CATALOG_NUMERIC_CODE_ROWS_SOURCE_FILES}
 return v

def witness(case,nonce,token,*,present=True,payload=32,code='123',identifier='52525252-5252-5252-5252-525252525252',description='Name '):
 raw=protocol.encode(dict(schema=1,nonce=nonce,token=token,case=case,operation='observe',present=present,
  actual_number=present,actual_code=code if present else '',actual_uuid=identifier if present else '',
  actual_description=description if present else '',code_length=measurement.CASES[case][0],description_length=8,payload_length=payload,autonumbering=False))
 return measurement.validate_witness(raw,nonce=nonce,token=token,case=case,operation='observe')

def evidence(r,name,index):
 s=next(x for x in r['snapshots']if x['id']==name)
 return dict(snapshot=name,token=str(index+1)*32,origin={k:s['physical'][k]for k in('bytes','sha256')},
  postimage={'bytes':65536,'sha256':'f'*64},logical=copy.deepcopy(s['logical']))

def observation(case='number3',payload=32,*,unresolved=False):
 edit=(lambda fields:fields[:4]+[('_CODE','N',0,measurement.CASES[case][0],1,'CS')]+fields[5:])if unresolved else None
 v=physical.source(measurement.CASES[case][0],123,payload,edit=edit)
 reader=physical_reader.read_numeric_code if unresolved else public_reader.read_numeric_code_rows
 return reader(v.read_at,v.size,catalog_name='NativeOracleItems')

def fixture(case='number3',nonce=NONCE,*,final=True,outcome='readback_matches'):
 r,_=lifecycle.fixture_report();base=p.empty_report(nonce,provenance(),numeric_case=case)
 for k in('schema','lane','nonce','provenance',*p.EXTRA_KEYS):r[k]=base[k]
 for s in r['snapshots']:s['logical']=p.expected_logical(s['id'])
 for index,name in enumerate(p.TARGETS):
  ev=evidence(r,name,index);payload=64 if name=='applied'else 32
  w=witness(case,nonce,ev['token'],present=name!='baseline',payload=payload,code='124'if outcome=='readback_differs'else'123')
  ob=None if name=='baseline'else observation(case,payload,unresolved=outcome=='layout_unresolved')
  r['numeric_code_rows_measurement']['states'].append(p.bind_state(ev,r,ob,w))
 if final:r['cleanup'].update(container_removed=True,private_staging_removed=True);r['accepted']=True
 return r

def validate(r,final=True):return p.validate_report(protocol.encode(r),nonce=r['nonce'],provenance=provenance(),final=final)

def native_marker(code='observed_number',count=1):
 return dict(schema=1,nonce=NONCE,token='b'*32,operation='observe',status='ok',actual_version=protocol.VERSION,
  user='NativeOracleCRUD',role_verified=True,nonprivileged=True,metadata_version=1,count=count,code=code,
  payload='alpha'if count else None,amount='1.25'if count else None,deletion_mark=False if count else None,
  same_reference=True if count else None,users_verified=False,payload_length=32,amount_digits=9,amount_scale=2)

class NumericPolicyTests(unittest.TestCase):
 def test_mapped_core_is_detached_and_old_K1_unchanged(self):
  for name in protocol.SNAPSHOTS:
   original=protocol.expected_logical(name);value=p.expected_logical(name);saved=copy.deepcopy(value);p.validate_logical(value,name)
   self.assertEqual(value,saved);self.assertEqual(protocol.expected_logical(name),original)
   if original['code']is not None:
    self.assertEqual(value['code'],'observed_number')
    with self.assertRaises(OracleError):protocol.validate_logical(value,name)
    with self.assertRaises(OracleError):p.validate_logical(original,name)
  raw=protocol.encode(native_marker());self.assertEqual(p.marker(raw,nonce=NONCE,token='b'*32,operation='observe')['code'],'observed_number')
  with self.assertRaises(OracleError):protocol.marker(raw,nonce=NONCE,token='b'*32,operation='observe')
  protocol.marker(protocol.encode(native_marker('K1')),nonce=NONCE,token='b'*32,operation='observe')
  for code,count in [('K1',1),(123,1),(True,1),(None,1),('observed_number',0),('other',1)]:
   with self.subTest(code=code,count=count),self.assertRaises(OracleError):p.marker(protocol.encode(native_marker(code,count)),nonce=NONCE,token='b'*32,operation='observe')
  self.assertIsNone(p.marker(protocol.encode(native_marker(None,0)),nonce=NONCE,token='b'*32,operation='observe')['code'])

 def test_four_bound_states_strict_success_only(self):
  self.assertEqual(len(inputs.CATALOG_NUMERIC_CODE_ROWS_SOURCE_FILES),43)
  self.assertEqual((p.SCHEMA,p.CAPTURE_SCHEMA,p.AGGREGATE_SCHEMA),(62,63,64))
  for case in p.CASES:
   for outcome in p.OUTCOMES:
    r=fixture(case,outcome=outcome);before=copy.deepcopy(r);validate(r);self.assertEqual(r,before)
    self.assertEqual(p._outcome(r),outcome)
    self.assertEqual(r['numeric_code_rows_measurement']['runtime_support'],'not_claimed')
    for s in r['numeric_code_rows_measurement']['states'][1:]:self.assertEqual(s['comparison']['status'],outcome)
  validate(fixture(final=False),False)

 def test_uuid_metadata_mandatory_and_witness_identity_private(self):
  r=fixture();r['numeric_code_rows_measurement']['states']=r['numeric_code_rows_measurement']['states'][:1]
  ev=evidence(r,'created',1);ob=observation();w=witness('number3',NONCE,ev['token'])
  for change in [dict(actual_uuid=UUID(int=1)),dict(code_length=6),dict(description_length=9),dict(payload_length=64),dict(autonumbering=True),dict(present=False),dict(case='number6'),dict(nonce='f'*32),dict(token='f'*32),dict(operation='create'),dict(actual_code=123),dict(actual_code=Decimal('NaN')),dict(actual_code=Decimal('1E999')),dict(actual_description='\ud800')]:
   with self.subTest(change=change),self.assertRaises((OracleError,ValueError)):p.bind_state(ev,r,ob,replace(w,**change))
  with self.assertRaises(OracleError):p.bind_state(ev,r,ob,replace(w,actual_description='Other'))
  state=p.bind_state(ev,r,ob,w)
  self.assertEqual(len(r['numeric_code_rows_measurement']['states']),1)
  for forbidden in ('actual_code','actual_uuid','actual_description','actual_number'):
   self.assertNotIn(('"'+forbidden+'":').encode(),protocol.encode(state))

 def test_strict_all_present_states_reject_differences_and_unresolved(self):
  import catalog_numeric_code_policy as observational
  import test_native_catalog_numeric_code_policy as old
  for case in p.CASES:
   original=fixture(case)
   for index in (1,2,3):
    for key,value in [('status','readback_differs'),('metadata_matches',False),('code_verdict','differs'),('uuid_verdict','differs'),('description_verdict','differs')]:
     r=copy.deepcopy(original);r['numeric_code_rows_measurement']['states'][index]['comparison'][key]=value
     with self.subTest(case=case,index=index,key=key),self.assertRaises(OracleError):validate(r)
    for outcome in ('readback_differs','layout_unresolved'):
     measured=old.fixture(case,outcome=outcome)
     observational.validate_report(protocol.encode(measured),nonce=measured['nonce'],provenance=measured['provenance'],final=True)
     r=copy.deepcopy(original);r['numeric_code_rows_measurement']['states'][index]['comparison']=measured['numeric_code_measurement']['states'][index]['comparison']
     with self.assertRaises(OracleError):validate(r)
   r=fixture(case);r['numeric_code_rows_measurement']['states']=r['numeric_code_rows_measurement']['states'][:1]
   ev=evidence(r,'created',1);w=witness(case,NONCE,ev['token'])
   with self.assertRaises(OracleError):p.bind_state(ev,r,observation(case,unresolved=True),w)
   with self.assertRaises(OracleError):p.bind_state(ev,r,observation(case),replace(w,actual_code=Decimal('124')))
   self.assertEqual(len(r['numeric_code_rows_measurement']['states']),1)
   old_report=old.fixture(case)
   with self.assertRaises(OracleError):p.validate_report(protocol.encode(old_report),nonce=NONCE,provenance=provenance(),final=True)
   r=fixture(case);r['numeric_code_rows_measurement']['profile_sha256']=observational.PROFILE_SHA256
   with self.assertRaises(OracleError):validate(r)

 def test_report_corruption_source_types_stale_and_cleanup(self):
  source=fixture();mutations=[(('numeric_case',),'number9'),(('schema',),53),(('numeric_code_rows_measurement','schema'),True),
   (('numeric_code_rows_measurement','runtime_support'),'supported'),(('numeric_code_rows_measurement','profile_sha256'),'e'*64),
   (('numeric_code_rows_measurement','states',1,'observe_token'),'1'*32),
   (('numeric_code_rows_measurement','states',1,'origin','sha256'),'e'*64),
   (('numeric_code_rows_measurement','states',3,'witness','payload_length'),32),
   (('numeric_code_rows_measurement','states',1,'comparison','uuid_verdict'),'differs'),
   (('numeric_code_rows_measurement','states',1,'comparison','metadata_matches'),False),
   (('numeric_code_rows_measurement','states',1,'comparison','physical','code_width'),99),
   (('numeric_code_rows_measurement','states',1,'comparison','physical','digit_count'),True),
   (('snapshots',2,'logical','code'),'K1'),(('description_failure',),{}),
   (('provenance','sources',next(iter(provenance()['sources']))),'e'*64)]
  for path,value in mutations:
   r=copy.deepcopy(source);node=r
   for k in path[:-1]:node=node[k]
   node[path[-1]]=value
   with self.subTest(path=path),self.assertRaises(OracleError):validate(r)
  import catalog_numeric_code_policy as old_policy
  import test_native_catalog_numeric_code_policy as old_fixture
  wrong=copy.deepcopy(source);wrong['provenance']=old_fixture.provenance()
  with self.assertRaises(OracleError):p.validate_report(protocol.encode(wrong),nonce=NONCE,provenance=wrong['provenance'],final=True)
  before=copy.deepcopy(source);validate(source);self.assertEqual(source,before)
  for key in source['cleanup']:
   r=copy.deepcopy(source);r['cleanup'][key]=False
   with self.assertRaises(OracleError):validate(r)
  for raw in (b'null',b'[]',b'NaN',b'\xff',b' '*32769,protocol.encode(source)[:-1]+b',"schema":59}'):
   with self.assertRaises(OracleError):p.validate_report(raw,nonce=NONCE,provenance=provenance(),final=True)

 def test_failed_capture_scrub_and_compact_aggregate_report_binding(self):
  r,_=lifecycle.fixture_report('create');base=p.empty_report(NONCE,provenance(),numeric_case='number3')
  for k in('schema','lane','nonce','provenance',*p.EXTRA_KEYS):r[k]=base[k]
  for s in r['snapshots']:s['logical']=p.expected_logical(s['id'])
  r['cleanup'].update(container_removed=True,private_staging_removed=True)
  with self.assertRaises(OracleError):validate(r)
  p.discard_capture(r,final=True);validate(r);self.assertIsNone(r['numeric_code_rows_measurement'])
  reports=[fixture(c,n*32)for c,n in zip(p.CASES,('a','b'))]
  hashes=[hashlib.sha256(protocol.encode(x)).hexdigest()for x in reports]
  a=p.build_aggregate(reports,hashes,run_id=123,run_attempt=1)
  self.assertNotIn('reports',a);self.assertEqual(a['cases'][0]['outcome'],'readback_matches')
  with self.assertRaises(OracleError):p.validate_aggregate(protocol.encode(a),provenance=provenance(),run_id=123,run_attempt=1,reports=reports,report_sha256s=['e'*64,hashes[1]])
  reports[1]['nonce']=reports[0]['nonce']
  with self.assertRaises(OracleError):p.build_aggregate(reports,hashes,run_id=123,run_attempt=1)

if __name__=='__main__':unittest.main()
