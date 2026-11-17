"""Temporary markers are not an ambient standalone/source capability."""
import unittest
from unittest.mock import patch
import test_source_temporary_storage as existing
from yadinassi.runtime import Interpreter
from yadinassi import temporary_storage as temporary
from yadinassi.experimental_naked_boundaries import BoundaryViolation
from yadinassi.errors import BSLError


class SourceTemporarySecurity(unittest.TestCase):
    app = existing.SourceTemporaryTests.app
    execute = existing.SourceTemporaryTests.execute

    def setUp(self):
        for name in ('_execute_program', 'call_routine'):
            poison=patch.object(Interpreter,name,side_effect=AssertionError('legacy '+name))
            poison.start(); self.addCleanup(poison.stop)

    def test_foreign_standalone_saved_marker_rejected_before_actual(self):
        app=self.app()
        vm=Interpreter(lambda _:None); self.addCleanup(vm.close)
        vm.register_function('Put',temporary.SourceTemporaryCall(app.temporary_storage,temporary.put_marker))
        vm.variables['saved']=vm.functions['put']
        vm.execute('Function Touch() Raise "wrong"; EndFunction')
        with self.assertRaisesRegex(BSLError,'another or closed'):
            vm.execute('Saved(Touch(),New UUID)')

    def test_foreign_source_marker_rejected_before_actual(self):
        first,other=self.app(),self.app()
        first.interpreter.register_function('Put',temporary.SourceTemporaryCall(other.temporary_storage,temporary.put_marker))
        first.interpreter.execute('Function Touch() Raise "wrong"; EndFunction')
        with self.assertRaises(BoundaryViolation):
            first.interpreter.execute('Put(Touch(),New UUID)')

    def test_store_hook_rejected_before_callback_or_actual(self):
        app=self.app()
        app.interpreter.execute('Function Touch() Raise "wrong"; EndFunction')
        callback=unittest.mock.Mock(side_effect=AssertionError('wrong-hook'))
        with patch.object(temporary.SourceTemporaryStorage,'authorize',callback):
            with self.assertRaises(BoundaryViolation):
                app.interpreter.execute('PutToTempStorage(Touch(),New UUID)')
        callback.assert_not_called()

    def test_marker_retargeted_during_argument_cannot_write(self):
        from yadinassi.configuration_source_runtime import SourceApplication
        from yadinassi.python_direct_source_server import _ACTIVE
        from test_source_server_call import configuration
        other=self.app(); output=[]
        def emit(value):
            output.append(value)
            fresh=_ACTIVE.get()[-1][0]
            fresh.functions['puttotempstorage'].function.owner=other.temporary_storage
        app=SourceApplication(configuration('',
            'Function Run() Export Return PutToTempStorage(Touch(),New UUID); EndFunction '
            'Function Touch() Message("arg"); Return 1; EndFunction'), output=emit)
        self.addCleanup(app.close); app.start()
        with self.assertRaises(BoundaryViolation):
            app.interpreter.execute('ServerAPI.Run()')
        self.assertEqual(output,['arg'])
        self.assertEqual(app.temporary_storage._entries,{})
        self.assertEqual(other.temporary_storage._entries,{})
        self.assertEqual(app.interpreter.execution_context,'client')

    def test_inherited_store_override_is_rejected(self):
        app=self.app()
        callback=unittest.mock.Mock(side_effect=AssertionError('wrong-override'))
        with patch.object(temporary.SourceTemporaryStorage,'put',callback):
            with self.assertRaises(BoundaryViolation):
                app.interpreter.execute('PutToTempStorage(1,New UUID)')
        callback.assert_not_called()

    def test_owner_pointer_rejected_without_callable_access(self):
        app=self.app(); calls=[]
        app.temporary_storage._application=lambda: (calls.append('wrong'),app)[1]
        with self.assertRaises(BoundaryViolation):
            app.interpreter.execute('PutToTempStorage(1,New UUID)')
        self.assertEqual(calls,[])


if __name__ == '__main__':
    unittest.main()
