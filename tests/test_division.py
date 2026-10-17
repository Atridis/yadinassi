"""Regressions for Yadinassi's bounded empirical decimal-division model.

Only NativeDivisionValueTests uses the owner's saved native observations. The
remaining cases validate the explicitly chosen model and its safety boundaries;
they are not evidence of universal 1C arithmetic, especially outside the observed
operand ranges. Exact halves at the chosen scale remain unsupported.
"""

from decimal import (
    Context, Decimal, ROUND_05UP, ROUND_CEILING, ROUND_DOWN, ROUND_FLOOR,
    ROUND_HALF_DOWN, ROUND_HALF_EVEN, ROUND_HALF_UP, ROUND_UP, localcontext,
)
from fractions import Fraction
from pathlib import Path
import random
import re
import subprocess
import sys
import unittest

from yadinassi import Interpreter
from yadinassi.errors import BSLRuntimeError
from yadinassi.values import divide, number, to_string


ROOT = Path(__file__).resolve().parents[1]
HALF_MESSAGE = r"(?i)точная половина.*пока не поддерживается в Yadinassi"
RESOURCE_MESSAGE = r"(?i)предел ресурсов Yadinassi"


def fraction_scale(value):
    """Get the exact finite fraction's scale without Decimal normalization."""
    denominator = Fraction(value).denominator
    powers = []
    for prime in (2, 5):
        count = 0
        while denominator % prime == 0:
            denominator //= prime
            count += 1
        powers.append(count)
    assert denominator == 1
    return max(powers)


