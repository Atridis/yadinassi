import unittest
from unittest.mock import patch
from yadinassi.runtime import Interpreter
from yadinassi.compiled_backend import Engine, CompiledUnsupported

class BlockFusionTests(unittest.TestCase):
    def pair(self, code):
        outputs=[]
        for backend in ('interpreter','compiled-strict'):
            with patch.object(Engine,'FORCE_PYTHON_TRANSLATION',True):
                vm=Interpreter(execution_backend=backend,compiled_plain_routines=True)
                error=None
                try: vm.execute(code)
                except Exception as exc: error=(type(exc).__name__,str(exc))
                from yadinassi.values import BSLArray
                outputs.append(({k: list(v.items) if type(v) is BSLArray else v for k,v in vm.variables.items()},error))
                self.assertIsNone(vm.locals)
                self.assertEqual(vm._compiled().active_frames,0)
                if backend=='compiled-strict':
                    self.assertEqual(vm.compiled_backend_stats.get('interpreter_fallbacks',0),0)
                    self.last=vm
        self.assertEqual(outputs[0],outputs[1])
        return outputs[1]
    @patch.object(Engine, "DETAILED_INLINE_STATS", True)
    def test_nested_loops_bounds_continue_break(self):
        result,_=self.pair('s=0; For i=1 To 3 Do For j=1 To 5 Do If j=2 Then Continue; EndIf; If j=4 Then Break; EndIf; s=s+i*j; EndDo; EndDo;')
        self.assertEqual(result['s'],24)
        self.assertGreater(self.last.compiled_backend_stats['python_inlined_blocks'],0)
    def test_while_foreach_nested(self):
        self.pair('a=New Array; a.Add(1);a.Add(2);s=0; For Each x In a Do j=0; While j<3 Do j=j+1; s=s+x;EndDo;EndDo;')
    def test_nested_try_return_byref(self):
        self.pair('Function F(x) Try For i=1 To 3 Do x=x+1; If i=2 Then Return x;EndIf;EndDo; Except x=99;EndTry;EndFunction x=4;r=F(x);')
    def test_nested_handler_and_parent_result(self):
        self.pair('x=0;Try Try x=1;Raise "inner";Except x=x+1;EndTry;Raise "outer";Except x=x+10;EndTry;')
    def test_partial_error_state(self):
        self.pair('x=0;For i=1 To 3 Do If i=2 Then x=x+1;z=1/0;EndIf; x=x+10;EndDo;')
    def test_goto_crosses_inlined_body(self):
        self.pair('x=0;While True Do If True Then x=1;Goto ~done;EndIf;EndDo;~done:x=x+2;')
    def test_nested_label_dispatch_remains_generated(self):
        self.pair('x=0;If True Then ~again:x=x+1;If x<3 Then Goto ~again;EndIf;EndIf;')
    def test_straightline_bytecode_has_no_pc(self):
        with patch.object(Engine,'FORCE_PYTHON_TRANSLATION',True):
            vm=Interpreter(execution_backend='compiled-strict',compiled_plain_routines=True)
            from yadinassi.syntax.parser import parse
            vm._compiled().prepare(parse('x=1;y=2;'),module_entry=True)
            units={id(u):u for _,u in vm._compiled()._python_units.values()}
            for unit in units.values():
                for _,fn in unit.blocks.values():self.assertNotIn('pc',fn.__code__.co_varnames)
    def test_admission_cap_before_effects(self):
        with patch.object(Engine,'FORCE_PYTHON_TRANSLATION',True):
            vm=Interpreter(execution_backend='compiled-strict',compiled_plain_routines=True)
            vm._compiled().MAX_INLINE_FUNCTION_BYTES=1000
            with self.assertRaises(CompiledUnsupported):vm.execute('x=1;For i=1 To 3 Do If True Then x=x+1;EndIf;EndDo;')
            self.assertNotIn('x',vm.variables)

