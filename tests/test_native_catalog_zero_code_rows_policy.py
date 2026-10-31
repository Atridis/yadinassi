"""Strict synthetic public zero-Code row parity; no native acceptance claim."""
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
import catalog_zero_code_rows_policy as p
import catalog_zero_code_rows_reader as rows_reader
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
 v['sources']={k:'c'*64 for k in inputs.CATALOG_ZERO_CODE_ROWS_SOURCE_FILES}
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
 return rows_reader.read_zero_code_rows(v.read_at,v.size,catalog_name='NativeOracleItems')

def fixture(case='zero8',nonce=NONCE,*,final=True,outcome='readback_matches'):
 r,_=lifecycle.fixture_report();base=p.empty_report(nonce,provenance(),zero_case=case)
 for k in('schema','lane','nonce','provenance',*p.EXTRA_KEYS):r[k]=base[k]
 for s in r['snapshots']:s['logical']=p.expected_logical(s['id'])
 for index,name in enumerate(p.TARGETS):
  ev=evidence(r,name,index);payload=64 if name=='applied'else 32
  w=witness(case,nonce,ev['token'],present=name!='baseline',payload=payload,description='Y'if outcome=='readback_differs'else'X')
  ob=None if name=='baseline'else observation(case,payload,unresolved=outcome=='layout_unresolved')
  r['zero_code_rows_measurement']['states'].append(p.bind_state(ev,r,ob,w))
 if final:r['cleanup'].update(container_removed=True,private_staging_removed=True);r['accepted']=True
 return r

def validate(r,final=True):return p.validate_report(protocol.encode(r),nonce=r['nonce'],provenance=provenance(),final=final)

def native_marker(code='observed_no_code',count=1):
 return dict(schema=1,nonce=NONCE,token='b'*32,operation='observe',status='ok',actual_version=protocol.VERSION,
  user='NativeOracleCRUD',role_verified=True,nonprivileged=True,metadata_version=1,count=count,code=code,
  payload='alpha'if count else None,amount='1.25'if count else None,deletion_mark=False if count else None,
  same_reference=True if count else None,users_verified=False,payload_length=32,amount_digits=9,amount_scale=2)


