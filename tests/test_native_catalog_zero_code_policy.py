"""Synthetic mapped numeric lane, no native or runtime acceptance claim."""
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
import catalog_zero_code_policy as p
import catalog_zero_code_measurement as measurement
import catalog_zero_code_physical as physical_reader
import inputs
import protocol
from snapshots import OracleError
import test_native_1c_db_oracle_stage as lifecycle
import test_native_catalog_zero_code_physical as physical
NONCE='a'*32

def provenance():
 v=lifecycle.provenance();v['actual_version']=protocol.VERSION
 v['sources']={k:'c'*64 for k in inputs.CATALOG_ZERO_CODE_SOURCE_FILES}
 return v

def witness(case,nonce,token,*,present=True,payload=32,code='',identifier='52525252-5252-5252-5252-525252525252',description='X',state='unavailable'):
 raw=protocol.encode(dict(schema=1,nonce=nonce,token=token,case=case,operation='observe',present=present,
  code_type='string',code_state=state if present else 'absent',actual_code=code if present else '',actual_uuid=identifier if present else '',
  actual_description=description if present and measurement.CASES[case] else '',code_length=0,description_length=measurement.CASES[case],payload_length=payload,autonumbering=False))
 return measurement.validate_witness(raw,nonce=nonce,token=token,case=case,operation='observe')

def evidence(r,name,index):
 s=next(x for x in r['snapshots']if x['id']==name)
 return dict(snapshot=name,token=str(index+1)*32,origin={k:s['physical'][k]for k in('bytes','sha256')},
  postimage={'bytes':65536,'sha256':'f'*64},logical=copy.deepcopy(s['logical']))

def observation(case='zero8',payload=32,*,unresolved=False):
 edit=(lambda fields:fields[:4]+[('_CODE','NVC',0,2,0,'CI')]+fields[4:])if unresolved else None
 v=physical.source(measurement.CASES[case],payload,edit=edit)
 return physical_reader.read_zero_code(v.read_at,v.size,catalog_name='NativeOracleItems')

def fixture(case='zero8',nonce=NONCE,*,final=True,outcome='readback_matches'):
 r,_=lifecycle.fixture_report();base=p.empty_report(nonce,provenance(),zero_case=case)
 for k in('schema','lane','nonce','provenance',*p.EXTRA_KEYS):r[k]=base[k]
 for s in r['snapshots']:s['logical']=p.expected_logical(s['id'])
 for index,name in enumerate(p.TARGETS):
  ev=evidence(r,name,index);payload=64 if name=='applied'else 32
  w=witness(case,nonce,ev['token'],present=name!='baseline',payload=payload,description='Y'if outcome=='readback_differs'else'X')
  ob=None if name=='baseline'else observation(case,payload,unresolved=outcome=='layout_unresolved')
  r['zero_code_measurement']['states'].append(p.bind_state(ev,r,ob,w))
 if final:r['cleanup'].update(container_removed=True,private_staging_removed=True);r['accepted']=True
 return r

def validate(r,final=True):return p.validate_report(protocol.encode(r),nonce=r['nonce'],provenance=provenance(),final=final)

def native_marker(code='observed_no_code',count=1):
 return dict(schema=1,nonce=NONCE,token='b'*32,operation='observe',status='ok',actual_version=protocol.VERSION,
  user='NativeOracleCRUD',role_verified=True,nonprivileged=True,metadata_version=1,count=count,code=code,
  payload='alpha'if count else None,amount='1.25'if count else None,deletion_mark=False if count else None,
  same_reference=True if count else None,users_verified=False,payload_length=32,amount_digits=9,amount_scale=2)

