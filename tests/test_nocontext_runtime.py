"""NoContext capability and server execution are separate axes."""
from decimal import Decimal
from pathlib import Path
import tempfile
import unittest
from yadinassi import Interpreter, BSLError

class NoContextRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.messages=[]
        self.vm=Interpreter(self.messages.append)

    def test_direct_normal_caught_and_escaping_copyout(self):
        self.vm.execute('''&AtServerNoContext
Function N(X, Val Mode)
X=X+10;
If Mode=1 Then Try Raise "caught"; Except X=X+1; EndTry; EndIf;
If Mode=2 Then Raise "escape"; EndIf;
Return X;
EndFunction
X=1; Message(N(X,0)); Message(X);
X=2; Message(N(X,1)); Message(X);
X=3; Try N(X,2); Except Message(ErrorDescription()); EndTry; Message(X);
''')
        self.assertEqual(self.messages[:4],['11','11','13','13'])
        self.assertIn('escape',self.messages[4]); self.assertEqual(self.messages[5],'3')
        self.assertEqual(self.vm.execution_context,'client'); self.assertTrue(self.vm._has_module_context)

    def test_context_to_nocontext_is_same_server_reference_call(self):
        self.vm.execute('''&AtServerNoContext
Procedure N(X) X=14; Raise "escape"; EndProcedure
&AtServer
Function S() X=3; Try N(X); Except EndTry; Return X; EndFunction
Message(S());
''')
        self.assertEqual(self.messages,['14'])

    def test_nested_nocontext_reference_and_object_call(self):
        self.vm.execute('''&AtServerNoContext
Function Inner(X) X.Add(7); Return X.Count(); EndFunction
&AtServerNoContext
Function Outer(X, Val Y) Inner(X); Y.Add(8); Return Y; EndFunction
X=New Array; Y=New Array; R=Outer(X,Y);
Message(X.Count()); Message(Y.Count()); Message(R[0]);
''')
        self.assertEqual(self.messages,['1','0','8'])

    def test_module_variables_hidden_and_capability_restored(self):
        self.vm.execute('''&AtServer\nVar S;
&AtServerNoContext
Function N() Return S; EndFunction
&AtServer
Function Read()
Try N(); Except EndTry;
Return S;
EndFunction
#If AtServer Then
S=42;
#EndIf
Message(Read());
''')
        self.assertEqual(self.messages,['42'])
        with self.assertRaises(BSLError): self.vm.execute('N()')
        self.assertTrue(self.vm._has_module_context)

    def test_hidden_name_assignment_is_local_not_module_write(self):
        self.vm.execute('''&AtServer\nVar S;
&AtServerNoContext
Procedure N() S=99; EndProcedure
&AtServer
Function Read() N(); Return S; EndFunction
#If AtServer Then
S=42;
#EndIf
Message(Read());
''')
        self.assertEqual(self.messages,['42'])

    def test_context_and_client_calls_rejected_before_actual_effects(self):
        for target in ('S','C'):
            with self.subTest(target=target):
                vm=Interpreter()
                vm.execute('''&AtClient
Function C(Val X) Return X; EndFunction
&AtServer
Function S(Val X) Return X; EndFunction
&AtServerNoContext
Function Effect(X) X=99; Return X; EndFunction
&AtServerNoContext
Function N(X)
Try '''+target+'''(Effect(X)); Except EndTry;
Return X;
EndFunction
X=1;
''')
                self.assertEqual(vm.execute('N(X)'),Decimal(1))
                self.assertEqual(vm.execute('X'),Decimal(1))

    def test_no_module_initializer_replay_is_explicit_local_profile_policy(self):
        # Not claimed as independently measured native initialization behavior.
        self.vm.execute('''&AtServerNoContext
Function N() Return 7; EndFunction
&AtServer
Function S() Return 8; EndFunction
#If AtServer Then
Raise "context initializer";
#EndIf
Message(N());
''')
        self.assertEqual(self.messages,['7'])
        with self.assertRaises(BSLError): self.vm.execute('S()')
        self.assertEqual(self.vm.execute('N()'),Decimal(7))
        self.assertEqual(self.vm._context_stack,['client'])
        self.assertEqual(self.vm._module_context_stack,[True])

    def test_execute_and_eval_cannot_recover_module_capability(self):
        for body in ('Return Eval("S");', 'Execute("X=S;"); Return X;',
                     'Return Eval("Read()");', 'Execute("X=Read();"); Return X;'):
            with self.subTest(body=body):
                vm=Interpreter()
                vm.execute('&AtServer\nVar S;\n&AtServer\nFunction Read() Return S; EndFunction\n'
                    '&AtServerNoContext\nFunction N() '+body+' EndFunction\n'
                    '#If AtServer Then\nS=42;\n#EndIf')
                with self.assertRaises(BSLError): vm.execute('N()')

    def test_implicit_module_receiver_hidden_direct_eval_execute(self):
        for expression in ('ThisObject=ThisObject', 'ЭтотОбъект=ЭтотОбъект',
                           'Eval("ThisObject=ThisObject")'):
            with self.subTest(expression=expression):
                self.vm.execute('&AtServerNoContext\nFunction N() Return '+expression+'; EndFunction')
                with self.assertRaises(BSLError): self.vm.execute('N()')
                self.assertTrue(self.vm._has_module_context)
                self.assertTrue(self.vm.execute('(ThisObject=ThisObject)'))
        self.vm.execute('&AtServerNoContext\nFunction N() Execute("X=ThisObject;"); Return X; EndFunction')
        with self.assertRaises(BSLError): self.vm.execute('N()')
        self.assertTrue(self.vm._has_module_context)

    def test_explicit_local_module_receiver_name_remains_legal(self):
        self.vm.execute('&AtServerNoContext\nFunction N() Var ThisObject; ThisObject=7; Return Eval("ThisObject"); EndFunction')
        self.assertEqual(self.vm.execute('N()'),Decimal(7))
        self.vm.execute('&AtServerNoContext\nFunction N(Val ЭтотОбъект) Return ЭтотОбъект; EndFunction')
        self.assertEqual(self.vm.execute('N(8)'),Decimal(8))

    def test_imported_nocontext_diagnostics_are_activation_local(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)
            (p/'M.bsl').write_text('''&AtServerNoContext
Function N() Export
Try Raise "server-error"; Except Return ErrorDescription(); EndTry;
EndFunction
''',encoding='utf-8')
            self.vm.execute('// #Импорт M.bsl\nTry Raise "client-secret"; Except Message(M.N()); EndTry;',str(p/'Root.bsl'))
        self.assertIn('server-error',self.messages[0]); self.assertNotIn('client-secret',self.messages[0])

    def test_same_name_context_family_collision_rejected_before_effects(self):
        with self.assertRaises(BSLError):
            self.vm.execute('Message("bad");\n&AtServer\nFunction F() Return 1; EndFunction\n'
                            '&AtServerNoContext\nFunction F() Return 2; EndFunction')
        self.assertEqual(self.messages,[])

    def test_persistent_replacement_keeps_new_capability(self):
        self.vm.execute('&AtServer\nFunction F() Return 1; EndFunction')
        self.vm.execute('&AtServerNoContext\nFunction F() Return 2; EndFunction')
        self.assertEqual(self.vm.execute('F()'),Decimal(2))
        self.assertFalse(self.vm.server_routines['f'].module_context)

if __name__=='__main__': unittest.main()
