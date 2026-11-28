"""Ordinary For Each uses Python's loop; BSL-specific behavior stays at the edges."""
import ast
import unittest
from decimal import Decimal

from yadinassi import Interpreter
from yadinassi.execution.codegen.direct_boundaries import BoundaryViolation


class DirectForEachLoweringTests(unittest.TestCase):
    def vm(self, **kwargs):
        vm = Interpreter(**kwargs)
        self.addCleanup(vm.close)
        return vm

    def test_untyped_inputs_use_for_with_no_next_or_exception_ladder(self):
        source = 'N=0; For Each X In A Do If X=2 Then Continue; EndIf; N=N+X; If X=3 Then Break; EndIf; EndDo;'
        vm = self.vm()
        plan = vm.prepare(source)
        emitted = ast.parse(plan._plan.generated_source)
        loops = [node for node in ast.walk(emitted) if isinstance(node, (ast.For, ast.While))]
        self.assertEqual([type(node) for node in loops], [ast.For])
        self.assertFalse(any(isinstance(node, ast.Name) and node.id in ('next', 'StopIteration')
                             for node in ast.walk(emitted)))
        vm.variables['a'] = [Decimal(i) for i in (1, 2, 3, 4)]
        vm.execute_prepared(plan)
        self.assertEqual((vm.variables['n'], vm.variables['x']), (Decimal(4), Decimal(3)))
        vm.variables['a'] = []
        vm.execute_prepared(plan)
        self.assertEqual((vm.variables['n'], vm.variables['x']), (Decimal(0), Decimal(3)))

    def test_routine_can_use_same_slot_for_input_and_loop_and_keeps_empty_slot(self):
        vm = self.vm()
        source = '''Function F(Val A)
        For Each A In A Do EndDo; Return A;
        EndFunction
        Empty=F(New Array); X=New Array; X.Add(1); X.Add(2); Last=F(X);'''
        vm.execute(source)
        self.assertEqual(vm.variables['empty'], [])
        self.assertEqual(vm.variables['last'], 2)

    def test_map_entries_are_live_and_structural_mutation_is_catchable(self):
        vm = self.vm()
        plan = vm.prepare('''M=New Map; M.Insert("a",1); M.Insert("b",2);
        S=0; For Each P In M Do S=S+P.Value; M.Insert("b",9); EndDo;
        N=0; Caught=False;
        Try For Each P In M Do N=N+1; M.Insert("c",3); EndDo;
        Except Caught=True; EndTry;''')
        vm.execute_prepared(plan)
        self.assertEqual((vm.variables['s'], vm.variables['n'], vm.variables['caught']), (10, 1, True))

    def test_unadmitted_iterator_does_not_call_python_dunder(self):
        effects = []
        class Foreign:
            def __iter__(self):
                effects.append(True)
                return iter(())
        class SequenceProtocol:
            def __getitem__(self, index):
                effects.append(index)
                raise IndexError(index)

        source = 'For Each X In A Do EndDo; After=True;'
        for prepared in (False, True):
            for value in (Foreign(), SequenceProtocol()):
                with self.subTest(prepared=prepared, protocol=type(value).__name__):
                    effects.clear()
                    vm = self.vm()
                    vm.variables['a'] = value
                    with self.assertRaises(BoundaryViolation):
                        if prepared:
                            vm.execute_prepared(vm.prepare(source))
                        else:
                            vm.execute(source)
                    self.assertEqual(effects, [])
                    self.assertNotIn('after', vm.variables)

    def test_iterates_native_fixed_map_snapshot(self):
        vm = self.vm()
        vm.execute('M=New Map; M.Insert("a",3); F=New FixedMap(M);'
                   'N=0; For Each Pair In F Do N=N+Pair.Value; EndDo;')
        self.assertEqual(vm.variables['n'], 3)

    def test_inline_native_array_needs_no_iteration_adapter(self):
        vm = self.vm()
        plan = vm.prepare('N=0; For Each X In New Array(2) Do N=N+1; EndDo;')
        tree = ast.parse(plan._plan.generated_source)
        loop = next(node for node in ast.walk(tree) if isinstance(node, ast.For))
        self.assertEqual(loop.iter.func.id, '_Array')
        vm.execute_prepared(plan)
        self.assertEqual(vm.variables['n'], 2)
