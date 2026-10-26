"""The native trig and exponential probes discriminate conversion order."""

from decimal import Decimal, Inexact, Rounded, ROUND_UP, localcontext
import math
import unittest

from yadinassi.numeric.math_conversion import decimal_to_binary64, UnsupportedConversionRange


class MathConversionTests(unittest.TestCase):
    def test_native_argument_discriminators(self):
        # These doubles reproduce the independent native Tan/Cos and Exp
        # observations. They are inferred inputs, not exported native bits.
        cases = {
            '1.5707963267948966': '0x1.921fb54442d18p+0',
            '1.5707963267948967': '0x1.921fb54442d18p+0',
            '1.5707963267948968': '0x1.921fb54442d1ap+0',
            '3.1415926535897932': '0x1.921fb54442d18p+1',
            '709.7827128933839': '0x1.62e42fefa39eep+9',
            '709.78271289338396': '0x1.62e42fefa39eep+9',
            '709.78271289338397': '0x1.62e42fefa39eep+9',
            '709.78271289338398': '0x1.62e42fefa39f0p+9',
            '709.782712893383970000000001': '0x1.62e42fefa39eep+9',
        }
        for text, expected in cases.items():
            with self.subTest(text=text):
                self.assertEqual(decimal_to_binary64(Decimal(text)).hex(), expected)

    def test_native_trig_results(self):
        cases = [
            (math.tan, '1.5707963267948966', '1.63312393531954e+16'),
            (math.tan, '1.5707963267948967', '1.63312393531954e+16'),
            (math.tan, '1.5707963267948968', '-2.61194216073562e+15'),
            (math.cos, '1.5707963267948966', '6.12323399573677e-17'),
            (math.cos, '1.5707963267948968', '-3.82856869892695e-16'),
            (math.sin, '3.1415926535897932', '1.22464679914735e-16'),
        ]
        for operation, text, expected in cases:
            with self.subTest(operation=operation.__name__, text=text):
                result = operation(decimal_to_binary64(Decimal(text)))
                self.assertEqual(format(result, '.15g'), expected)

    def test_native_exponential_results(self):
        for text in ('709.7827128933839', '709.78271289338396',
                     '709.78271289338397', '709.782712893383970000000001'):
            with self.subTest(text=text):
                result = math.exp(decimal_to_binary64(Decimal(text)))
                self.assertEqual(format(result, '.15g'), '1.79769313486207e+308')
        with self.assertRaises(OverflowError):
            math.exp(decimal_to_binary64(Decimal('709.78271289338398')))

    def test_equal_decimal_representations_convert_identically(self):
        for text in ('1.5707963267948968', '709.78271289338397',
                     '1', '1234567890123456789', '0.000000001'):
            original = Decimal(text)
            sign, digits, exponent = original.as_tuple()
            padded = Decimal((sign, digits + (0,) * 1000, exponent - 1000))
            with self.subTest(text=text):
                self.assertEqual(decimal_to_binary64(padded), decimal_to_binary64(original))

    def test_signs_and_exact_simple_values(self):
        for text in ('1.5707963267948968', '709.78271289338397', '0.5',
                     '1234.5', '0.000000001', '1000000000'):
            value = Decimal(text)
            with self.subTest(text=text):
                self.assertEqual(decimal_to_binary64(value.copy_negate()),
                                 -decimal_to_binary64(value))
        for text in ('0', '-0', '-0.0000', '0e1000000000', '-0e-1000000000'):
            self.assertEqual(decimal_to_binary64(Decimal(text)).hex(), '0x0.0p+0')

    def test_independent_of_decimal_context(self):
        with localcontext() as context:
            context.prec = 2
            context.rounding = ROUND_UP
            context.Emax = 9
            context.Emin = -9
            context.traps[Inexact] = True
            context.traps[Rounded] = True
            context.clear_flags()
            self.assertEqual(decimal_to_binary64(Decimal('709.78271289338397')).hex(),
                             '0x1.62e42fefa39eep+9')
            self.assertFalse(any(context.flags.values()))

    def test_explicit_unsupported_ranges_without_expansion(self):
        for text in ('1e1000000000', '1e-1000000000', '1e309',
                     '1e-307', '1.' + '0' * 4000 + '1', '9' * 307):
            with self.subTest(text=text[:50]):
                with self.assertRaisesRegex(UnsupportedConversionRange, 'Yadinassi|переполнение'):
                    decimal_to_binary64(Decimal(text))
        # These boundaries document the local budget, not native 1C parity.
        for text in ('1e-306', '1e306', '1e308', '9' * 306):
            with self.subTest(text=text[:50]):
                self.assertTrue(math.isfinite(decimal_to_binary64(Decimal(text))))

    def test_nonfinite_and_nondecimal_inputs_rejected(self):
        for value in (Decimal('NaN'), Decimal('sNaN'), Decimal('Infinity'),
                      Decimal('-Infinity'), 1, True, 1.0, '1', None):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    decimal_to_binary64(value)


if __name__ == '__main__':
    unittest.main()
