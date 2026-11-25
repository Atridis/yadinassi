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
