"""Explicit reference-oracle boundary tests plus independently selected strict ABI.

Reference cases are not compiled coverage. Private backend assignment is not a
supported switching API; a suspended frame keeps the path selected on entry.
"""
import unittest
from unittest.mock import patch
from yadinassi import Interpreter
from yadinassi.compiled_backend import Engine
from yadinassi.errors import BSLError, BSLRuntimeError
from yadinassi.syntax.parser import parse


class ReferenceVisitBoundaryTests(unittest.TestCase):
    def setup_case(self, backend='interpreter'):
        return Interpreter(execution_backend=backend), parse('42;', 'boundary.bsl')[0].expression

    def consume(self, generator):
        with self.assertRaises(StopIteration) as done:
            next(generator)
        return done.exception.value

    def test_reference_dynamic_override_and_super_remain_observable(self):
        seen=[]
        class Custom(Interpreter):
            def visit_Literal(self,node):
                seen.append('custom')
                return super().visit_Literal(node)
        vm=Custom(execution_backend='interpreter')
        original=Interpreter.visit_Literal
        def base(vm,node):
            seen.append('base');return original(vm,node)
        with patch.object(Interpreter,'visit_Literal',base):
            self.assertEqual(vm.execute('42;'),42)
        self.assertEqual(seen,['custom','base'])

    def test_reference_generator_return_and_injected_error_conversion(self):
        vm,node=self.setup_case()
        def handler(node):
            yield 'pause'
            return 19
        vm.visit_Literal=handler
        generator=vm._visit(node)
        self.assertEqual(next(generator),'pause')
        self.assertEqual(self.consume(generator),19)
        generator=vm._visit(node);next(generator)
        with self.assertRaisesRegex(BSLRuntimeError,'Деление на ноль') as caught:
            generator.throw(ZeroDivisionError('host wording'))
        self.assertIn('boundary.bsl:1:1:',str(caught.exception))

    def test_reference_exact_host_failure_identity_precedes_conversion(self):
        vm,node=self.setup_case()
        class Dangerous(ValueError):
            def __str__(self): raise AssertionError('host failure stringified')
        error=Dangerous()
        def handler(node):raise error
        vm.visit_Literal=handler
        vm._scheduler.active_context.host_failure=error
        with self.assertRaises(Dangerous) as caught:next(vm._visit(node))
        self.assertIs(caught.exception,error)
        vm._scheduler.active_context.host_failure=ValueError('same')
        error=ValueError('same')
        with self.assertRaisesRegex(BSLRuntimeError,'same'):next(vm._visit(node))

    def test_reference_bsl_and_control_exception_identity(self):
        vm,node=self.setup_case()
        class HostStop(BaseException):pass
        for error in (BSLRuntimeError('ready','x',2,3),HostStop(),KeyboardInterrupt(),GeneratorExit()):
            def handler(node):raise error
            vm.visit_Literal=handler
            with self.subTest(kind=type(error).__name__),self.assertRaises(type(error)) as caught:
                next(vm._visit(node))
            self.assertIs(caught.exception,error)

    def test_reference_recursion_eval_message_and_getattr_conversion(self):
        vm,node=self.setup_case()
        vm._eval_depth[0]=1
        def handler(node):raise RecursionError('original')
        vm.visit_Literal=handler
        with self.assertRaisesRegex(BSLRuntimeError,'Вычислить: превышен предел глубины выражения Yadinassi'):
            next(vm._visit(node))
        class Lookup(Interpreter):
            def __getattribute__(self,name):
                if name=='visit_Literal':raise ValueError('lookup failure')
                return super().__getattribute__(name)
        with self.assertRaisesRegex(BSLRuntimeError,'lookup failure'):
            next(Lookup(execution_backend='interpreter')._visit(node))

    def test_reference_does_not_invoke_strict_only_exception_hook(self):
        vm,node=self.setup_case()
        def handler(node):raise ValueError('baseline')
        vm.visit_Literal=handler
        with patch.object(vm,'compiled_exception',side_effect=AssertionError('strict hook')):
            with self.assertRaisesRegex(BSLRuntimeError,'baseline'):next(vm._visit(node))

    def test_reference_suspended_frame_does_not_switch_path_on_private_write(self):
        vm,node=self.setup_case()
        def handler(node):
            yield 'pause'
            raise ValueError('legacy frame')
        vm.visit_Literal=handler
        generator=vm._visit(node);self.assertEqual(next(generator),'pause')
        vm._execution_backend='compiled-strict'
        with patch.object(vm,'compiled_exception',side_effect=AssertionError('switched frame')):
            with self.assertRaisesRegex(BSLRuntimeError,'legacy frame'):next(generator)

    @patch.object(Engine, "DETAILED_INLINE_STATS", True)
    def test_strict_hooks_exception_conversion_and_execution_remain_observed(self):
        vm,node=self.setup_case('compiled-strict')
        seen=[]
        before,after,error=vm.compiled_before,vm.compiled_after,vm.compiled_exception
        def enter(node):seen.append('before');return before(node)
        def leave(node,value):seen.append('after');return after(node,value)
        def fail(node,failure):seen.append('exception');return error(node,failure)
        vm.compiled_before,vm.compiled_after,vm.compiled_exception=enter,leave,fail
        self.assertEqual(vm.execute('42;'),42)
        self.assertIn('before',seen);self.assertIn('after',seen)
        with self.assertRaisesRegex(BSLRuntimeError,'Деление на ноль'):vm.execute('1/0;')
        self.assertIn('exception',seen)
        stats=vm.compiled_backend_stats
        if vm._compiled().FORCE_PYTHON_TRANSLATION:
            self.assertGreater(stats.get('python_translated_blocks', 0), 0)
            self.assertGreater(stats.get('python_translated_node_kinds', {}).get('Binary', 0), 0)
            for key in ('emitted_executions', 'helper_executions', 'inline_blocks',
                        'inline_fragments', 'plain_adapter_blocks'):
                self.assertEqual(stats.get(key, 0), 0, key)
        else:
            self.assertGreater(sum(stats.get(k,0) for k in ('emitted_executions','helper_executions','inline_blocks','inline_fragments')),0)
        self.assertEqual(stats['interpreter_fallbacks'],0)