class ZeroRowsPolicyTests(unittest.TestCase):
 def test_strict_public_lane_and_no_private_values(self):
  self.assertEqual((p.SCHEMA,p.CAPTURE_SCHEMA,p.AGGREGATE_SCHEMA),(68,69,70))
  self.assertEqual(len(inputs.CATALOG_ZERO_CODE_ROWS_SOURCE_FILES),43)
  for case in p.CASES:
   r=fixture(case);saved=copy.deepcopy(r);validate(r);self.assertEqual(r,saved)
   self.assertEqual(p._outcome(r),'readback_matches')
   for value in r['zero_code_rows_measurement']['states'][1:]:
    self.assertEqual(value['comparison']['reader'],'public-read-catalog-rows-once')
    for forbidden in ('actual_code','actual_uuid','actual_description'):
     self.assertNotIn(('"'+forbidden+'":').encode(),protocol.encode(value))
 def test_empty_observation_is_independent_not_success_selector(self):
  r=fixture();r['zero_code_rows_measurement']['states']=r['zero_code_rows_measurement']['states'][:1]
  ev=evidence(r,'created',1);ob=observation()
  for state,code,empty in [('string','',True),('string','private',False),('unavailable','',None),('other','',None),('number','12.5',None)]:
   value=p.bind_state(ev,r,ob,witness('zero8',NONCE,ev['token'],state=state,code=code))
   self.assertIs(value['witness']['code_is_empty'],empty)
   self.assertEqual(value['comparison']['status'],'readback_matches')
 def test_observer_only_or_mismatching_readback_is_not_acceptance(self):
  r=fixture();r['zero_code_rows_measurement']['states']=r['zero_code_rows_measurement']['states'][:1]
  ev=evidence(r,'created',1);ob=observation();w=witness('zero8',NONCE,ev['token'])
  with self.assertRaises(OracleError):p.bind_state(ev,r,ob.physical,w)
  for change in [dict(actual_description='Other'),dict(actual_uuid=UUID(int=1)),dict(payload_length=64),dict(code_length=1)]:
   with self.subTest(change=change),self.assertRaises(OracleError):p.bind_state(ev,r,ob,replace(w,**change))
 def test_closed_report_rejects_corruption(self):
  source=fixture();key='zero_code_rows_measurement'
  mutations=[(('schema',),65),((key,'schema'),66),((key,'states',1,'comparison','reader'),'physical-observer'),
   ((key,'states',1,'comparison','status'),'readback_differs'),((key,'states',1,'comparison','uuid_verdict'),'differs'),
   ((key,'states',1,'comparison','description_verdict'),'differs'),((key,'states',1,'comparison','metadata_matches'),False),
   ((key,'states',1,'comparison','physical','code_field_count'),1),((key,'states',1,'comparison','physical','active_count'),0),
   ((key,'states',1,'witness','code_is_empty'),True),((key,'states',1,'observe_token'),'1'*32)]
  for path,value in mutations:
   r=copy.deepcopy(source);node=r
   for part in path[:-1]:node=node[part]
   node[path[-1]]=value
   with self.subTest(path=path),self.assertRaises(OracleError):validate(r)
  for field in source['cleanup']:
   r=copy.deepcopy(source);r['cleanup'][field]=False
   with self.assertRaises(OracleError):validate(r)
  r=copy.deepcopy(source);del r[key]['states'][1]['witness']['code_is_empty']
  with self.assertRaises(OracleError):validate(r)
 def test_string_empty_projection_has_exact_boolean_type(self):
  r=fixture();key='zero_code_rows_measurement';state=r[key]['states'][1]
  state['witness']['code_state']='string';state['comparison']['code_availability']='string'
  for value in (True,False):state['witness']['code_is_empty']=value;validate(r)
  for value in (None,0,1,'',[],{}):
   state['witness']['code_is_empty']=value
   with self.subTest(value=value),self.assertRaises(OracleError):validate(r)

 def test_failed_scrub_and_aggregate_binds_both_finals(self):
  r,_=lifecycle.fixture_report('create');base=p.empty_report(NONCE,provenance(),zero_case='zero8')
  for k in ('schema','lane','nonce','provenance',*p.EXTRA_KEYS):r[k]=base[k]
  for snapshot in r['snapshots']:snapshot['logical']=p.expected_logical(snapshot['id'])
  r['cleanup'].update(container_removed=True,private_staging_removed=True)
  with self.assertRaises(OracleError):validate(r)
  p.discard_capture(r,final=True);validate(r)
  reports=[fixture(case,n*32)for case,n in zip(p.CASES,('a','b'))]
  hashes=[hashlib.sha256(protocol.encode(value)).hexdigest()for value in reports]
  value=p.build_aggregate(reports,hashes,run_id=123,run_attempt=1)
  self.assertEqual(value['schema'],70);self.assertNotIn('reports',value)
  with self.assertRaises(OracleError):p.validate_aggregate(protocol.encode(value),provenance=provenance(),run_id=123,run_attempt=1,reports=reports,report_sha256s=['e'*64,hashes[1]])
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
 r['zero_code_rows_measurement']=None
 if final:r['cleanup'].update(container_removed=True,private_staging_removed=True)
 return r

class ZeroBootstrapDiagnosticTests(unittest.TestCase):
 def test_optional_failure_cleanup_and_detached_copy(self):
  for final in (False,True):
   r=bootstrap_failure(final);d=bootstrap_diagnostic();saved=copy.deepcopy(d)
   self.assertTrue(p.set_bootstrap_failure(r,d,final=final));validate(r,final)
   d['out']['state']='changed';self.assertEqual(r['zero_bootstrap_failure'],saved)
   self.assertFalse(r['accepted']);self.assertIsNone(r['zero_code_rows_measurement'])
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
  mutations=[(('nonce',),'b'*32),(('schema',),59),(('status',),'ok'),(('accepted',),True),(('failed_stage',),'create'),(('failure_kind',),'process_failed'),(('failure_context','operation'),'enterprise'),(('failure_context','site'),'launch'),(('snapshots',),[{}]),(('zero_code_rows_measurement',),{})]
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
