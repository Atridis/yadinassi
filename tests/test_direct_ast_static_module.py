import unittest
from decimal import Decimal as D
from unittest.mock import patch
from yadinassi import Interpreter
from yadinassi.syntax.parser import parse
from yadinassi.python_direct_static_module import analyze
from yadinassi import python_direct
from direct_ast_text_oracle import compile_module as oracle

class StaticModuleTests(unittest.TestCase):
    def compare(self,source):
        results=[]
        for enabled in (False,True):
            vm=Interpreter();self.addCleanup(vm.close)
            with patch.object(python_direct,'_compile',python_direct._compile if enabled else oracle):
                plan=vm.prepare_program(parse(source))
            if True:
                try:vm.execute_prepared(plan);error=None
                except Exception as exc:error=(type(exc).__name__,str(exc))
            results.append(({key:list(value) if isinstance(value,list) else value for key,value in vm.variables.items()},error))
        self.assertEqual(results[0],results[1]);return results[1]
    def test_nested_loops_alias_branches_and_write(self):
        state,error=self.compare('A=New Array;B=A;R=0;For I=1 To 4 Do For J=1 To 3 Do If J=2 Then B.Add(I*J);Else A.Add(I+J);EndIf;EndDo;EndDo;I=0;While I<A.Count() Do R=R+A[I];A[I]=A[I]+1;I=I+1;EndDo;')
        self.assertIsNone(error);self.assertEqual(len(state['a']),12)
    def test_errors_preserve_reached_state(self):
        for source in ('A=New Array;A.Add(4);R=7;R=A[99];After=1;', 'R=1;For I=0 To 3 Do R=10/(2-I);EndDo;After=1;'):
            with self.subTest(source=source):self.compare(source)
    def test_zero_iterations_and_conditional_binding(self):
        self.compare('R=1;For I=3 To 1 Do Hidden=9;EndDo;If R=1 Then X=2;Else X=3;EndIf;R=R+X;')
    def test_dynamic_inputs_and_callbacks_decline(self):
        for source in ('R=Incoming+1;', 'A=New Array;Host(A);', 'Execute("X=1;");', 'R=Eval("1");'):
            self.assertIsNone(analyze(parse(source)))
    def test_local_generated_path_uses_no_state_reads(self):
        vm=Interpreter();self.addCleanup(vm.close)
        plan=vm.prepare_program(parse('A=New Array;For I=0 To 4 Do A.Add(I);EndDo;R=A[2]+A.Get(1);'))
        fast=plan._plan.generated_source
        self.assertEqual(fast.count('_initial.get'),3);self.assertNotIn('_partial',fast)
        vm.execute_prepared(plan);self.assertEqual(vm.variables['r'],D(3))

if __name__=='__main__':unittest.main()
