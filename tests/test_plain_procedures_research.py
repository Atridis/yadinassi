import unittest
from yadinassi import Interpreter
from compiled_contract_fixture import legacy_compiler_fixture

@legacy_compiler_fixture
class ProcedureTests(unittest.TestCase):
 def test_val_procedures_defaults_early_and_implicit_returns(self):
  for body in ('','x=x+1;','If x>0 Then Return;EndIf;x=x+1;'):
   for enabled in (False,True):
    vm=Interpreter(execution_backend='compiled-strict',compiled_plain_routines=enabled)
    vm.execute('Procedure P(Val x=1) '+body+' EndProcedure P();')
    self.assertIsNone(vm.locals)
    self.assertEqual(vm.compiled_backend_stats['interpreter_fallbacks'],0)
    if enabled:self.assertEqual(vm.compiled_backend_stats.get('plain_routine_calls'),1)
 def test_default_literal_and_actual_effect_once(self):
  for enabled in (False,True):
   effects=[];vm=Interpreter(execution_backend='compiled-strict',compiled_plain_routines=enabled)
   from decimal import Decimal
   def host():effects.append(1);return Decimal(3)
   vm.register_function('Host',host)
   vm.execute('Function F(Val x=4) Return x+1;EndFunction r=F(Host());d=F();')
   self.assertEqual(vm.variables['r'],4);self.assertEqual(effects,[1]);self.assertEqual(vm.variables['d'],5)
   if enabled:self.assertEqual(vm.compiled_backend_stats.get('plain_routine_calls'),2)
if __name__=='__main__':unittest.main()
