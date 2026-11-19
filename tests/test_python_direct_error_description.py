import unittest
from unittest.mock import patch
from yadinassi import Interpreter
from yadinassi.types.errors import BSLRuntimeError
from yadinassi.execution.codegen.experimental_naked_boundaries import BoundaryViolation

class DirectErrorDescriptionTests(unittest.TestCase):
    def test_source_ast_prepared_handlers_without_vm(self):
        from yadinassi.syntax.parser import parse
        source='Before=ErrorDescription();Try Raise "message";Except R=ОписаниеОшибки();EndTry;After=ErrorDescription();'
        for route in ('source','ast','prepared'):
            vm=Interpreter()
            with patch.object(Interpreter,'block',side_effect=AssertionError('VM')),patch.object(Interpreter,'call_routine',side_effect=AssertionError('VM')):
                if route=='source':vm.execute(source,'description.bsl')
                elif route=='ast':vm.execute_program(parse(source,'description.bsl'))
                else:vm.execute_prepared(vm.prepare(source,'description.bsl'))
            self.assertEqual(vm.variables['before'],'');self.assertEqual(vm.variables['after'],'')
            self.assertIn('description.bsl:1:',vm.variables['r']);self.assertTrue(vm.variables['r'].endswith('message'))

    def test_nested_handler_discards_outer_and_rethrow_preserves_origin(self):
        source='''Try Raise "outer";Except
 A=ErrorDescription();Try Raise "inner";Except B=ErrorDescription();EndTry;
 C=ErrorDescription();
EndTry;
Try
 Try Raise "origin";Except Raise;EndTry;
Except D=ErrorDescription();EndTry;'''
        rows=[]
        for backend in ('python-direct','compiled-strict'):
            vm=Interpreter(execution_backend=backend);vm.execute(source,'nested.bsl');rows.append(vm.variables)
        self.assertEqual(*rows);self.assertEqual(rows[0]['c'],'');self.assertIn('origin',rows[0]['d'])

    def test_stale_outer_rethrow_is_rejected(self):
        source='Try Raise "outer";Except Try Raise "inner";Except X=1;EndTry;Raise;EndTry;'
        for backend in ('python-direct','compiled-strict'):
            with self.assertRaisesRegex(BSLRuntimeError,'после вложенного обработчика'):
                Interpreter(execution_backend=backend).execute(source)

    def test_python_failure_is_normalized_at_bsl_source(self):
        vm=Interpreter();vm.execute('Try\n R=1/0;\nExcept\n D=ErrorDescription();\nEndTry;','division.bsl')
        self.assertIn('division.bsl:2:',vm.variables['d']);self.assertTrue(vm.variables['d'].endswith('Деление на ноль'))

    def test_same_side_helpers_inherit_but_server_crossing_is_fresh(self):
        source='''Function C() Return ErrorDescription();EndFunction
&AtClientAtServerNoContext
Function D() Return ErrorDescription();EndFunction
&AtServerNoContext
Function S() Return ErrorDescription();EndFunction
Try Raise "caller";Except A=C();B=D();C=S();E=ErrorDescription();EndTry;'''
        rows=[]
        for backend in ('python-direct','compiled-strict'):
            vm=Interpreter(execution_backend=backend);vm.execute(source);rows.append(tuple(vm.variables[k] for k in ('a','b','c','e')))
        self.assertEqual(*rows);self.assertEqual(rows[0][2],'');self.assertEqual(rows[0][0],rows[0][1])

    def test_custom_builtin_and_bad_arity_are_preserved(self):
        vm=Interpreter(allow_extensions=True);vm.register_function('ErrorDescription',lambda:'custom')
        vm.execute('Try Raise "real";Except D=ErrorDescription();EndTry;');self.assertEqual(vm.variables['d'],'custom')
        with self.assertRaises(BSLRuntimeError):Interpreter(allow_extensions=True).execute('ErrorDescription(1);')

    def test_failed_handler_and_early_return_do_not_leak(self):
        vm=Interpreter();vm.execute('Function F() Try Raise "old";Except Return ErrorDescription();EndTry;EndFunction R=F();D=ErrorDescription();')
        self.assertEqual(vm.variables['d'],'');self.assertIn('old',vm.variables['r'])
        with self.assertRaises(BSLRuntimeError):vm.execute('Try Raise "one";Except Raise "two";EndTry;')
        vm.execute('D=ErrorDescription();');self.assertEqual(vm.variables['d'],'')

    def test_external_python_exception_does_not_supply_bsl_description(self):
        vm=Interpreter()
        try:raise ValueError('host')
        except ValueError:vm.execute('D=ErrorDescription();')
        self.assertEqual(vm.variables['d'],'')

    def test_owner_revocation_is_not_caught_or_hidden(self):
        vm=Interpreter(allow_extensions=True);vm.register_function('Close',vm.close)
        with self.assertRaises(BoundaryViolation):vm.execute('Try Raise "x";Except Close();D=ErrorDescription();EndTry;')
        self.assertNotIn('d',vm.variables)

    def test_class_level_builtin_override_is_not_mistaken_for_canonical(self):
        with patch.object(Interpreter,'_error_description',lambda self:'host override'):
            vm=Interpreter();vm.execute('D=ErrorDescription();')
        self.assertEqual(vm.variables['d'],'host override')