class ResultLifetimeTests(unittest.TestCase):
 def test_previous_statement_result_lives_through_next_call(self):
  import weakref
  class Payload:pass
  outcomes=[]
  for backend,force in (('interpreter',False),('compiled-strict',True)):
   references=[];seen=[]
   vm=Interpreter(execution_backend=backend,compiled_plain_routines=True)
   def make():
    value=Payload();references.append(weakref.ref(value));return value
   vm.register_function('Make',make)
   vm.register_function('Check',lambda:seen.append(references[-1]() is not None))
   with patch.object(Engine,'FORCE_PYTHON_TRANSLATION',force):vm.execute('Make();Check();')
   outcomes.append(seen)
  self.assertEqual(outcomes,[[True],[True]])

 def test_discarded_nested_block_result_not_pinned_after_handler(self):
  import weakref,gc
  class Payload:pass
  outcomes=[]
  for backend,force in (('interpreter',False),('compiled-strict',True)):
   references=[];seen=[]
   vm=Interpreter(execution_backend=backend,compiled_plain_routines=True)
   def make():
    value=Payload();references.append(weakref.ref(value));return value
   def check():gc.collect();seen.append(references[-1]() is not None)
   vm.register_function('Make',make);vm.register_function('Check',check)
   with patch.object(Engine,'FORCE_PYTHON_TRANSLATION',force):
    vm.execute('Try Make();Raise "failure";Except x=1;EndTry;Check();')
   outcomes.append(seen)
  self.assertEqual(outcomes,[[False],[False]])

class EntryBudgetTests(unittest.TestCase):
 def test_inlined_descendants_keep_metadata_without_duplicate_functions(self):
  from yadinassi.syntax.parser import parse
  from yadinassi.owned_syntax import syntax_kind
  from yadinassi.syntax import ast
  with patch.object(Engine,'FORCE_PYTHON_TRANSLATION',True):
   vm=Interpreter(execution_backend='compiled-strict')
   engine=vm._compiled()
   engine.prepare(parse('If True Then x=1;If True Then x=x+1;EndIf;EndIf;'),module_entry=True)
   units={id(unit):unit for _,unit in engine._python_units.values()}
   self.assertEqual(len(units),1)
   unit=next(iter(units.values()))
   self.assertEqual(sum(fn is not None for _,fn in unit.blocks.values()),1)
   nested=[block for block,fn in unit.blocks.values() if fn is None and block]
   self.assertTrue(nested)
   for block in nested:engine._verify_owned_identity(block)
   # An explicitly requested preflight is a legitimate new entry, not fallback.
   body=nested[0]
   engine.prepare_block(body)
   admitted,entry=engine._python_units[tuple(id(node) for node in body)]
   self.assertIs(admitted,body)
   self.assertIsNotNone(entry.blocks[tuple(id(node) for node in body)][1])
 def test_retained_routine_keeps_inlined_descendant_metadata(self):
  with patch.object(Engine,'FORCE_PYTHON_TRANSLATION',True):
   vm=Interpreter(execution_backend='compiled-strict')
   vm.execute('Function F(Val x) If x>0 Then While x<3 Do x=x+1;EndDo;EndIf;Return x;EndFunction')
   vm.execute('unrelated=5;')
   vm.execute('r=F(1);')
   self.assertEqual(vm.variables['r'],3)
   self.assertEqual(vm.compiled_backend_stats.get('interpreter_fallbacks',0),0)

class RetainedSingletonTests(unittest.TestCase):
 def test_retained_single_execute_body_keeps_original_owned_identity(self):
  with patch.object(Engine,'FORCE_PYTHON_TRANSLATION',True):
   vm=Interpreter(execution_backend='compiled-strict')
   vm.execute('Procedure F() Execute("x=3;");EndProcedure')
   vm.execute('other=1;')
   vm.execute('F();')
   self.assertEqual(vm.compiled_backend_stats.get('interpreter_fallbacks',0),0)
