import unittest
from decimal import Decimal
from yadinassi import Interpreter
from compiled_contract_fixture import legacy_compiler_fixture

@legacy_compiler_fixture
class PrefixTests(unittest.TestCase):
 def test_prefix_suffix_live_locals_and_once(self):
  source='Function F(Val n) s=0;For i=1 To n Do s=s+i;EndDo;s=Host(s);Return s+1;EndFunction r=F(5);'
  for enabled in (False,True):
   seen=[];vm=Interpreter(execution_backend='compiled-strict',compiled_plain_routines=enabled)
   def host(s):seen.append(s);vm.locals['n']=Decimal(99);return s+2
   vm.register_function('Host',host);vm.execute(source)
   self.assertEqual(vm.variables['r'],18);self.assertEqual(seen,[Decimal(15)]);self.assertIsNone(vm.locals)
   self.assertEqual(vm.compiled_backend_stats['interpreter_fallbacks'],0)
   if enabled:
    self.assertEqual(vm.compiled_backend_stats.get('plain_suffix_adapter_entries'),1)
    # _Return travels through the existing adapter; entry is witnessed even
    # though plain-prefix normal completion count may remain zero.
    self.assertEqual(vm.compiled_backend_stats.get('plain_routine_calls',0),0)
 def test_suffix_goto_backwards_does_not_replay_prefix(self):
  source='Function F(Val n) n=n+2;~Again:n=n-1;If n>0 Then Goto ~Again;EndIf;Return n;EndFunction r=F(3);'
  for enabled in (False,True):
   vm=Interpreter(execution_backend='compiled-strict',compiled_plain_routines=enabled);vm.execute(source)
   self.assertEqual(vm.variables['r'],0)
   if enabled:self.assertEqual(vm.compiled_backend_stats.get('plain_suffix_adapter_entries',0),0)
 def test_suffix_uses_already_admitted_nodes_after_budget_change(self):
  for enabled in (False,True):
   vm=Interpreter(execution_backend='compiled-strict',compiled_plain_routines=enabled);seen=[]
   def limit():vm._compiled().MAX_INLINE_UNIT_BYTES=0;return Decimal(3)
   def host(n):seen.append(n);return n
   vm.register_function('Limit',limit);vm.register_function('Host',host)
   vm.execute('Function F(Val n) n=n+2;n=Host(n);Return n;EndFunction r=F(Limit());')
   self.assertEqual(vm.variables['r'],5);self.assertEqual(seen,[Decimal(5)])
   self.assertIsNone(vm.locals)
if __name__=='__main__':unittest.main()
