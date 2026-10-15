"""BSL constant defaults and comma-delimited skipped positions."""
from decimal import Decimal
import unittest

from yadinassi import BSLError, Interpreter
from yadinassi import ast
from yadinassi.errors import IncompleteInput
from yadinassi.parser import parse


class DefaultParameterTests(unittest.TestCase):
    def setUp(self):
        self.output = []
        self.vm = Interpreter(output=self.output.append)

    def test_defaults_and_explicit_arguments_bilingual(self):
        self.vm.execute('''
            Сообщить(Сумма());
            Функция Сумма(Знач а = 10, б = -2)
                Возврат а + б;
            КонецФункции
            Сообщить(Сумма(3)); Сообщить(Сумма(, 4));
            Function Echo(Val value = "default") Return value; EndFunction
            Message(Echo()); Message(Echo("explicit"));
        ''')
        self.assertEqual(self.output, ['8', '1', '14', 'default', 'explicit'])

    def test_supported_constant_types(self):
        values = [('0', Decimal(0)), ('+1.25', Decimal('1.25')),
                  ('-2.5', Decimal('-2.5')), ('"a""b"', 'a"b'),
                  ('Истина', True), ('False', False), ('Неопределено', None)]
        for literal, expected in values:
            with self.subTest(literal=literal):
                self.vm.execute(f'Function F(x = {literal}) Return x; EndFunction')
                value = self.vm.execute('F()')
                self.assertEqual(value, expected)
                self.assertIs(type(value), type(expected))

    def test_required_after_optional_and_explicit_skips(self):
        self.vm.execute('''
            Function F(a = 1, b, c = 3)
                Return String(a) + ":" + String(b) + ":" + String(c);
            EndFunction
        ''')
        self.assertEqual(self.vm.execute('F(, 2)'), '1:2:3')
        self.assertEqual(self.vm.execute('F(,,3)'), '1::3')
        self.assertEqual(self.vm.execute('F(,,9)'), '1::9')
        for code in ['F()', 'F(1)', 'F(1,)']:
            with self.subTest(code=code), self.assertRaises(BSLError):
                self.vm.execute(code)

    def test_interior_skips_and_trailing_comma_diagnostics(self):
        self.vm.execute('Procedure P(a, b, c) Message(a = Undefined); '
                        'Message(b = Undefined); Message(c); EndProcedure')
        self.vm.execute('P(,,3)')
        self.assertEqual(self.output, ['Да', 'Да', '3'])
        for code in ['P(,)', 'P(,,)', 'P(,,,)', 'P(1,)', 'P(1,,)']:
            with self.subTest(code=code), self.assertRaisesRegex(BSLError, 'Запятая в конце'):
                self.vm.execute('Message("bad"); ' + code)
        self.assertEqual(self.output, ['Да', 'Да', '3'])
        for code, count in [('P()', 0), ('P(,1)', 2), ('P(,,1)', 3), ('P(1,,2)', 3)]:
            with self.subTest(code=code):
                self.assertEqual(len(parse(code)[0].expression.arguments), count)
        self.assertIsInstance(parse('P(,1)')[0].expression.arguments[0], ast.OmittedArgument)

    def test_undefined_is_an_explicit_value_not_a_skip(self):
        self.vm.execute('Function F(x = 7) Return x; EndFunction Var value;')
        self.assertEqual(self.vm.execute('F()'), Decimal(7))
        for code in ['F(Undefined)', 'F(value)', 'F(?(True, Undefined, 1))']:
            with self.subTest(code=code):
                self.assertIsNone(self.vm.execute(code))

    def test_default_temporaries_and_explicit_references(self):
        self.vm.execute('''
            Function Increment(x = 10) x = x + 1; Return x; EndFunction
            Procedure Forward(x = 20) Message(Increment(x)); EndProcedure
            Message(Increment()); Message(Increment()); Forward(); Forward();
            x = 30; Message(Increment(x)); Message(x);
        ''')
        self.assertEqual(self.output, ['11', '11', '21', '21', '31', '31'])
        self.assertIsNone(self.vm.locals)

    def test_recursion_default_frames_and_redefinition(self):
        self.vm.execute('''
            Function F(Val n, Val sum = 0)
                If n = 0 Then Return sum; EndIf;
                Return F(n - 1, sum + n);
            EndFunction
            Message(F(3)); Message(F(2));
        ''')
        self.assertEqual(self.output, ['6', '3'])
        self.vm.execute('Function F(x = 9) Return x; EndFunction')
        self.assertEqual(self.vm.execute('F()'), Decimal(9))
        self.vm.execute('Function F(x) Return x; EndFunction')
        with self.assertRaises(BSLError):
            self.vm.execute('F()')

    def test_left_to_right_evaluation_with_skipped_positions(self):
        self.vm.execute('''
            Var count; count = 0;
            Function Next() count = count + 1; Return count; EndFunction
            Function F(Val a, b = 5, Val c = 9) Return a * 100 + b * 10 + c; EndFunction
            Message(F(Next(),,Next())); Message(count);
        ''')
        self.assertEqual(self.output, ['152', '2'])

    def test_arity_error_precedes_side_effects_and_has_call_location(self):
        self.vm.execute('Procedure P(a = 1, b) Message("body"); EndProcedure')
        for code in ['P(Message("bad"))', 'P(1, 2, Message("bad"))', 'P(,,,4)']:
            with self.subTest(code=code), self.assertRaises(BSLError) as caught:
                self.vm.execute(code, 'caller.bsl')
            self.assertEqual(caught.exception.source, 'caller.bsl')
            self.assertEqual(caught.exception.line, 1)
        self.assertEqual(self.output, [])

    def test_default_expressions_rejected_before_module_effects(self):
        for default in ['name', 'F()', 'New Array', '1 + 2', '(1)', 'Not True',
                        '-True', '+"x"', '--1', '?(True, 1, 2)']:
            with self.subTest(default=default), self.assertRaises(BSLError):
                self.vm.execute(f'Message("bad"); Function F(x = {default}) EndFunction')
        self.assertEqual(self.output, [])

    def test_host_omissions_rejected_without_argument_effects(self):
        for code in ['Message(,1)', 'Message(Message("bad"),,1)',
                     'New Array(,1)', 'a.Add(,1)']:
            self.vm.execute('a = New Array')
            with self.subTest(code=code), self.assertRaisesRegex(BSLError, 'Пропуск аргументов'):
                self.vm.execute(code)
        self.assertEqual(self.output, [])

    def test_incomplete_defaults_and_calls(self):
        for code in ['Function F(x =', 'Function F(x = -', 'Function F(x = 1',
                     'Function F(x = 1,', 'F(,', 'F(1,,']:
            with self.subTest(code=code), self.assertRaises(IncompleteInput):
                parse(code)


if __name__ == '__main__':
    unittest.main()
