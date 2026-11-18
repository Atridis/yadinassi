"""Ordinary error recovery in bounded scalar configuration commands."""
from decimal import Decimal
import unittest
from unittest.mock import patch

from yadinassi.configuration_runtime import ConfigurationApplication
from yadinassi.errors import BSLError, BSLRuntimeError
from yadinassi.experimental_naked_boundaries import BoundaryViolation
from yadinassi.python_direct import PythonDirectUnsupported
from yadinassi.python_direct_configuration import ConfigurationBoundary, _COMMAND_SCOPE
from configuration_runtime_fixture import module_files

MODULE=('Tools','Procedure Fail() Export Raise "boom";EndProcedure Function Double(Val X) Export Return X*2;EndFunction',{})


class ConfigurationCommandErrorTests(unittest.TestCase):
    def app(self,output=None):
        app=ConfigurationApplication.from_files(module_files([MODULE]),output=output or (lambda x:None))
        self.addCleanup(lambda:app.close(force=True));app.start();return app

    def test_ordinary_export_errors_catchable_on_repeated_commands(self):
        output=[];app=self.app(output.append)
        original=app._modules['tools','client'].interpreter.routines['fail']
        for word in ('caught','again'):
            self.assertIsNone(app.execute(f'Try Tools.Fail();Except Message("{word}");EndTry;'))
            self.assertIs(app._modules['tools','client'].interpreter.routines['fail'],original)
            self.assertIsNone(_COMMAND_SCOPE.get());self.assertFalse(app.interpreter._direct_active)
        self.assertEqual(output,['caught','again'])
        self.assertEqual(app.execute('Tools.Double(3)'),Decimal(6))

    def test_nested_rethrow_cleanup_and_scalar_state(self):
        output=[];app=self.app(output.append)
        app.execute('X=1;Try Try X=2;Tools.Fail();Except X=3;Raise;EndTry;Except Message("outer");EndTry;X=X+1;')
        self.assertEqual(output,['outer']);self.assertEqual(app.execute('X'),Decimal(4))
        self.assertIsNone(_COMMAND_SCOPE.get())
        self.assertTrue(app.interpreter._transaction_activation_allowed)
        self.assertEqual(app.interpreter._context_stack,['client'])
        with self.assertRaises(BSLError):app.execute('Raise;')
        app.execute('Message("clean");')
        self.assertEqual(output,['outer','clean'])

    def test_scalar_errors_match_compiled_strict_oracle(self):
        from yadinassi import Interpreter
        cases=(
            'X=1;Try X=2;Raise "boom";Except X=X+3;EndTry;',
            'X=1;Try X=1/0;Except X=7;EndTry;',
            'X=1;Try Try Raise "inner";Except Raise;EndTry;Except X=9;EndTry;',
            'X=1;Try Raise 42;Except X=6;EndTry;',
        )
        for source in cases:
            with self.subTest(source=source):
                app=self.app();oracle=Interpreter(execution_backend='compiled-strict')
                oracle.execute(source);app.execute(source)
                self.assertEqual(app.interpreter.variables['x'],oracle.variables['x'])

    def test_body_and_unreachable_nested_handler_validate_before_effects(self):
        forbidden=('X=New Array();','Eval("1");','Tools=1;','Var X;',
                   'While False Do EndDo;','Raise("bad",1);','Message(Tools);')
        for statement in forbidden:
            for branch in ('Try '+statement+'Except Message("caught");EndTry;',
                           'Try Message("body");Except Try Message("inner");Except '+statement+'EndTry;EndTry;'):
                output=[];app=self.app(output.append)
                with self.subTest(statement=statement,branch=branch):
                    with self.assertRaises((PythonDirectUnsupported,ValueError,BSLError)):
                        app.execute('Message("before");'+branch)
                    self.assertEqual(output,[])
                    self.assertIsNone(_COMMAND_SCOPE.get());self.assertFalse(getattr(app.interpreter,'_direct_active',False))

    def test_boundary_violation_is_never_caught_and_scope_is_restored(self):
        output=[];app=self.app(output.append)
        def denied(value):raise BoundaryViolation('denied')
        with patch.object(app,'_output',denied):
            with self.assertRaises(BoundaryViolation):
                app.execute('Try Message("effect");Except Message("swallowed");EndTry;')
        self.assertEqual(output,[])
        self.assertIsNone(_COMMAND_SCOPE.get());self.assertFalse(app.interpreter._direct_active)
        app.execute('Message(Tools.Double(2));');self.assertEqual(output,['4'])

    def test_transitive_disallowed_host_call_is_not_catchable(self):
        app=ConfigurationApplication.from_files(module_files([('Tools',
            'Procedure Fail() Export Try Eval("1");Except Message("inner");EndTry;EndProcedure',{})]),output=self.fail)
        self.addCleanup(lambda:app.close(force=True));app.start()
        with self.assertRaises(BoundaryViolation):
            app.execute('Try Tools.Fail();Except Message("outer");EndTry;')
        self.assertIsNone(_COMMAND_SCOPE.get())

    def test_saved_boundary_cannot_be_revived_after_error_or_rethrow(self):
        import contextvars
        output=[];app=self.app(output.append);contexts=[]
        original=ConfigurationBoundary.__init__
        def capture(context,*args,**kwargs):
            original(context,*args,**kwargs);contexts.append(context)
        with patch.object(ConfigurationBoundary,'__init__',capture):
            with self.assertRaisesRegex(BSLRuntimeError,'boom') as caught:
                app.execute('Try Tools.Fail();Except Raise;EndTry;','command.bsl')
        self.assertEqual(caught.exception.message,'boom')
        self.assertEqual(caught.exception.source,'<configuration:CommonModules/Tools/Ext/Module.bsl>')
        self.assertIsNone(_COMMAND_SCOPE.get());self.assertFalse(app.interpreter._direct_active)
        for context in contexts:
            for callback in (lambda:context.resolve_service('Message')(Decimal(1)),
                             lambda:contextvars.Context().run(lambda:context.resolve_service('Message')(Decimal(1)))):
                with self.assertRaises(BoundaryViolation):callback()
        self.assertEqual(output,[])
        self.assertEqual(app.execute('Tools.Double(5)'),Decimal(10))

    def test_missing_export_is_catchable_before_argument_effects(self):
        output=[];app=self.app(output.append)
        app.execute('Try Tools.Missing(Message("bad"));Except Message("missing");EndTry;Message(Tools.Double(4));')
        self.assertEqual(output,['missing','8'])

    def test_rejected_host_signature_in_handler_cannot_mask_initial_error(self):
        output=[];app=self.app(output.append)
        original=app.interpreter.functions['message'].function
        app.interpreter.functions['message'].function=lambda value:output.append('foreign')
        with self.assertRaises(BoundaryViolation):
            app.execute('Try Tools.Fail();Except Message("handler");EndTry;')
        self.assertEqual(output,[])
        self.assertIsNone(_COMMAND_SCOPE.get());self.assertFalse(app.interpreter._direct_active)
        app.interpreter.functions['message'].function=original
        app.execute('Message("recovered");');self.assertEqual(output,['recovered'])

    def test_error_and_rethrow_paths_do_not_dispatch_legacy_ast(self):
        from contextlib import ExitStack
        from yadinassi.runtime import Interpreter
        output=[];app=self.app(output.append)
        with ExitStack() as stack:
            for name in ('execute_program','block','_visit','call_routine'):
                stack.enter_context(patch.object(Interpreter,name,side_effect=AssertionError(name)))
            app.execute('Try Try Tools.Fail();Except Raise;EndTry;Except Message("caught");EndTry;')
        self.assertEqual(output,['caught'])

    def test_closed_or_failed_application_does_not_enter_except_handler(self):
        for state in ('closed','failed','cancelled'):
            app=None
            def output(value):
                if state=='closed':app.close(force=True)
                else:app.state=state
            app=self.app(output)
            with self.subTest(state=state),self.assertRaises(BoundaryViolation):
                app.execute('Caught=False;Try Message("invalidate");Except Caught=True;EndTry;')
            self.assertIs(app.interpreter.variables['caught'],False)
            self.assertIsNone(_COMMAND_SCOPE.get());self.assertFalse(app.interpreter._direct_active)
            self.assertTrue(app.interpreter._transaction_activation_allowed)
