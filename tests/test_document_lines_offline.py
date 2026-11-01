"""Finite failure retention only; no physical profile admission or native claim."""
from pathlib import Path
import copy,os,subprocess,sys,tempfile,unittest
from unittest import mock
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'scripts/native_1c_db_oracle')]
import document_lines_readback as r
import document_lines_fixture as f
from snapshots import OracleError
from yadinassi.storage import filedb_catalog as c

class OfflineTests(unittest.TestCase):
 def test_closed_failure_no_raw_values(self):
  d=dict(stage='physical-observe',category='value_error',code=None,location=None)
  self.assertEqual(r.OfflineFailure(d).diagnostic,d)
  for key,value in (('extra','secret'),('stage','secret'),('category','secret'),('code','secret'),
    ('location',dict(filename='/tmp/secret',line=1)),('location',dict(filename='filedb_catalog.py',line=True)),
    ('location',dict(filename='filedb_catalog.py',line=5001))):
   bad=dict(d);bad[key]=value
   with self.assertRaises(ValueError):r.OfflineFailure(bad)
  bad=dict(d,code='descriptor_shape')
  with self.assertRaises(ValueError):r.validate_failure(bad)
 def test_known_categories_and_untrusted_codes(self):
  for error,category,code in ((ValueError('private'),'value_error',None),(TypeError('private'),'type_error',None),
     (ImportError('private'),'import_error',None),(c.InvalidStructure('descriptor_shape'),'catalog_error','descriptor_shape'),
     (c.UnsupportedLayout('private'),'catalog_error',None),
     (c.ResourceLimit('private'),'resource_limit',None),(c.UnsupportedSharing('private'),'unsupported_sharing',None)):
   def fail():raise error
   with self.assertRaises(r.OfflineFailure) as got:r._attempt('physical-observe',fail)
   self.assertEqual(got.exception.diagnostic,dict(stage='physical-observe',category=category,code=code,location=None))
   self.assertNotIn('private',str(got.exception))
 def test_security_budget_and_base_exceptions_propagate(self):
  for error in (OracleError('snapshot_changed'),OracleError('artifact_limit'),c.ChangedDuringRead('private'),c.SourceIOError('private'),c.NotRegularFile('private'),
    RuntimeError('private'),KeyboardInterrupt(),SystemExit()):
   def fail():raise error
   with self.assertRaises(type(error)) as got:r._attempt('physical-observe',fail)
   self.assertIs(got.exception,error)
 def test_real_physical_failure_meaningful_location(self):
  import document_lines_physical as physical
  s,m,files=f.load(1);p=m['profile'];mapping=f.actual_mapping(s,p,{n:v for n,v in files.items() if n.endswith('.xml')})
  mapping['section']['name']='wrong'
  with self.assertRaises(r.OfflineFailure) as got:r.readback(lambda *a: self.fail('unexpected I/O'),0,'unused',s,{},mapping)
  d=got.exception.diagnostic
  self.assertEqual(d['stage'],'physical-observe');self.assertEqual(d['category'],'value_error')
  self.assertEqual(d['location']['filename'],'document_lines_physical.py')
  line=Path(physical.__file__).read_text().splitlines()[d['location']['line']-1]
  self.assertIn('_check(section==expected)',line)
 def test_stage_is_exact_and_compare_is_not_success(self):
  s,_,_=f.load(1)
  for stage in ('runtime-execute','compare'):
   with mock.patch('document_lines_physical.observe',return_value={}),mock.patch.object(r,'execute',
       side_effect=ValueError('private') if stage=='runtime-execute' else None,return_value={b:'' for b in f.BLOCKS}):
    with self.assertRaises(r.OfflineFailure) as got:r.readback(None,0,'unused',s,{b:'' for b in f.BLOCKS},{})
    self.assertEqual(got.exception.diagnostic['stage'],stage)
 def test_actual_interpreter_unavailable_remains_bounded(self):
  from yadinassi.database_context import FileDBContext
  s,_,_=f.load(1)
  with tempfile.TemporaryDirectory() as directory,mock.patch.object(FileDBContext,'document_metadata',side_effect=ValueError('config_document_profile')):
   out=r.execute(directory,s)
  self.assertEqual(set(out),set(f.BLOCKS))
  for block,raw in out.items():self.assertEqual(f.validate_capture(raw.encode('ascii'),s,block),{'availability':'unavailable'})
 def test_standalone_cold_import(self):
  with tempfile.TemporaryDirectory() as directory:
   env=dict(os.environ,PYTHONPATH=str(ROOT/'scripts/native_1c_db_oracle'))
   result=subprocess.run([sys.executable,'-c',"import document_lines_readback as r; r.validate_failure(dict(stage='compare',category='value_error',code=None,location=None))"],cwd=directory,env=env,capture_output=True,text=True)
   self.assertEqual(result.returncode,0,result.stderr)

if __name__=='__main__':unittest.main()
