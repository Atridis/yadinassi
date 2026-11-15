"""Real VM activation around an injected suspension, not scheduler parity.

The host call wrapper supplies one yield at an existing compiled Call
boundary. Both routes must retain/clean the real call_routine activation. Async
scheduler and form contexts are separately exercised by existing suites.
"""
from decimal import Decimal
import unittest
from yadinassi import Interpreter
from yadinassi.syntax.parser import parse
from yadinassi.syntax import ast
from yadinassi.owned_syntax import syntax_kind


class PrefixActivationTests(unittest.TestCase):
    def start(self, enabled):
        vm = Interpreter(execution_backend='compiled-strict', compiled_plain_routines=enabled)
        self.addCleanup(vm.close)
        effects = []
        vm.register_function('Host', lambda x: effects.append(x) or x+Decimal(2))
        vm.execute('Function F(Val x) x=x+1;y=Host(x);Return x+y;EndFunction')
        original = vm.call
        yielded = []
        def suspend(node, **kwargs):
            if (syntax_kind(node) is ast.Call and syntax_kind(node.callee) is ast.Name
                    and node.callee.name.casefold() == 'host' and not yielded):
                yielded.append(True)
                yield 'host-boundary'
            return (yield from original(node, **kwargs))
        vm.call = suspend
        vm._test_initial_context = tuple(vm._context_stack)
        call = vm.call_routine(vm.routines['f'], [parse('3;')[0].expression], vm, require_value=True)
        self.assertEqual(next(call), 'host-boundary')
        self.assertEqual(vm.locals['x'], Decimal(4))
        self.assertEqual(effects, [])
        if enabled:
            self.assertEqual(vm.compiled_backend_stats.get('plain_suffix_adapter_entries'), 1)
        return vm, call, effects

    def clean(self, vm):
        self.assertIsNone(vm.locals)
        self.assertEqual(vm.pending_promises, ())
        self.assertEqual(tuple(vm._context_stack), vm._test_initial_context)
        self.assertEqual(vm._compiled().active_frames, 0)
        self.assertEqual(vm.compiled_backend_stats['interpreter_fallbacks'], 0)

    def test_resume_uses_live_scope_after_real_activation_suspension(self):
        for enabled in (False, True):
            with self.subTest(enabled=enabled):
                vm, call, effects = self.start(enabled)
                identity = vm.locals
                vm.locals['x'] = Decimal(8)
                with self.assertRaises(StopIteration) as ended:
                    next(call)
                self.assertEqual(ended.exception.value, Decimal(18))
                self.assertEqual(effects, [Decimal(8)])
                self.assertEqual(identity['y'], Decimal(10))
                self.clean(vm)

    def test_close_unwinds_without_running_pending_host_effect(self):
        for enabled in (False, True):
            vm, call, effects = self.start(enabled)
            call.close()
            self.assertEqual(effects, [])
            self.clean(vm)

    def test_throw_unwinds_without_replaying_prefix_or_host(self):
        for enabled in (False, True):
            vm, call, effects = self.start(enabled)
            error = RuntimeError('host cancellation')
            with self.assertRaises(RuntimeError) as caught:
                call.throw(error)
            self.assertIs(caught.exception, error)
            self.assertEqual(effects, [])
            self.clean(vm)

    def test_host_authority_revoked_while_suffix_is_suspended(self):
        for enabled in (False, True):
            vm, call, effects = self.start(enabled)
            checks = []
            class Denied:
                def resolve_module(self, name, caller):
                    return None
                def resolve_global(self, name, caller):
                    return None
                def check_host_service(self, function, caller):
                    checks.append(function)
                    raise PermissionError('revoked during suspension')
            vm._configuration_runtime = Denied()
            with self.assertRaisesRegex(PermissionError, 'revoked during suspension'):
                next(call)
            self.assertEqual(len(checks), 1)
            self.assertEqual(effects, [])
            self.clean(vm)

    def test_live_call_authority_not_cached_by_warmed_prefix(self):
        for enabled in (False, True):
            vm = Interpreter(execution_backend='compiled-strict', compiled_plain_routines=enabled)
            self.addCleanup(vm.close)
            vm.register_function('Host', lambda x:x)
            vm.execute('Function F(Val x) x=x+1;y=Host(x);Return y;EndFunction r=F(3);')
            class Denied:
                def check_call(self, function, caller):
                    raise PermissionError('revoked')
            vm._configuration_runtime = Denied()
            vm._test_initial_context = tuple(vm._context_stack)
            call = vm.call_routine(vm.routines['f'], [parse('3;')[0].expression], vm, require_value=True)
            with self.assertRaisesRegex(PermissionError, 'revoked'):
                next(call)
            self.clean(vm)


if __name__ == '__main__':
    unittest.main()
