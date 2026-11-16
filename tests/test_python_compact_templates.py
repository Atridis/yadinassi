import unittest
from unittest.mock import patch
from yadinassi import Interpreter
from yadinassi import python_translation_blocks as blocks
from yadinassi.python_translation_expressions import prepare_expressions
from yadinassi.syntax.parser import parse

class CompactTemplateTests(unittest.TestCase):
 def run_mode(self,source,backend):
  original=blocks.prepare_blocks
  def compact(*args,**kwargs):kwargs['compact_control']=True;return original(*args,**kwargs)
  with patch.object(blocks,'prepare_blocks',compact):
   vm=Interpreter(execution_backend=backend);error=None
   try:vm.execute(source)
   except Exception as exc:error=(type(exc).__name__,str(exc))
   self.assertIsNone(vm.locals)
   self.assertEqual(vm._compiled().active_frames,0)
   if backend=='compiled-strict':
    self.assertGreater(vm.compiled_backend_stats.get('python_compact_statement_calls',0),0)
    self.assertEqual(vm.compiled_backend_stats.get('interpreter_fallbacks',0),0)
   return dict(vm.variables),error
 def test_nested_control_goto_and_partial_errors(self):
  for source in (
   's=0;For i=1 To 3 Do For j=1 To 5 Do If j=2 Then Continue;EndIf;If j=4 Then Break;EndIf;s=s+i*j;EndDo;EndDo;',
   'x=0;Try x=1;Raise "bad";Except x=x+4;EndTry;',
   'x=0;While True Do If True Then x=1;Goto ~done;EndIf;EndDo;~done:x=x+2;',
   'x=0;If True Then ~again:x=x+1;If x<3 Then Goto ~again;EndIf;EndIf;',
   'x=0;For i=1 To 3 Do x=x+1;If i=2 Then y=1/0;EndIf;EndDo;',
   'Function F(x) For i=1 To 3 Do x=x+1;If i=2 Then Return x;EndIf;EndDo;EndFunction x=4;r=F(x);'):
   with self.subTest(source=source):self.assertEqual(self.run_mode(source,'interpreter'),self.run_mode(source,'compiled-strict'))
 def test_expression_operator_bindings_are_not_confused(self):
  nodes=[parse('r='+source+';')[0].value for source in ('8+2','8-2','8*2','8/2')]
  plan=prepare_expressions(nodes)
  functions=[plan.functions[id(node)][1] for node in nodes]
  self.assertEqual(len({id(fn.__code__) for fn in functions}),1)
  self.assertEqual(self.run_mode('a=8+2;b=8-2;c=8*2;d=8/2;','interpreter'),self.run_mode('a=8+2;b=8-2;c=8*2;d=8/2;','compiled-strict'))
 def test_retained_compact_routine_after_repl(self):
  original=blocks.prepare_blocks
  def compact(*args,**kwargs):kwargs['compact_control']=True;return original(*args,**kwargs)
  with patch.object(blocks,'prepare_blocks',compact):
   vm=Interpreter();vm.execute('Function F(Val x=2) Return x+1;EndFunction')
   for _ in range(3):vm.execute('other=1;')
   vm.execute('r=F();');self.assertEqual(vm.variables['r'],3)
 def test_literal_payload_binding_never_hashes_or_compares_host(self):
  class Host:
   def __hash__(self):raise AssertionError('host hash')
   def __eq__(self,other):raise AssertionError('host equality')
  program=parse('x=1;');payload=Host();program[0].value.value=payload
  vm=Interpreter();vm.execute_program(program);self.assertIs(vm.variables['x'],payload)
 def test_template_operand_budget_is_not_hidden_by_code_sharing(self):
  from yadinassi.python_translation_expressions import UnsupportedExpression
  with self.assertRaises(UnsupportedExpression):prepare_expressions([parse('r=1+2;')[0].value],max_bindings=0)
