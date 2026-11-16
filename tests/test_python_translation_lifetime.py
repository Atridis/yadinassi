import gc,weakref,unittest
from unittest.mock import patch
from yadinassi.runtime import Interpreter
from yadinassi.compiled_backend import Engine,CompiledUnsupported
from yadinassi.syntax.parser import parse
class ForceLifetimeTests(unittest.TestCase):
 def test_retained_routine_defaults_survive_unrelated_repl_units(self):
  with patch.object(Engine,'FORCE_PYTHON_TRANSLATION',True):
   vm=Interpreter(execution_backend='compiled-strict',compiled_plain_routines=True)
   vm.execute('Function F(Val x=3) Return x+1;EndFunction')
   for _ in range(3):vm.execute('other=1;')
   units={id(unit):unit for _,unit in vm._compiled()._python_units.values()}
   for unit in units.values():
    functions=[entry[1] for entry in unit.expressions.functions.values()]
    self.assertLessEqual(len({id(fn.__globals__) for fn in functions}),1)
    self.assertLessEqual(len({id(fn.__globals__['_nodes']) for fn in functions}),1)
   vm.execute('r=F();');self.assertEqual(vm.variables['r'],4)
   self.assertEqual(vm.compiled_backend_stats['interpreter_fallbacks'],0)
 def test_retention_does_not_pin_unrelated_literal_payload(self):
  class Payload:pass
  with patch.object(Engine,'FORCE_PYTHON_TRANSLATION',True):
   vm=Interpreter(execution_backend='compiled-strict',compiled_plain_routines=True)
   program=parse('Function F() Return 1;EndFunction x=0;')
   value=Payload();reference=weakref.ref(value);program[-1].value.value=value
   vm.execute_program(program);del program,value
   vm.variables.pop('x');gc.collect();self.assertIsNone(reference())
   vm.execute('r=F();');self.assertEqual(vm.variables['r'],1)
 def test_function_source_limit_rejects_before_effects(self):
  with patch.object(Engine,'FORCE_PYTHON_TRANSLATION',True):
   vm=Interpreter(execution_backend='compiled-strict',compiled_plain_routines=True)
   vm._compiled().MAX_INLINE_FUNCTION_BYTES=100
   with self.assertRaises(CompiledUnsupported):vm.execute('x=1;')
   self.assertNotIn('x',vm.variables)

class ReprepareLifetimeTests(unittest.TestCase):
 def test_repeated_admission_reuses_filtered_owned_block(self):
  with patch.object(Engine,'FORCE_PYTHON_TRANSLATION',True):
   vm=Interpreter(execution_backend='compiled-strict',compiled_plain_routines=True)
   engine=vm._compiled();program=parse('x=1;')
   engine.prepare(program,allow_reprepare=False,module_entry=True)
   before=(len(engine._owned.memo),len(engine._owned.versions),len(engine._python_units))
   for _ in range(10):engine.prepare(program,allow_reprepare=False,module_entry=True)
   self.assertEqual(before,(len(engine._owned.memo),len(engine._owned.versions),len(engine._python_units)))
