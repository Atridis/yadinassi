"""Owner PR52 confirms modulo-2**32 left shift; local domain safety tests."""
from decimal import Decimal, Inexact, Rounded, localcontext
import unittest

from yadinassi import BSLError, Interpreter
from yadinassi.numeric.bits import bitwise_shift_left


class BitwiseShiftLeftTests(unittest.TestCase):
    def setUp(self):
        self.vm = Interpreter(output=lambda text: None)

    def test_all_bit_positions_and_offsets_against_modular_multiplication(self):
        # Modular multiplication is an independent oracle, without bit operators.
        for position in range(32):
            for offset in range(32):
                value = Decimal(2**position)
                actual = bitwise_shift_left(value, Decimal(offset))
                self.assertIs(type(actual), Decimal)
                self.assertEqual(actual, (2**position * 2**offset) % 2**32)

    def test_mixed_bits_and_boundaries(self):
        for value in (0, 1, 26, 1431655765, 2863311530, 2147483648, 4294967295):
            for offset in range(32):
                self.assertEqual(bitwise_shift_left(Decimal(value), Decimal(offset)),
                                 (value * 2**offset) % 2**32)

    def test_scaled_integers_and_negative_zero(self):
        self.assertEqual(self.vm.execute('BitwiseShiftLeft(26.000, 3.000)'), 208)
        self.assertEqual(self.vm.execute('BitwiseShiftLeft(-0.000, -0.000)'), 0)

    def test_each_argument_domain(self):
        for argument in ('-1', '0.5', '4294967296', 'Number("1e1000000")',
                         'Number("1e-1000000")'):
            for call in (f'BitwiseShiftLeft({argument}, 0)',
                         f'BitwiseShiftLeft(0, {argument})'):
                with self.subTest(call=call), self.assertRaises(BSLError):
                    self.vm.execute(call)
        with self.assertRaises(BSLError):
            self.vm.execute('BitwiseShiftLeft(0, 32)')

    def test_unsupported_coercions_are_local_guards(self):
        for value in ('True', '"1"', 'Undefined', 'New Array', 'Type("Number")'):
            for args in (f'{value}, 0', f'0, {value}'):
                with self.subTest(args=args), self.assertRaises(BSLError):
                    self.vm.execute(f'BitwiseShiftLeft({args})')

    def test_nonfinite_and_host_numbers_are_local_guards(self):
        for invalid in (Decimal('NaN'), Decimal('sNaN'), Decimal('Infinity'),
                        Decimal('-Infinity'), 1, 1.0, True, None):
            for args in ((invalid, Decimal(0)), (Decimal(0), invalid)):
                with self.subTest(args=args), self.assertRaises(TypeError):
                    bitwise_shift_left(*args)

    def test_arity_and_omissions(self):
        for args in ('', '1', '1, 2, 3', ', 1', '1,'):
            with self.subTest(args=args), self.assertRaises(BSLError):
                self.vm.execute(f'BitwiseShiftLeft({args})')

    def test_context_independence(self):
        with localcontext() as context:
            context.prec = 1
            context.Emax = 1
            context.Emin = -1
            context.traps[Inexact] = context.traps[Rounded] = True
            context.clear_flags()
            self.assertEqual(bitwise_shift_left(Decimal(4294967295), Decimal(1)), 4294967294)
            self.assertFalse(any(context.flags.values()))

    def test_internal_roundtrip_and_type(self):
        self.vm.execute('''value = BitwiseShiftLeft(4294967295, 0);
        copy = ValueFromStringInternal(ValueToStringInternal(value));''')
        self.assertIs(type(self.vm.variables['copy']), Decimal)
        self.assertEqual(self.vm.variables['copy'], 4294967295)
        self.assertTrue(self.vm.execute('(TypeOf(copy) = Type("Number"))'))

    def test_eval_execute_routine_and_input_unchanged(self):
        self.vm.execute('''Function Shift(value) Return BitwiseShiftLeft(value, 3); EndFunction
        original = 26; result = Shift(original);
        Execute("result = ПобитовыйСдвигВлево(result, 1);");''')
        self.assertEqual(self.vm.variables['original'], 26)
        self.assertEqual(self.vm.variables['result'], 416)
        self.assertEqual(self.vm.execute('Eval("BitwiseShiftLeft(26, 3)")'), 208)

    def test_catchable_error_preserves_assignment_and_recovers(self):
        self.vm.execute('''saved = 42;
        Try saved = BitwiseShiftLeft(1, 32); Except caught = True; EndTry;
        recovered = BitwiseShiftLeft(26, 3);''')
        self.assertEqual(self.vm.variables['saved'], 42)
        self.assertIs(self.vm.variables['caught'], True)
        self.assertEqual(self.vm.variables['recovered'], 208)

    def test_registration_is_per_interpreter_and_alias(self):
        self.vm.register_function('BitwiseShiftLeft', lambda value, offset: 'override')
        self.assertEqual(self.vm.execute('BitwiseShiftLeft(26, 3)'), 'override')
        self.assertEqual(self.vm.execute('ПобитовыйСдвигВлево(26, 3)'), 208)
        self.assertEqual(Interpreter().execute('BitwiseShiftLeft(26, 3)'), 208)
