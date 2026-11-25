"""The production generator leaves ordinary operations as Python syntax."""
import ast
from contextlib import closing
from decimal import Decimal
import unittest

from yadinassi import BSLError, Interpreter


class DirectDefaultLoweringTests(unittest.TestCase):
    def test_local_assign_arithmetic_if_while_and_call_are_python_nodes(self):
        source = """Function Increment(Val X)
    Return X + 1;
EndFunction
Function Run()
    S = 0;
    While S < 4 Do
        If S = 0 Then
            S = Increment(S);
        Else
            S = S + 1;
        EndIf;
    EndDo;
    Return S;
EndFunction
Run()
"""
        with closing(Interpreter()) as vm:
            plan = vm.prepare(source)
            self.assertEqual(vm.execute_prepared(plan), Decimal(4))
            tree = ast.parse(plan._plan.generated_source)
        routines = {
            item.name: item for item in ast.walk(tree)
            if isinstance(item, ast.FunctionDef) and item.name != 'naked_module'
        }
        loops = [node for node in ast.walk(tree) if isinstance(node, ast.While)]
        self.assertEqual(len(loops), 1)
        loop = loops[0]
        self.assertIsInstance(loop.test, ast.Compare)
        branch, = loop.body
        self.assertIsInstance(branch, ast.If)
        self.assertIsInstance(branch.test, ast.Compare)
        call = branch.body[0].value
        self.assertIn(call.func.id, routines)
        self.assertIsInstance(branch.orelse[0].value, ast.BinOp)
        self.assertFalse(any(isinstance(node, ast.Call) and node is not call
                             for node in ast.walk(loop)))

    def test_bsl_condition_accepts_generated_whole_numbers_and_rejects_text(self):
        with closing(Interpreter()) as vm:
            self.assertEqual(vm.execute('X=2; If X Then R=1; Else R=0; EndIf; R'), Decimal(1))
            self.assertEqual(vm.execute('X=0; If X Then R=1; Else R=0; EndIf; R'), Decimal(0))
            with self.assertRaisesRegex(BSLError, 'булево значение или число'):
                vm.execute('X="nonempty"; If X Then R=1; EndIf;')

    def test_foreach_map_observes_entries_not_python_dict_keys(self):
        with closing(Interpreter()) as vm:
            self.assertEqual(vm.execute('M=New Map; M.Insert("A",2); R=0; '
                                       'For Each Pair In M Do R=R+Pair.Value; EndDo; R'), Decimal(2))

    def test_empty_suites_only_emit_pass_when_python_requires_it(self):
        with closing(Interpreter()) as vm:
            source = 'If True Then X=1; EndIf; If False Then EndIf;'
            plan = vm.prepare(source)
            vm.execute_prepared(plan)
            self.assertEqual(vm.variables['x'], Decimal(1))
            tree = ast.parse(plan._plan.generated_source)
            branches = [node for node in ast.walk(tree) if isinstance(node, ast.If)]
            self.assertTrue(all(not branch.orelse for branch in branches))
            self.assertEqual(sum(isinstance(node, ast.Pass) for node in ast.walk(tree)), 1)
            empty = ast.parse(vm.prepare('')._plan.generated_source).body[0]
            self.assertEqual([arg.arg for arg in empty.args.args], ['_S', '_K', '_C', '_Bind'])
            self.assertEqual([type(node) for node in empty.body], [ast.Return])

    def test_for_literals_are_direct_and_dynamic_bounds_are_evaluated_once(self):
        with closing(Interpreter()) as vm:
            generated = vm.prepare('For I=1 To 3 Do EndDo;')._plan.generated_source
            self.assertIn('i = 1\n    while i <= 3:', generated)
            self.assertNotIn('pass', generated)
            source = '''Var I, Trace;
Function First()
    Trace=Trace+"F"; Return 1;
EndFunction
Function Last()
    Trace=Trace+String(I); Return 3;
EndFunction
Trace=""; I=9; Sum=0;
For I=First() To Last() Do Sum=Sum+I; EndDo;
'''
            vm.execute(source)
            self.assertEqual(vm.variables['trace'], 'F9')
            self.assertEqual(vm.variables['sum'], Decimal(6))
            self.assertEqual(vm.variables['i'], Decimal(4))

    def test_constructor_result_uses_python_iteration_without_general_dispatch(self):
        with closing(Interpreter()) as vm:
            source = 'R=0; For Each X In New Array(3) Do R=R+1; EndDo; R'
            plan = vm.prepare(source)
            self.assertEqual(vm.execute_prepared(plan), Decimal(3))
            self.assertIn('for x in _Array(3):', plan._plan.generated_source)
            self.assertNotIn('_BSLIterable', plan._plan.generated_source)

    def test_member_dispatch_tracks_rebinding_without_type_proof(self):
        with closing(Interpreter()) as vm:
            source = """Function Result(Val A)
    Return A.Count();
EndFunction
A=New Array(3); First=Result(A);
A=New Map; A.Insert("k",42); Second=Result(A);
"""
            vm.execute(source)
            self.assertEqual(vm.variables['first'], Decimal(3))
            self.assertEqual(vm.variables['second'], Decimal(1))
            with self.assertRaises(BSLError):
                vm.execute('A=New Array; Result=A.Add(1);')

    def test_builtin_name_can_be_resolved_to_a_bsl_routine(self):
        with closing(Interpreter()) as vm:
            self.assertEqual(vm.execute('''
Function StrLen(Val Text)
    Return 17;
EndFunction
StrLen("foo")
'''), Decimal(17))

    def test_prepared_builtin_call_observes_extension_rebinding(self):
        with closing(Interpreter(allow_extensions=True)) as vm:
            plan = vm.prepare('StrLen("foo")')
            self.assertEqual(vm.execute_prepared(plan), Decimal(3))
            vm.register_function('StrLen', lambda _: Decimal(17))
            self.assertEqual(vm.execute_prepared(plan), Decimal(17))
