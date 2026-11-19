"""cancel_pending cannot reset a family during synchronous direct execute."""
import threading
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from yadinassi import Interpreter
from yadinassi.execution.codegen.experimental_naked_boundaries import BoundaryViolation
from yadinassi.configuration.configuration_runtime import ConfigurationApplication
from configuration_runtime_fixture import CLIENT,module_files


class DirectCancellationTests(unittest.TestCase):
    def vm(self,root=None):
        if root is None:
            vm=Interpreter(execution_backend='python-direct', allow_extensions=True)
        else:
            directory=TemporaryDirectory();self.addCleanup(directory.cleanup)
            path=Path(directory.name);name='Child'+str(len(root.imports))
            (path/(name+'.bsl')).write_text('// child',encoding='utf-8')
            root.execute('// #Import '+name+'.bsl\n',str(path/'Main.bsl'))
            vm=root.imports[name.casefold()].interpreter
        self.addCleanup(vm.close);return vm

    def test_root_callback_rejection_matches_compiled_oracle_and_cleans_up(self):
        for backend in ('python-direct','compiled-strict'):
            vm=Interpreter(execution_backend=backend, allow_extensions=True);self.addCleanup(vm.close)
            vm.register_function('CancelInside',vm.cancel_pending)
            with self.subTest(backend=backend),self.assertRaisesRegex(RuntimeError,'active scheduler'):
                vm.execute('CancelInside();')
            self.assertEqual(vm.execute('6*7'),42)
            vm.cancel_pending()
            self.assertEqual(vm._direct_executions,0)

    def test_child_callback_protects_root_but_other_family_is_independent(self):
        root=self.vm();child=self.vm(root);other=self.vm();events=[]
        child.register_function('CancelRoot',root.cancel_pending)
        with self.assertRaisesRegex(RuntimeError,'active scheduler'):child.execute('CancelRoot();')
        child.register_function('CancelOther',lambda: (other.cancel_pending(),events.append('other'))[-1])
        child.execute('CancelOther();');self.assertEqual(events,['other'])
        self.assertEqual(root._direct_executions,0);self.assertEqual(child.execute('3+4'),7)

    def test_runtime_error_is_not_swallowed_by_bsl_handler(self):
        vm=self.vm();vm.register_function('CancelInside',vm.cancel_pending)
        with self.assertRaisesRegex(RuntimeError,'active scheduler'):
            vm.execute('Caught=False;Try CancelInside();Except Caught=True;EndTry;')
        self.assertIs(vm.variables['caught'],False);self.assertEqual(vm._direct_executions,0)

    def test_nested_sibling_execution_retains_outer_activity(self):
        root=self.vm();child=self.vm(root);events=[]
        def nested():
            child.execute('X=1;')
            try:root.cancel_pending()
            except RuntimeError:events.append('blocked')
        root.register_function('Nested',nested);root.execute('Nested();')
        self.assertEqual(events,['blocked']);self.assertEqual(root._direct_executions,0)
        root.cancel_pending()

    def test_exception_and_fatal_failure_release_execution_marker(self):
        for failure in (ValueError('ordinary'),BoundaryViolation('fatal')):
            vm=self.vm()
            def fail():raise failure
            vm.register_function('Fail',fail)
            with self.assertRaises(BaseException):vm.execute('Fail();')
            self.assertEqual(vm._direct_executions,0);vm.cancel_pending()
            self.assertEqual(vm.execute('2+2'),4)

    def test_parallel_siblings_keep_family_active_until_both_finish(self):
        root=self.vm();children=[self.vm(root),self.vm(root)]
        entered=[threading.Event(),threading.Event()];release=[threading.Event(),threading.Event()];errors=[]
        def worker(index):
            def hold():
                entered[index].set()
                if not release[index].wait(5):raise AssertionError('worker release timeout')
            children[index].register_function('Hold',hold)
            try:children[index].execute('Hold();')
            except BaseException as error:errors.append(error)
        threads=[threading.Thread(target=worker,args=(i,)) for i in range(2)]
        try:
            for thread in threads:thread.start()
            for event in entered:self.assertTrue(event.wait(5))
            with self.assertRaisesRegex(RuntimeError,'active scheduler'):root.cancel_pending()
            release[0].set();threads[0].join(5);self.assertFalse(threads[0].is_alive())
            with self.assertRaisesRegex(RuntimeError,'active scheduler'):root.cancel_pending()
        finally:
            for event in release:event.set()
            for thread in threads:thread.join(5)
        self.assertEqual(errors,[]);self.assertEqual(root._direct_executions,0);root.cancel_pending()

    def test_configuration_command_callback_uses_same_family_guard(self):
        app=None
        def output(value):app.interpreter.cancel_pending()
        app=ConfigurationApplication.from_files(module_files([CLIENT]),output=output)
        self.addCleanup(lambda:app.close(force=True));app.start()
        with self.assertRaisesRegex(RuntimeError,'active scheduler'):app.execute('Message("cancel");')
        self.assertEqual(app.interpreter._direct_executions,0)
        self.assertEqual(app.execute('Tools.Double(3)'),6)

    def test_new_direct_entry_cannot_race_scheduler_reset(self):
        root=self.vm();child=self.vm(root);entered=threading.Event();release=threading.Event();errors=[]
        original=root._scheduler.reset
        def held_reset():
            entered.set()
            if not release.wait(5):raise AssertionError('reset release timeout')
            original()
        def reset():
            try:root.cancel_pending()
            except BaseException as error:errors.append(error)
        with patch.object(root._scheduler,'reset',held_reset):
            thread=threading.Thread(target=reset);thread.start()
            try:
                self.assertTrue(entered.wait(5))
                with self.assertRaisesRegex(RuntimeError,'cancellation is active'):child.execute('X=1;')
                self.assertNotIn('x',child.variables)
                with self.assertRaisesRegex(RuntimeError,'active scheduler'):root.cancel_pending()
            finally:release.set();thread.join(5)
        self.assertFalse(thread.is_alive());self.assertEqual(errors,[])
        self.assertFalse(root._direct_cancelling);self.assertEqual(root._direct_executions,0)
        self.assertEqual(child.execute('3+4'),7)

    def test_reset_failure_does_not_leave_family_marked_cancelling(self):
        root=self.vm()
        with patch.object(root._scheduler,'reset',side_effect=RuntimeError('reset failure')):
            with self.assertRaisesRegex(RuntimeError,'reset failure'):root.cancel_pending()
        self.assertFalse(root._direct_cancelling);self.assertEqual(root.execute('1+2'),3)

    def test_marker_unwinds_original_family_after_owner_tampering(self):
        root=self.vm();other=self.vm()
        def change():root._family_owner=other
        root.register_function('ChangeOwner',change)
        try:
            with self.assertRaises(BoundaryViolation):root.execute('ChangeOwner();')
        finally:root._family_owner=root
        self.assertEqual(root._direct_executions,0);self.assertEqual(other._direct_executions,0)
        root.cancel_pending();other.cancel_pending()

    def test_execution_lease_does_not_dispatch_rebound_host_hook(self):
        vm=self.vm();events=[]
        def hostile(*args):events.append('hook');raise AssertionError('custom lease')
        vm.register_function('CancelInside',vm.cancel_pending)
        with patch.object(Interpreter,'_direct_execution_scope',hostile),patch.object(vm,'_direct_execution_scope',hostile):
            with self.assertRaisesRegex(RuntimeError,'active scheduler'):vm.execute('CancelInside();')
        self.assertEqual(events,[]);self.assertEqual(vm._direct_executions,0)

    def test_dual_and_nocontext_rejection_matches_oracle_write_semantics(self):
        for backend in ('python-direct','compiled-strict'):
            for annotation in ('&AtClientAtServerNoContext','&AtServerNoContext'):
                vm=Interpreter(execution_backend=backend, allow_extensions=True);self.addCleanup(vm.close)
                vm.register_function('CancelInside',vm.cancel_pending)
                vm.execute(annotation+'\nProcedure F(X) X=9;CancelInside();EndProcedure X=1;')
                with self.subTest(backend=backend,annotation=annotation):
                    with self.assertRaisesRegex(RuntimeError,'^Cannot reset an active scheduler$') as caught:
                        vm.execute('Caught=False;Try F(X);Except Caught=True;EndTry;')
                    self.assertIs(type(caught.exception),RuntimeError)
                    self.assertIs(vm.variables['caught'],False)
                    # Dual resolves locally on the client (live byref write);
                    # server NoContext must not copy back on a failed crossing.
                    self.assertEqual(vm.variables['x'],9 if annotation=='&AtClientAtServerNoContext' else 1)
                    self.assertEqual(vm.execution_context,'client')
                    self.assertEqual(vm._module_context_stack,[True])
                    self.assertEqual(vm._direct_executions,0)
