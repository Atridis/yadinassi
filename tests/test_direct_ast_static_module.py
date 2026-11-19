import unittest
from decimal import Decimal as D
from yadinassi import Interpreter
from yadinassi.errors import BSLRuntimeError
from yadinassi.syntax.parser import parse
from yadinassi.python_direct_static_module import analyze

class StaticModuleTests(unittest.TestCase):
    def prepare(self,source):
        vm=Interpreter();self.addCleanup(vm.close)
        return vm,vm.prepare_program(parse(source))

    def test_nested_loops_alias_branches_and_write(self):
        vm,plan=self.prepare('A=New Array;B=A;R=0;For I=1 To 4 Do For J=1 To 3 Do If J=2 Then B.Add(I*J);Else A.Add(I+J);EndIf;EndDo;EndDo;I=0;While I<A.Count() Do R=R+A[I];A[I]=A[I]+1;I=I+1;EndDo;')
        vm.execute_prepared(plan)
        state=vm.variables
        self.assertIs(state['a'],state['b'])
        self.assertEqual(list(state['a']),[3,3,5,4,5,6,5,7,7,6,9,8])
        self.assertEqual(state['r'],D(56))
        self.assertEqual(state['i'],D(12))

    def test_errors_preserve_reached_state(self):
        cases=(
            ('A=New Array;A.Add(4);R=7;R=A[99];After=1;', 'index out of range', {'a':[D(4)],'r':D(7)}),
            ('R=1;For I=0 To 3 Do R=10/(2-I);EndDo;After=1;', 'Деление на ноль', {'i':D(2),'r':D(10)}),
        )
        for source,message,expected in cases:
            with self.subTest(source=source):
                vm,plan=self.prepare(source)
                with self.assertRaisesRegex(BSLRuntimeError,message):vm.execute_prepared(plan)
                state={name:list(value) if isinstance(value,list) else value
                       for name,value in vm.variables.items()}
                self.assertEqual(state,expected)

    def test_zero_iterations_and_conditional_binding(self):
        vm,plan=self.prepare('R=1;For I=3 To 1 Do Hidden=9;EndDo;If R=1 Then X=2;Else X=3;EndIf;R=R+X;')
        vm.execute_prepared(plan)
        self.assertEqual(vm.variables,{'r':D(3),'i':D(3),'x':D(2)})

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
