"""Bounded logical client/server calls; predictions are not native captures."""
from decimal import Decimal
from pathlib import Path
import tempfile
import unittest

from yadinassi import Interpreter, BSLError
from yadinassi.parser import parse


class ExecutionDirectiveTests(unittest.TestCase):
    def setUp(self):
        self.messages = []
        self.vm = Interpreter(self.messages.append)
        self.vm.register_function('Context', lambda: self.vm.execution_context)

    def test_bilingual_server_calls_and_context_restoration(self):
        self.vm.execute('''
&НаСервере
Функция Сумма(Знач А = 40) Экспорт
    Сообщить(Context()); Возврат А + 2;
КонецФункции
&AtClient
Procedure Start()
    Message(Context()); Message(Сумма()); Message(Context());
EndProcedure
Start();
''')
        self.assertEqual(self.messages, ['client', 'server', '42', 'client'])
        self.assertEqual(self.vm.execution_context, 'client')

    def test_preprocessor_selects_server_body_and_client_root(self):
        self.vm.execute('''
&AtServer
Function Side()
#If Server And Not Client Then
 Return "server";
#Else
 Return "wrong";
#EndIf
EndFunction
#If Server Then
Message("never execute server root");
#Else
Message("client");
#EndIf
Message(Side());
''')
        self.assertEqual(self.messages, ['client', 'server'])

    def test_server_only_declaration_and_wrong_side_annotation(self):
        self.vm.execute('''
#If Server Then
&AtServer
Function S() Return 42; EndFunction
&AtClient
Function Invisible() Return 0; EndFunction
#EndIf
#If Client Then
&AtServer
Function AlsoInvisible() Return 0; EndFunction
#EndIf
Message(S());
''')
        self.assertEqual(self.messages, ['42'])
        self.assertEqual(set(self.vm.server_routines), {'s'})
        self.assertNotIn('invisible', self.vm.routines)

    def test_nested_server_calls_and_recursion_stay_server(self):
        self.vm.execute('''
&AtServer
Function F(Val N)
 If N = 0 Then Return Context(); EndIf;
 Return F(N - 1);
EndFunction
Message(F(3));
''')
        self.assertEqual(self.messages, ['server'])

    def test_same_side_server_reference_parameters_remain_live(self):
        self.vm.execute("""
&AtServer
Procedure Inner(X) X = X + 2; EndProcedure
&AtServer
Function Outer(Val X) Inner(X); Return X; EndFunction
Message(Outer(40));
""")
        self.assertEqual(self.messages, ['42'])

    def test_positive_native_probe_is_only_a_local_prediction(self):
        source = (Path(__file__).resolve().parents[1] /
                  'integrational_tests/directive_probes/client_server.bsl').read_text(encoding="utf-8")
        self.vm.execute(source)
        self.assertEqual(self.messages, [])
        self.vm.execute('RunDirectiveProbe();')
        labels = ['call.add', 'preprocessor.server', 'preprocessor.client',
                  'call.nested', 'param.val', 'exception', 'return.number',
                  'return.string', 'return.boolean', 'return.undefined', 'call.recovery']
        self.assertEqual([row.split(':')[0] for row in self.messages],
                         ['directive.' + label for label in labels])
        # These are explicitly local model predictions, never native fixtures.
        self.assertEqual([row.split(': ', 1)[1] for row in self.messages],
                         ['{"N",42}', 'server', 'client', 'server', '{"N",7}',
                          '{"B",1}', '{"N",42}', '{"S","x"}', '{"B",1}',
                          '{"U"}', '{"N",42}'])
        self.assertEqual(self.vm.execution_context, 'client')

    def test_persistent_declaration_replaces_old_context_atomically(self):
        self.vm.execute('Function F() Return "client"; EndFunction')
        self.vm.execute('&AtServer\nFunction F() Return "server"; EndFunction')
        self.assertEqual(self.vm.execute('F()'), 'server')
        self.assertNotIn('f', self.vm.routines)
        self.vm.execute('&AtClient\nFunction F() Return "client-again"; EndFunction')
        self.assertEqual(self.vm.execute('F()'), 'client-again')
        self.assertNotIn('f', self.vm.server_routines)
        with self.assertRaisesRegex(BSLError, 'Одноименные'):
            self.vm.execute('Message("bad"); Function F() Return 0; EndFunction\n'
                            '&AtServer\nFunction F() Return 1; EndFunction')
        self.assertEqual(self.messages, [])
        self.assertEqual(self.vm.execute('F()'), 'client-again')

    def test_unavailable_client_body_cannot_promote_nested_server_routine(self):
        for declaration in ('&AtClient\nProcedure C()', 'Procedure C()',
                            'unused = 1; Procedure C()'):
            with self.subTest(declaration=declaration):
                self.vm.execute(f"""
#If Server Then
{declaration}
 &AtServer
 Function S() Return 42; EndFunction
EndProcedure
#EndIf
""")
                self.assertNotIn('s', self.vm.server_routines)
                with self.assertRaises(BSLError):
                    self.vm.execute('S();')

    def test_server_to_client_denied_before_argument_effects(self):
        self.vm.execute('''
&AtClient
Function ClientOnly(Val X) Return X; EndFunction
&AtServer
Function S() Return ClientOnly(Effect()); EndFunction
''')
        calls = []
        self.vm.register_function('Effect', lambda: calls.append('effect'))
        with self.assertRaisesRegex(BSLError, 'клиентской подпрограммы с сервера'):
            self.vm.execute('S();')
        self.assertEqual(calls, [])
        self.assertEqual(self.vm.execution_context, 'client')

    def test_root_state_does_not_leak_to_server(self):
        self.vm.execute('''
Var Secret;
&AtServer
Function S() Return Secret; EndFunction
Secret = 42;
''')
        with self.assertRaises(BSLError):
            self.vm.execute('S();')
        self.assertEqual(self.vm.variables['secret'], Decimal(42))

    def test_server_local_write_does_not_change_client_storage(self):
        self.vm.execute('''
Var Counter;
&AtServer
Function S() Counter = 7; Return Counter; EndFunction
Counter = 42; Message(S()); Message(Counter);
''')
        self.assertEqual(self.messages, ['7', '42'])

    def test_non_val_expression_boundary_is_explicit_before_effects(self):
        self.vm.execute('&AtServer\nProcedure S(X) EndProcedure')
        calls = []
        self.vm.register_function('Effect', lambda: calls.append('effect'))
        with self.assertRaisesRegex(BSLError, 'без Знач'):
            self.vm.execute('S(Effect());')
        self.assertEqual(calls, [])

    def test_scalar_values_and_val_rebinding(self):
        self.vm.execute('''
&AtServer
Function Identity(Val X) Return X; EndFunction
&AtServer
Procedure Replace(Val X) X = 9; EndProcedure
x = 3; Replace(x); Message(x);
''')
        for expression, expected in [('"x"', 'x'), ('42', Decimal(42)),
                                     ('True', True), ('Undefined', None)]:
            self.assertEqual(self.vm.execute(f'Identity({expression})'), expected)
        self.assertEqual(self.messages, ['3'])

    def test_unsupported_objects_rejected_at_boundary_without_callee_effects(self):
        self.vm.execute('''
&AtServer
Function S(Val X) Message("entered"); Return X; EndFunction
''')
        with self.assertRaisesRegex(BSLError, 'Межконтекстная передача'):
            self.vm.execute('S(New Map());')
        self.assertEqual(self.messages, [])

    def test_unsupported_return_rejected_and_caller_restored(self):
        self.vm.execute('&AtServer\nFunction S() Return New Map(); EndFunction')
        with self.assertRaisesRegex(BSLError, 'Межконтекстная передача'):
            self.vm.execute('S();')
        self.assertEqual(self.vm.execution_context, 'client')

    def test_server_exception_can_be_caught_and_execution_restored(self):
        self.vm.execute('''
&AtServer
Procedure S() Raise "server failure"; EndProcedure
Try S(); Except Message(ErrorDescription()); EndTry;
Message(Context());
''')
        self.assertIn('server failure', self.messages[0])
        self.assertEqual(self.messages[1], 'client')
        self.assertEqual(self.vm.execution_context, 'client')

    def test_eval_execute_keep_server_scope(self):
        self.vm.execute('''
&AtServer
Function S(Val X)
 Execute("X = X + 1;"); Return Eval("X + 1");
EndFunction
Message(S(40));
''')
        self.assertEqual(self.messages, ['42'])
        with self.assertRaises(BSLError):
            self.vm.execute('Execute("&AtServer");')

    def test_import_owner_and_same_module_exports_use_server_registry(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d)
            (p / 'Side.bsl').write_text('&AtServer\nFunction F(Val X=40) Export Return X+2; EndFunction', encoding="utf-8")
            self.vm.execute('// #Импорт Side.bsl\nMessage(Side.F());', str(p/'root.bsl'))
        self.assertEqual(self.messages, ['42'])
        self.vm.execute('&AtServer\nFunction S() Export Return 7; EndFunction')
        self.assertEqual(self.vm.execute('ThisObject.S()'), Decimal(7))

    def test_imported_server_diagnostics_do_not_read_client_handler(self):
        for nested in (False, True):
            with self.subTest(nested=nested), tempfile.TemporaryDirectory() as d:
                root = Path(d)
                (root / 'Leaf.bsl').write_text("""
&AtServer
Function Description() Export
 Try Raise "server-error"; Except Return ErrorDescription(); EndTry;
EndFunction
&AtServer
Function InfoDescription() Export
 Try Raise "server-error"; Except Return ErrorInfo().Description; EndTry;
EndFunction
&AtServer
Function EmptyDescription() Export
 Return ErrorDescription();
EndFunction
""", encoding="utf-8")
                if nested:
                    (root / 'Middle.bsl').write_text("""// #Импорт Leaf.bsl
Function Description() Export Return Leaf.Description(); EndFunction
Function InfoDescription() Export Return Leaf.InfoDescription(); EndFunction
Function EmptyDescription() Export Return Leaf.EmptyDescription(); EndFunction
""", encoding="utf-8")
                name = 'Middle' if nested else 'Leaf'
                messages = []
                vm = Interpreter(messages.append)
                vm.execute(f"""// #Импорт {name}.bsl
Message({name}.Description());
Message({name}.InfoDescription());
Try Raise "client-secret"; Except
 Message({name}.Description());
 Message({name}.InfoDescription());
 Message({name}.EmptyDescription());
 Message(ErrorDescription());
EndTry;
""", str(root / 'root.bsl'))
                self.assertEqual(len(messages), 6)
                for message in messages[:4]:
                    self.assertIn('server-error', message)
                    self.assertNotIn('client-secret', message)
                self.assertEqual(messages[4], '')
                self.assertIn('client-secret', messages[5])
                self.assertEqual(vm.execution_context, 'client')

    def test_invalid_server_placement_and_unsupported_families(self):
        for code in ('&AtServer\nx=1;',
                     '&AtServer\n&AtClient\nProcedure P() EndProcedure',
                     'Procedure P()\n&AtServer\nProcedure S() EndProcedure\nEndProcedure',
                     '&AtServerNoContext\nProcedure S() EndProcedure',
                     '&AtClientAtServerNoContext\nProcedure S() EndProcedure'):
            with self.subTest(code=code), self.assertRaises(BSLError):
                parse(code)

    def test_server_parse_error_precedes_root_effects(self):
        with self.assertRaises(BSLError):
            self.vm.execute('Message("bad");\n#If Server Then\n&AtServer\nFunction S() Return +; EndFunction\n#EndIf')
        self.assertEqual(self.messages, [])

    def test_routine_declarations_are_not_scanned_from_strings(self):
        self.vm.execute('Message("text\n|&AtServer\n|Function S() Return 9; EndFunction");')
        self.assertEqual(self.vm.server_routines, {})

    def test_server_condition_does_not_activate_root_imports(self):
        self.vm.execute('#If Server Then\n// #Импорт Missing.bsl\n#EndIf\n42')
        self.assertEqual(self.vm.imports, {})

if __name__ == '__main__':
    unittest.main()
