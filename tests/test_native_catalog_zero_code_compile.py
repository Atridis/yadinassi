"""Bounded syntax diagnostics are observations, never measurement acceptance."""
import copy
import unittest
from unittest import mock
import test_native_catalog_zero_code_bootstrap as base
import test_native_catalog_zero_code_policy as facts
import catalog_zero_code_measurement as m
import catalog_zero_code_policy as p
import protocol

LOG='{ОбщийМодуль.NativeOracleServer.Модуль(17,9)}: Переменная не определена (PRIVATE)\n'
def diagnostic():
 d=facts.bootstrap_diagnostic();d['bootstrap']='valid_ok'
 d['frontier']={point:dict(state='absent',status=None,phase=None)for point in m.FRONTIER_POINTS}
 d['frontier']['client_before_call']=dict(state='valid',status='entered',phase='dispatch')
 return d

class CompileProjectionTests(unittest.TestCase):
 def test_encodings_and_private_projection(self):
  for encoding in ('utf-8','utf-16','cp1251'):
   d=m.compile_log_projection(LOG.encode(encoding));self.assertEqual(d['issues'],[dict(module='server',line=17,column=9,category='undefined_symbol')]);self.assertNotIn('PRIVATE',str(d))
  self.assertEqual(m.compile_log_projection(b'unknown PRIVATE')['issues'],[])
  self.assertEqual(m.compile_log_projection(b'')['log_state'],'empty')
  d=m.compile_log_projection(b'{PRIVATE(1,2)}: Syntax error');self.assertEqual(d['issues'],[dict(module='other',line=0,column=0,category='syntax_error')])
 def test_no_cross_line_classification(self):
  d=m.compile_log_projection(b'{CommonModule.NativeOracleServer.Module(1,2)}: \nVariable is not defined')
  self.assertEqual(d['issues'][0]['category'],'other')
 def test_limits_and_deduplication(self):
  self.assertEqual(len(m.compile_log_projection((LOG*10).encode())['issues']),1)
  d=m.compile_log_projection(''.join(LOG.replace('(17,9)',f'({i},9)')for i in range(1,12)).encode());self.assertEqual(len(d['issues']),8);self.assertTrue(d['truncated'])
  with self.assertRaises(ValueError):m.compile_log_projection(b'x'*32769)
  with self.assertRaises(ValueError):m.compile_log_projection('PRIVATE')
 def test_policy_and_failure_gate(self):
  value=dict(state='completed',result_code=1,**m.compile_log_projection(LOG.encode()))
  d=diagnostic();d['compile']=value;p.validate_bootstrap_failure(d)
  report=facts.bootstrap_failure();self.assertTrue(p.set_bootstrap_failure(report,d,final=True));facts.validate(report)
  for key,val in [('state','PRIVATE'),('result_code',True),('result_code',256),('raw','PRIVATE'),('truncated',True),('log_state','empty')]:
   with self.subTest(key=key),self.assertRaises(protocol.OracleError):p.validate_compile_projection({**value,key:val})
  for point in ('client_before_call','server_enter'):
   bad=copy.deepcopy(d);bad['frontier'][point]=dict(state='invalid',status=None,phase=None)
   with self.assertRaises(protocol.OracleError):p.validate_bootstrap_failure(bad)

class CompileProcessTests(base.BootstrapDiagnosticTests):
 def launch(self,args,label):
  self.assertEqual(label,'zero-compile');self.assertIn('/CheckConfig',args);self.assertIn('-Server',args);self.assertIn('-ThickClientManagedApplication',args)
  self.assertNotIn('/UpdateDBCfg',args)
  (self.native.evidence/'002-zero-compile.log').write_bytes(LOG.encode())
  (self.native.evidence/'002-zero-compile.result').write_bytes(b'1')
 def test_post_failure_compile_and_nonzero(self):
  for kind in (None,'process_failed','timeout'):
   for path in self.native.evidence.glob('002-zero-compile.*'):path.unlink()
   def process(*args):
    self.launch(*args)
    if kind:raise protocol.OracleError(kind)
   with mock.patch.object(self.native,'process',side_effect=process):
    result=self.native._zero_compile_diagnostic(self.db,diagnostic())
   self.assertEqual(result['state'],kind or 'completed');self.assertEqual(result['result_code'],1);self.assertEqual(result['issues'][0]['line'],17)
 def test_no_unowned_or_nonquiescent_launch(self):
  for d in (facts.bootstrap_diagnostic(),{**diagnostic(),'nonce':'c'*32}):
   with mock.patch.object(self.native,'process')as launch:self.assertIsNone(self.native._zero_compile_diagnostic(self.db,d));launch.assert_not_called()
  with mock.patch.object(self.native,'quiescent',return_value=False),mock.patch.object(self.native,'process')as launch:
   self.assertIsNone(self.native._zero_compile_diagnostic(self.db,diagnostic()));launch.assert_not_called()
 def test_original_timeout_preserved_and_cleanup(self):
  error=protocol.OracleError('timeout');error.oracle_site='poll'
  with mock.patch.object(self.native,'process',side_effect=error),mock.patch.object(self.native,'_zero_bootstrap_diagnostic',return_value=diagnostic()),mock.patch.object(self.native,'_zero_compile_diagnostic',return_value=dict(state='completed',result_code=1,**m.compile_log_projection(LOG.encode())))as compile_check:
   with self.assertRaises(protocol.OracleError)as caught:self.native.enterprise(self.db,'bootstrap',token=self.token)
  self.assertIs(caught.exception,error);compile_check.assert_called_once();self.assertIn('compile',self.native.zero_bootstrap_failure)

if __name__=='__main__':unittest.main()
