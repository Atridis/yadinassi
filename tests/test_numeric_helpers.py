"""Helper model tests; owner-generated probes establish native parity separately."""

from decimal import Decimal, Inexact, Rounded, ROUND_UP, localcontext
import unittest

from yadinassi import BSLError, Interpreter
from yadinassi.numbers import integer_part


class NumericHelperTests(unittest.TestCase):
    def setUp(self):
        self.vm = Interpreter(output=lambda message: None)

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

    def test_integer_part_pending_coercions_are_explicit(self):
        for expression in ('Int(True)', 'Цел("12.75")', 'Int(Undefined)',
                           'Int(New Array)'):
            with self.subTest(expression=expression), self.assertRaisesRegex(
                    BSLError, "преобразование аргумента к числу пока не поддерживается"):
                self.vm.execute(expression)

    def test_integer_part_omitted_argument_uses_existing_guard(self):
        with self.assertRaisesRegex(BSLError, "Пропуск аргументов"):
            self.vm.execute("Int(, 1)")

    def test_integer_part_nonfinite_host_values_are_rejected(self):
        for text in ('NaN', 'sNaN', 'Infinity', '-Infinity'):
            with self.subTest(text=text), self.assertRaises(ValueError):
                integer_part(Decimal(text))


if __name__ == '__main__':
    unittest.main()
