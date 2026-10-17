"""Documented string boundaries and explicitly unprobed shared UTF-16 contracts."""

from decimal import Decimal
import unittest

from yadinassi import BSLError, Interpreter
from yadinassi.strings import starts_with, ends_with
from yadinassi.values import BSLArray


class StringBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.vm = Interpreter(output=lambda message: None)

    def test_bilingual_case_insensitive_aliases_and_boolean_type(self):
        for name in ('СтрНачинаетсяС', 'sTrStArTsWiTh', 'сТрНаЧиНаЕтСяС',
                     'СтрЗаканчиваетсяНа', 'sTrEnDsWiTh', 'сТрЗаКаНчИвАеТсЯнА'):
            with self.subTest(name=name):
                self.assertIs(self.vm.execute(f'{name}("Я", "Я")'), True)
                self.assertIs(self.vm.execute(f'{name}("Я", "я")'), False)
                self.assertTrue(self.vm.execute(f'(TypeOf({name}("A", "A")) = Type("Boolean"))'))

    def test_documented_exact_case_sensitive_boundaries(self):
        for text, needle, prefix, suffix in [
            ('abc', 'a', True, False), ('abc', 'c', False, True),
            ('abc', 'b', False, False), ('abc', 'abc', True, True),
            ('abc', 'abcd', False, False), ('', 'a', False, False),
            (' Ab ', ' ', True, True), ('Ab', 'a', False, False),
            ('ёж', 'е', False, False), ('é', 'e\u0301', False, False),
            ('абв', 'аб', True, False), ('абв', 'бв', False, True),
        ]:
            with self.subTest(text=text, needle=needle):
                self.assertIs(starts_with(text, needle), prefix)
                self.assertIs(ends_with(text, needle), suffix)

    def test_empty_search_is_an_error_even_with_empty_source(self):
        for function in (starts_with, ends_with):
            for text in ('', 'abc', '\0', '😀'):
                with self.subTest(function=function, text=text):
                    with self.assertRaisesRegex(ValueError, 'строка поиска не должна быть пустой'):
                        function(text, '')

    def test_shared_utf16_contract_not_separate_native_observations(self):
        for text, needle, prefix, suffix in [
            ('😀', '\ud83d', True, False), ('😀', '\ude00', False, True),
            ('😀', '\ud83d\ude00', True, True), ('\ud83d\ude00', '😀', True, True),
            ('\0a\0', '\0', True, True), ('a\0b', '\0', False, False),
            ('😀A', '😀', True, False), ('A😀', '😀', False, True),
            ('\ud83d', '😀', False, False), ('\ude00', '😀', False, False),
        ]:
            with self.subTest(text=repr(text), needle=repr(needle)):
                self.assertIs(starts_with(text, needle), prefix)
                self.assertIs(ends_with(text, needle), suffix)

    def test_shared_string_conversion_contract_not_native_observations(self):
        for value, prefix, suffix in [(Decimal('1234.5'), '1\u00a0', ',5'),
                                       (True, 'Д', 'а'), (False, 'Н', 'т'),
                                       (BSLArray(), 'Мас', 'сив')]:
            self.assertTrue(starts_with(value, prefix))
            self.assertTrue(ends_with(value, suffix))
        self.assertTrue(starts_with('123', Decimal(12)))
        self.assertTrue(ends_with('123', Decimal(23)))
        for function in (starts_with, ends_with):
            self.assertFalse(function(None, 'x'))
            with self.assertRaises(ValueError):
                function('x', None)

    def test_composition_and_existing_boolean_serialization(self):
        expressions = ['StrStartsWith("😀X", Left("😀", 1))',
                       'СтрЗаканчиваетсяНа("X😀", Right("😀", 1))',
                       'StrStartsWith(Char(0) + "X", Char(0))',
                       'СтрЗаканчиваетсяНа("X" + Char(0), Char(0))']
        for expression in expressions:
            self.assertEqual(self.vm.execute(f'ValueToStringInternal({expression})'), '{"B",1}')
            self.assertIs(self.vm.execute(f'ValueFromStringInternal(ValueToStringInternal({expression}))'), True)

    def test_arity_errors_and_recovery_preserve_assignment(self):
        for name in ('StrStartsWith', 'СтрНачинаетсяС', 'StrEndsWith', 'СтрЗаканчиваетсяНа'):
            for args in ('', '"a"', '"a", "a", "a"', '"a", ""', '"", ""'):
                expression = f'{name}({args})'
                with self.subTest(expression=expression):
                    self.vm.execute('saved = 7')
                    with self.assertRaises(BSLError):
                        self.vm.execute('saved = ' + expression, 'boundaries.bsl')
                    self.assertEqual(self.vm.execute('saved'), Decimal(7))
                    self.assertIs(self.vm.execute('caught = False; Try ' + expression +
                                                 '; Except caught = True; EndTry; caught'), True)
                    self.assertIs(self.vm.execute(f'{name}("x", "x")'), True)

    def test_long_search_and_repeated_prefix(self):
        for function in (starts_with, ends_with):
            self.assertFalse(function('a', 'a' * 100000))
            self.assertTrue(function('a' * 100000, 'a' * 99999))
            self.assertFalse(function('a' * 100000, 'a' * 99999 + 'b'))


if __name__ == '__main__':
    unittest.main()
