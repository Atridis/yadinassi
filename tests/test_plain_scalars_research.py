import unittest
from yadinassi import Interpreter
from compiled_contract_fixture import legacy_compiler_fixture

@legacy_compiler_fixture
class ScalarTests(unittest.TestCase):
 def test_scalar_values_ternary_declarations_division_modulo(self):
  for expression,arg in [('x+"!"','"abc"'),('NOT x','False'),('x=Undefined','Undefined'),('?(x,10,20)','True'),('x/2','9'),('x%2','9')]:
   values=[]
   for mode in ('interpreter','compiled-strict'):
    vm=Interpreter(execution_backend=mode,compiled_plain_routines=True)
    vm.execute('Function F(Val x) Var a;a='+expression+';Return a;EndFunction r=F('+arg+');')
    values.append(vm.variables['r']);self.assertIsNone(vm.locals)
    if mode=='compiled-strict':
     self.assertEqual(vm.compiled_backend_stats.get('plain_routine_calls'),1)
     self.assertEqual(vm.compiled_backend_stats['interpreter_fallbacks'],0)
   self.assertEqual(*values)
 def test_redeclaration_of_existing_slot_has_valid_noop_body(self):
  for enabled in (False,True):
   vm=Interpreter(execution_backend='compiled-strict',compiled_plain_routines=enabled)
   vm.execute('Function F() x=3;Var x;Return x;EndFunction r=F();')
   self.assertEqual(vm.variables['r'],3)
   if enabled:self.assertEqual(vm.compiled_backend_stats.get('plain_routine_calls'),1)
 def test_module_counter_shadowing_retains_adapter_semantics(self):
  source='Var i;Procedure F() For i=1 To 2 Do Var i;i=10;EndDo;EndProcedure F();'
  for mode,enabled in (('interpreter',False),('compiled-strict',False),('compiled-strict',True)):
   vm=Interpreter(execution_backend=mode,compiled_plain_routines=enabled);vm.execute(source)
   self.assertEqual(vm.variables['i'],1)
   self.assertEqual(vm.compiled_backend_stats.get('plain_routine_calls',0),0)
if __name__=='__main__':unittest.main()
