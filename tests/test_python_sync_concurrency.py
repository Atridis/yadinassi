"""Closed scalar admission must decline asynchronous Python authority sources."""
import signal
import threading
import unittest
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import patch

from yadinassi import Interpreter
from yadinassi.compiled_backend import Engine, CompiledUnsupported
from yadinassi.errors import BSLRuntimeError
from yadinassi.owned_syntax import syntax_kind
from yadinassi.syntax import ast


SOURCE = 's=0;For i=1 To 500000 Do s=s+i;EndDo;result=s;'


class SyncConcurrencyTests(unittest.TestCase):
    def assert_general(self, vm):
        stats = vm.compiled_backend_stats
        for key in ('python_sync_segment_calls', 'python_sync_routine_calls', 'python_scalar_regions'):
            self.assertEqual(stats.get(key, 0), 0, key)
        self.assertEqual(vm._compiled()._active_frames, 0)

    def test_budget_hook_inside_loop_cannot_be_coalesced(self):
        vm = Interpreter(execution_backend='compiled-strict')
        original = Engine.verify_node
        visits = []
        def budget(engine, node):
            original(engine, node)
            if syntax_kind(node) is ast.Binary:
                visits.append(node)
                if len(visits) >= 20:
                    raise RuntimeError('per-node budget exhausted')
        with patch.object(Engine, 'verify_node', budget):
            with self.assertRaisesRegex(RuntimeError, 'per-node budget exhausted'):
                vm.execute(SOURCE)
        self.assertLess(vm.variables['i'], 500000)
        self.assert_general(vm)

    def run_worker_revocation(self, action, exception):
        vm = Interpreter(execution_backend='compiled-strict')
        engine = vm._compiled()
        stop = threading.Event()
        changed = threading.Event()
        worker_errors = []
        def worker():
            try:
                while not stop.wait(.001):
                    if vm.variables.get('i', Decimal(0)) >= 10:
                        action(vm, engine)
                        changed.set()
                        return
            except BaseException as error:
                worker_errors.append(error)
        thread = threading.Thread(target=worker, daemon=True)
        thread.start()
        try:
            with self.assertRaises(exception):
                vm.execute(SOURCE)
        finally:
            stop.set()
            thread.join(5)
            vm._configuration_runtime = None
        self.assertFalse(thread.is_alive())
        self.assertEqual(worker_errors, [])
        self.assertTrue(changed.is_set())
        self.assertLess(vm.variables['i'], 500000)
        self.assertNotIn('result', vm.variables)
        self.assert_general(vm)

    def test_worker_revokes_owned_binary_while_loop_is_running(self):
        def revoke(vm, engine):
            node = next(plan.node for plan in engine._nodes.values() if syntax_kind(plan.node) is ast.Binary)
            del engine._nodes[id(node)]
        self.run_worker_revocation(revoke, CompiledUnsupported)

    def test_worker_installs_denying_assignment_policy_during_loop(self):
        def revoke(vm, engine):
            def deny(*args):
                raise PermissionError('assignment authority revoked')
            vm._configuration_runtime = SimpleNamespace(check_assignment=deny)
        self.run_worker_revocation(revoke, PermissionError)

    @unittest.skipUnless(hasattr(signal, 'SIGINT'), 'SIGINT unavailable')
    def test_custom_signal_handler_declines_closed_regions(self):
        original = signal.getsignal(signal.SIGINT)
        vm = Interpreter(execution_backend='compiled-strict')
        try:
            signal.signal(signal.SIGINT, lambda signum, frame: None)
            vm.execute('Function F(Val n) s=0;For i=1 To n Do s=s+i;EndDo;Return s;EndFunction result=F(3);')
        finally:
            signal.signal(signal.SIGINT, original)
        self.assertEqual(vm.variables['result'], 6)
        self.assert_general(vm)

    def test_previous_host_result_destructor_is_not_delayed_across_segment(self):
        outcomes = []
        for observed in (True, False):
            vm = Interpreter(execution_backend='compiled-strict')
            if observed:
                vm.compiled_before = lambda node: None
            events = []
            class Payload:
                def __del__(self):
                    events.append((vm.variables.get('s'), vm.variables.get('i')))
                    vm.variables['s'] = Decimal(100)
            vm.register_function('Make', Payload)
            vm.execute('s=0;Make();For i=1 To 3 Do s=s+i;EndDo;result=s;')
            outcomes.append((vm.variables['result'], events))
            self.assertEqual(vm.compiled_backend_stats.get('python_sync_segment_calls', 0), 0)
        self.assertEqual(outcomes[0], outcomes[1])
        self.assertEqual(outcomes[1], (100, [(6, 4)]))

    def test_gc_callbacks_decline_closed_routes(self):
        import gc
        def observer(phase, info):
            pass
        vm = Interpreter(execution_backend='compiled-strict')
        gc.callbacks.append(observer)
        try:
            vm.execute('Function F(Val n) s=0;For i=1 To n Do s=s+i;EndDo;Return s;EndFunction result=F(3);')
        finally:
            gc.callbacks.remove(observer)
        self.assertEqual(vm.variables['result'], 6)
        self.assert_general(vm)

    def test_gc_state_restored_after_success_error_and_pre_disabled_entry(self):
        import gc
        original = gc.isenabled()
        try:
            for enabled in (False, True):
                for error in (False, True):
                    with self.subTest(enabled=enabled, error=error):
                        (gc.enable if enabled else gc.disable)()
                        vm = Interpreter(execution_backend='compiled-strict')
                        source = ('s=0;For i=1 To 3 Do s=s+i;q=1/(2-i);EndDo;'
                                  if error else 's=0;For i=1 To 3 Do s=s+i;EndDo;result=s;')
                        if error:
                            with self.assertRaises(BSLRuntimeError):
                                vm.execute(source)
                        else:
                            vm.execute(source)
                            self.assertEqual(vm.variables['result'], 6)
                        self.assertEqual(gc.isenabled(), enabled)
                        self.assertGreater(vm.compiled_backend_stats.get('python_sync_segment_calls', 0), 0)
                        self.assertEqual(vm._compiled()._active_frames, 0)
        finally:
            (gc.enable if original else gc.disable)()

    def test_worker_started_after_entry_proof_invalidates_without_publishing(self):
        import gc
        from yadinassi.python_translation_scalar_regions import ClosedLease
        original_backedge = ClosedLease.backedge
        original_gc = gc.isenabled()
        try:
            gc.enable()
            for mode in ('metadata', 'policy'):
                for iterations in (1, 100000):
                    with self.subTest(mode=mode, iterations=iterations):
                        vm = Interpreter(execution_backend='compiled-strict')
                        vm.variables['sentinel'] = Decimal(7)
                        engine = vm._compiled()
                        stop = threading.Event()
                        changed = threading.Event()
                        workers = []
                        failures = []
                        def worker():
                            try:
                                if mode == 'metadata':
                                    node = next(p.node for p in engine._nodes.values()
                                                if syntax_kind(p.node) is ast.Binary)
                                    del engine._nodes[id(node)]
                                else:
                                    def deny(*args):
                                        raise PermissionError('revoked after entry')
                                    vm._configuration_runtime = SimpleNamespace(check_assignment=deny)
                                changed.set()
                                stop.wait(5)
                            except BaseException as error:
                                failures.append(error)
                                changed.set()
                        def enter_then_spawn(lease):
                            original_backedge(lease)
                            if not workers:
                                thread = threading.Thread(target=worker, daemon=True)
                                workers.append(thread)
                                thread.start()
                                self.assertTrue(changed.wait(3), 'worker did not mutate authority')
                        try:
                            with patch.object(ClosedLease, 'backedge', enter_then_spawn):
                                with self.assertRaises(CompiledUnsupported):
                                    vm.execute(f's=0;For i=1 To {iterations} Do s=s+i;EndDo;result=s;')
                        finally:
                            stop.set()
                            for thread in workers:
                                thread.join(5)
                            vm._configuration_runtime = None
                        self.assertEqual(failures, [])
                        self.assertEqual(len(workers), 1)
                        self.assertFalse(workers[0].is_alive())
                        self.assertEqual(vm.variables, {'sentinel': Decimal(7)})
                        self.assertEqual(engine.stats.get('python_sync_segment_calls'), 1)
                        self.assertEqual(engine._active_frames, 0)
                        self.assertTrue(gc.isenabled())
        finally:
            (gc.enable if original_gc else gc.disable)()

    def test_policy_inserted_after_publish_check_is_enforced_by_live_setter(self):
        import gc
        import sys
        from yadinassi.python_translation_scalar_regions import ClosedLease
        original_check = ClosedLease.check
        original_gc = gc.isenabled()
        vm = Interpreter(execution_backend='compiled-strict')
        vm.variables['sentinel'] = Decimal(7)
        checks = []
        installed = []
        def deny(name, caller):
            checks.append((name, caller is vm))
            raise PermissionError('publication denied after lease check')
        def check_then_install(lease):
            original_check(lease)
            if not installed and sys._getframe(1).f_code.co_name == 'publish':
                installed.append(True)
                vm._configuration_runtime = SimpleNamespace(check_assignment=deny)
        try:
            gc.enable()
            with patch.object(ClosedLease, 'check', check_then_install):
                with self.assertRaisesRegex(CompiledUnsupported, 'live storage publication rejected'):
                    vm.execute('s=0;For i=1 To 3 Do s=s+i;EndDo;result=s;')
            self.assertTrue(gc.isenabled())
        finally:
            vm._configuration_runtime = None
            (gc.enable if original_gc else gc.disable)()
        self.assertEqual(installed, [True])
        self.assertEqual(checks, [('s', True)])
        self.assertEqual(vm.variables, {'sentinel': Decimal(7)})
        self.assertEqual(vm.compiled_backend_stats.get('python_sync_segment_calls'), 1)
        self.assertEqual(vm._compiled()._active_frames, 0)
