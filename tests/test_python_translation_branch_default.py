import unittest
from yadinassi.runtime import Interpreter
from yadinassi.compiled_backend import Engine
from yadinassi.execution_policy import current_backend,execution_backend_policy,ui_backend
class BranchDefaultTests(unittest.TestCase):
 def test_ordinary_constructor_uses_translation(self):
  self.assertTrue(Engine.FORCE_PYTHON_TRANSLATION)
  vm=Interpreter();self.assertEqual(vm.execution_backend,'compiled-strict')
  vm.execute('x=0;For i=1 To 3 Do x=x+i;EndDo;')
  self.assertEqual(vm.variables['x'],6)
  self.assertGreater(vm.compiled_backend_stats.get('python_translated_blocks',0),0)
  self.assertEqual(vm.compiled_backend_stats.get('interpreter_fallbacks',0),0)
 def test_explicit_oracle_and_family(self):
  vm=Interpreter(execution_backend='interpreter');child=Interpreter(family_owner=vm)
  self.assertEqual(child.execution_backend,'interpreter');vm.execute('x=2;')
  self.assertEqual(vm.compiled_backend_stats.get('python_translated_blocks',0),0)
 def test_policy_scopes_restore_branch_default(self):
  self.assertEqual(current_backend(),'compiled-strict');self.assertEqual(ui_backend(),'compiled-strict')
  with execution_backend_policy('interpreter'):self.assertEqual(Interpreter().execution_backend,'interpreter')
  self.assertEqual(Interpreter().execution_backend,'compiled-strict')
