"""Scalar ServerCall reuse cannot turn warm cache entries into authority."""
import unittest
from unittest.mock import patch
from test_source_server_call import configuration
from yadinassi.configuration.configuration_source_runtime import SourceApplication
from yadinassi.runtime import Interpreter
from yadinassi.application.reusable_values import ReusableValueCache
from yadinassi.execution.codegen.experimental_naked_boundaries import BoundaryViolation
from yadinassi.types.errors import BSLError


class SourceServerReuseSecurity(unittest.TestCase):
    def setUp(self):
        for name in ('_execute_program','call_routine','_planned_routine_block'):
            poison=patch.object(Interpreter,name,side_effect=AssertionError('legacy '+name))
            poison.start();self.addCleanup(poison.stop)

    def app(self,body='Function Run(Val X) Export Message("body"); Return X; EndFunction'):
        output=[]
        app=SourceApplication(configuration('',body,reuse='DuringSession'),output=output.append)
        self.addCleanup(app.close);app.start();return app,output

    def test_warm_cache_replacements_rejected_before_arguments(self):
        for change in ('origin','reuse','cache'):
            with self.subTest(change=change):
                app,output=self.app()
                app.interpreter.execute('ServerAPI.Run("warm"); Function Touch() Message("arg"); Return "warm"; EndFunction')
                self.assertEqual(output,['body']);output.clear()
                owner=app._instances[('serverapi','server',False)]
                routine=owner.server_routines['run']
                if change=='origin':app._instances[('serverapi','server',False)]=app.interpreter
                elif change=='reuse':app._reuse_routines[id(routine)]=tuple(list(app._reuse_routines[id(routine)]))
                else:app.reusable_values._session=ReusableValueCache()
                with self.assertRaises((BoundaryViolation,BSLError,ValueError)):
                    app.interpreter.execute('ServerAPI.Run(Touch());')
                self.assertEqual(output,[])

    def test_argument_enables_safe_mode_before_warm_lookup(self):
        app,output=self.app()
        app.interpreter.execute('ServerAPI.Run("warm");');output.clear()
        def enable():
            output.append('arg');app.safe_mode.set(True);return 'warm'
        app.interpreter.register_function('Enable',enable)
        with self.assertRaises((BSLError,ValueError)):
            app.interpreter.execute('Function Call() Return ServerAPI.Run(Enable()); EndFunction\nCall();')
        self.assertEqual(output,['arg'])
        self.assertEqual(app.interpreter.execution_context,'client')
        self.assertEqual(app.interpreter._module_context_stack,[True])

    def test_private_lexical_input_rejected_before_body(self):
        app,output=self.app('Function Run(Val X) Export Return Hidden(New Array); EndFunction\n'
            'Function Hidden(Val X) Message("wrong-body"); Return 1; EndFunction')
        with self.assertRaises((BSLError,ValueError,TypeError)):
            app.interpreter.execute('ServerAPI.Run("key");')
        self.assertEqual(output,[])
        self.assertEqual(app.reusable_values._session._entries,{})

    def test_private_lexical_output_rejected_before_use(self):
        app,output=self.app('Function Run(Val X) Export A=Hidden(X); Message("wrong-use"); Return 1; EndFunction\n'
            'Function Hidden(Val X) Message("hidden"); Return New Array; EndFunction')
        with self.assertRaises((BSLError,ValueError,TypeError)):
            app.interpreter.execute('ServerAPI.Run("key");')
        self.assertEqual(output,['hidden'])
        self.assertEqual(app.reusable_values._session._entries,{})

    def test_failure_is_not_cached(self):
        app,output=self.app('Function Run(Val X) Export Message("compute"); Raise "failure"; EndFunction')
        for _ in range(2):
            with self.assertRaises(BSLError):app.interpreter.execute('ServerAPI.Run("key");')
        self.assertEqual(output,['compute','compute'])
        self.assertEqual(app.reusable_values._session._entries,{})
        self.assertIsNone(app.interpreter._scheduler.active_context.request_cache)

    def test_refresh_during_compute_does_not_publish_old_reservation(self):
        app,output=self.app('Function Run(Val X) Export Message("compute"); RefreshReusableValues(); Return X; EndFunction')
        for _ in range(2):self.assertEqual(app.interpreter.execute('ServerAPI.Run("key");'),'key')
        self.assertEqual(output,['compute','compute'])
        self.assertEqual(app.reusable_values._session._entries,{})