class ZeroPolicyTests(unittest.TestCase):
 def test_mapped_core_is_detached_and_old_K1_unchanged(self):
  for name in protocol.SNAPSHOTS:
   original=protocol.expected_logical(name);value=p.expected_logical(name);saved=copy.deepcopy(value);p.validate_logical(value,name)
   self.assertEqual(value,saved);self.assertEqual(protocol.expected_logical(name),original)
   if original['code']is not None:
    self.assertEqual(value['code'],'observed_no_code')
    with self.assertRaises(OracleError):protocol.validate_logical(value,name)
    with self.assertRaises(OracleError):p.validate_logical(original,name)
  raw=protocol.encode(native_marker());self.assertEqual(p.marker(raw,nonce=NONCE,token='b'*32,operation='observe')['code'],'observed_no_code')
  with self.assertRaises(OracleError):protocol.marker(raw,nonce=NONCE,token='b'*32,operation='observe')
  protocol.marker(protocol.encode(native_marker('K1')),nonce=NONCE,token='b'*32,operation='observe')
  for code,count in [('K1',1),(123,1),(True,1),(None,1),('observed_no_code',0),('other',1)]:
   with self.subTest(code=code,count=count),self.assertRaises(OracleError):p.marker(protocol.encode(native_marker(code,count)),nonce=NONCE,token='b'*32,operation='observe')
  self.assertIsNone(p.marker(protocol.encode(native_marker(None,0)),nonce=NONCE,token='b'*32,operation='observe')['code'])

 def test_four_bound_states_all_measurement_outcomes(self):
  self.assertEqual(len(inputs.CATALOG_ZERO_CODE_SOURCE_FILES),42)
  self.assertEqual((p.SCHEMA,p.CAPTURE_SCHEMA,p.AGGREGATE_SCHEMA),(65,66,67))
  for case in p.CASES:
   for outcome in (p.OUTCOMES if case=='zero8' else ('readback_matches','layout_unresolved')):
    r=fixture(case,outcome=outcome);before=copy.deepcopy(r);validate(r);self.assertEqual(r,before)
    self.assertEqual(p._outcome(r),outcome)
    self.assertEqual(r['zero_code_measurement']['runtime_support'],'not_claimed')
    for s in r['zero_code_measurement']['states'][1:]:self.assertTrue(s['comparison']['metadata_matches'])
  validate(fixture(final=False),False)

 def test_uuid_metadata_mandatory_and_witness_identity_private(self):
  r=fixture();r['zero_code_measurement']['states']=r['zero_code_measurement']['states'][:1]
  ev=evidence(r,'created',1);ob=observation();w=witness('zero8',NONCE,ev['token'])
  for change in [dict(actual_uuid=UUID(int=1)),dict(code_length=6),dict(description_length=9),dict(payload_length=64),dict(autonumbering=True),dict(present=False),dict(case='zero0'),dict(nonce='f'*32),dict(token='f'*32),dict(operation='create'),dict(actual_code=123),dict(actual_code=Decimal('NaN')),dict(actual_code=Decimal('1E999')),dict(actual_description='\ud800')]:
   with self.subTest(change=change),self.assertRaises((OracleError,ValueError)):p.bind_state(ev,r,ob,replace(w,**change))
  state=p.bind_state(ev,r,ob,replace(w,actual_description='Other'))
  self.assertEqual(state['comparison']['description_verdict'],'differs')
  self.assertEqual(len(r['zero_code_measurement']['states']),1)
  for forbidden in ('actual_code','actual_uuid','actual_description','actual_number'):
   self.assertNotIn(('"'+forbidden+'":').encode(),protocol.encode(state))

 def test_baseline_metadata_and_all_code_availability_states(self):
  r=fixture();r['zero_code_measurement']['states']=[];ev=evidence(r,'baseline',0)
  w=witness('zero8',NONCE,ev['token'],present=False)
  for changes in ({'code_type':'number'},{'code_length':2},{'description_length':0},{'autonumbering':True},{'payload_length':64},{'code_state':'unavailable'}):
   with self.subTest(changes=changes),self.assertRaises(OracleError):p.bind_state(ev,r,None,replace(w,**changes))
  r['zero_code_measurement']['states'].append(p.bind_state(ev,r,None,w))
  ev=evidence(r,'created',1);ob=observation()
  for state,code in [('unavailable',''),('other',''),('string',''),('string','private'),('number','-12.50')]:
   w=witness('zero8',NONCE,ev['token'],state=state,code=code)
   value=p.bind_state(ev,r,ob,w)
   self.assertEqual(value['comparison']['code_availability'],state)
   self.assertNotIn(b'private',protocol.encode(value))
  for state,code in [('number',Decimal('NaN')),('number',Decimal('1E999')),('string','\ud800')]:
   with self.assertRaises(OracleError):p.bind_state(ev,r,ob,replace(w,code_state=state,actual_code=code))

 def test_report_corruption_source_types_stale_and_cleanup(self):
  source=fixture();mutations=[(('zero_case',),'zero9'),(('schema',),53),(('zero_code_measurement','schema'),True),
   (('zero_code_measurement','runtime_support'),'supported'),(('zero_code_measurement','profile_sha256'),'e'*64),
   (('zero_code_measurement','states',1,'observe_token'),'1'*32),
   (('zero_code_measurement','states',1,'origin','sha256'),'e'*64),
   (('zero_code_measurement','states',3,'witness','payload_length'),32),
   (('zero_code_measurement','states',1,'comparison','uuid_verdict'),'differs'),
   (('zero_code_measurement','states',1,'comparison','metadata_matches'),False),
   (('zero_code_measurement','states',1,'comparison','physical','first_attribute_offset'),99),
   (('zero_code_measurement','states',1,'comparison','physical','field_count'),True),
   (('snapshots',2,'logical','code'),'K1'),(('description_failure',),{}),
   (('provenance','sources',next(iter(provenance()['sources']))),'e'*64)]
  for path,value in mutations:
   r=copy.deepcopy(source);node=r
   for k in path[:-1]:node=node[k]
   node[path[-1]]=value
   with self.subTest(path=path),self.assertRaises(OracleError):validate(r)
  for key in source['cleanup']:
   r=copy.deepcopy(source);r['cleanup'][key]=False
   with self.assertRaises(OracleError):validate(r)
  for raw in (b'null',b'[]',b'NaN',b'\xff',b' '*32769,protocol.encode(source)[:-1]+b',"schema":65}'):
   with self.assertRaises(OracleError):p.validate_report(raw,nonce=NONCE,provenance=provenance(),final=True)

 def test_closed_projection_order_presence_and_scalar_types(self):
  original=fixture()
  paths=[('zero_code_measurement',),('zero_code_measurement','states',0),
   ('zero_code_measurement','states',1,'witness'),('zero_code_measurement','states',1,'comparison'),
   ('zero_code_measurement','states',1,'comparison','physical')]
  for path in paths:
   r=copy.deepcopy(original);node=r
   for key in path:node=node[key]
   node['actual_private']='not_exportable'
   with self.subTest(path=path),self.assertRaises(OracleError):validate(r)
  mutations=[(('zero_code_measurement','states',0,'witness','code_type'),'number'),
   (('zero_code_measurement','states',0,'witness','code_length'),True),
   (('zero_code_measurement','states',0,'witness','present'),True),
   (('zero_code_measurement','states',1,'witness','code_state'),'absent'),
   (('zero_code_measurement','states',1,'comparison','schema'),True),
   (('zero_code_measurement','states',1,'comparison','code_availability'),'other'),
   (('zero_code_measurement','states',1,'comparison','physical','code_field_count'),1),
   (('zero_code_measurement','states',1,'comparison','physical','description_field_count'),0),
   (('zero_code_measurement','states',1,'comparison','physical','record_size'),4096),
   (('zero_code_measurement','states',1,'comparison','physical','active_count_known'),1)]
  for path,value in mutations:
   r=copy.deepcopy(original);node=r
   for key in path[:-1]:node=node[key]
   node[path[-1]]=value
   with self.subTest(path=path),self.assertRaises(OracleError):validate(r)
  r=copy.deepcopy(original);r['zero_code_measurement']['states'].reverse()
  with self.assertRaises(OracleError):validate(r)
  r=copy.deepcopy(original);r['zero_code_measurement']['states']=r['zero_code_measurement']['states'][:1]
  ev=evidence(r,'updated',2)
  with self.assertRaises(OracleError):p.bind_state(ev,r,observation(),witness('zero8',NONCE,ev['token']))
  r=copy.deepcopy(original);del r['provenance']['sources'][next(iter(r['provenance']['sources']))]
  with self.assertRaises(OracleError):p.validate_report(protocol.encode(r),nonce=NONCE,provenance=r['provenance'],final=True)

 def test_failed_capture_scrub_and_compact_aggregate_report_binding(self):
  r,_=lifecycle.fixture_report('create');base=p.empty_report(NONCE,provenance(),zero_case='zero8')
  for k in('schema','lane','nonce','provenance',*p.EXTRA_KEYS):r[k]=base[k]
  for s in r['snapshots']:s['logical']=p.expected_logical(s['id'])
  r['cleanup'].update(container_removed=True,private_staging_removed=True)
  with self.assertRaises(OracleError):validate(r)
  p.discard_capture(r,final=True);validate(r);self.assertIsNone(r['zero_code_measurement'])
  reports=[fixture(c,n*32,outcome='layout_unresolved')for c,n in zip(p.CASES,('a','b'))]
  hashes=[hashlib.sha256(protocol.encode(x)).hexdigest()for x in reports]
  a=p.build_aggregate(reports,hashes,run_id=123,run_attempt=1)
  self.assertNotIn('reports',a);self.assertEqual(a['cases'][0]['outcome'],'layout_unresolved')
  with self.assertRaises(OracleError):p.validate_aggregate(protocol.encode(a),provenance=provenance(),run_id=123,run_attempt=1,reports=reports,report_sha256s=['e'*64,hashes[1]])
  reports[1]['nonce']=reports[0]['nonce']
  with self.assertRaises(OracleError):p.build_aggregate(reports,hashes,run_id=123,run_attempt=1)


