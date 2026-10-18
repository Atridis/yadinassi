"""Documented bit contracts, independent truth tables, and local safety guards.

These tests are not a native 1C transcript. Coercions remain intentionally outside
this implementation's compatibility claim.
"""
from decimal import Decimal, Inexact, Rounded, localcontext
import unittest

from yadinassi import BSLError, Interpreter
from yadinassi import bits


class BitOperationTests(unittest.TestCase):
    def setUp(self):
        self.vm = Interpreter(output=lambda text: None)

    def test_bilingual_case_insensitive_names(self):
        arguments = ('10, 12', '10, 12', '10, 12', '0', '10, 12',
                     '2147483648, 31', '26, 24', '0, 31, True')
        expected = (8, 14, 6, 4294967295, 2, True, True, 2147483648)
        for (ru, function, en), args, value in zip(bits.BUILTINS, arguments, expected):
            for name in (ru, en, ru.upper(), en.lower()):
                with self.subTest(name=name):
                    actual = self.vm.execute(f'{name}({args})')
                    self.assertIs(type(actual), bool if type(value) is bool else Decimal)
                    self.assertEqual(actual, value)

    def test_truth_tables(self):
        for a, b, conjunction, disjunction, exclusive in (
            (0, 0, 0, 0, 0), (0, 1, 0, 1, 1),
            (1, 0, 0, 1, 1), (1, 1, 1, 1, 0),
        ):
            for position in range(32):
                x, y = Decimal(a * 2**position), Decimal(b * 2**position)
                self.assertEqual(bits.bitwise_and(x, y), conjunction * 2**position)
                self.assertEqual(bits.bitwise_or(x, y), disjunction * 2**position)
                self.assertEqual(bits.bitwise_xor(x, y), exclusive * 2**position)
                self.assertEqual(bits.bitwise_and_not(x, y), (a and not b) * 2**position)

    def test_complement_is_unsigned_32_bit(self):
        for value, expected in ((0, 4294967295), (4294967295, 0),
                                (2147483648, 2147483647), (10, 4294967285)):
            self.assertEqual(bits.bitwise_not(Decimal(value)), expected)

    def test_every_bit_can_be_set_cleared_and_checked(self):
        for position in range(32):
            bit = Decimal(position)
            value = bits.set_bit(Decimal(0), bit, True)
            self.assertEqual(value, 2**position)
            self.assertIs(bits.check_bit(value, bit), True)
            self.assertEqual(bits.set_bit(value, bit, True), value)
            self.assertEqual(bits.set_bit(value, bit, False), 0)
            self.assertIs(bits.check_bit(Decimal(0), bit), False)
            self.assertEqual(bits.set_bit(Decimal(4294967295), bit, False),
                             4294967295 - 2**position)

    def test_mask_means_all_selected_bits(self):
        for number, mask, expected in ((26, 24, True), (26, 16, True),
                                       (26, 12, False), (0, 0, True),
                                       (4294967295, 0, True), (0, 1, False)):
            self.assertIs(bits.check_by_bit_mask(Decimal(number), Decimal(mask)), expected)

    def test_scaled_integral_values_and_negative_zero(self):
        self.assertEqual(self.vm.execute('BitwiseOr(1.000, -0.000)'), 1)
        self.assertEqual(self.vm.execute('SetBit(0, 31.000, True)'), 2147483648)

    def test_all_numeric_parameters_reject_fractions_and_out_of_range(self):
        calls = [('BitwiseNot', ['0']), ('BitwiseAnd', ['0', '0']),
                 ('BitwiseOr', ['0', '0']), ('BitwiseXor', ['0', '0']),
                 ('BitwiseAndNot', ['0', '0']), ('CheckBit', ['0', '0']),
                 ('CheckByBitMask', ['0', '0']), ('SetBit', ['0', '0', 'True'])]
        for name, args in calls:
            for index in range(len(args) - (name == 'SetBit')):
                for invalid in ('-1', '0.5', '4294967296', 'Number("1e1000000")',
                                'Number("1e-1000000")'):
                    candidate = args.copy(); candidate[index] = invalid
                    with self.subTest(name=name, index=index, invalid=invalid), self.assertRaises(BSLError):
                        self.vm.execute(f'{name}({", ".join(candidate)})')
        for name, suffix in (('CheckBit', ''), ('SetBit', ', True')):
            with self.assertRaises(BSLError):
                self.vm.execute(f'{name}(0, 32{suffix})')

    def test_unsupported_coercions_are_explicit_local_guards(self):
        for value in ('True', '"1"', 'Undefined', 'New Array', 'Тип("Число")'):
            with self.subTest(value=value), self.assertRaises(BSLError):
                self.vm.execute(f'BitwiseNot({value})')
        for value in ('1', '0', '"True"', 'Undefined'):
            with self.subTest(value=value), self.assertRaises(BSLError):
                self.vm.execute(f'SetBit(0, 0, {value})')

    def test_nonfinite_and_host_numbers_are_local_guards(self):
        for value in (Decimal('NaN'), Decimal('sNaN'), Decimal('Infinity'),
                      Decimal('-Infinity'), 1, 1.0, True, None):
            with self.subTest(value=value), self.assertRaises(TypeError):
                bits.bitwise_not(value)

    def test_arity_and_omission_errors(self):
        for expression in ('BitwiseNot()', 'BitwiseNot(0, 1)', 'BitwiseAnd(1)',
                           'BitwiseOr(1, 2, 3)', 'BitwiseXor(, 2)', 'CheckBit(1)',
                           'CheckByBitMask(1,)', 'SetBit(0, 1)', 'SetBit(0, 1, True, 1)'):
            with self.subTest(expression=expression), self.assertRaises(BSLError):
                self.vm.execute(expression)

    def test_host_decimal_context_cannot_round_bit_results(self):
        with localcontext() as context:
            context.prec = 1
            context.Emax = 1
            context.Emin = -1
            context.traps[Inexact] = context.traps[Rounded] = True
            context.clear_flags()
            self.assertEqual(bits.bitwise_not(Decimal(0)), 4294967295)
            self.assertEqual(bits.set_bit(Decimal(0), Decimal(31), True), 2147483648)
            self.assertFalse(any(context.flags.values()))

    def test_values_roundtrip_through_existing_internal_codec(self):
        for expression in ('BitwiseNot(0)', 'SetBit(0, 31, True)',
                           'CheckBit(1, 0)', 'CheckByBitMask(0, 1)'):
            self.vm.execute(f'value = {expression}; copy = ValueFromStringInternal(ValueToStringInternal(value));')
            self.assertIs(type(self.vm.variables['copy']), type(self.vm.variables['value']))
            self.assertEqual(self.vm.variables['copy'], self.vm.variables['value'])

    def test_eval_execute_and_routine_composition(self):
        result = self.vm.execute('''
        Function Enable(Value) Return SetBit(Value, 3, True); EndFunction
        flags = Enable(16);
        Execute("flags = BitwiseAndNot(flags, 16);");
        Eval("CheckBit(flags, 3)")
        ''')
        self.assertIs(result, True)

    def test_catchable_error_preserves_assignment_and_recovers(self):
        self.vm.execute('''saved = 42;
        Try saved = BitwiseAnd(1.5, 2); Except caught = True; EndTry;
        recovered = BitwiseOr(1, 2);''')
        self.assertEqual(self.vm.variables['saved'], 42)
        self.assertIs(self.vm.variables['caught'], True)
        self.assertEqual(self.vm.variables['recovered'], 3)

    def test_independent_registration_and_host_override(self):
        self.vm.register_function('BitwiseNot', lambda value: 'override')
        self.assertEqual(self.vm.execute('BitwiseNot(0)'), 'override')
        self.assertEqual(self.vm.execute('ПобитовоеНе(0)'), 4294967295)
        self.assertEqual(Interpreter().execute('BitwiseNot(0)'), 4294967295)
