"""Positional routine parameters, reference aliases, and Val semantics."""
from decimal import Decimal
import unittest

from yadinassi import BSLError, Interpreter
from yadinassi.errors import IncompleteInput
from yadinassi.syntax.parser import parse


class ParameterTests(unittest.TestCase):
    def setUp(self):
        self.output = []
        self.vm = Interpreter(output=self.output.append)

    def test_sum_forward_call_and_bilingual_parameters(self):
        self.vm.execute('''
            Сообщить(ПолучитьСумму(1, 2));
            Функция ПолучитьСумму(Знач Первое, vAl Второе) Экспорт
                Возврат первое + ВТОРОЕ;
            КонецФункции
        ''')
        self.assertEqual(self.output, ['3'])
        self.assertTrue(self.vm.routines['получитьсумму'].exported)

    def test_reference_rebinding_and_value_isolation(self):
        self.vm.execute('''
            Procedure Change(reference, Val value)
                reference = 7; value = 8;
            EndProcedure
            x = 1; y = 2; Change(x, y); Message(x); Message(y);
        ''')
        self.assertEqual(self.output, ['7', '2'])

    def test_aliases_are_live_not_copied_back_at_return(self):
        self.vm.execute('''
            Procedure Change(first, second)
                first = 8; Message(second); second = second + 1; Message(first);
            EndProcedure
            x = 0; Change(x, x); Message(x);
        ''')
        self.assertEqual(self.output, ['8', '9', '9'])

    def test_forwarded_reference_and_value_parameter(self):
        self.vm.execute('''
            Procedure Inner(x) x = x + 1; EndProcedure
            Procedure Outer(x, Val y)
                Inner(x); Inner(y); Message(y);
            EndProcedure
            x = 1; y = 4; Outer(x, y); Message(x); Message(y);
        ''')
        self.assertEqual(self.output, ['5', '2', '4'])

    def test_parameters_shadow_module_names_and_use_caller_scope(self):
        self.vm.execute('''
            Var x; x = 100;
            Procedure Change(x) x = x + 1; EndProcedure
            Function Outer(Val x) Change(x); Return x; EndFunction
            Message(Outer(7)); Message(x);
            Change(x); Message(x);
        ''')
        self.assertEqual(self.output, ['8', '100', '101'])
        self.assertIsNone(self.vm.locals)

    def test_value_parameters_do_not_clone_mutable_objects(self):
        self.vm.execute('''
            Procedure Change(Val a)
                a.Add(7); a = New Array; a.Add(9);
            EndProcedure
            a = New Array; Change(a); Message(a.Count()); Message(a[0]);
        ''')
        self.assertEqual(self.output, ['1', '7'])

    def test_reference_parameter_can_replace_object(self):
        self.vm.execute('''
            Procedure Replace(a) a = New Array; a.Add(9); EndProcedure
            a = New Array; a.Add(7); Replace(a); Message(a[0]);
        ''')
        self.assertEqual(self.output, ['9'])

    def test_literals_expressions_and_function_results_use_temporaries(self):
        self.vm.execute('''
            Function Two() Return 2; EndFunction
            Function Change(x) x = x + 1; Return x; EndFunction
            x = 10;
            Message(Change(1)); Message(Change(x + 1)); Message(Change(Two()));
            Message(Change(?(True, x, 1 / 0))); Message(x);
            Message(Change((x + 2))); Message(Change((x) + 2));
        ''')
        self.assertEqual(self.output, ['2', '12', '3', '11', '10', '13', '13'])

    def test_recursion_and_early_return_restore_bindings(self):
        self.vm.execute('''
            Function Factorial(Val n)
                If n <= 1 Then Return 1; EndIf;
                Return n * Factorial(n - 1);
            EndFunction
            n = 5; Message(Factorial(n)); Message(n);
        ''')
        self.assertEqual(self.output, ['120', '5'])
        self.assertIsNone(self.vm.locals)

    def test_argument_evaluation_is_once_left_to_right_in_caller(self):
        self.vm.execute('''
            Var counter; counter = 0;
            Function Next() counter = counter + 1; Return counter; EndFunction
            Function Pair(Val a, Val b) Return a * 10 + b; EndFunction
            Function Caller(Val counter) Return Pair(counter, Next()); EndFunction
            Message(Pair(Next(), Next())); Message(Caller(8)); Message(counter);
        ''')
        self.assertEqual(self.output, ['12', '83', '3'])

    def test_value_snapshot_and_reference_binding_before_later_argument(self):
        self.vm.execute('''
            Var x; x = 1;
            Function Change() x = 9; Return 0; EndFunction
            Procedure Show(Val snapshot, reference, unused)
                Message(snapshot); Message(reference);
            EndProcedure
            Show(x, x, Change());
        ''')
        self.assertEqual(self.output, ['1', '9'])

    def test_grouped_and_indexed_reference_arguments_update_caller(self):
        self.vm.execute('Procedure P(x) x = x + 1; EndProcedure x = 1; '
                        'a = New Array; a.Add(1);')
        for code in ['P((x))', 'P(((x)))', 'P(a[0])', 'P((a[0]))']:
            self.vm.execute(code)
        self.assertEqual(self.vm.execute('x'), Decimal(3))
        self.assertEqual(self.vm.execute('a[0]'), Decimal(3))

    def test_value_parameters_accept_grouped_and_indexed_expressions(self):
        self.vm.execute('''
            Function F(Val x) x = x + 1; Return x; EndFunction
            a = New Array; a.Add(7); x = 1;
            Message(F(a[0])); Message(F((x))); Message(a[0]); Message(x);
        ''')
        self.assertEqual(self.output, ['8', '2', '7', '1'])

    def test_declared_undefined_variable_can_be_output_parameter(self):
        self.vm.execute('''
            Procedure SetValue(x) x = 42; EndProcedure
            Var result; SetValue(result); Message(result);
        ''')
        self.assertEqual(self.output, ['42'])
        with self.assertRaisesRegex(BSLError, 'не определена'):
            self.vm.execute('SetValue(undeclared)')

    def test_parameter_loop_assignments_use_reference(self):
        self.vm.execute('''
            Procedure Loop(i)
                For i = 1 To 2 Do EndDo;
            EndProcedure
            x = 0; Loop(x); Message(x);
        ''')
        self.assertEqual(self.output, ['3'])

    def test_foreach_assigns_through_reference_parameter(self):
        self.vm.execute('''
            Procedure Last(item, Val items)
                For Each item In items Do EndDo;
            EndProcedure
            a = New Array; a.Add(2); a.Add(7);
            x = 0; Last(x, a); Message(x);
        ''')
        self.assertEqual(self.output, ['7'])

    def test_group_nodes_preserve_calls_and_postfix_access(self):
        self.vm.execute('''
            Procedure P(x) x = x + 1; EndProcedure
            Function F(Val x) Return x + 1; EndFunction
            x = 1; ((P))(x); (P(x));
            (Message)(((F))(x));
            a = New Array; (a).Add(8); Message((a)[0]);
        ''')
        self.assertEqual(self.output, ['4', '8'])

    def test_wrong_arity_rejects_before_argument_or_body_effects(self):
        self.vm.execute('Procedure P(a, b) Message("body"); EndProcedure')
        for code in ['P();', 'P(Message("bad"));', 'P(1, 2, Message("bad"));']:
            with self.subTest(code=code), self.assertRaisesRegex(BSLError, '2 аргументов'):
                self.vm.execute(code)
        self.assertEqual(self.output, [])

    def test_error_restores_frames_but_keeps_reference_writes(self):
        self.vm.execute('''
            Procedure Inner(x) x = 7; fail = 1 / 0; EndProcedure
            Procedure Outer(x) Inner(x); EndProcedure
            x = 1;
        ''', 'definition.bsl')
        with self.assertRaises(BSLError) as caught:
            self.vm.execute('Outer(x)', 'caller.bsl')
        self.assertEqual(caught.exception.source, 'definition.bsl')
        self.assertEqual(self.vm.variables['x'], Decimal(7))
        self.assertIsNone(self.vm.locals)

    def test_argument_error_does_not_enter_body_or_leak_frame(self):
        self.vm.execute('Procedure P(x, y) Message("bad"); EndProcedure')
        with self.assertRaises(BSLError):
            self.vm.execute('P(1, 1 / 0)')
        self.assertEqual(self.output, [])
        self.assertIsNone(self.vm.locals)

    def test_invalid_parameter_syntax_fails_before_side_effects(self):
        cases = [
            ('Procedure P(a, A) EndProcedure', 'Повторное'),
            ('Procedure P(x) Var X; EndProcedure', 'уже объявлена'),
            ('Procedure P(Val) EndProcedure', 'IDENT'),
            ('Procedure P(x,) EndProcedure', 'IDENT'),
        ]
        for code, message in cases:
            with self.subTest(code=code), self.assertRaisesRegex(BSLError, message):
                self.vm.execute('Message("bad"); ' + code)
        self.assertEqual(self.output, [])

    def test_incomplete_parameters_allow_multiline_input(self):
        for code in ['Function F(', 'Function F(Val', 'Function F(a,',
                     'Function F(a)', 'F(1,']:
            with self.subTest(code=code), self.assertRaises(IncompleteInput):
                parse(code)

    def test_redefinition_replaces_parameter_signature(self):
        self.vm.execute('Function F(x) Return x; EndFunction')
        self.assertEqual(self.vm.execute('F(7)'), Decimal(7))
        self.vm.execute('Function F(x, y) Return x + y; EndFunction')
        with self.assertRaisesRegex(BSLError, '2 аргументов'):
            self.vm.execute('F(7)')
        self.assertEqual(self.vm.execute('F(7, 8)'), Decimal(15))


if __name__ == '__main__':
    unittest.main()