def model_scale(left, right):
    return 27 + 9 * ((fraction_scale(left) + 8) // 9) + 9 * (right.adjusted() // 9)


def fraction_oracle(left, right):
    """Exact rational nearest rounding; None denotes an unsupported true half."""
    scale = model_scale(left, right)
    quantum = Fraction(1, 10 ** scale) if scale >= 0 else Fraction(10 ** -scale)
    exact = Fraction(left) / Fraction(right)
    units = abs(exact) / quantum
    whole, remainder = divmod(units.numerator, units.denominator)
    comparison = 2 * remainder - units.denominator
    if comparison == 0:
        return None
    if comparison > 0:
        whole += 1
    rounded = whole * quantum
    return -rounded if exact < 0 else rounded


class NativeDivisionValueTests(unittest.TestCase):
    """Read native values as Decimals, independently of numeric presentation."""

    def test_all_saved_native_quotients_are_actual_decimal_values(self):
        lines = (ROOT / 'integrational_tests/output/numbers.out').read_text(
            encoding='utf-8-sig').splitlines()
        observed = {}
        for line in lines:
            match = re.fullmatch(r'([^:]+): \[([^\]]+)\]', line)
            if match and (match[1].startswith('div.') or match[1] == 'exact.divide_one'):
                observed[match[1]] = Decimal(match[2].replace('\u00a0', '').replace(',', '.'))
        operands = {
            'div.1_3': ('1', '3'),
            'div.10_3': ('10', '3'),
            'div.100_3': ('100', '3'),
            'div.2_3': ('2', '3'),
            'div.1_7': ('1', '7'),
            'div.negative_1_7': ('-1', '7'),
            'div.fractional_operand': ('13.1', '3'),
            'div.tiny': ('1e-28', '3'),
            'div.large': ('1e27', '3'),
            'exact.divide_one': ('1.2345678901234567890123456789', '1'),
            'div.fractional_divisor': ('1', '0.3'),
            'div.fractional_divisor_scale10': ('1', '3e-10'),
            'div.equal_scales': ('0.1', '0.3'),
            'div.mixed_scales_left': ('1e-10', '0.3'),
            'div.mixed_scales_right': ('0.1', '3e-10'),
            'div.numerator_scale9': ('1e-9', '3'),
            'div.numerator_scale10': ('1e-10', '3'),
            'div.numerator_scale18': ('1e-18', '3'),
            'div.numerator_scale19': ('1e-19', '3'),
            'div.trailing_zero_integer': ('1.0000000000', '3'),
            'div.trailing_zero_fraction': ('13.1000000000', '3'),
            'div.redivide': (observed['div.1_3'], '7'),
            'div.negative_third': ('-1', '3'),
            # These native labels are historical: at S=54 they are exact,
            # rather than halves at the model's selected quantization scale.
            'div.tie_positive': ('1', '2e27'),
            'div.tie_odd': ('3', '2e27'),
            'div.tie_negative': ('-1', '2e27'),
        }
        self.assertEqual(set(observed), set(operands))
        vm = Interpreter()
        for label, (left, right) in operands.items():
            with self.subTest(native_label=label):
                left, right = Decimal(left), Decimal(right)
                vm.variables.update(left=left, right=right)
                for actual in (divide(left, right), vm.execute('left / right')):
                    self.assertIs(type(actual), Decimal)
                    self.assertEqual(actual, observed[label])
                self.assertEqual(vm.variables['left'].as_tuple(), left.as_tuple())
                self.assertEqual(vm.variables['right'].as_tuple(), right.as_tuple())


class DivisionModelRegressionTests(unittest.TestCase):
    """Model regressions, including deliberate extrapolations beyond native data."""

    def assert_model_result(self, left, right):
        expected = fraction_oracle(left, right)
        before = (left.as_tuple(), right.as_tuple())
        if expected is None:
            with self.assertRaisesRegex((ArithmeticError, ValueError), HALF_MESSAGE):
                divide(left, right)
        else:
            actual = divide(left, right)
            self.assertIs(type(actual), Decimal)
            self.assertEqual(Fraction(actual), expected)
        self.assertEqual((left.as_tuple(), right.as_tuple()), before)

    def test_scale_boundaries_and_both_operand_signs_against_exact_rationals(self):
        numerator_scales = (0, 1, 8, 9, 10, 17, 18, 19, 26, 27, 28)
        divisor_orders = (-37, -36, -28, -27, -19, -18, -10, -9,
                          -1, 0, 8, 9, 17, 18, 26, 27, 35, 36)
        for fraction_digits in numerator_scales:
            for order in divisor_orders:
                for left_sign, right_sign in ((0, 0), (1, 0), (0, 1), (1, 1)):
                    left = Decimal((left_sign, (1, 3, 1), -fraction_digits))
                    right = Decimal((right_sign, (7,), order))
                    with self.subTest(fraction_digits=fraction_digits, order=order,
                                      left_sign=left_sign, right_sign=right_sign):
                        self.assert_model_result(left, right)

    def test_seeded_varied_coefficients_exponents_and_scales_against_exact_rationals(self):
        generator = random.Random(20261017)
        for case in range(250):
            values = []
            for unused in range(2):
                coefficient = generator.randrange(1, 10 ** 35)
                digits = tuple(map(int, str(coefficient)))
                values.append(Decimal((generator.randrange(2), digits,
                                       generator.randrange(-75, 76))))
            with self.subTest(case=case, left=values[0], right=values[1]):
                self.assert_model_result(*values)

    def test_nearest_rounding_below_and_above_half_with_carry(self):
        cases = [('1', '3'), ('2', '3'), ('1', '7'), ('4', '7'),
                 ('9999999999999999999999999999', '10000000000000000000000000001'),
                 ('1', '999999999'), ('999999999', '999999998'),
                 ('268435455', '268435457'), ('268435457', '268435455')]
        for left, right in cases:
            for negative in (False, True):
                left_value = Decimal(('-' if negative else '') + left)
                with self.subTest(left=left_value, right=right):
                    self.assert_model_result(left_value, Decimal(right))
        # These straddle the last retained half-unit, with a carry to 1.
        self.assertEqual(divide(Decimal('1'), Decimal('1.' + '0' * 27 + '4')), Decimal(1))
        self.assertEqual(divide(Decimal('1'), Decimal('1.' + '0' * 27 + '6')),
                         Decimal('0.' + '9' * 27))
        # At negative S=-9, nearest rounding is to billions.
        self.assertEqual(divide(Decimal('1'), Decimal('6e-28')), Decimal('1666666666666666667000000000'))
        self.assertEqual(divide(Decimal('1'), Decimal('3e-28')), Decimal('3333333333333333333000000000'))

    def test_trailing_zero_spelling_has_no_effect_on_the_model(self):
        for spellings in [('1', '1.0', '1.0000000000', '1000e-3'),
                          ('13.1', '13.1000000000', '13100e-3'),
                          ('0.000000001', '0.000000001000000000', '1000e-12'),
                          ('0.0000000001', '0.0000000001000', '1000e-13')]:
            for divisor in ('3', '0.3', '3000000000', '0.0000000003'):
                expected = divide(Decimal(spellings[0]), Decimal(divisor))
                for spelling in spellings:
                    with self.subTest(numerator=spelling, divisor=divisor):
                        self.assertEqual(divide(Decimal(spelling), Decimal(divisor)), expected)
        for spelling in ('3', '3.0', '3.000000000000000000', '30000e-4'):
            self.assertEqual(divide(Decimal('1'), Decimal(spelling)), Decimal('0.' + '3' * 27))

    def test_normalized_padding_is_not_an_artificial_operand_digit_limit(self):
        left = Decimal('1.' + '0' * 5000)
        right = Decimal('3.' + '0' * 5000)
        self.assertEqual(divide(left, right), Decimal('0.' + '3' * 27))
        self.assertEqual(left.as_tuple().exponent, -5000)
        self.assertEqual(right.as_tuple().exponent, -5000)

    def test_exact_large_operands_exceed_400_digits_without_a_float_round_trip(self):
        integer = Decimal('1234567890' * 100 + '123456789')
        fraction = Decimal('0.' + '1234567890' * 70 + '123456789')
        with localcontext() as context:
            context.prec = 2
            for value in (integer, integer.copy_negate(), fraction, fraction.copy_negate()):
                with self.subTest(digits=len(value.as_tuple().digits), sign=value.is_signed()):
                    self.assertEqual(divide(value, Decimal(1)), value)
                    self.assertEqual(divide(value, value), Decimal(1))
        self.assert_model_result(integer, Decimal('7'))

    def test_true_target_halves_are_rejected_for_both_signs_and_even_or_odd_integer_units(self):
        for numerator in ('1', '3', '-1', '-3', '1.000000000000', '-3.0000'):
            for divisor in ('268435456', '-268435456', '268435456.000000'):
                with self.subTest(numerator=numerator, divisor=divisor):
                    left, right = Decimal(numerator), Decimal(divisor)
                    self.assertIsNone(fraction_oracle(left, right))
                    self.assert_model_result(left, right)

    def test_historical_native_half_labels_remain_exact_at_scale_54(self):
        for numerator, expected in [('1', '5e-28'), ('3', '15e-28'),
                                    ('-1', '-5e-28'), ('-3', '-15e-28')]:
            left, right = Decimal(numerator), Decimal('2e27')
            with self.subTest(numerator=numerator):
                self.assertEqual(model_scale(left, right), 54)
                self.assertEqual(divide(left, right), Decimal(expected))

    def test_zero_results_and_division_by_signed_zero(self):
        for zero in ('0', '-0', '0.0000000000', '-0e25'):
            for divisor in ('1', '-3', '0.0003', '1e-40', '-1e40'):
                with self.subTest(zero=zero, divisor=divisor):
                    result = divide(Decimal(zero), Decimal(divisor))
                    self.assertIs(type(result), Decimal)
                    self.assertEqual(result, Decimal(0))
                    self.assertEqual(to_string(result), '0')
            for numerator in ('0', '-0', '1', '-1'):
                with self.subTest(numerator=numerator, zero=zero):
                    with self.assertRaisesRegex((ArithmeticError, ValueError), 'Деление на ноль'):
                        divide(Decimal(numerator), Decimal(zero))

    def test_all_decimal_rounding_modes_traps_and_exponent_limits_are_irrelevant(self):
        modes = (ROUND_05UP, ROUND_CEILING, ROUND_DOWN, ROUND_FLOOR,
                 ROUND_HALF_DOWN, ROUND_HALF_EVEN, ROUND_HALF_UP, ROUND_UP)
        operands = [(Decimal('1'), Decimal('3')), (Decimal('-2'), Decimal('3')),
                    (Decimal('13.1000000000'), Decimal('0.3')),
                    (Decimal('1e-28'), Decimal('3')),
                    (Decimal('1e60'), Decimal('7')),
                    (Decimal('1'), Decimal('3e-40'))]
        expected = [fraction_oracle(*pair) for pair in operands]
        vm = Interpreter()
        for mode in modes:
            with self.subTest(rounding=mode), localcontext() as context:
                context.prec = 2
                context.Emin, context.Emax = -2, 2
                context.clamp = 1
                context.rounding = mode
                for signal in context.traps:
                    context.traps[signal] = True
                context.clear_flags()
                original = context.copy()
                for (left, right), result in zip(operands, expected):
                    self.assertEqual(Fraction(divide(left, right)), result)
                    vm.variables.update(left=left, right=right)
                    self.assertEqual(Fraction(vm.execute('left / right')), result)
                with self.assertRaisesRegex((ArithmeticError, ValueError), HALF_MESSAGE):
                    divide(Decimal('1'), Decimal('268435456'))
                self.assertEqual(context.prec, original.prec)
                self.assertEqual(context.Emin, original.Emin)
                self.assertEqual(context.Emax, original.Emax)
                self.assertEqual(context.rounding, original.rounding)
                self.assertEqual(context.clamp, original.clamp)
                self.assertEqual(context.flags, original.flags)
                self.assertEqual(context.traps, original.traps)


class DivisionRuntimeRegressionTests(unittest.TestCase):
    def setUp(self):
        self.output = []
        self.vm = Interpreter(output=self.output.append)

    def test_chained_division_uses_the_stored_first_quotient(self):
        first = Decimal('0.' + '3' * 27)
        result = self.vm.execute('third = 1 / 3; third / 7')
        self.assertEqual(self.vm.variables['third'], first)
        self.assertEqual(Fraction(result), fraction_oracle(first, Decimal('7')))
        self.assertEqual(result, self.vm.execute('1 / 3 / 7'))
        self.assertNotEqual(result, self.vm.execute('1 / (3 * 7)'))

    def test_error_is_source_aware_catchable_and_preserves_assignment_state(self):
        self.vm.variables.update(a=Decimal(1), b=Decimal('268435456'))
        self.vm.execute('result = 17;')
        with self.assertRaisesRegex(BSLRuntimeError, HALF_MESSAGE) as caught:
            self.vm.execute('\nresult = a / b;', 'half.bsl')
        self.assertEqual((caught.exception.source, caught.exception.line,
                          caught.exception.column), ('half.bsl', 2, 12))
        self.assertEqual(self.vm.variables['result'], Decimal(17))
        self.vm.execute('''
            Попытка result = a / b;
            Исключение Сообщить(ОписаниеОшибки()); КонецПопытки;
            Message(result); Message(ErrorDescription() = "");
            result = 1 / 2; Message(result);
        ''', 'caught-half.bsl')
        self.assertRegex(self.output[0], HALF_MESSAGE)
        self.assertIn('caught-half.bsl:2:', self.output[0])
        self.assertEqual(self.output[1:], ['17', 'Да', '0,5'])
        self.assertEqual(self.vm.execute('ErrorDescription()'), '')

    def test_division_by_zero_remains_catchable_with_existing_diagnostic(self):
        for expression in ('1 / 0', '0 / 0', '1 / -0.000'):
            with self.subTest(expression=expression):
                with self.assertRaises(BSLRuntimeError) as caught:
                    self.vm.execute(expression, 'zero.bsl')
                self.assertEqual(caught.exception.message, 'Деление на ноль')
        self.vm.execute('Try x = 1 / 0; Except Message("caught"); EndTry; Message(1 / 2);')
        self.assertEqual(self.output, ['caught', '0,5'])

    def test_other_arithmetic_retains_the_existing_38_digit_context(self):
        left = Decimal('1234567890123456789012345678901234567.89123')
        right = Decimal('3.14159')
        self.vm.variables.update(left=left, right=right)
        with localcontext(Context(prec=38)):
            expected = {'left + right': left + right, 'left - right': left - right,
                        'left * right': left * right, 'left % right': left % right}
        for expression, result in expected.items():
            with self.subTest(expression=expression):
                self.assertEqual(self.vm.execute(expression), result)
        # Division can preserve an exact operand that the other operators round.
        self.assertEqual(self.vm.execute('left / 1'), left)
        self.assertNotEqual(self.vm.execute('left + 0'), left)

    def test_unary_sign_preserves_long_values_under_tiny_trapping_contexts(self):
        left = Decimal('0.' + '123456789' * 40)
        self.vm.variables['left'] = left
        expected = fraction_oracle(left.copy_negate(), Decimal(7))
        with localcontext() as context:
            context.prec = 2
            context.Emin, context.Emax = -2, 2
            for signal in context.traps:
                context.traps[signal] = True
            context.clear_flags()
            self.assertEqual(self.vm.execute('-left').as_tuple(), left.copy_negate().as_tuple())
            self.assertIs(self.vm.execute('+left'), left)
            self.assertEqual(self.vm.execute('-(-left)').as_tuple(), left.as_tuple())
            self.assertEqual(Fraction(self.vm.execute('-left / 7')), expected)
            self.assertEqual(Fraction(self.vm.execute('-(left / 7)')), expected)
            self.assertFalse(any(context.flags.values()))
        self.assertIs(self.vm.variables['left'], left)

    def test_non_numeric_runtime_operands_still_raise_the_number_type_error(self):
        for expression in ('True / 1', '1 / False', '"1" / 3', '1 / Undefined'):
            with self.subTest(expression=expression):
                with self.assertRaisesRegex(BSLRuntimeError, 'Ожидается число'):
                    self.vm.execute(expression)

    def test_resource_failures_are_catchable_and_keep_previous_value(self):
        for left, right in [('9' * 4097, '3'), ('1e-4096', '3'),
                            ('1', '1e4096'), ('1e4050', '1e-100')]:
            with self.subTest(left_length=len(left), right=right):
                self.vm.variables.update(left=Decimal(left), right=Decimal(right), value=Decimal(17))
                self.vm.execute('''
                    Try value = left / right;
                    Except description = ErrorDescription(); EndTry;
                    after = 1 / 2;
                ''', 'resources.bsl')
                self.assertRegex(self.vm.variables['description'], RESOURCE_MESSAGE)
                self.assertIn('resources.bsl:2:', self.vm.variables['description'])
                self.assertEqual(self.vm.variables['value'], Decimal(17))
                self.assertEqual(self.vm.variables['after'], Decimal('0.5'))
                self.assertEqual(self.vm.execute('ErrorDescription()'), '')

    def test_extreme_exponents_fail_promptly_without_constructing_huge_powers(self):
        # A process timeout makes a broken guard fail safely rather than stall
        # the test runner allocating 10**1000000000 or formatting such a value.
        program = '''
from decimal import Decimal, localcontext
from yadinassi import Interpreter
from yadinassi.errors import BSLRuntimeError
from yadinassi.values import divide, to_string
pairs = [('1e1000000000', '3'), ('1e-1000000000', '3'),
         ('1', '3e1000000000'), ('1', '3e-1000000000'),
         ('1e1000000000', '1e1000000000')]
with localcontext() as context:
    context.prec = 1
    for signal in context.traps:
        context.traps[signal] = True
    for left, right in pairs:
        left, right = Decimal(left), Decimal(right)
        try:
            divide(left, right)
        except (ArithmeticError, ValueError) as error:
            assert 'предел ресурсов Yadinassi' in str(error), str(error)
        else:
            raise AssertionError('extreme exponent was accepted')
        vm = Interpreter()
        vm.variables.update(left=left, right=right)
        try:
            vm.execute('left / right', 'extreme.bsl')
        except BSLRuntimeError as error:
            assert 'предел ресурсов Yadinassi' in error.message, error.message
        else:
            raise AssertionError('runtime extreme exponent was accepted')
    for text in ('1e1000000000', '1e-1000000000', '-1e-1000000000'):
        try:
            to_string(Decimal(text))
        except (ArithmeticError, ValueError) as error:
            assert 'предел ресурсов Yadinassi' in str(error), str(error)
        else:
            raise AssertionError('extreme presentation was accepted')
    assert to_string(Decimal('0e1000000000')) == '0'
    assert to_string(Decimal('-0e-1000000000')) == '0'
print('guarded')
'''
        completed = subprocess.run([sys.executable, '-c', program], cwd=ROOT,
                                   capture_output=True, text=True, timeout=5)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(completed.stdout, 'guarded\n')
        self.assertEqual(completed.stderr, '')


class BoundedDivisionPresentationTests(unittest.TestCase):
    """Chosen display contract; these examples are not additional native goldens.

    Arithmetic remains exact to the division model's own selected scale.
    Presentation may lose fractional positions beyond 324 only for |value|<1.
    """

    def test_subunit_boundary_rounding_counts_fractional_positions(self):
        cases = [
            ('0.' + '1' * 323 + '2', '0,' + '1' * 323 + '2'),
            ('0.' + '1' * 324 + '4', '0,' + '1' * 324),
            ('0.' + '1' * 324 + '6', '0,' + '1' * 323 + '2'),
            ('0.' + '1' * 324 + '5001', '0,' + '1' * 323 + '2'),
            ('0.' + '0' * 100 + '1' * 224 + '6', '0,' + '0' * 100 + '1' * 223 + '2'),
            ('0.' + '9' * 324 + '6', '1'),
            ('0.' + '0' * 324 + '4', '0'),
            ('0.' + '0' * 324 + '6', '0,' + '0' * 323 + '1'),
            ('1e-4096', '0'),
        ]
        for spelling, expected in cases:
            for negative in (False, True):
                value = Decimal(('-' if negative else '') + spelling)
                before = value.as_tuple()
                signed_expected = '-' + expected if negative and expected != '0' else expected
                with self.subTest(value=spelling, negative=negative):
                    self.assertEqual(to_string(value), signed_expected)
                    self.assertEqual(value.as_tuple(), before)

    def test_presentation_roundtrip_is_intentionally_lossy_without_mutating_value(self):
        value = Decimal('0.' + '1' * 324 + '6')
        expected = '0,' + '1' * 323 + '2'
        before = value.as_tuple()
        output = []
        vm = Interpreter(output=output.append)
        vm.variables['source'] = value
        vm.execute('''
            rendered = String(source); parsed = Number(rendered);
            Message(source); Message("value=" + source);
            Message(source = parsed);
        ''')
        self.assertEqual(vm.variables['rendered'], expected)
        self.assertEqual(vm.variables['parsed'], number(expected))
        self.assertNotEqual(vm.variables['parsed'], value)
        self.assertEqual(output, [expected, 'value=' + expected, 'Нет'])
        self.assertIs(vm.variables['source'], value)
        self.assertEqual(value.as_tuple(), before)
        exact_boundary = Decimal('0.' + '1' * 323 + '2')
        self.assertEqual(number(to_string(exact_boundary)), exact_boundary)

    def test_presentation_ignores_context_rounding_traps_and_exponent_limits(self):
        value = Decimal('0.' + '1' * 324 + '6')
        for mode in (ROUND_DOWN, ROUND_UP, ROUND_HALF_EVEN, ROUND_FLOOR, ROUND_CEILING):
            with self.subTest(rounding=mode), localcontext() as context:
                context.prec = 1
                context.Emin, context.Emax = -2, 2
                context.rounding = mode
                for signal in context.traps:
                    context.traps[signal] = True
                context.clear_flags()
                self.assertEqual(to_string(value), '0,' + '1' * 323 + '2')
                self.assertEqual(to_string(value.copy_negate()), '-0,' + '1' * 323 + '2')
                self.assertFalse(any(context.flags.values()))
                self.assertEqual(context.prec, 1)
                self.assertEqual(context.rounding, mode)

    def test_normalized_trailing_padding_does_not_trigger_presentation_limits(self):
        for spelling, expected in [
            ('0.123' + '0' * 5000, '0,123'),
            ('0.' + '1' * 324 + '0' * 5000, '0,' + '1' * 324),
            ('1234.' + '0' * 5000, '1\u00a0234'),
            ('1234.' + '1' * 324, '1\u00a0234,' + '1' * 324),
        ]:
            for negative in (False, True):
                value = Decimal(('-' if negative else '') + spelling)
                before = value.as_tuple()
                with self.subTest(normalized=expected[:16], negative=negative):
                    self.assertEqual(to_string(value), ('-' if negative else '') + expected)
                    self.assertEqual(number(to_string(value)), value)
                    self.assertEqual(value.as_tuple(), before)

    def test_true_display_halves_and_large_magnitude_long_fractions_are_explicit_errors(self):
        halves = ['0.' + '0' * 324 + '5', '0.' + '0' * 323 + '15',
                  '0.' + '1' * 324 + '50000']
        unverified_magnitudes = ['1.' + '0' * 324 + '1', '1234.' + '1' * 325]
        for spelling in halves + unverified_magnitudes:
            for negative in (False, True):
                value = Decimal(('-' if negative else '') + spelling)
                before = value.as_tuple()
                with self.subTest(value=spelling[:20], negative=negative):
                    with self.assertRaisesRegex(ValueError, 'пока не поддерживается в Yadinassi') as caught:
                        to_string(value)
                    if spelling in halves:
                        self.assertIn('точная половина на границе 324 позиций', str(caught.exception))
                    else:
                        self.assertIn('более 324 дробных позиций при модуле не меньше 1', str(caught.exception))
                    vm = Interpreter()
                    vm.variables.update(value=value, shown='unchanged')
                    vm.execute('''
                        Try shown = String(value);
                        Except description = ErrorDescription(); EndTry;
                    ''', 'presentation-limit.bsl')
                    self.assertEqual(vm.variables['shown'], 'unchanged')
                    self.assertIn('presentation-limit.bsl:2:', vm.variables['description'])
                    self.assertIn('пока не поддерживается в Yadinassi', vm.variables['description'])
                    self.assertEqual(value.as_tuple(), before)
                    self.assertEqual(vm.execute('ErrorDescription()'), '')


if __name__ == '__main__':
    unittest.main()
