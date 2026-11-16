import unittest
from decimal import Decimal
from yadinassi import Interpreter

from compiled_contract_fixture import legacy_compiler_fixture

@legacy_compiler_fixture
class TailCallTests(unittest.TestCase):
 def run_source(self,source,optin,setup=lambda v:None):
  vm=Interpreter(execution_backend='compiled-strict',compiled_plain_routines=optin)
  setup(vm);vm.execute(source)
  self.assertIsNone(vm.locals);self.assertEqual(vm._compiled().active_frames,0)
  self.assertEqual(vm.compiled_backend_stats['interpreter_fallbacks'],0)
  return vm
 def test_tail_plain_callee_route(self):
  source='Function G(Val x) Return x+1;EndFunction Function F(Val x) x=x+2;Return G(x);EndFunction r=F(3);'
  for enabled in (False,True):
   vm=self.run_source(source,enabled);self.assertEqual(vm.variables['r'],6)
   if enabled:
    self.assertEqual(vm.compiled_backend_stats['plain_routine_calls'],2)
    self.assertEqual(vm.compiled_backend_stats['plain_call_adapter_boundaries'],1)
 def test_host_tail_effect_once_and_live_spill(self):
  source='Function F(Val x) x=x+2;Return Host(x);EndFunction r=F(3);'
  for enabled in (False,True):
   effects=[]
   def setup(vm):
    def host(x):
     effects.append((x,vm.locals['x']));return x+1
    vm.register_function('Host',host)
   vm=self.run_source(source,enabled,setup)
   self.assertEqual(vm.variables['r'],6);self.assertEqual(effects,[(Decimal(5),Decimal(5))])
 def test_wrong_arity_before_actual_effects(self):
  source='Function G(Val x) Return x;EndFunction Function F(Val x) Return G(Tick(),Tick());EndFunction r=F(1);'
  for enabled in (False,True):
   events=[];vm=Interpreter(execution_backend='compiled-strict',compiled_plain_routines=enabled)
   vm.register_function('Tick',lambda:events.append(1))
   with self.assertRaises(Exception):vm.execute(source)
   self.assertEqual(events,[]);self.assertIsNone(vm.locals);self.assertEqual(vm._compiled().active_frames,0)

if __name__=='__main__':unittest.main()
