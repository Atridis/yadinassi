"""Native StrCompare cases and explicitly local safety/Unicode policies."""
from decimal import Decimal
from pathlib import Path
import unittest
from unittest.mock import patch

from yadinassi import BSLError, Interpreter
from yadinassi.collation import caseless_string_key, string_key
from yadinassi.strings import compare


PAIRS = (('ascii-case', 'aBc', 'AbC', 0), ('less', 'a', 'b', -1),
         ('greater', 'b', 'a', 1), ('empty', '', 'a', -1), ('both-empty', '', '', 0),
         ('russian-case', 'ЁЖ', 'ёж', 0), ('yo-e', 'ё', 'е', 1),
         ('sharp-s', 'ß', 'SS', 1), ('dotted-i', 'İ', 'i', 1),
         ('canonical', 'é', 'e\u0301', 0), ('punctuation', 'a-b', 'ab', -1),
         ('cross-script', 'a', 'а', -1))


class StringCompareTests(unittest.TestCase):
    def test_native_cases_aliases_and_reverse(self):
        output = (Path(__file__).resolve().parents[1] /
                  'integrational_tests/output/strings.out').read_text(encoding='utf-8')
        vm = Interpreter()
        for label, first, second, expected in PAIRS:
            self.assertIn(f'compare.{label}: [{{"N",{expected}}}]\n', output)
            vm.variables.update(first=first, second=second)
            for name in ('СтрСравнить', 'StrCompare', 'сТрСрАвНиТь', 'sTrCoMpArE'):
                value = vm.execute(f'{name}(first, second)')
                self.assertIs(type(value), Decimal)
                self.assertEqual(value, Decimal(expected))
                self.assertEqual(vm.execute(f'{name}(second, first)'), -value)

    def test_internal_serialization_both_directions(self):
        vm = Interpreter()
        for _, first, second, expected in PAIRS:
            vm.variables.update(first=first, second=second)
            self.assertEqual(vm.execute('ValueFromStringInternal(ValueToStringInternal(StrCompare(first, second)))'), Decimal(expected))
            self.assertEqual(vm.execute('StrCompare(ValueFromStringInternal(ValueToStringInternal(first)), second)'), Decimal(expected))

    def test_case_weights_not_unicode_casefold(self):
        # Additional Unicode cases are local UCA policy, not extra native probes.
        for first, second in (('ẞ', 'ß'), ('Σ', 'σ'), ('А', 'а')):
            self.assertEqual(compare(first, second), Decimal(0))
        self.assertNotEqual(compare('ß', 'SS'), Decimal(0))
        self.assertNotEqual(compare('İ', 'i'), Decimal(0))
        self.assertNotEqual(compare('é', 'e'), Decimal(0))
        self.assertEqual(compare('a\0', 'a'), Decimal(0))
        self.assertEqual(compare('\ud800', '\ud800'), Decimal(0))

    def test_existing_exact_equality_and_order_are_unchanged(self):
        vm = Interpreter()
        self.assertFalse(vm.execute('"A" = "a"'))
        self.assertFalse(vm.execute('"é" = "é"'))
        self.assertNotEqual(string_key('A'), string_key('a'))
        self.assertEqual(caseless_string_key('A'), caseless_string_key('a'))

    def test_strict_types_do_not_call_host_hooks(self):
        class Hostile:
            def __str__(self):
                raise AssertionError('unexpected host conversion')
        for value in (None, True, Decimal(1), 1, [], Hostile()):
            with self.assertRaises(TypeError):
                compare(value, 'a')
            with self.assertRaises(TypeError):
                compare('a', value)

    def test_resource_limits_even_for_equal_arguments(self):
        self.assertEqual(compare('a' * 4096, 'A' * 4096), Decimal(0))
        for first, second in (('a' * 4097, ''), ('', 'a' * 4097), ('a' * 4097, 'a' * 4097)):
            with self.assertRaisesRegex(ValueError, '4096'):
                compare(first, second)
        with patch('yadinassi.collation.MAX_NORMALIZED_LENGTH', 1):
            with self.assertRaisesRegex(ValueError, 'нормализации'):
                compare('é', 'é')

    def test_arity_errors_and_recovery(self):
        vm = Interpreter()
        for expression in ('StrCompare()', 'StrCompare("a")', 'StrCompare("a", "b", 1)',
                           'StrCompare(, "b")', 'StrCompare(1, "b")',
                           'StrCompare("a", Undefined)'):
            vm.execute('saved = "old";')
            with self.assertRaises(BSLError):
                vm.execute('saved = ' + expression)
            self.assertEqual(vm.execute('saved'), 'old')
            vm.execute(f'Try saved = {expression}; Except caught = True; EndTry;')
            self.assertTrue(vm.execute('caught'))
            self.assertEqual(vm.execute('StrCompare("A", "a")'), Decimal(0))

    def test_arguments_evaluate_once_left_to_right(self):
        vm = Interpreter()
        vm.execute('''Перем Порядок;
Функция Аргумент(Знач Метка)
    Порядок = Порядок + Метка;
    Возврат Метка;
КонецФункции
Порядок = "";
Результат = СтрСравнить(Аргумент("a"), Аргумент("b"));''')
        self.assertEqual(vm.execute('Порядок'), 'ab')
        self.assertEqual(vm.execute('Результат'), Decimal(-1))
