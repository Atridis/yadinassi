"""Numeric helpers: owner-derived cases and separately identified resource guards."""

from decimal import Decimal, Inexact, Rounded, ROUND_UP, localcontext
from pathlib import Path
import unittest

from yadinassi import BSLError, Interpreter
from yadinassi.numbers import integer_part, minimum, maximum


class NumericHelperTests(unittest.TestCase):
    def setUp(self):
        self.vm = Interpreter(output=lambda message: None)

    def test_owner_native_numeric_subset(self):
        # Both owner uploads are compared without filtering pending strings.
        root = Path(__file__).resolve().parents[1] / 'integrational_tests'
        output = []
        Interpreter(output=output.append).execute((root / 'tests/numbers.bsl').read_text(encoding='utf-8-sig'))
        expected = (root.parent / 'tests/fixtures/native_windows/numbers.out').read_text(encoding='utf-8').splitlines()
        self.assertEqual(output, expected)

    def test_integer_part_bilingual_and_toward_zero(self):
        for expression, expected in [
            ('Цел(1.99)', '1'), ('Int(-1.99)', '-1'),
            ('цЕл(0.99)', '0'), ('INT(-0.99)', '0'),
            ('Цел(0)', '0'), ('Int(-12)', '-12'),
            ('Int(12.000)', '12'), ('Цел(1 / 3)', '0'),
        ]:
            with self.subTest(expression=expression):
                actual = self.vm.execute(expression)
                self.assertIs(type(actual), Decimal)
                self.assertEqual(actual, Decimal(expected))

    def test_integer_part_preserves_long_coefficient(self):
        digits = '1234567890' * 12
        for sign in ('', '-'):
            value = Decimal(sign + digits + '.987654321')
            expected = Decimal(sign + digits)
            self.assertEqual(integer_part(value), expected)
            self.vm.variables['value'] = value
            self.assertEqual(self.vm.execute('Int(value)'), expected)

    def test_integer_part_does_not_apply_host_context(self):
        with localcontext() as context:
            context.prec = 2
            context.rounding = ROUND_UP
            context.Emax = 9
            context.Emin = -9
            context.traps[Inexact] = True
            context.traps[Rounded] = True
            context.clear_flags()
            self.assertEqual(integer_part(Decimal('12345678901234567890.9')),
                             Decimal('12345678901234567890'))
            self.assertEqual(integer_part(Decimal('-1e-1000000')), Decimal(0))
            self.assertEqual(integer_part(Decimal('1e1000000')), Decimal('1e1000000'))
            self.assertFalse(any(context.flags.values()))

    def test_integer_part_arity_errors_are_bsl_errors(self):
        for expression in ('Int()', 'Цел(1, 2)'):
            with self.subTest(expression=expression), self.assertRaises(BSLError):
                self.vm.execute(expression, 'numeric_helpers.bsl')

    def test_integer_part_numeric_conversion(self):
        for expression, expected in [('Int(True)', 1), ('Int(False)', 0),
                                     ('Цел("12.75")', 12), ('Int("-12.75")', -12)]:
            with self.subTest(expression=expression):
                actual = self.vm.execute(expression)
                self.assertIs(type(actual), Decimal)
                self.assertEqual(actual, Decimal(expected))
        for expression in ('Int(Undefined)', 'Int("not a number")', 'Int(New Array)'):
            with self.subTest(expression=expression), self.assertRaises(BSLError):
                self.vm.execute(expression)

    def test_extrema_bilingual_variadic_numeric_results(self):
        for expression, expected in [('Мин(2, -3)', -3), ('Max(2, -3)', 2),
                                     ('мИн(7, -2, 0, -1)', -2), ('MAX(-7, 2, 0, 1)', 2),
                                     ('Min(7)', 7), ('Макс(7)', 7)]:
            with self.subTest(expression=expression):
                actual = self.vm.execute(expression)
                self.assertIs(type(actual), Decimal)
                self.assertEqual(actual, Decimal(expected))

    def test_extrema_keep_winning_type_and_first_tie(self):
        for function in (minimum, maximum):
            for value in (Decimal(0), Decimal(1), False, True):
                with self.subTest(function=function.__name__, value=value):
                    self.assertIs(function(value), value)
                    other = bool(value) if type(value) is Decimal else Decimal(int(value))
                    self.assertIs(function(value, other), value)
                    self.assertIs(function(other, value), other)
        for values in ((Decimal(2), True), (True, Decimal(2))):
            self.assertIs(minimum(*values), True)
            self.assertIs(type(maximum(*values)), Decimal)
            self.assertEqual(maximum(*values), Decimal(2))

    def test_extrema_reject_invalid_types_and_mixed_numeric_strings(self):
        for expression in ('Min(2, "10")', 'Max("2", 10)', 'Min(Undefined)',
                           'Max(New Array)', 'Min(2, Undefined)', 'Max(Undefined, 2)',
                           'Min()', 'Max()'):
            with self.subTest(expression=expression), self.assertRaises(BSLError):
                self.vm.execute(expression)

    def test_string_extrema(self):
        for lower, upper in [('a', 'A'), ('Aa', 'az'), ('A', 'b'),
                             ('е', 'ё'), ('я', 'Я'), ('a', 'aa'), ('10', '2')]:
            for values in ((lower, upper), (upper, lower)):
                self.assertEqual(minimum(*values), lower)
                self.assertEqual(maximum(*values), upper)
        self.assertEqual(minimum('value'), 'value')
        self.assertEqual(maximum('a', 'A', 'b'), 'b')

    def test_extrema_numeric_boolean_multivalue_selection_and_omissions(self):
        for expression, expected in [('Min(True, False)', False), ('Max(False, True)', True),
                                     ('Min(0, False, -1)', Decimal(-1)),
                                     ('Max(1, True, 0)', Decimal(1))]:
            actual = self.vm.execute(expression)
            self.assertIs(type(actual), type(expected))
            self.assertEqual(actual, expected)
        for expression in ('Min(, 1)', 'Max(1, , 2)'):
            with self.subTest(expression=expression), self.assertRaisesRegex(BSLError, "Пропуск аргументов"):
                self.vm.execute(expression)

    def test_extrema_do_not_round_long_numbers_or_use_host_context(self):
        lower = Decimal('1234567890' * 12 + '.1')
        upper = Decimal('1234567890' * 12 + '.2')
        with localcontext() as context:
            context.prec = 2
            context.traps[Inexact] = context.traps[Rounded] = True
            self.assertIs(minimum(upper, lower), lower)
            self.assertIs(maximum(lower, upper), upper)
        for function in (minimum, maximum):
            for value in ('NaN', 'sNaN', 'Infinity', '-Infinity'):
                with self.subTest(function=function.__name__, value=value), self.assertRaises(ValueError):
                    function(Decimal(value))

    def test_integer_part_omitted_argument_uses_existing_guard(self):
        with self.assertRaisesRegex(BSLError, "Пропуск аргументов"):
            self.vm.execute("Int(, 1)")

    def test_integer_part_nonfinite_host_values_are_rejected(self):
        for text in ('NaN', 'sNaN', 'Infinity', '-Infinity'):
            with self.subTest(text=text), self.assertRaises(ValueError):
                integer_part(Decimal(text))


if __name__ == '__main__':
    unittest.main()