def bootstrap_diagnostic():
 return dict(schema=1,nonce=NONCE,token='e'*32,bootstrap='absent',result='invalid',completion='valid_error',pending='valid_error',
  **{k:dict(state='nonempty',module_error=True,undefined_symbol=False,syntax_error=False)for k in ('out','console')})

def bootstrap_failure(final=True):
 r,_=lifecycle.fixture_report('seed_v1');base=p.empty_report(NONCE,provenance(),zero_case='zero0')
 for key in ('schema','lane','nonce','provenance',*p.EXTRA_KEYS):r[key]=base[key]
 r['failure_kind']='seed_bootstrap_timeout'
 r['failure_context']=dict(operation='enterprise_bootstrap',site='poll',bsl_phase=None,region=None,reason=None)
 r['zero_code_measurement']=None
 if final:r['cleanup'].update(container_removed=True,private_staging_removed=True)
 return r

class ZeroBootstrapDiagnosticTests(unittest.TestCase):
 def test_optional_failure_cleanup_and_detached_copy(self):
  for final in (False,True):
   r=bootstrap_failure(final);d=bootstrap_diagnostic();saved=copy.deepcopy(d)
   self.assertTrue(p.set_bootstrap_failure(r,d,final=final));validate(r,final)
   d['out']['state']='changed';self.assertEqual(r['zero_bootstrap_failure'],saved)
   self.assertFalse(r['accepted']);self.assertIsNone(r['zero_code_measurement'])
   p.discard_capture(r,final=final);self.assertNotIn('zero_bootstrap_failure',r);validate(r,final)
  r=bootstrap_failure(False);self.assertFalse(p.set_bootstrap_failure(r,bootstrap_diagnostic(),final=True))

 def test_finite_states_and_flags(self):
  import itertools
  for marker in ('bootstrap','result','completion','pending'):
   for state in ('absent','invalid','valid_ok')+(('valid_error',)if marker in ('completion','pending')else()):
    d=bootstrap_diagnostic();d[marker]=state;p.validate_bootstrap_failure(d)
  for name in ('out','console'):
   for state in p.BOOTSTRAP_LOG_STATES:
    for flags in itertools.product((False,True),repeat=3):
     d=bootstrap_diagnostic();d[name]=dict(zip(('state','module_error','undefined_symbol','syntax_error'),(state,*flags)))
     if state=='nonempty' or not any(flags):p.validate_bootstrap_failure(d)
     else:
      with self.assertRaises(OracleError):p.validate_bootstrap_failure(d)

 def test_bad_shapes_types_private_fields_and_binding(self):
  for path,value in [(('schema',),True),(('schema',),1.0),(('nonce',),'bad'),(('token',),'bad'),(('bootstrap',),'valid_error'),(('result',),'valid_error'),(('completion',),'private'),(('private_path',),'/private'),(('out','raw'),'secret'),(('console','module_error'),1),(('pending',),None)]:
   d=bootstrap_diagnostic();node=d
   for key in path[:-1]:node=node[key]
   node[path[-1]]=value
   with self.subTest(path=path),self.assertRaises(OracleError):p.validate_bootstrap_failure(d)
   self.assertFalse(p.set_bootstrap_failure(bootstrap_failure(),d,final=True))
  mutations=[(('nonce',),'b'*32),(('schema',),59),(('status',),'ok'),(('accepted',),True),(('failed_stage',),'create'),(('failure_kind',),'process_failed'),(('failure_context','operation'),'enterprise'),(('failure_context','site'),'launch'),(('snapshots',),[{}]),(('zero_code_measurement',),{})]
  mutations += [(('cleanup',key),v) for key in bootstrap_failure()['cleanup'] for v in (False,1,1.0)]
  for path,value in mutations:
   r=bootstrap_failure();node=r
   for key in path[:-1]:node=node[key]
   node[path[-1]]=value
   self.assertFalse(p.set_bootstrap_failure(r,bootstrap_diagnostic(),final=True))
   r['zero_bootstrap_failure']=bootstrap_diagnostic()
   with self.subTest(path=path),self.assertRaises(OracleError):validate(r,True)
  r=fixture();r['zero_bootstrap_failure']=bootstrap_diagnostic()
  with self.assertRaises(OracleError):validate(r)

 def test_foreign_mapping_keys_never_invoke_hooks(self):
  class Key:
   def __hash__(self):return hash('schema')
   def __eq__(self,other):raise AssertionError('equality hook')
  class Mapping(dict):
   def __iter__(self):raise AssertionError('iteration hook')
  bad=bootstrap_diagnostic();bad.pop('schema');bad[Key()]=1
  for d in (bad,Mapping(bootstrap_diagnostic())):
   with self.assertRaises(OracleError):p.validate_bootstrap_failure(d)

if __name__=='__main__':unittest.main()
