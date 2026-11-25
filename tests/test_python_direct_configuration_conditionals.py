"""Finite scalar conditionals preserve configuration scope and admission."""
from decimal import Decimal
import contextvars
import unittest
from unittest.mock import patch
from yadinassi.configuration.configuration_runtime import ConfigurationApplication
from yadinassi.types.errors import BSLError
from yadinassi.execution.codegen.experimental_naked_boundaries import BoundaryViolation
from yadinassi.execution.direct.python_direct import PythonDirectUnsupported
from yadinassi.execution.direct.python_direct_configuration import _COMMAND_SCOPE,ConfigurationBoundary
from configuration_runtime_fixture import CLIENT,module_files


class ConfigurationConditionalTests(unittest.TestCase):
    def app(self,output=None):
        app=ConfigurationApplication.from_files(module_files([CLIENT]),output=output or (lambda value:None))
        self.addCleanup(lambda:app.close(force=True));app.start();return app

    def test_scalar_if_elseif_else_selects_right_branch(self):
        cases=(
            'X=0;If True Then X=1;Else X=2;EndIf;',
            'X=0;If False Then X=1;ElsIf 2>1 Then X=3;Else X=4;EndIf;',
            'X=0;If False Then X=1;ElsIf False Then X=2;Else X=4;EndIf;',
            'X=0;If True Then If False Then X=1;Else X=5;EndIf;EndIf;',
            'X=0;Try If 1 Then X=1;EndIf;Except X=6;EndTry;',
            'X=0;Try If True Then Raise "boom";EndIf;Except If True Then X=7;EndIf;EndTry;',
            'X=0;If True Then Try Try Raise "boom";Except Raise;EndTry;Except X=8;EndTry;EndIf;',
        )
        for source,expected in zip(cases,(1,3,4,5,1,7,8)):
            with self.subTest(source=source):
                app=self.app();app.execute(source)
                self.assertEqual(app.interpreter.variables['x'],expected)
                self.assertIsNone(_COMMAND_SCOPE.get())

    def test_metadata_predicate_calls_only_selected_scalar_routine(self):
        seen=[];app=self.app(seen.append)
        app.execute('If Metadata.CommonModules.Count()=1 Then X=Tools.Double(3);Message(X);Else X=1/0;EndIf;')
        self.assertEqual(seen,['6']);self.assertEqual(app.execute('X'),Decimal(6))
        app.execute('If True Then X=4;ElsIf 1/0 Then X=5;EndIf;')
        self.assertEqual(app.execute('X'),Decimal(4))

    def test_all_unreachable_branches_and_conditions_reject_before_effects(self):
        forbidden=('Eval("1");','X=New Array;','Tools=1;','Message(Tools);',
                   'Metadata.CommonModules.Tools.Name="bad";','While False Do EndDo;')
        for bad in forbidden:
            for command in ('If False Then '+bad+'EndIf;',
                            'If True Then X=1;ElsIf False Then '+bad+'Else X=2;EndIf;',
                            'If True Then X=1;Else Try X=2;Except '+bad+'EndTry;EndIf;'):
                seen=[];app=self.app(seen.append)
                with self.subTest(command=command),self.assertRaises((BSLError,PythonDirectUnsupported,ValueError)):
                    app.execute('Message("before");'+command)
                self.assertEqual(seen,[]);self.assertNotIn('x',app.interpreter.variables)
        seen=[];app=self.app(seen.append)
        with self.assertRaises(PythonDirectUnsupported):
            app.execute('Message("before");If True Then X=1;ElsIf Eval("True") Then X=2;EndIf;')
        self.assertEqual(seen,[])

    def test_fatal_revocation_inside_branch_cannot_enter_handler(self):
        for state in ('closed','failed','cancelled'):
            seen=[];app=self.app()
            def output(value):
                seen.append(value);app.state=state
            app.interpreter.output=output
            with self.subTest(state=state),self.assertRaises(BoundaryViolation):
                app.execute('Try If True Then Message("revoke");Else Message("else");EndIf;Except Message("caught");EndTry;')
            self.assertEqual(seen,['revoke']);self.assertIsNone(_COMMAND_SCOPE.get())
            self.assertFalse(app.interpreter._direct_active)

    def test_saved_boundary_cannot_cross_context_or_outlive_conditional(self):
        app=self.app();saved=[];original=ConfigurationBoundary.resolve_member
        def resolve(context,value,name):
            result=original(context,value,name);saved.append(result)
            with self.assertRaises(BoundaryViolation):contextvars.copy_context().run(result,Decimal(2))
            return result
        with patch.object(ConfigurationBoundary,'resolve_member',resolve):
            app.execute('If True Then X=Tools.Double(2);EndIf;')
        self.assertEqual(app.execute('X'),Decimal(4))
        with self.assertRaises(BoundaryViolation):saved[0](Decimal(2))

    def test_direct_branch_execution_never_enters_vm(self):
        app=self.app()
        def forbidden(*args,**kwargs):raise AssertionError('old evaluator entered')
        app.execute('If True Then X=Tools.Double(5);Else X=0;EndIf;')
        self.assertEqual(app.execute('X'),Decimal(10))
