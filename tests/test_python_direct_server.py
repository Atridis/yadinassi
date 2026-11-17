"""Direct logical server execution, intentionally not native parity evidence."""
from decimal import Decimal
import unittest
from unittest.mock import patch
from yadinassi import Interpreter
from yadinassi.python_direct import PythonDirectUnsupported
from yadinassi.errors import BSLRuntimeError
from yadinassi.experimental_naked_boundaries import BoundaryViolation

SOURCE='''
Var Client;
&AtServer
Var Counter;
&AtServer
Function F(Val N=2)
 If Counter=Undefined Then Counter=0; EndIf;
 Counter=Counter+1;
 If N>0 Then Return F(N-1); EndIf;
 Return Counter;
EndFunction
Client=99;
R=F();
'''
class DirectServerTests(unittest.TestCase):
    def test_source_ast_prepared_and_persistent_without_dispatch(self):
        from yadinassi.syntax.parser import parse
        for route in ('source','ast','prepared'):
            vm=Interpreter()
            with patch.object(Interpreter,'block',side_effect=AssertionError('legacy')),patch.object(Interpreter,'call_routine',side_effect=AssertionError('legacy')):
                if route=='source':vm.execute(SOURCE)
                elif route=='ast':vm.execute_program(parse(SOURCE))
                else:vm.execute_prepared(vm.prepare(SOURCE))
                self.assertEqual(vm.variables['r'],3)
                vm.execute('R=F(0);')
                self.assertEqual(vm.variables['r'],1)
                self.assertEqual(vm.variables['client'],99)
                self.assertNotIn('counter',vm.variables)
    def test_side_and_restoration(self):
        vm=Interpreter();vm.register_function('Side',lambda:vm.execution_context)
        vm.execute('&AtServer\nFunction S() Return Side(); EndFunction R=S();')
        self.assertEqual(vm.variables['r'],'server');self.assertEqual(vm.execution_context,'client')
    def test_collections_are_copied_in_both_directions(self):
        vm=Interpreter();vm.execute('''
&AtServer
Function S(Val X) X.A.Add(2); Return X; EndFunction
A=New Array; A.Add(1); X=New Structure("A",A); R=S(X); R.A.Add(3);
''')
        self.assertEqual(vm.variables['a'],[Decimal(1)])
        self.assertEqual(vm.variables['r'].get('A'),[Decimal(1),Decimal(2),Decimal(3)])
    def test_server_cannot_read_client_state(self):
        vm=Interpreter();vm.execute('Var Secret;Secret=42;\n&AtServer\nFunction S() Return Secret; EndFunction')
        with self.assertRaises(NameError):vm.execute('S();')
        self.assertEqual(vm.variables['secret'],42);self.assertEqual(vm.execution_context,'client')
    def test_client_call_denied_before_argument_effect(self):
        vm=Interpreter();effects=[];vm.register_function('Effect',lambda:effects.append(1))
        vm.execute('Function C(Val X) Return X; EndFunction\n&AtServer\nFunction S() Return C(Effect()); EndFunction')
        with self.assertRaises(BSLRuntimeError):vm.execute('S();')
        self.assertEqual(effects,[]);self.assertEqual(vm.execution_context,'client')
    def test_fault_restores_context_and_original_definition_location(self):
        vm=Interpreter();vm.execute('&AtServer\nFunction S()\nReturn 1/0;\nEndFunction',source='server.bsl')
        with self.assertRaises(BSLRuntimeError) as caught:vm.execute('S();',source='caller.bsl')
        self.assertIn('server.bsl:3:',str(caught.exception));self.assertEqual(vm.execution_context,'client')
    def test_revoked_owner_stays_fail_closed(self):
        vm=Interpreter();vm.register_function('Close',vm.close)
        vm.execute('&AtServer\nProcedure S() Close(); EndProcedure')
        with self.assertRaises(BoundaryViolation):vm.execute('S();')
    def test_unsupported_declarations_and_duplicate_refuse_before_effect(self):
        for declaration in ('&AtServerNoContext\nFunction S() Return 1; EndFunction',
            'Function S() Return 1; EndFunction\n&AtServer\nFunction S() Return 2; EndFunction'):
            vm=Interpreter()
            with self.assertRaises(PythonDirectUnsupported):vm.execute('Effect=1;\n'+declaration)
            self.assertEqual(vm.variables,{})
    def test_cycle_rejected_and_next_call_recovers(self):
        vm=Interpreter();vm.execute('&AtServer\nFunction S(Val X) Return X; EndFunction A=New Array; A.Add(A);')
        with self.assertRaises(BSLRuntimeError):vm.execute('S(A);')
        vm.execute('R=S(42);');self.assertEqual(vm.variables['r'],42)

    def test_transfer_limits_share_one_budget_across_native_and_host_containers(self):
        from yadinassi.python_direct_server import transfer
        from yadinassi.values import BSLArray
        first=BSLArray();first.items=[None]*6000
        with self.assertRaises(ValueError):transfer([first,first])
        root=[];child=BSLArray();root.append(child);child.items=[root]
        with self.assertRaises(ValueError):transfer(root)

    def test_server_layout_and_same_side_state_across_declaration_modules(self):
        vm=Interpreter()
        vm.execute('&AtServer\nVar N;\n&AtServer\nFunction ReadN() Return N; EndFunction')
        vm.execute('&AtServer\nFunction SetN() N=42; Return ReadN(); EndFunction')
        vm.execute('R=SetN();')
        self.assertEqual(vm.variables['r'],42)
        self.assertNotIn('n',vm.variables)
    def test_server_layout_expansion_rejects_stale_calls_before_effect(self):
        vm=Interpreter();vm.execute('&AtServer\nFunction S() Return 42; EndFunction')
        vm.execute('&AtServer\nVar N;\n&AtServer\nFunction T() Return N; EndFunction')
        with self.assertRaisesRegex(PythonDirectUnsupported,'server module-name layout changed'):
            vm.execute('Effect=1;S();')
        self.assertNotIn('effect',vm.variables)

    def test_prepared_does_not_import_ambient_server_declarations(self):
        first=Interpreter()
        first.execute('&AtServer\nVar N;\n&AtServer\nFunction Old() Return N; EndFunction')
        plan=first.prepare('&AtServer\nFunction S() N=42; Return F(); EndFunction\n&AtServer\nFunction F() Return N; EndFunction')
        second=Interpreter()
        with self.assertRaisesRegex(PythonDirectUnsupported,'prepared server module-name layout changed'):
            second.execute_prepared(plan)
        self.assertEqual(second.variables,{})
        self.assertFalse(getattr(second,'_direct_routine_modules',{}))
