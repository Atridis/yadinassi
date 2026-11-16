import unittest
from decimal import Decimal
from unittest.mock import patch
from yadinassi import Interpreter
from yadinassi.compiled_backend import Engine
from yadinassi.async_runtime import AwaitRequest
from yadinassi.python_translation_expressions import prepare_expressions
from yadinassi.syntax.parser import parse

class TranslatedAwait(unittest.TestCase):
    def run_vm(self,source,setup=lambda vm:None):
        vm=Interpreter(execution_backend='compiled-strict',compiled_plain_routines=True)
        setup(vm)
        with patch.object(Engine,'FORCE_PYTHON_TRANSLATION',True): vm.execute(source)
        return vm

    def test_real_async_scalar(self):
        vm=self.run_vm('Async Function F(Val x) Return (Await x)+1;EndFunction p=F(3);')
        self.assertEqual(vm.variables['p'].result,4)
        self.assertEqual(vm.compiled_backend_stats['interpreter_fallbacks'],0)
        self.assertEqual(vm.compiled_backend_stats['inline_fragments'],0)
        self.assertIsNone(vm.locals)

    def test_pending_siblings_restore_context(self):
        def setup(vm):
            vm.signal=vm._scheduler.new_pending(); vm.register_function('Signal',lambda:vm.signal)
        vm=self.run_vm('Async Function F(Val n) local=n;x=Await Signal();Return local+x;EndFunction a=F(10);b=F(20);',setup)
        self.assertEqual(vm.variables['a'].state,'pending')
        vm._scheduler.resolve(vm.signal,Decimal(3))
        with patch.object(Engine,'FORCE_PYTHON_TRANSLATION',True): vm.run_until_idle()
        self.assertEqual(vm.variables['a'].result,13);self.assertEqual(vm.variables['b'].result,23)
        self.assertIsNone(vm.locals);self.assertEqual(vm._context_stack,['client'])
        self.assertFalse(vm.pending_promises)

    def test_close_pending_releases_tasks(self):
        def setup(vm):
            vm.signal=vm._scheduler.new_pending();vm.register_function('Signal',lambda:vm.signal)
        vm=self.run_vm('Async Function F() Return Await Signal();EndFunction p=F();',setup)
        self.assertTrue(vm.pending_promises)
        vm.close()
        self.assertFalse(vm._scheduler._tasks);self.assertIsNone(vm.locals)

    def test_resume_rechecks_authority_before_result(self):
        node=parse('Async Function F() Return Await 1;EndFunction')[0].body[0].value
        vm=Interpreter(); seen=[]; allowed=[True]
        def guard(node):
            seen.append(node)
            if not allowed[0]:raise PermissionError('revoked')
        task=prepare_expressions([node]).bind(vm,guard=guard,access=None).evaluate(node)
        self.assertIsInstance(next(task),AwaitRequest)
        allowed[0]=False
        with self.assertRaisesRegex(PermissionError,'revoked'):task.send(Decimal(2))
        self.assertIs(seen[-1],node)
