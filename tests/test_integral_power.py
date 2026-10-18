"""Owner-observed integral powers and separate bounded-algorithm defenses."""

from decimal import Decimal, Inexact, ROUND_UP, localcontext
import sys
import unittest

from yadinassi.powers import integral_power
from yadinassi.values import divide


class IntegralPowerTests(unittest.TestCase):
    def test_owner_observed_exact_powers(self):
        for base, exponent, expected in [
            ('2', '10', '1024'),
            ('-2', '3', '-8'),
            ('0', '0', '1'),
            ('10', '309', '1e309'),
            ('-2', '-3', '-0.125'),
            ('9007199254740993', '1', '9007199254740993'),
            ('3', '-1', '0.333333333333333333333333333'),
            ('1.1', '20', '6.72749994932560009201'),
            ('2', '100', '1267650600228229401496703205376'),
            ('1.234567890123456789012', '2',
             '1.524157875323883675048681628113153483936144'),
        ]:
            with self.subTest(base=base, exponent=exponent):
                actual = integral_power(Decimal(base), Decimal(exponent))
                self.assertIs(type(actual), Decimal)
                self.assertEqual(actual, Decimal(expected))

    def test_coefficient_and_scale_regression_grid(self):
        # Independent integer-power reference; not additional native evidence.
        for coefficient in range(-25, 26):
            for scale in range(-3, 4):
                base = Decimal((coefficient < 0,
                                Decimal(abs(coefficient)).as_tuple().digits, scale))
                for exponent in range(8):
                    powered = coefficient ** exponent
                    expected = Decimal((powered < 0,
                                        Decimal(abs(powered)).as_tuple().digits,
                                        scale * exponent))
                    with self.subTest(coefficient=coefficient, scale=scale,
                                      exponent=exponent):
                        self.assertEqual(integral_power(base, Decimal(exponent)), expected)

    def test_trailing_zeroes_and_integral_decimal_exponents(self):
        for base, exponent, expected in [
            ('1.10000', '20.000', '6.72749994932560009201'),
            ('-2.00', '3.000', '-8'),
            ('-2.00', '2.000', '4'),
            ('-2.00', '-3.000', '-0.125'),
            ('0.000', '3.000', '0'),
            ('-0.000', '3.000', '0'),
            ('2', '-0e-1000000', '1'),
        ]:
            with self.subTest(base=base, exponent=exponent):
                actual = integral_power(Decimal(base), Decimal(exponent))
                self.assertEqual(actual, Decimal(expected))
                if actual.is_zero():
                    self.assertFalse(actual.is_signed())

    def test_huge_exponents_use_zero_and_unit_shortcuts(self):
        for exponent in ['1e1000000', '-1e1000000', '1' + '0' * 5000 + '1',
                         '-1' + '0' * 5000 + '1']:
            value = Decimal(exponent)
            odd = exponent.endswith('1')
            self.assertEqual(integral_power(Decimal(1), value), Decimal(1))
            self.assertEqual(integral_power(Decimal('-1.0000'), value),
                             Decimal(-1 if odd else 1))
            if value.is_signed():
                with self.assertRaisesRegex(ValueError, 'ноль'):
                    integral_power(Decimal(0), value)
            else:
                self.assertEqual(integral_power(Decimal('-0'), value), Decimal(0))
        for base in ['1e1000000', '-1e-1000000', '9' * 5000]:
            self.assertEqual(integral_power(Decimal(base), Decimal(0)), Decimal(1))

    def test_negative_powers_reuse_division_rules(self):
        for base, exponent in [('3', 2), ('7', 3), ('-3', 3), ('0.3', 2),
                               ('1.1', 20), ('2', 100)]:
            positive = integral_power(Decimal(base), Decimal(exponent))
            self.assertEqual(integral_power(Decimal(base), Decimal(-exponent)),
                             divide(Decimal(1), positive))
        # Existing division intentionally does not infer native exact-tie rules.
        with self.assertRaisesRegex(ValueError, 'точная половина'):
            integral_power(Decimal(2), Decimal(-28))

    def test_digit_budget_boundaries_are_exact(self):
        for base, exponent, expected in [
            ('10', '4095', Decimal('1e4095')),
            ('0.1', '4096', Decimal('1e-4096')),
            ('9' * 4096, '1', Decimal('9' * 4096)),
            ('9' * 2048, '2', Decimal(int('9' * 2048) ** 2)),
            ('2', '13606', Decimal(2 ** 13606)),
        ]:
            with self.subTest(base_digits=len(base), exponent=exponent):
                self.assertEqual(integral_power(Decimal(base), Decimal(exponent)), expected)
        for base, exponent in [('10', '4096'), ('0.1', '4097'), ('2', '13607'),
                               ('9' * 4097, '1'), ('9' * 2049, '2'),
                               ('9' * 2048, '3')]:
            with self.subTest(base_digits=len(base), exponent=exponent):
                with self.assertRaisesRegex(ValueError, 'предел ресурсов Yadinassi'):
                    integral_power(Decimal(base), Decimal(exponent))

    def test_huge_metadata_is_rejected_before_expansion(self):
        for base, exponent in [('2', '1e1000000'), ('2', '-1e1000000'),
                               ('0.9', '1e1000000'), ('1e1000000', '1'),
                               ('1e-1000000', '1'), ('1e1000000', '-1'),
                               ('1e-1000000', '-1')]:
            with self.subTest(base=base, exponent=exponent):
                with self.assertRaisesRegex(ValueError, 'предел ресурсов Yadinassi'):
                    integral_power(Decimal(base), Decimal(exponent))

    def test_independent_of_all_host_traps_limits_and_flags(self):
        cases = [(Decimal(base), Decimal(exponent), Decimal(expected))
                 for base, exponent, expected in [
                     ('1.1', '20', '6.72749994932560009201'),
                     ('-2', '100', '1267650600228229401496703205376'),
                     ('3', '-1', '0.333333333333333333333333333'),
                     ('10', '309', '1e309'),
                     ('0.1', '4096', '1e-4096'),
                     ('-1', '1e1000000', '1'),
                 ]]
        with localcontext() as context:
            context.prec = 1
            context.rounding = ROUND_UP
            context.Emax = 1
            context.Emin = -1
            context.clamp = 1
            for signal in context.traps:
                context.traps[signal] = True
            context.clear_flags()
            context.flags[Inexact] = True
            before = context.copy()
            for base, exponent, expected in cases:
                self.assertEqual(integral_power(base, exponent), expected)
            for base, exponent in [('2', '1e1000000'), ('2', '0.5'), ('0', '-1')]:
                with self.assertRaises(ValueError):
                    integral_power(Decimal(base), Decimal(exponent))
            self.assertEqual(context.flags, before.flags)
            self.assertEqual(context.traps, before.traps)
            self.assertEqual((context.prec, context.rounding, context.Emax,
                              context.Emin, context.clamp),
                             (before.prec, before.rounding, before.Emax,
                              before.Emin, before.clamp))

    @unittest.skipUnless(hasattr(sys, 'set_int_max_str_digits'), 'Python 3.11 guard')
    def test_no_dependency_on_host_integer_string_limit(self):
        before = sys.get_int_max_str_digits()
        try:
            sys.set_int_max_str_digits(640)
            value = Decimal('9' * 4096)
            self.assertEqual(integral_power(value, Decimal(1)), value)
            self.assertEqual(integral_power(Decimal(2), Decimal(13606)),
                             Decimal(2 ** 13606))
        finally:
            sys.set_int_max_str_digits(before)

    def test_nonfinite_nonintegral_and_non_decimal_inputs(self):
        for value in ['NaN', 'sNaN', 'Infinity', '-Infinity']:
            for base, exponent in [(Decimal(value), Decimal(0)),
                                   (Decimal(1), Decimal(value))]:
                with self.subTest(base=base, exponent=exponent):
                    with self.assertRaisesRegex(ValueError, 'конечные'):
                        integral_power(base, exponent)
        for exponent in ['0.5', '-0.5', '3.0000000000000000000000001', '1e-1000000']:
            for base in ['0', '1', '-1', '2']:
                with self.subTest(base=base, exponent=exponent):
                    with self.assertRaisesRegex(ValueError, 'целый показатель'):
                        integral_power(Decimal(base), Decimal(exponent))
        for value in [None, True, '2', 2, 2.0]:
            with self.subTest(value=value), self.assertRaises(TypeError):
                integral_power(value, Decimal(2))
            with self.subTest(value=value), self.assertRaises(TypeError):
                integral_power(Decimal(2), value)


if __name__ == '__main__':
    unittest.main()
