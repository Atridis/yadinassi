"""Direct lifecycle behavior; deleted Engine registry/tier assertions removed."""
from decimal import Decimal
import unittest
from yadinassi import Interpreter

class CompiledLifecycleTests(unittest.TestCase):
    def vm(self):
        return Interpreter(execution_backend='python-direct')

    def test_repeated_host_routine_calls_return_values(self):
        vm = self.vm()
        vm.execute('Function F(Val x=1) Return x+2; EndFunction')
        for value in range(12):
            result = vm.execute(f'F({value});')
            self.assertEqual(result, Decimal(value + 2))

    def pending_vm(self):
        vm = self.vm()
        signal = vm._scheduler.new_pending()
        vm.register_function('Signal', lambda: signal)
        vm.execute('Async Function F() Return Await Signal(); EndFunction p=F();')
        self.assertTrue(vm.pending_promises)
        return vm, signal

    def test_pending_result_survives_until_settlement(self):
        vm, signal = self.pending_vm()
        vm._scheduler.resolve(signal, Decimal(9))
        vm.run_until_idle()
        self.assertEqual(vm.variables['p'].result, Decimal(9))

    def test_reset_clears_pending_promises(self):
        vm, signal = self.pending_vm()
        vm._scheduler.reset()
        self.assertEqual(vm.pending_promises, ())

    def test_late_host_callback_child_inherits_strict_scheduler_policy(self):
        from yadinassi.execution.execution_policy import current_backend
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
        self.assertEqual(children[0].execution_backend, 'python-direct')
        # Scheduler scope must not leak into subsequent unrelated embedding.
        self.assertEqual(Interpreter().execution_backend, entry_backend)

    def test_execution_error_propagates(self):
        vm = self.vm()
        with self.assertRaises(Exception):
            vm.execute('r=1/0;')
