"""Behavior retained from retired translation engines; only the direct backend runs.

Implementation-only registry, fusion emitter, instrumentation and inline-budget
checks belonged to deleted engines and are retired, not skipped or emulated.
Unsupported behavioral cases deliberately remain ordinary failing tests.
"""
import unittest
from decimal import Decimal
from unittest.mock import patch
from yadinassi import Interpreter, BSLError
class DirectAsyncBehavior(unittest.TestCase):

    def run_vm(self, source, setup=lambda vm: None):
        vm = Interpreter()
        self.addCleanup(vm.close)
        setup(vm)
        vm.execute(source)
        return vm

    def test_real_async_scalar(self):
        vm = self.run_vm('Async Function F(Val x) Return (Await x)+1;EndFunction p=F(3);')
        self.assertEqual(vm.variables['p'].result, 4)
        self.assertIsNone(vm.locals)

    def test_pending_siblings_restore_context(self):

        def setup(vm):
            vm.signal = vm._scheduler.new_pending()
            vm.register_function('Signal', lambda: vm.signal)
        vm = self.run_vm('Async Function F(Val n) local=n;x=Await Signal();Return local+x;EndFunction a=F(10);b=F(20);', setup)
        self.assertEqual(vm.variables['a'].state, 'pending')
        vm._scheduler.resolve(vm.signal, Decimal(3))
        vm.run_until_idle()
        self.assertEqual(vm.variables['a'].result, 13)
        self.assertEqual(vm.variables['b'].result, 23)
        self.assertIsNone(vm.locals)
        self.assertEqual(vm._context_stack, ['client'])
        self.assertFalse(vm.pending_promises)

    def test_close_pending_releases_tasks(self):

        def setup(vm):
            vm.signal = vm._scheduler.new_pending()
            vm.register_function('Signal', lambda: vm.signal)
        vm = self.run_vm('Async Function F() Return Await Signal();EndFunction p=F();', setup)
        self.assertTrue(vm.pending_promises)
        vm.close()
        self.assertFalse(vm._scheduler._tasks)
        self.assertIsNone(vm.locals)
