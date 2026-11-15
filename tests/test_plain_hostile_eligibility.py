import unittest
from yadinassi import Interpreter
from yadinassi.syntax.parser import parse
from yadinassi.plain_routines import lower, Ineligible
class HostileEligibilityTests(unittest.TestCase):
 def value(self, events, answer):
  class Meta(type):
   def __eq__(self, other):events.append(other);return answer
   __hash__=type.__hash__
  class Value(metaclass=Meta):pass
  return Value()
 def test_foreign_parameter_never_invokes_metaclass_or_plain_body(self):
  for answer in (False,True):
   for enabled in (False,True):
    events=[];value=self.value(events,answer)
    vm=Interpreter(execution_backend='compiled-strict',compiled_plain_routines=enabled);vm.variables['x']=value
    vm.execute('Function F(Val x) Return x;EndFunction r=F(x);')
    self.assertIs(vm.variables['r'],value);self.assertEqual(events,[])
    self.assertEqual(vm.compiled_backend_stats.get('plain_routine_calls',0),0)
    self.assertEqual(vm.compiled_backend_stats['interpreter_fallbacks'],0)
 def test_foreign_literal_lowering_rejects_without_metaclass(self):
  for answer in (False,True):
   events=[];routine=parse('Function F() Return 1;EndFunction')[0]
   routine.body[0].value.value=self.value(events,answer)
   with self.assertRaises(Ineligible):lower(routine)
   self.assertEqual(events,[])
if __name__=='__main__':unittest.main()
