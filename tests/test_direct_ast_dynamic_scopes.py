"""Direct AST imports/Execute/Eval never invoke the old text compiler."""
from contextlib import ExitStack
from pathlib import Path
from decimal import Decimal
import tempfile
import unittest
from unittest.mock import patch
from yadinassi import Interpreter
from yadinassi.experimental_naked_boundaries import BoundaryViolation
from yadinassi import experimental_naked_collections as old
from yadinassi.syntax.parser import parse

class DirectASTDynamicScopesTests(unittest.TestCase):
    def no_old(self):
        stack=ExitStack()
        stack.enter_context(patch.object(old,'prepare',create=True,side_effect=AssertionError('old text compiler')))
        for name in ('block','call_routine','_execute_program'):
            stack.enter_context(patch.object(Interpreter,name,side_effect=AssertionError('legacy visitor')))
        return stack
    def test_nested_fragments_live_scopes_no_old_compile(self):
        source='''Var M;M=10;
Procedure P(X,Val Y)
 L=2;Execute("X=X+L;Y=99;L=8;M=M+1;Fresh=33;Later=42;");
 X=X+L;Later=1;Z=Eval("L+Y");Message(Z);
EndProcedure
X=1;Y=2;P(X,Y);Execute("");Execute(Undefined);'''
        for route in ('source','ast','prepared'):
            output=[];vm=Interpreter(output=output.append);self.addCleanup(vm.close)
            with self.no_old():
                if route=='source':vm.execute(source)
                elif route=='ast':vm.execute_program(parse(source))
                else:vm.execute_prepared(vm.prepare(source))
            self.assertEqual(output,['107']);self.assertEqual(vm.variables['x'],11)
            self.assertEqual(vm.variables['m'],11);self.assertEqual(vm.variables['y'],2)
            self.assertNotIn('fresh',vm.variables)
    def test_imported_export_dynamic_scope_and_reference(self):
        with tempfile.TemporaryDirectory() as tmp:
            main=str(Path(tmp)/'Main.bsl')
            (Path(tmp)/'Side.bsl').write_text('Var N Export;N=2;Function F(X) Export Execute("X=X+N;");Return Eval("X+1");EndFunction',encoding='utf-8')
            vm=Interpreter();self.addCleanup(vm.close)
            with self.no_old():
                vm.execute('// #Import Side.bsl\nX=4;R=Side.F(X);Side.N=8;',main)
            self.assertEqual(vm.variables['x'],6);self.assertEqual(vm.variables['r'],7)
            self.assertEqual(vm.imports['side'].interpreter.variables['n'],8)
    def test_eval_mutated_after_resolution_is_fatal_not_fallback(self):
        vm=Interpreter();self.addCleanup(vm.close);original=vm.functions['eval'];effects=[]
        def mutate():original.function=lambda text:effects.append(text);return '1'
        vm.register_function('Mutate',mutate)
        with self.no_old(),self.assertRaises(BoundaryViolation):vm.execute('Try Eval(Mutate());Except Caught=True;EndTry;')
        self.assertEqual(effects,[]);self.assertNotIn('caught',vm.variables)
    def test_eval_procedure_rejected_before_arguments_even_cached(self):
        vm=Interpreter();self.addCleanup(vm.close);effects=[]
        vm.register_function('F',lambda x:None,returns_value=False)
        vm.register_function('Effect',lambda:effects.append(1) or 1)
        for _ in range(2):
            with self.no_old():vm.execute('Try R=Eval("F(Effect())");Except Caught=True;EndTry;')
            self.assertTrue(vm.variables['caught'])
        self.assertEqual(effects,[])
    def test_fragment_reference_expires_after_return(self):
        vm=Interpreter();self.addCleanup(vm.close);refs=[]
        vm.register_function('Capture',lambda x:refs.append(x));vm.functions['capture'].reference_parameters=frozenset((0,))
        with self.no_old():vm.execute('X=2;Execute("Capture(X)");')
        with self.assertRaises(BoundaryViolation):refs[0].get()
    def test_omitted_service_slots_are_resolved_before_actual_effects(self):
        vm=Interpreter();self.addCleanup(vm.close);effects=[]
        vm.register_function('Effect',lambda:effects.append(1) or 1)
        with self.no_old():vm.execute('Try Eval(,Effect());Except Caught=True;EndTry;R="";Execute("R=StrFindByRegularExpression(""a1b2"",""[0-9]"",,,2).Value;");')
        self.assertEqual(effects,[]);self.assertEqual(vm.variables['r'],'2')
