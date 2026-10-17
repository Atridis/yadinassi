"""Native PR30 character regressions plus explicitly broader robustness tests."""

from decimal import Decimal, Inexact, Rounded, ROUND_UP, localcontext
import unittest

from yadinassi import BSLError, Interpreter
from yadinassi.strings import character, character_code


class CharacterTests(unittest.TestCase):
    def setUp(self):
        self.vm = Interpreter(output=lambda message: None)

    def test_bilingual_case_insensitive_aliases(self):
        for expression, expected in [('сИмВоЛ(1103)', 'я'), ('CHAR(65)', 'A'),
                                     ('кОдСиМвОлА("Я")', Decimal(1071)),
                                     ('CHARCODE("AB", 2)', Decimal(66))]:
            with self.subTest(expression=expression):
                actual = self.vm.execute(expression)
                self.assertIs(type(actual), type(expected))
                self.assertEqual(actual, expected)

    def test_native_character_code_units(self):
        for code in [0, 1, 65, 1103, 55357, 56832, 65535]:
            with self.subTest(code=code):
                value = self.vm.execute(f'Char({code})')
                self.assertIs(type(value), str)
                self.assertEqual(value, chr(code))
                self.assertEqual(character_code(value), Decimal(code))

    def test_native_character_invalid_range_returns_empty(self):
        for code in [-1, 65536, 99999999999999999999999999999999999999]:
            with self.subTest(code=code):
                self.assertEqual(self.vm.execute(f'Символ({code})'), '')

    def test_native_character_fraction_and_conversions(self):
        for expression, expected in [('Char(65.9)', 'A'), ('Char(0.0001)', '\0'),
                                     ('Char("65")', 'A'), ('Char(True)', '\1')]:
            with self.subTest(expression=expression):
                self.assertEqual(self.vm.execute(expression), expected)
        with self.assertRaises(BSLError):
            self.vm.execute('Символ(Неопределено)')

    def test_native_code_default_and_position(self):
        for expression, expected in [('CharCode("АБ")', 1040),
                                     ('CharCode("АБ", 1.9)', 1040),
                                     ('CharCode(123)', 49),
                                     ('CharCode("АБ", "2")', 1041)]:
            with self.subTest(expression=expression):
                actual = self.vm.execute(expression)
                self.assertIs(type(actual), Decimal)
                self.assertEqual(actual, Decimal(expected))

    def test_native_code_empty_and_bounds(self):
        for expression in ['CharCode("")', 'CharCode("АБ", 0)',
                           'CharCode("АБ", -1)', 'CharCode("АБ", 3)']:
            with self.subTest(expression=expression):
                self.assertEqual(self.vm.execute(expression), Decimal(-1))

    def test_native_surrogate_pair(self):
        self.assertEqual(self.vm.execute('Char(55357) + Символ(56832)'), '😀')
        self.assertEqual(self.vm.execute('CharCode("😀", 1)'), Decimal(55357))
        self.assertEqual(self.vm.execute('КодСимвола("😀", 2)'), Decimal(56832))
        self.assertEqual(self.vm.execute('СтрДлина(Char(55357) + Char(56832))'), Decimal(2))

    def test_character_composes_with_utf16_string_operations(self):
        self.assertEqual(self.vm.execute('CharCode("A😀B", 4)'), Decimal(66))
        self.assertEqual(self.vm.execute('CharCode(Left("😀", 1))'), Decimal(55357))
        self.assertEqual(self.vm.execute('CharCode(Right("😀", 1))'), Decimal(56832))
        self.assertEqual(self.vm.execute('Find("a" + Char(0) + "b", Char(0))'), Decimal(2))
        self.assertEqual(self.vm.execute('StrLen(Char(0) + Char(0))'), Decimal(2))

    def test_existing_internal_serialization_preserves_units(self):
        for expression in ['Char(0)', 'Char(55357)', 'Char(56832)',
                           'Char(65535)', 'Char(55357) + Char(56832)']:
            with self.subTest(expression=expression):
                self.vm.execute('Value = ' + expression)
                self.assertTrue(self.vm.execute(
                    '(ValueFromStringInternal(ValueToStringInternal(Value)) = Value)'))
        self.assertEqual(self.vm.execute('ValueToStringInternal(Char(55357))'),
                         '{"S",""\\d83d"}')

    def test_truncate_then_range_is_the_interpreter_boundary_contract(self):
        # These fractional boundaries are not separate native observations.
        for value, expected in [('-0.9', '\0'), ('65535.9', '\uffff'),
                                ('65536.1', ''), ('-1.9', '')]:
            self.assertEqual(character(Decimal(value)), expected)
        for value, expected in [('0.9', -1), ('1.9', 65), ('2.9', 66), ('3.1', -1)]:
            self.assertEqual(character_code('AB', Decimal(value)), Decimal(expected))

    def test_huge_exponents_are_bounded_without_expanding_integers(self):
        # Python-host robustness, not a claim about native numeric limits.
        self.assertEqual(character(Decimal('1e1000000')), '')
        self.assertEqual(character(Decimal('-1e1000000')), '')
        self.assertEqual(character(Decimal('1e-1000000')), '\0')
        self.assertEqual(character_code('AB', Decimal('1e1000000')), Decimal(-1))
        self.assertEqual(character_code('AB', Decimal('-1e1000000')), Decimal(-1))

    def test_host_decimal_context_cannot_change_results(self):
        with localcontext() as context:
            context.prec = 1
            context.rounding = ROUND_UP
            context.Emax = 9
            context.Emin = -9
            context.traps[Inexact] = True
            context.traps[Rounded] = True
            context.clear_flags()
            self.assertEqual(character(Decimal('55357.9')), '\ud83d')
            self.assertEqual(character_code('😀', Decimal('1.9')), Decimal(55357))
            self.assertEqual(character(Decimal('1e1000000')), '')
            self.assertFalse(any(context.flags.values()))

    def test_arity_and_conversion_errors_are_catchable(self):
        expressions = ['Char()', 'Char(65, 1)', 'CharCode()', 'CharCode("A", 1, 2)',
                       'Char("bad")', 'Char(New Array)', 'CharCode("A", Undefined)',
                       'CharCode("A", "bad")', 'CharCode("A", New Array)']
        for expression in expressions:
            with self.subTest(expression=expression):
                with self.assertRaises(BSLError):
                    self.vm.execute(expression, 'characters.bsl')
                self.assertTrue(self.vm.execute(
                    'Caught = False; Try ' + expression +
                    '; Except Caught = True; EndTry; Caught'))
                self.assertEqual(self.vm.execute('CharCode(Char(65))'), Decimal(65))

    def test_nonfinite_python_inputs_rejected(self):
        for value in ['NaN', 'sNaN', 'Infinity', '-Infinity']:
            with self.subTest(value=value):
                with self.assertRaises((ValueError, ArithmeticError)):
                    character(Decimal(value))
                with self.assertRaises((ValueError, ArithmeticError)):
                    character_code('A', Decimal(value))


if __name__ == '__main__':
    unittest.main()
