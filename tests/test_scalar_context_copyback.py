"""Bounded scalar client/server copyback and its explicit local safety guards.

The scalar semantics follow the audited native 8.3.27.1508 core capture.
The rejection/atomic-validation tests specify Yadinassi's narrower boundary,
not additional native behavior for objects or unsupported actual expressions.
"""
from decimal import Decimal
from pathlib import Path
import tempfile
import unittest

from yadinassi import BSLError, Interpreter


class ScalarContextCopybackTests(unittest.TestCase):
    def setUp(self):
        self.messages = []
        self.vm = Interpreter(self.messages.append)
        self.vm.register_function('Context', lambda: self.vm.execution_context)

    def assert_restored(self):
        self.assertEqual(self.vm.execution_context, 'client')
        self.assertEqual(self.vm._context_stack, ['client'])
        self.assertIsNone(self.vm.locals)

    def test_scalar_copyback_and_val_isolation(self):
        self.vm.execute('''
&НаСервере
Процедура Заменить(А, Знач Б, Знач Новое)
    А = Новое; Б = Новое;
КонецПроцедуры
&AtClient
Procedure Start()
    Var A, B;
    A = 1; B = 2; Заменить(A, B, 43); Message(A); Message(B);
    Заменить(A, B, "text"); Message(A);
    Заменить(A, B, True); Message(ValueToStringInternal(A));
    Заменить(A, B, Undefined); Message(ValueToStringInternal(A));
EndProcedure
Start();
''')
        self.assertEqual(self.messages, ['43', '2', 'text', '{"B",1}', '{"U"}'])
        self.assert_restored()

    def test_function_result_and_output_are_separate(self):
        self.vm.execute('''
&AtServer
Function Change(X) X = 43; Return 97; EndFunction
x = 1; result = Change(x);
''')
        self.assertEqual(self.vm.variables['result'], Decimal(97))
        self.assertEqual(self.vm.variables['x'], Decimal(43))
        self.assert_restored()

    def test_early_procedure_and_implicit_function_returns_copy_out(self):
        self.vm.execute('''
&AtServer
Procedure Early(X) X = 43; Return; X = 99; EndProcedure
&AtServer
Function Implicit(X) X = 47; EndFunction
x = 1; Early(x); Message(x); Message(ValueToStringInternal(Implicit(x))); Message(x);
''')
        self.assertEqual(self.messages, ['43', '{"U"}', '47'])
        self.assert_restored()

    def test_server_bindings_are_detached_until_return(self):
        observed = []
        self.vm.register_function('ObserveCaller', lambda: observed.append(
            (self.vm.variables['x'], self.vm.execution_context)))
        self.vm.execute('''
&AtServer
Procedure Change(X) X = 43; ObserveCaller(); EndProcedure
x = 1; Change(x);
''')
        self.assertEqual(observed, [(Decimal(1), 'server')])
        self.assertEqual(self.vm.variables['x'], Decimal(43))
        self.assert_restored()

    def test_repeated_actuals_have_independent_formals(self):
        self.vm.execute('''
&AtServer
Function Independent(A, B) A = 41; Return B; EndFunction
x = 1; result = Independent(x, x);
''')
        self.assertEqual(self.vm.variables['result'], Decimal(1))
        self.assertEqual(self.vm.variables['x'], Decimal(1))
        self.assert_restored()

    def test_all_formals_copy_out_in_position_order_not_write_order(self):
        for body, expected in [
                ('B = 52; A = 41;', Decimal(52)),
                ('A = 41;', Decimal(1)),
                ('A = 41; B = B;', Decimal(1)),
                ('A = 41; B = 2; B = 1;', Decimal(1))]:
            with self.subTest(body=body):
                self.vm.execute(f'''
&AtServer
Procedure Aliases(A, B) {body} EndProcedure
x = 1; Aliases(x, x);
''')
                self.assertEqual(self.vm.variables['x'], expected)
                self.assert_restored()

    def test_non_val_copy_in_follows_all_actual_expression_effects(self):
        self.vm.execute('''
&AtServer
Function Timing(Val Before, A, Val After)
    Return Before * 100 + A * 10 + After;
EndFunction
&AtClient
Function Before(Calls) Calls = Calls + 1; Return Calls; EndFunction
&AtClient
Function Change(X, Calls) Calls = Calls + 1; X = 9; Return Calls; EndFunction
&AtClient
Procedure Start()
    X = 1; Calls = 0;
    Message(Timing(Before(Calls), X, Change(X, Calls))); Message(X); Message(Calls);
EndProcedure
Start();
''')
        self.assertEqual(self.messages, ['192', '9', '2'])
        self.assert_restored()

    def test_val_snapshot_is_not_delayed_with_non_val_copy_in(self):
        self.vm.execute('''
&AtServer
Function Timing(Val Snapshot, A, Val Ignored) Return Snapshot * 10 + A; EndFunction
Function Change(X) X = 9; Return 0; EndFunction
x = 1; result = Timing(x, x, Change(x));
''')
        self.assertEqual(self.vm.variables['result'], Decimal(19))
        self.assertEqual(self.vm.variables['x'], Decimal(9))

    def test_escaping_exception_does_not_copy_out_and_recovery_works(self):
        self.vm.execute('''
&AtServer
Procedure Fails(X, Y, Val Control)
    X = 47; Control = 99; Raise "server-failure";
EndProcedure
&AtServer
Procedure Recover(X) X = 43; EndProcedure
x = 1; y = 2; control = 3;
Try Fails(x, y, control); Except
    Message(x); Message(y); Message(control); Message(Context());
    Message(ValueToStringInternal(Find(ErrorDescription(), "server-failure") > 0));
EndTry;
Recover(x); Message(x);
''')
        self.assertEqual(self.messages[:4], ['1', '2', '3', 'client'])
        self.assertEqual(self.messages[-1], '43')
        self.assertEqual(self.messages[4], '{"B",1}')
        self.assert_restored()

    def test_server_caught_exception_with_normal_return_does_copy_out(self):
        self.vm.execute('''
&AtServer
Function Caught(X)
    X = 47;
    Try Raise "server-failure"; Except
        Return Find(ErrorDescription(), "server-failure") > 0;
    EndTry;
EndFunction
x = 1; result = Caught(x);
''')
        self.assertIs(self.vm.variables['result'], True)
        self.assertEqual(self.vm.variables['x'], Decimal(47))
        self.assert_restored()

    def test_failure_keeps_actual_expression_effects_not_pre_call_state(self):
        self.vm.execute('''
&AtServer
Procedure Fails(X, Val Ignored) X = 47; Raise "server-failure"; EndProcedure
Function Change(X) X = 9; Return 0; EndFunction
x = 1; Try Fails(x, Change(x)); Except Message(x); EndTry;
''')
        self.assertEqual(self.messages, ['9'])
        self.assert_restored()

    def test_forwarded_caller_references_and_val_frame_restore(self):
        self.vm.execute('''
&AtServer
Procedure Change(X) X = 43; EndProcedure
Procedure ForwardAgain(X) Change(X); EndProcedure
Procedure Forward(X, Val Y)
    ForwardAgain(X); ForwardAgain(Y); Message(Y); Message(Context());
EndProcedure
x = 1; y = 2; Forward(x, y); Message(x); Message(y);
''')
        self.assertEqual(self.messages, ['43', 'client', '43', '2'])
        self.assert_restored()

    def test_forwarded_property_and_index_sinks_do_not_widen_boundary(self):
        self.vm.execute('''
&AtServer
Procedure Change(A, B) Message("entered"); A = 43; B = 47; EndProcedure
Procedure ForwardAgain(A, B) Change(A, B); EndProcedure
Procedure Forward(A, B) ForwardAgain(A, B); EndProcedure
s = New Structure("Value", 2); f = New FixedStructure(s);
a = New Array(); a.Add(2); fa = New FixedArray(a);
m = New Map(); m.Insert("key", 2); fm = New FixedMap(m);
x = 1;
''')
        for sink in ('s.Value', 'f.Value', 's["Value"]', 'f["Value"]',
                     'a[0]', 'fa[0]', 'm["key"]', 'fm["key"]'):
            for actuals in (f'x, {sink}', f'{sink}, x'):
                with self.subTest(actuals=actuals), self.assertRaisesRegex(
                        BSLError, 'без Знач.*имя переменной'):
                    self.vm.execute(f'Forward({actuals});')
                self.assertEqual(self.vm.variables['x'], Decimal(1))
                self.assertEqual(self.vm.execute(sink), Decimal(2))
                self.assertEqual(self.messages, [])
                self.assert_restored()

    def test_execute_preserves_named_storage_and_does_not_launder_sink_references(self):
        self.vm.execute('''
&AtServer
Procedure Change(A, B) Message("entered"); A = 43; B = 47; EndProcedure
Procedure Forward(A, B) Execute("Change(A, B);"); EndProcedure
x = 1; y = 2; Execute("Forward(x, y);");
''')
        self.assertEqual(self.vm.variables['x'], Decimal(43))
        self.assertEqual(self.vm.variables['y'], Decimal(47))
        self.assertEqual(self.messages, ['entered'])
        self.messages.clear()
        self.vm.execute('x = 1; s = New Structure("Value", 2); f = New FixedStructure(s);')
        for sink in ('s.Value', 'f.Value'):
            with self.subTest(sink=sink), self.assertRaisesRegex(
                    BSLError, 'без Знач.*имя переменной'):
                self.vm.execute(f'Forward(x, {sink});')
            self.assertEqual(self.vm.variables['x'], Decimal(1))
            self.assertEqual(self.vm.execute(sink), Decimal(2))
            self.assertEqual(self.messages, [])
            self.assert_restored()

    def test_nested_server_calls_keep_live_same_side_aliases(self):
        self.vm.execute('''
&AtServer
Procedure Inner(A, B) A = 41; Message(B); B = 52; EndProcedure
&AtServer
Procedure Outer(X) Inner(X, X); Message(X); Message(Context()); EndProcedure
x = 1; Outer(x); Message(x);
''')
        self.assertEqual(self.messages, ['41', '52', 'server', '52'])
        self.assert_restored()

    def test_nested_server_exception_caught_by_outer_copies_prior_live_write(self):
        self.vm.execute('''
&AtServer
Procedure Inner(X) X = 47; Raise "nested"; EndProcedure
&AtServer
Procedure Outer(X)
    Try Inner(X); Except Message(X); EndTry;
EndProcedure
x = 1; Outer(x); Message(x);
''')
        self.assertEqual(self.messages, ['47', '47'])
        self.assert_restored()

    def test_same_side_client_alias_and_exception_behavior_is_unchanged(self):
        self.vm.execute('''
Procedure Change(A, B)
    A = 41; Message(B); B = 52; Raise "client-failure";
EndProcedure
x = 1; Try Change(x, x); Except Message(x); EndTry;
''')
        self.assertEqual(self.messages, ['41', '52'])
        self.assert_restored()

    def test_all_outgoing_values_validate_before_any_caller_write(self):
        for body in ('A = 43; B = New Array();',
                     'A = New Array(); B = 43;'):
            with self.subTest(body=body):
                self.vm.execute(f'''
&AtServer
Procedure Invalid(A, B) {body} EndProcedure
x = 1; y = 2;
''')
                for actuals in ('x, y', 'x, x'):
                    with self.subTest(actuals=actuals), self.assertRaisesRegex(
                            BSLError, 'Межконтекстная передача'):
                        self.vm.execute(f'Invalid({actuals});')
                    self.assertEqual(self.vm.variables['x'], Decimal(1))
                    self.assertEqual(self.vm.variables['y'], Decimal(2))
                    self.assert_restored()

    def test_invalid_function_result_prevents_copyout_even_when_discarded(self):
        self.vm.execute('''
&AtServer
Function Invalid(X) X = 43; Return New Array(); EndFunction
x = 1;
''')
        for call in ('Invalid(x);', 'result = Invalid(x);'):
            with self.subTest(call=call), self.assertRaisesRegex(
                    BSLError, 'Межконтекстная передача'):
                self.vm.execute(call)
            self.assertEqual(self.vm.variables['x'], Decimal(1))
            self.assert_restored()

    def test_val_formal_is_not_an_outgoing_value(self):
        self.vm.execute('''
&AtServer
Procedure Change(X, Val Control) X = 43; Control = New Array(); EndProcedure
x = 1; control = 2; Change(x, control);
''')
        self.assertEqual(self.vm.variables['x'], Decimal(43))
        self.assertEqual(self.vm.variables['control'], Decimal(2))
        self.assert_restored()

    def test_non_scalar_input_rejected_before_server_body(self):
        self.vm.execute('''
&AtServer
Procedure Change(X) Message("entered"); X = 43; EndProcedure
''')
        for expression in ('New Array()', 'New Structure()', 'Date(2026, 1, 1)'):
            with self.subTest(expression=expression):
                self.vm.execute(f'x = {expression};')
                original = self.vm.variables['x']
                with self.assertRaisesRegex(BSLError, 'Межконтекстная передача'):
                    self.vm.execute('Change(x);')
                self.assertIs(self.vm.variables['x'], original)
                self.assertEqual(self.messages, [])
                self.assert_restored()

    def test_non_val_scalar_validation_uses_late_snapshot(self):
        self.vm.execute('''
&AtServer
Procedure Change(X, Val Ignored) Message(X); X = 43; EndProcedure
Function Scalar(X) X = 9; Return 0; EndFunction
Function ObjectValue(X) X = New Array(); Return 0; EndFunction
x = New Array(); Change(x, Scalar(x));
''')
        self.assertEqual(self.messages, ['9'])
        self.assertEqual(self.vm.variables['x'], Decimal(43))
        with self.assertRaisesRegex(BSLError, 'Межконтекстная передача'):
            self.vm.execute('Change(x, ObjectValue(x));')
        self.assertEqual(self.messages, ['9'])
        self.assertEqual(self.vm.execute('x.Count()'), Decimal(0))
        self.assert_restored()

    def test_unsupported_non_val_actuals_rejected_before_any_argument_effects(self):
        effects = []
        self.vm.register_function('Effect', lambda: effects.append('effect'))
        self.vm.execute('''
&AtServer
Procedure Change(Val Before, X = 1, Val After = 0) Message("entered"); EndProcedure
''')
        for call in ('Change(Effect(), Owner().Value);',
                     'Change(Effect(), Owner()[Effect()]);',
                     'Change(Effect(), (Owner().Value));',
                     'Change(Effect(), Effect());',
                     'Change(Effect(), 1);',
                     'Change(Effect(), 1 + Effect());',
                     'Change(Effect(), , 0);',
                     'Change(Effect());'):
            with self.subTest(call=call), self.assertRaisesRegex(
                    BSLError, 'без Знач.*имя переменной'):
                self.vm.execute(call)
            self.assertEqual(effects, [])
            self.assertEqual(self.messages, [])
            self.assert_restored()

    def test_non_storage_names_are_not_accepted_as_output_actuals(self):
        self.vm.execute('&AtServer\nProcedure Change(X) X = 43; EndProcedure')
        with self.assertRaisesRegex(BSLError, 'без Знач.*имя переменной'):
            self.vm.execute('Change(Chars);')
        self.assert_restored()

    def test_declared_undefined_grouped_actual_and_val_defaults_remain_supported(self):
        self.vm.execute('''
&AtServer
Procedure Change(X, Val Defaulted = 43, Val After = 0) X = Defaulted; EndProcedure
Var x; Change(((x)), , 0); Message(x); Change(x); Message(x);
''')
        self.assertEqual(self.messages, ['43', '43'])
        self.assert_restored()

    def test_server_to_client_rejection_discards_pending_copyback(self):
        effects = []
        self.vm.register_function('Effect', lambda: effects.append('effect'))
        self.vm.execute('''
&AtClient
Procedure Client(Val X) EndProcedure
&AtServer
Procedure Server(X) X = 43; Client(Effect()); EndProcedure
x = 1;
''')
        with self.assertRaisesRegex(BSLError, 'клиентской подпрограммы с сервера'):
            self.vm.execute('Server(x);')
        self.assertEqual(self.vm.variables['x'], Decimal(1))
        self.assertEqual(effects, [])
        self.assert_restored()

    def test_imported_forwarding_uses_owner_server_and_restores_all_frames(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'Leaf.bsl').write_text('''
Var Secret;
Secret = 99;
&AtServer
Procedure Inner(X) X = X + 1; EndProcedure
&AtServer
Procedure Change(X) Export
    Inner(X); Message(Context());
EndProcedure
&AtServer
Procedure Fails(X) Export X = 47; Raise "imported-failure"; EndProcedure
&AtServer
Procedure ReadClient(X) Export X = Secret; EndProcedure
''', encoding='utf-8')
            (root / 'Middle.bsl').write_text('''// #Импорт Leaf.bsl
Procedure Forward(X) Export Leaf.Change(X); EndProcedure
Procedure Fails(X) Export Leaf.Fails(X); EndProcedure
Procedure ReadClient(X) Export Leaf.ReadClient(X); EndProcedure
''', encoding='utf-8')
            self.vm.execute('''// #Импорт Middle.bsl
Var Secret;
&AtServer
Procedure Inner(X) X = 999; EndProcedure
Secret = 100; x = 42; Middle.Forward(x); Message(x);
Try Middle.Fails(x); Except Message(x); Message(Context()); EndTry;
Try Middle.ReadClient(x); Except Message(x); EndTry;
Middle.Forward(x); Message(x); Message(Secret);
''', str(root / 'root.bsl'))
        self.assertEqual(self.messages, ['server', '43', '43', 'client', '43',
                                         'server', '44', '100'])
        middle = self.vm.imports['middle'].interpreter
        leaf = middle.imports['leaf'].interpreter
        self.assertEqual(leaf.variables['secret'], Decimal(99))
        self.assertIsNone(middle.locals)
        self.assertIsNone(leaf.locals)
        self.assert_restored()


if __name__ == '__main__':
    unittest.main()
