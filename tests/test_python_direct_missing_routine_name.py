"""Undefined lexical names are BSL faults, not generated Python globals."""
import unittest
from unittest.mock import patch
from decimal import Decimal

from yadinassi import Interpreter
from yadinassi.types.errors import BSLRuntimeError
from yadinassi.syntax.parser import parse


class MissingRoutineNameTests(unittest.TestCase):
    def run_source(self, vm, source, route):
        if route == 'source':
            vm.execute(source, source='scope.bsl')
        elif route == 'ast':
            vm.execute_program(parse(source, 'scope.bsl'))
        else:
            vm.execute_prepared(vm.prepare(source, source='scope.bsl'))

    def test_missing_name_routes_keep_bsl_name_and_definition_location(self):
        for route in ('source', 'ast', 'prepared'):
            for directive in ('', '&AtServer', '&AtServerNoContext', '&AtClientAtServerNoContext'):
                with self.subTest(route=route, directive=directive):
                    vm = Interpreter()
                    source = directive+'\nFunction ReadHidden()\nReturn Secret;\nEndFunction\nReadHidden();'
                    with patch.object(Interpreter, 'block', side_effect=AssertionError('legacy')), patch.object(Interpreter, 'call_routine', side_effect=AssertionError('legacy')):
                        with self.assertRaisesRegex(BSLRuntimeError, 'не определена: Secret') as caught:
                            self.run_source(vm, source, route)
                    self.assertIn('scope.bsl:3:', str(caught.exception))
                    self.assertNotIn('v0', str(caught.exception))
                    self.assertEqual(vm.execution_context, 'client')

    def test_missing_name_catchable_inside_server_without_client_leak(self):
        vm = Interpreter()
        vm.execute('''Var Secret; Secret=42;
&AtServer
Function ReadHidden()
 Try Return Secret; Except Return "missing"; EndTry;
EndFunction
Result=ReadHidden();''')
        self.assertEqual(vm.variables['result'], 'missing')
        self.assertEqual(vm.variables['secret'], Decimal(42))

    def test_unrelated_routine_binding_does_not_make_name_visible(self):
        vm = Interpreter()
        vm.execute('Function One() Hidden=42; Return Hidden; EndFunction Function Two() Return Hidden; EndFunction Result=One();')
        with self.assertRaisesRegex(BSLRuntimeError, 'не определена: Hidden'):
            vm.execute('Two();')
        self.assertEqual(vm.variables['result'], Decimal(42))

    def test_declared_assigned_parameter_loop_and_reference_bindings_still_work(self):
        vm = Interpreter()
        vm.execute('''
Procedure SetValue(X) X=7; EndProcedure
Function ReadValues(Val P)
 Var Declared, Output;
 Assigned=2;
 SetValue(Output);
 For I=1 To 2 Do Assigned=Assigned+I; EndDo;
 Return New Array;
EndFunction
Function Result(Val P) Var Output;
 SetValue(Output);
 Return Output+P;
EndFunction
A=ReadValues(3); R=Result(5);
''')
        self.assertEqual(vm.variables['r'], Decimal(12))

    def test_host_python_nameerror_is_not_reclassified(self):
        vm = Interpreter(allow_extensions=True)
        def fail():
            raise NameError('host implementation bug')
        vm.register_function('HostFail', fail)
        with self.assertRaisesRegex(NameError, 'host implementation bug'):
            vm.execute('Function F() Return HostFail(); EndFunction F();')

    def test_hidden_implicit_receiver_is_catchable_not_created(self):
        vm = Interpreter()
        vm.execute('''&AtServerNoContext
Function F()
 Try Return ThisObject; Except Return "hidden"; EndTry;
EndFunction
R=F();''')
        self.assertEqual(vm.variables['r'], 'hidden')
        self.assertNotIn('thisobject', vm.variables)
