"""Conditional expressions evaluate exactly one result branch."""

from decimal import Decimal
import unittest

from yadinassi import BSLError, Interpreter
from yadinassi.errors import IncompleteInput
from yadinassi.syntax.parser import parse


class ConditionalTests(unittest.TestCase):
    def setUp(self):
        self.vm = Interpreter(output=lambda value: None)

    def test_boolean_selection_and_result_types(self):
        for expression, expected in (
            ('?(Истина, 42, "other")', Decimal(42)),
            ('?(Ложь, 42, "other")', "other"),
            ('?(True, False, 42)', False),
            ('?(False, 42, Undefined)', None),
        ):
            with self.subTest(expression=expression):
                actual = self.vm.execute(expression)
                self.assertEqual(actual, expected)
                self.assertIs(type(actual), type(expected))

    def test_unselected_branch_is_not_evaluated(self):
        for expression in (
            '?(Истина, 42, Неизвестно())',
            '?(Ложь, Неизвестно(), 42)',
            '?(Истина, 42, 1 / 0)',
            '?(Ложь, 1 / 0, 42)',
        ):
            with self.subTest(expression=expression):
                self.assertEqual(self.vm.execute(expression), Decimal(42))

    def test_condition_and_selected_branch_run_once_in_order(self):
        for condition in (True, False):
            calls = []

            def record(label, value):
                calls.append(label)
                return value

            self.vm.register_function("Record", record)
            expression = f'?(Record("condition", {condition}), Record("true", 1), Record("false", 2))'
            self.assertEqual(self.vm.execute(expression), Decimal(1 if condition else 2))
            self.assertEqual(calls, ["condition", "true" if condition else "false"])

    def test_nested_expressions_and_operator_precedence(self):
        self.assertEqual(self.vm.execute('''
            x = 2 + ?(Не 1 = 2 И 3 > 2, ?(Ложь, 0, 4), 9) * 10;
            x
        '''), Decimal(42))
        self.assertEqual(self.vm.execute('?(?(Истина, Ложь, Истина), 0, 42)'), Decimal(42))
        self.assertEqual(self.vm.execute('?(Ложь, 0, ?(Истина, 42, 9))'), Decimal(42))

    def test_selected_object_keeps_identity_and_supports_postfix(self):
        self.vm.execute('a = Новый Массив; a.Добавить(42); b = Новый Массив;')
        self.assertIs(self.vm.execute('?(Истина, a, b)'), self.vm.variables['a'])
        self.assertEqual(self.vm.execute('?(Истина, a, b)[0]'), Decimal(42))
        self.assertEqual(self.vm.execute('?(Ложь, b, a).Количество()'), Decimal(1))

    def test_numeric_conditions_follow_existing_boolean_conversion(self):
        self.assertEqual(self.vm.execute('?(0, 1, 42)'), Decimal(42))
        self.assertEqual(self.vm.execute('Представление = ?(-2, 42, 1); Представление'), Decimal(42))

    def test_invalid_condition_does_not_run_either_branch(self):
        calls = []
        self.vm.register_function('Effect', lambda: calls.append('called'))
        with self.assertRaises(BSLError) as caught:
            self.vm.execute('\n?("invalid", Effect(), Effect())', 'condition.bsl')
        self.assertEqual(calls, [])
        self.assertIn('булево', caught.exception.message)
        self.assertEqual((caught.exception.source, caught.exception.line, caught.exception.column),
                         ('condition.bsl', 2, 1))

    def test_selected_branch_error_keeps_source_location(self):
        for expression, line in (('?(Истина,\n 1 / 0, 42)', 2),
                                 ('?(Ложь, 42,\n 1 / 0)', 2)):
            with self.subTest(expression=expression), self.assertRaises(BSLError) as caught:
                self.vm.execute(expression, 'branch.bsl')
            self.assertIn('Деление на ноль', caught.exception.message)
            self.assertEqual((caught.exception.source, caught.exception.line, caught.exception.column),
                             ('branch.bsl', line, 4))

    def test_malformed_syntax_is_rejected_even_in_unselected_branch(self):
        for expression in ('?()', '?(Истина)', '?(Истина, 1)',
                           '?(Истина, 1, 2, 3)', '?(Истина,, 2)',
                           '? Истина, 1, 2', '?(Истина, 1, )',
                           '?(Истина, 1, 2 + )'):
            with self.subTest(expression=expression), self.assertRaises(BSLError):
                parse(expression)

    def test_incomplete_expression_requests_more_repl_input(self):
        for expression in ('?', '?(', '?(Истина', '?(Истина,',
                           '?(Истина, 1,', '?(Истина, 1, 2'):
            with self.subTest(expression=expression), self.assertRaises(IncompleteInput):
                parse(expression)

    def test_syntax_is_checked_before_any_side_effects(self):
        calls = []
        self.vm.register_function('Effect', lambda: calls.append('called'))
        with self.assertRaises(BSLError):
            self.vm.execute('Effect(); ?(Истина, 1, 2 + )')
        self.assertEqual(calls, [])


if __name__ == '__main__':
    unittest.main()
