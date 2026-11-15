import unittest
from unittest.mock import patch
from yadinassi import Interpreter
from yadinassi.syntax.parser import parse
class AdmissionTests(unittest.TestCase):
 def test_checks_still_lazy_until_generator_runs(self):
  v=Interpreter(execution_backend='compiled-strict');v.execute('Function F(Val x) Return x; EndFunction')
  with patch.object(v,'_require_family',side_effect=ValueError('revoked')):
   call=v.call_routine(v.routines['f'],[],v,require_value=True)
   with self.assertRaisesRegex(ValueError,'revoked'):next(call)
 def test_bad_arity_rejects_before_argument_effects(self):
  v=Interpreter(execution_backend='compiled-strict');events=[]
  v.register_function('Touch',lambda:events.append(1))
  v.execute('Function F(Val x) Return x; EndFunction')
  with self.assertRaises(Exception):v.execute('r=F(Touch(),Touch());')
  self.assertEqual(events,[]);self.assertIsNone(v.locals)
 def test_live_revocation_not_cached_after_success(self):
  v=Interpreter(execution_backend='compiled-strict');v.execute('Function F(Val x) Return x+1; EndFunction r=F(3);')
  class Denied:
   def check_call(self,function,caller):raise PermissionError('revoked')
  v._configuration_runtime=Denied()
  arguments=[parse('r=3;')[0].value]
  call=v.call_routine(v.routines['f'],arguments,v,require_value=True)
  with self.assertRaisesRegex(PermissionError,'revoked'):next(call)
  self.assertIsNone(v.locals)
 def test_byref_defaults_cleanup(self):
  v=Interpreter(execution_backend='compiled-strict');v.execute('Procedure P(x,Val y=2) x=x+y; EndProcedure a=1;P(a);')
  self.assertEqual(v.variables['a'],3);self.assertIsNone(v.locals)
if __name__=='__main__':unittest.main()
