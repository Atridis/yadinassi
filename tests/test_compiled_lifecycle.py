from compiled_contract_fixture import mutable_compiled_contract
"""Runtime-owned strict compiler lifetime and late scheduler context regressions."""
from decimal import Decimal
import unittest
from unittest.mock import patch
from yadinassi.compiled_backend import Engine

from yadinassi import Interpreter
from yadinassi.syntax.parser import parse


class CompiledLifecycleTests(unittest.TestCase):
    def setUp(self):
        super().setUp()
        stats = patch.object(Engine, 'DETAILED_INLINE_STATS', True)
        stats.start(); self.addCleanup(stats.stop)

    def vm(self):
        return Interpreter(execution_backend='compiled-strict')

    def assert_released(self, vm):
        engine = vm._compiled()
        self.assertEqual(engine.active_frames, 0)
        self.assertEqual(engine._nodes, {})
        self.assertEqual(engine._blocks, {})

    @mutable_compiled_contract
    def test_repeated_host_routine_calls_release_materialized_plans(self):
        vm = self.vm()
        vm.execute('Function F(Val x=1) Return x+2; EndFunction')
        self.assert_released(vm)
        for value in range(12):
            result = vm.visit(parse(f'F({value});')[0].expression)
            self.assertEqual(result, Decimal(value + 2))
            self.assert_released(vm)
        self.assertGreater(vm.compiled_backend_stats['emitted_executions'], 12)
        self.assertEqual(vm.compiled_backend_stats['interpreter_fallbacks'], 0)

    def pending_vm(self):
        vm = self.vm()
        signal = vm._scheduler.new_pending()
        vm.register_function('Signal', lambda: signal)
        vm.execute('Async Function F() Return Await Signal(); EndFunction p=F();')
        self.assertTrue(vm.pending_promises)
        self.assertGreater(vm._compiled().active_frames, 0)
        self.assertTrue(vm._compiled()._nodes)
        return vm, signal

    @mutable_compiled_contract
    def test_pending_plans_survive_until_settlement(self):
        vm, signal = self.pending_vm()
        vm._scheduler.resolve(signal, Decimal(9))
        self.assertTrue(vm._compiled()._nodes)
        vm.run_until_idle()
        self.assertEqual(vm.variables['p'].result, Decimal(9))
        self.assert_released(vm)

    @mutable_compiled_contract
    def test_reset_closes_suspended_frames_before_release(self):
        vm, signal = self.pending_vm()
        vm._scheduler.reset()
        self.assertEqual(vm.pending_promises, ())
        self.assert_released(vm)

    @mutable_compiled_contract
    def test_late_host_callback_child_inherits_strict_scheduler_policy(self):
        from yadinassi.execution_policy import current_backend
        entry_backend = current_backend()
        vm = self.vm()
        signal = vm._scheduler.new_pending()
        vm.register_function('Signal', lambda: signal)
        children = []
        def child():
            other = Interpreter()
            children.append(other)
            other.execute('r=40+2;')
            return other.variables['r']
        vm.register_function('Child', child)
        vm.execute('Async Function F() x=Await Signal(); Return Child(); EndFunction p=F();')
        self.assertFalse(children)
        vm._scheduler.resolve(signal)
        vm.run_until_idle()
        self.assertEqual(vm.variables['p'].result, Decimal(42))
        self.assertEqual(children[0].execution_backend, 'compiled-strict')
        self.assertGreater(children[0].compiled_backend_stats['emitted_executions'], 0)
        self.assert_released(children[0])
        self.assert_released(vm)
        # Scheduler scope must not leak into subsequent unrelated embedding.
        self.assertEqual(Interpreter().execution_backend, entry_backend)

    def test_error_path_releases_finished_plans(self):
        vm = self.vm()
        with self.assertRaises(Exception):
            vm.execute('r=1/0;')
        self.assert_released(vm)


if __name__ == '__main__':
    unittest.main()

class LegacyCompatibilityTests(unittest.TestCase):
    def test_legacy_for_and_known_receiver_preserve_name_override(self):
        class Observed(Interpreter):
            def __init__(self):
                super().__init__(execution_backend='interpreter')
                self.reads = []
            def visit_Name(self, node):
                self.reads.append(node.name.casefold())
                return super().visit_Name(node)
        vm = Observed()
        vm.execute('For i=1 To 2 Do EndDo; x=7;')
        self.assertGreaterEqual(vm.reads.count('i'), 5)
        node = parse('x;')[0].expression
        self.assertEqual(vm.known_receiver(node), Decimal(7))
        self.assertEqual(vm.reads[-1], 'x')

class ReentrantAdmissionTests(unittest.TestCase):
    @mutable_compiled_contract
    def test_reentrant_root_cannot_readmit_mutated_active_routine(self):
        from yadinassi.compiled_backend import CompiledUnsupported
        vm = Interpreter(execution_backend='compiled-strict')
        program = parse('Procedure Original() Message("original"); EndProcedure Mutate(); Original();')
        def mutate():
            program[0].body[0].expression.arguments[0].value = 'changed'
            vm.execute_program([program[0]])
        vm.register_function('Mutate', mutate, returns_value=False)
        with self.assertRaises(CompiledUnsupported):
            vm.execute_program(program)
