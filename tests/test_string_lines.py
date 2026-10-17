"""Native-observed line boundaries and separately labelled shared contracts."""
from decimal import Decimal
import unittest

from yadinassi import BSLError, Interpreter
from yadinassi.strings import line_count, get_line


class StringLineTests(unittest.TestCase):
    def setUp(self):
        self.vm = Interpreter(output=lambda message: None)

    def test_native_line_boundaries(self):
        cases = [('', ['']), ('A', ['A']), ('\n', ['']), ('\n\n', ['', '']),
                 ('A\nB', ['A', 'B']), ('\nA', ['', 'A']),
                 ('A\n\nB', ['A', '', 'B']), ('A\n', ['A']),
                 ('A\n\n', ['A', '']), ('A\r\nB\r\n', ['A', 'B']),
                 ('A\rB\r', ['A', 'B']), ('\r', ['']),
                 ('😀\nЯ\0', ['😀', 'Я\0']),
                 ('A\v\f\x85\u2028\u2029B', ['A\v\f\x85\u2028\u2029B'])]
        for text, lines in cases:
            with self.subTest(text=repr(text)):
                self.assertEqual(line_count(text), Decimal(len(lines)))
                self.assertIsInstance(line_count(text), Decimal)
                self.assertEqual([get_line(text, Decimal(i)) for i in range(1, 5)],
                                 (lines + [''] * 4)[:4])

    def test_native_index_and_conversion_observations(self):
        for index, expected in [(0, ''), (-1, ''), (Decimal('1.9'), 'A'),
                                (Decimal('0.9'), ''), (Decimal('9' * 38), ''), ('2', 'B')]:
            self.assertEqual(get_line('A\nB', index), expected)
        with self.assertRaises(ValueError):
            get_line('A\nB', None)
        for value, expected in [(Decimal(123), '123'), (None, '')]:
            self.assertEqual(line_count(value), Decimal(1))
            self.assertEqual(get_line(value, 1), expected)
            self.assertEqual(get_line(value, 2), '')

    def test_bilingual_case_insensitive_names_and_types(self):
        for name in ('СтрЧислоСтрок', 'sTrLiNeCoUnT', 'сТрЧиСлОсТрОк'):
            self.assertEqual(self.vm.execute(f'{name}("A" + Char(13) + "B")'), Decimal(2))
            self.assertTrue(self.vm.execute(f'(TypeOf({name}("")) = Type("Number"))'))
        for name in ('СтрПолучитьСтроку', 'sTrGeTlInE', 'сТрПоЛуЧиТьСтРоКу'):
            self.assertEqual(self.vm.execute(f'{name}("A" + Char(10) + "B", 2)'), 'B')
            self.assertTrue(self.vm.execute(f'(TypeOf({name}("", 1)) = Type("String"))'))

    def test_existing_internal_serialization(self):
        for expression in ('StrLineCount("A" + Char(13) + "B")',
                           'StrGetLine("A" + Char(10) + "😀", 2)'):
            self.assertEqual(self.vm.execute(expression), self.vm.execute(
                f'ValueFromStringInternal(ValueToStringInternal({expression}))'))

    def test_arity_errors_preserve_assignment_and_recover(self):
        for expression in ('StrLineCount()', 'СтрЧислоСтрок("A", 1)',
                           'StrGetLine()', 'СтрПолучитьСтроку("A")',
                           'StrGetLine("A", 1, 2)', 'StrGetLine("A", Undefined)'):
            with self.subTest(expression=expression):
                self.vm.execute('saved = "old"')
                with self.assertRaises(BSLError):
                    self.vm.execute('saved = ' + expression)
                self.assertEqual(self.vm.execute('saved'), 'old')
                self.assertTrue(self.vm.execute('caught = False; Try ' + expression +
                                                '; Except caught = True; EndTry; caught'))
                self.assertEqual(self.vm.execute('StrGetLine("new", 1)'), 'new')

    def test_mixed_separators_are_generalized_not_separate_native_evidence(self):
        self.assertEqual(line_count('A\r\n\rB\n\rC\n'), Decimal(5))
        self.assertEqual([get_line('A\r\n\rB\n\rC\n', i) for i in range(1, 7)],
                         ['A', '', 'B', '', 'C', ''])

    def test_shared_utf16_and_coercion_contracts_not_new_native_evidence(self):
        self.assertEqual(get_line('\ud83d\ude00\n\ud83d', 1), '😀')
        self.assertEqual(get_line('\ud83d\ude00\n\ud83d', 2), '\ud83d')
        self.assertEqual(get_line(True, True), 'Да')
        self.assertEqual(line_count(False), Decimal(1))

    def test_large_text_and_resource_safe_indices(self):
        text = ('A\r\n' * 100000) + 'end'
        self.assertEqual(line_count(text), Decimal(100001))
        self.assertEqual(get_line(text, 100001), 'end')
        self.assertEqual(get_line(text, Decimal('1e1000000')), '')
        self.assertEqual(get_line(text, Decimal('-1e1000000')), '')
        self.assertEqual(get_line(text, Decimal('1.999999999999999999999999999999')), 'A')
