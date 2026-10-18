"""Documented default StrFind, not a claim of optional-direction parity."""
from decimal import Decimal
import unittest

from yadinassi import Interpreter, BSLError


class StrFindTests(unittest.TestCase):
    def test_aliases_and_documented_search_contract(self):
        vm = Interpreter()
        for name in ('СтрНайти', 'StrFind', 'сТрНаЙтИ', 'sTrFiNd'):
            for text, needle, expected in [('ababa', 'ba', 2), ('abc', 'c', 3),
                                           ('abc', 'x', 0), ('ABC', 'b', 0),
                                           ('abc', '', 1), ('', '', 1), ('', 'a', 0)]:
                with self.subTest(name=name, text=text, needle=needle):
                    value = vm.execute(f'{name}("{text}", "{needle}")')
                    self.assertIs(type(value), Decimal)
                    self.assertEqual(value, Decimal(expected))

    def test_existing_find_utf16_and_conversion_contract(self):
        # Shared local behavior, not additional native observations for StrFind.
        vm = Interpreter()
        for text, needle in [('Я😀ёж', 'ёж'), ('😀', '\ude00'),
                             ('\ud83d\ude00', '😀'), ('a\0b', '\0'),
                             ('é', 'e\u0301'), (Decimal(123), '2'),
                             (True, 'а'), (None, ''), ('abc', None),
                             ('a' * 100000 + 'b', 'b')]:
            vm.variables.update(haystack=text, needle=needle)
            self.assertEqual(vm.execute('StrFind(haystack, needle)'),
                             vm.execute('Find(haystack, needle)'))
        self.assertEqual(vm.execute('СтрНайти("Я😀ёж", "ёж")'), Decimal(4))

    def test_serialization_both_directions(self):
        vm = Interpreter()
        self.assertEqual(vm.execute('ValueToStringInternal(StrFind("abc", "b"))'), '{"N",2}')
        self.assertEqual(vm.execute('ValueFromStringInternal(ValueToStringInternal(StrFind("abc", "b")))'), Decimal(2))

    def test_arity_unsupported_options_and_recovery(self):
        vm = Interpreter()
        for expression in ('StrFind()', 'StrFind("a")',
                           'СтрНайти("abc", "b", Undefined)',
                           'StrFind("abc", "b", Undefined, 1, 1)',
                           'StrFind("abc", "b", , 1)'):
            with self.subTest(expression=expression):
                vm.execute('saved = 7;')
                with self.assertRaises(BSLError):
                    vm.execute('saved = ' + expression)
                self.assertEqual(vm.execute('saved'), Decimal(7))
                vm.execute(f'Try {expression}; Except saved = StrFind("abc", "b"); EndTry;')
                self.assertEqual(vm.execute('saved'), Decimal(2))
