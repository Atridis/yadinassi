"""Native-backed occurrence counting with explicitly shared UTF-16 contracts."""
from decimal import Decimal
import unittest

from yadinassi import Interpreter, BSLError
from yadinassi.strings import occurrence_count
from yadinassi.serialization import value_to_string_internal, value_from_string_internal


class StringOccurrenceTests(unittest.TestCase):
    def test_native_observations(self):
        for text, needle, expected in [('aaaa', 'aa', 2), ('abc', '', 0), ('', '', 0),
                                      ('AaA', 'a', 1), ('Я😀Я😀', '😀', 2),
                                      (Decimal(12121), '1', 3)]:
            with self.subTest(text=text, needle=needle):
                self.assertEqual(occurrence_count(text, needle), Decimal(expected))

    def test_aliases_and_result_type(self):
        vm = Interpreter()
        for name in ('СтрЧислоВхождений', 'StrOccurrenceCount', 'сТрЧиСлОвХоЖдЕнИй', 'sTrOcCuRrEnCeCoUnT'):
            result = vm.execute(f'{name}("aaaa", "aa")')
            self.assertIsInstance(result, Decimal)
            self.assertEqual(result, Decimal(2))

    def test_nonoverlap_no_match_and_edges(self):
        for text, needle, count in [('ababa', 'aba', 1), ('aaaaa', 'aa', 2),
                                   ('aaa', 'aaa', 1), ('aaa', 'aaaa', 0), ('', 'a', 0),
                                   ('abc', 'x', 0), ('aabaa', 'aa', 2)]:
            self.assertEqual(occurrence_count(text, needle), Decimal(count))

    def test_shared_utf16_nul_and_surrogate_contract(self):
        # Unit tests of the shared representation, not additional native probes.
        self.assertEqual(occurrence_count('😀😀', '\ud83d'), Decimal(2))
        self.assertEqual(occurrence_count('\ud83d\ude00😀', '😀'), Decimal(2))
        self.assertEqual(occurrence_count('a\0a\0', '\0'), Decimal(2))
        self.assertEqual(occurrence_count('é', 'e\u0301'), Decimal(0))

    def test_existing_conversion_contract(self):
        self.assertEqual(occurrence_count(None, ''), Decimal(0))
        self.assertEqual(occurrence_count('abc', None), Decimal(0))
        self.assertEqual(occurrence_count(True, 'Да'), Decimal(1))
        self.assertEqual(occurrence_count('12121', Decimal(1)), Decimal(3))

    def test_serialization_both_directions(self):
        value = occurrence_count('aaaa', 'aa')
        self.assertEqual(value_to_string_internal(value), '{"N",2}')
        self.assertEqual(value_from_string_internal(value_to_string_internal(value)), value)

    def test_arity_errors_preserve_assignment_and_recover(self):
        vm = Interpreter()
        for expression in ('StrOccurrenceCount()', 'StrOccurrenceCount("a")',
                           'СтрЧислоВхождений("a", "a", "a")'):
            vm.execute('saved = 7;')
            with self.subTest(expression=expression), self.assertRaises(BSLError):
                vm.execute('saved = ' + expression)
            self.assertEqual(vm.execute('saved'), Decimal(7))
            vm.execute(f'Try {expression}; Except saved = StrOccurrenceCount("aba", "a"); EndTry;')
            self.assertEqual(vm.execute('saved'), Decimal(2))

    def test_long_inputs(self):
        self.assertEqual(occurrence_count('Ж' * 100000, 'ЖЖ'), Decimal(50000))
        self.assertEqual(occurrence_count('a' * 100000, 'a' * 50000 + 'b'), Decimal(0))
