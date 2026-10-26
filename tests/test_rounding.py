"""Round: owner-observed numeric rules plus explicit context/resource defenses."""

from decimal import Decimal, Inexact, Rounded, ROUND_UP, ROUND_HALF_UP, ROUND_HALF_DOWN, localcontext
import unittest

from yadinassi import BSLError, Interpreter
from yadinassi.numeric.numbers import round_number
from yadinassi.numeric.round_modes import BSLRoundMode


class RoundingTests(unittest.TestCase):
    def setUp(self):
        self.vm = Interpreter(output=lambda text: None)

    def test_native_defaults_and_bilingual_names(self):
        for expression, expected in [
            ('Окр(1.5)', '2'), ('Round(-1.5)', '-2'),
            ('оКр(2.5)', '3'), ('ROUND(-2.5)', '-3'),
            ('Окр(-0.5)', '-1'), ('Round(12.345, 2)', '12.35'),
            ('Round(Истина)', '1'), ('Round("12.75")', '13'),
            ('Round(123456789012345678901234567890.5)', '123456789012345678901234567891'),
        ]:
            with self.subTest(expression=expression):
                actual = self.vm.execute(expression)
                self.assertIs(type(actual), Decimal)
                self.assertEqual(actual, Decimal(expected))

    def test_native_modes_and_precision(self):
        for value, precision, mode, expected in [
            ('1.5', '0', '0', '1'), ('-1.5', '0', '0', '-1'),
            ('1.5', '0', '1', '2'), ('-1.5', '0', '1', '-2'),
            ('-1.5001', '0', '0', '-2'), ('-1.4999', '0', '1', '-1'),
            ('12.345', '2', '1', '12.35'), ('1250', '-2', '1', '1300'),
            ('-1250', '-2', '0', '-1200'), ('12.345', '1.9', '1', '12.3'),
            ('1250', '-1.9', '1', '1250'), ('12.345', '100', '1', '12.345'),
            ('12.345', '-100', '1', '0'), ('1.5', '0', '2', '2'),
            ('1.5', '0', '-1', '2'), ('1.5', '0', '0.9', '1'),
        ]:
            with self.subTest(value=value, precision=precision, mode=mode):
                self.assertEqual(round_number(Decimal(value), Decimal(precision), Decimal(mode)),
                                 Decimal(expected))
        self.assertEqual(round_number(Decimal('12.345'), '2'), Decimal('12.35'))
        self.assertEqual(round_number(Decimal('12.345'), True), Decimal('12.3'))

    def test_native_enum_modes(self):
        for namespace, low, high in [('РежимОкругления', 'Окр15как10', 'Окр15как20'),
                                     ('RoundMode', 'Round15as10', 'Round15as20')]:
            for sign in ('', '-'):
                self.assertEqual(self.vm.execute(f'Round({sign}1.5, 0, {namespace}.{low})'),
                                 Decimal(sign + '1'))
                self.assertEqual(self.vm.execute(f'Round({sign}1.5, 0, {namespace}.{high})'),
                                 Decimal(sign + '2'))

    def test_native_rejections(self):
        for expression in ['Round("не число")', 'Round(Неопределено)',
                           'Round(12.345, Неопределено)', 'Round(12.345, "x")',
                           'Round(1.5, 0, "1")', 'Round(1.5, 0, Истина)',
                           'Round(1.5, 0, Неопределено)']:
            with self.subTest(expression=expression), self.assertRaises(BSLError):
                self.vm.execute(expression)

    def test_arity_and_errors_remain_catchable(self):
        for expression in ['Round()', 'Round(1, 0, 1, 2)', 'Round(Новый Массив)',
                           'Round(1, Новый Массив)', 'Round(1, 0, Новый Массив)']:
            with self.subTest(expression=expression):
                self.vm.execute(f'caught = Ложь; Попытка {expression}; Исключение caught = Истина; КонецПопытки;')
                self.assertIs(self.vm.variables['caught'], True)
                self.assertEqual(self.vm.execute('Round(1.5)'), Decimal(2))

    def test_exact_long_coefficients_and_carry_defense(self):
        # Implementation defenses, not additional native platform observations.
        for sign in ('', '-'):
            self.assertEqual(round_number(Decimal(sign + '9' * 200 + '.5')),
                             Decimal(sign + '1' + '0' * 200))
            value = Decimal(sign + '1234567890')
            self.assertEqual(round_number(value, Decimal(100)), value)
        self.assertEqual(round_number(Decimal('-0.5'), mode=BSLRoundMode.ROUND15_AS10), Decimal(0))
        self.assertFalse(round_number(Decimal('-0.5'), mode=BSLRoundMode.ROUND15_AS10).is_signed())
        self.assertEqual(round_number(Decimal('0.50000000001'), mode=Decimal(0)), Decimal(1))

    def test_independent_of_host_context_and_flags(self):
        value = Decimal('-123456789012345678901234567890.555')
        expected = Decimal('-123456789012345678901234567890.56')
        with localcontext() as context:
            context.prec = 2
            context.rounding = ROUND_UP
            context.Emax = 9
            context.Emin = -9
            context.traps[Inexact] = True
            context.traps[Rounded] = True
            context.clear_flags()
            self.assertEqual(round_number(value, Decimal('2.9')), expected)
            self.assertFalse(any(context.flags.values()))

    def test_huge_precision_and_modes_do_not_expand_requested_scale(self):
        # Output work is input-sized; these are resource defenses, not native caps.
        value = Decimal('12.345')
        for precision, expected in [('1e1000000', value), ('-1e1000000', Decimal(0))]:
            self.assertEqual(round_number(value, Decimal(precision)), expected)
        self.assertEqual(round_number(Decimal('1.5'), mode=Decimal('1e1000000')), Decimal(2))
        self.assertEqual(round_number(Decimal('1.5'), mode=Decimal('1e-1000000')), Decimal(1))
        self.assertEqual(round_number(Decimal('1e1000000')), Decimal('1e1000000'))
        self.assertEqual(round_number(Decimal('1e-1000000')), Decimal(0))

    def test_coefficient_algorithm_matches_independent_quantize_reference(self):
        # Algorithm regression grid, distinct from owner-derived native evidence.
        with localcontext() as context:
            context.prec = 50
            for coefficient in range(-1015, 1016, 7):
                value = Decimal((coefficient < 0, tuple(map(int, str(abs(coefficient)))), -2))
                for precision in range(-3, 5):
                    quantum = Decimal((0, (1,), -precision))
                    for mode, rounding in [(0, ROUND_HALF_DOWN), (1, ROUND_HALF_UP)]:
                        with self.subTest(coefficient=coefficient, precision=precision, mode=mode):
                            self.assertEqual(round_number(value, Decimal(precision), Decimal(mode)),
                                             value.quantize(quantum, rounding=rounding))

    def test_nonfinite_inputs_rejected_without_context_errors(self):
        for value in ['NaN', 'sNaN', 'Infinity', '-Infinity']:
            for position in range(3):
                args = [Decimal('1.5'), Decimal(0), Decimal(1)]
                args[position] = Decimal(value)
                with self.subTest(value=value, position=position), self.assertRaises((TypeError, ValueError)):
                    round_number(*args)


if __name__ == '__main__':
    unittest.main()
