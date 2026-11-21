import unittest
from types import CodeType
from decimal import Decimal as D
from yadinassi import Interpreter
from yadinassi.types.errors import BSLRuntimeError
from yadinassi.syntax.parser import parse
from yadinassi.execution.direct.python_direct_static_module import analyze

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
            ('R=1;For I=0 To 3 Do R=10/(2-I);EndDo;After=1;', 'Деление на ноль', {'i':D(2),'r':D(10)}),
        )
        for source,message,expected in cases:
            with self.subTest(source=source):
                vm,plan=self.prepare(source)
                with self.assertRaisesRegex(BSLRuntimeError,message):vm.execute_prepared(plan)
                state={name:list(value) if isinstance(value,list) else value
                       for name,value in vm.variables.items()}
                self.assertEqual(state,expected)

    def test_array_bounds_error_preserves_site_and_reached_state(self):
        source = 'A=New Array;A.Add(4);R=7;\nR=A[99];\nAfter=1;'
        for prepared in (False, True):
            with self.subTest(prepared=prepared):
                vm = Interpreter()
                self.addCleanup(vm.close)
                with self.assertRaises(BSLRuntimeError) as raised:
                    if prepared:
                        vm.execute_prepared(vm.prepare(source, 'bounds.bsl'))
                    else:
                        vm.execute(source, 'bounds.bsl')
                error = raised.exception
                self.assertIsInstance(error.__context__, IndexError)
                self.assertEqual((error.source, error.line, error.source_line),
                                 ('bounds.bsl', 2, 'R=A[99];'))
                self.assertEqual(error.column, 4 if hasattr(CodeType, 'co_positions') else 1)
                self.assertEqual(set(vm.variables), {'a', 'r'})
                array = vm.variables['a']
                self.assertEqual((list(array), vm.variables['r']), ([D(4)], D(7)))
                vm.execute('Caught=False;Try R=A[99];Except Caught=True;EndTry;After=A[0];')
                self.assertIs(vm.variables['a'], array)
                self.assertEqual(list(array), [D(4)])
                self.assertEqual((vm.variables['r'], vm.variables['after']), (D(7), D(4)))
                self.assertIs(vm.variables['caught'], True)

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
