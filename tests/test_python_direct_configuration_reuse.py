"""Lazy functools reuse inside the existing same-side scalar command lane."""
import unittest
from unittest.mock import patch
from decimal import Decimal
from yadinassi.configuration_runtime import ConfigurationApplication
from yadinassi.errors import BSLRuntimeError
from configuration_runtime_fixture import module_files

SOURCE='''Function F(Val X) Export Message(X);Return X;EndFunction
Function Failure(Val X) Export Message(X);Raise "failure";EndFunction
Procedure Touch(Val X) Export Message(X);EndProcedure'''

class DirectConfigurationReuseTests(unittest.TestCase):
    def app(self,mode='DuringSession'):
        output=[]
        app=ConfigurationApplication.from_files(module_files([('Tools',SOURCE,{'ReturnValuesReuse':mode})]),output=output.append)
        self.addCleanup(app.close,force=True);app.start();return app,output

    def test_lazy_session_wrapper_and_no_effect_replay(self):
        app,output=self.app()
        self.assertFalse(hasattr(app.reusable_values._session,'_direct_functions'))
        self.assertEqual(app.execute('1+2'),Decimal(3))
        self.assertFalse(hasattr(app.reusable_values._session,'_direct_functions'))
        self.assertEqual(app.execute('Tools.F(7)'),Decimal(7))
        self.assertEqual(app.execute('Tools.F(7)'),Decimal(7))
        wrapper=next(iter(app.reusable_values._session._direct_functions.values()))[3]
        self.assertEqual((wrapper.cache_info().hits,wrapper.cache_info().misses),(1,1))
        self.assertEqual(output,['7'])

    def test_request_lifetime_and_failure_cleanup(self):
        app,output=self.app('DuringRequest')
        app.execute('Tools.F(7);Tools.F(7);')
        self.assertEqual(output,['7'])
        self.assertIsNone(app.interpreter._scheduler.active_context.request_cache)
        app.execute('Tools.F(7);')
        self.assertEqual(output,['7','7'])
        with self.assertRaises(BSLRuntimeError):app.execute('Tools.F(9);Raise "stop";')
        self.assertIsNone(app.interpreter._scheduler.active_context.request_cache)
        app.execute('Tools.F(9);')
        self.assertEqual(output[-2:],['9','9'])

    def test_failures_and_procedures_are_not_cached(self):
        app,output=self.app()
        for i in range(2):
            with self.assertRaises(BSLRuntimeError):app.execute('Tools.Failure(3);')
        app.execute('Tools.Touch(5);Tools.Touch(5);')
        self.assertEqual(output,['3','3','5','5'])

    def test_refresh_close_and_family_separation(self):
        app,output=self.app();other,other_output=self.app()
        app.execute('Tools.F(1)');other.execute('Tools.F(1)')
        app.reusable_values.refresh(app.interpreter);app.execute('Tools.F(1)')
        self.assertEqual(output,['1','1']);self.assertEqual(other_output,['1'])
        wrappers=app.reusable_values._session._direct_functions
        app.close(force=True)
        self.assertEqual(wrappers,{})

    def test_scalar_argument_types_do_not_alias(self):
        app,output=self.app()
        self.assertIs(app.execute('Tools.F(True)'),True)
        self.assertEqual(app.execute('Tools.F(1)'),Decimal(1))
        self.assertEqual(output,['Да','1'])

    def test_ordinary_command_does_not_enter_reuse_or_request_scope(self):
        app=ConfigurationApplication.from_files(module_files([('Tools','Function F(Val X) Export Return X;EndFunction',{})]))
        self.addCleanup(app.close,force=True);app.start()
        with patch('yadinassi.python_direct_configuration.invoke_reusable',side_effect=AssertionError('ordinary reuse')), \
             patch('yadinassi.python_direct_source_requests.request_scope',side_effect=AssertionError('ordinary request')):
            self.assertEqual(app.execute('Tools.F(3)'),Decimal(3))
            self.assertEqual(app.execute('1+2'),Decimal(3))

    def test_numeric_equal_keys_and_current_target_check_on_hit(self):
        app,output=self.app()
        app.execute('Tools.F(1.00)')
        from yadinassi.python_direct_configuration_commands import _Scope
        original=_Scope.check;owners=[]
        def checked(scope,application,owner):
            owners.append(owner)
            return original(scope,application,owner)
        with patch.object(_Scope,'check',checked):
            self.assertEqual(app.execute('Tools.F(1)'),Decimal(1))
        self.assertEqual(len(output),1)
        self.assertIn(app._modules['tools','client'].interpreter,owners)

    def test_nonfinite_arguments_refused_before_effects(self):
        app,output=self.app()
        for value in (Decimal('NaN'),Decimal('Infinity')):
            app.interpreter.variables['x']=value
            with self.assertRaises(BSLRuntimeError):app.execute('Tools.F(X)')
        self.assertEqual(output,[])
