import unittest
from unittest.mock import patch
from yadinassi.runtime import Interpreter
from yadinassi.compiled_backend import Engine,CompiledUnsupported

class ForceControlsTests(unittest.TestCase):
 def test_declarations_and_exception_blocks_without_adapter(self):
  cases=['Function F(Val x) Return x+1;EndFunction',
   'x=1;Try x=2;y=1/0;Except r=x+1;EndTry;',
   'x=1;Try x=2;Except x=3;EndTry;r=x;',
   'Try Try x=1/0;Except y=2;EndTry;Except y=3;EndTry;']
  for source in cases:
   outcomes=[]
   for backend in ('interpreter','compiled-strict'):
    vm=Interpreter(execution_backend=backend,compiled_plain_routines=True)
    with patch.object(Engine,'FORCE_PYTHON_TRANSLATION',True):
     result=vm.execute(source)
    outcomes.append((result,{k:vm.variables[k] for k in ('x','y','r') if k in vm.variables}))
    if backend=='compiled-strict':
     self.assertGreater(vm.compiled_backend_stats.get('python_translated_blocks',0),0)
     self.assertEqual(vm.compiled_backend_stats.get('plain_adapter_blocks',0),0)
     self.assertEqual(vm.compiled_backend_stats['interpreter_fallbacks'],0)
    self.assertEqual(vm._handled_errors,[])
   self.assertEqual(*outcomes)
 def test_unsupported_syntax_rejected_before_host_effect(self):
  vm=Interpreter(execution_backend='compiled-strict',compiled_plain_routines=True);seen=[]
  vm.register_function('Host',lambda:seen.append(1))
  from yadinassi.syntax import ast
  from yadinassi.syntax.parser import parse
  class UnsupportedStatement(ast.Node):pass
  program=parse('Host();');program.append(UnsupportedStatement(program[0].token))
  with patch.object(Engine,'FORCE_PYTHON_TRANSLATION',True),self.assertRaises(CompiledUnsupported):
   vm._compiled().prepare(program)
   vm._scheduler.run_inline(vm.block(program))
  self.assertEqual(seen,[])

 def test_supported_registered_host_executes_once_without_adapter(self):
  vm=Interpreter(execution_backend='compiled-strict');seen=[]
  vm.register_function('Host',lambda:seen.append(1) or 7)
  with patch.object(Engine,'FORCE_PYTHON_TRANSLATION',True):vm.execute('r=Host();')
  self.assertEqual(seen,[1]);self.assertEqual(vm.variables['r'],7)
  self.assertGreater(vm.compiled_backend_stats.get('python_translated_blocks',0),0)
  self.assertEqual(vm.compiled_backend_stats.get('plain_adapter_blocks',0),0)
  self.assertEqual(vm.compiled_backend_stats['interpreter_fallbacks'],0)
