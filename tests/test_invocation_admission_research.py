"""Live direct invocation checks; retired lazy call_routine generator removed."""
import unittest
from yadinassi import Interpreter
from yadinassi.experimental_naked_boundaries import BoundaryViolation

class AdmissionTests(unittest.TestCase):
 def test_bad_arity_rejects_before_argument_effects(self):
  v=Interpreter(execution_backend='python-direct');events=[]
  v.register_function('Touch',lambda:events.append(1))
  v.execute('Function F(Val x) Return x; EndFunction')
  with self.assertRaises(Exception):v.execute('r=F(Touch(),Touch());')
  self.assertEqual(events,[]);self.assertIsNone(v.locals)
 def test_live_revocation_not_cached_after_success(self):
  v=Interpreter(execution_backend='python-direct');events=[]
  v.register_function('Touch',lambda:events.append(1))
  v.execute('Function F(Val x) Return x+1; EndFunction r=F(3);')
  self.assertEqual(v.variables['r'],4)
  plan=v.prepare('r=F(Touch());')
  v.close()
  with self.assertRaises((ValueError,BoundaryViolation)):v.execute_prepared(plan)
  self.assertEqual(events,[]);self.assertIsNone(v.locals)
 def test_byref_defaults_cleanup(self):
  v=Interpreter(execution_backend='python-direct');v.execute('Procedure P(x,Val y=2) x=x+y; EndProcedure a=1;P(a);')
  self.assertEqual(v.variables['a'],3);self.assertIsNone(v.locals)
