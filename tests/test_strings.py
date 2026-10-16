"""Independent examples for the documented string builtin contract.

These are interpreter unit tests, not output captured on a native 1C platform.
"""

from decimal import Decimal
from pathlib import Path
import tempfile
import subprocess
import sys
import unittest

from yadinassi import BSLError, Interpreter
from yadinassi.values import BSLArray


class StringTests(unittest.TestCase):
    def setUp(self):
        self.output = []
        self.vm = Interpreter(output=self.output.append)

    def evaluate(self, expression):
        return self.vm.execute(expression, 'strings.bsl')

    def assert_cases(self, cases):
        for expression, expected in cases:
            with self.subTest(expression=expression):
                result = self.evaluate(expression)
                self.assertIs(type(result), type(expected))
                self.assertEqual(result, expected)

    def test_bilingual_aliases_and_case_insensitive_names(self):
        cases = [
            ('сТрДлИнА("Ёж")', Decimal(2)), ('STRLEN("Ёж")', Decimal(2)),
            ('Лев("абв", 2)', 'аб'), ('LEFT("абв", 2)', 'аб'),
            ('Прав("абв", 2)', 'бв'), ('RIGHT("абв", 2)', 'бв'),
            ('Сред("абв", 2)', 'бв'), ('MID("абв", 2)', 'бв'),
            ('Найти("абв", "б")', Decimal(2)), ('FIND("абв", "б")', Decimal(2)),
            ('СтрЗаменить("абв", "б", "!")', 'а!в'),
            ('STRREPLACE("абв", "б", "!")', 'а!в'),
            ('СокрЛ(" аб ")', 'аб '), ('TRIML(" аб ")', 'аб '),
            ('СокрП(" аб ")', ' аб'), ('TRIMR(" аб ")', ' аб'),
            ('СокрЛП(" аб ")', 'аб'), ('TRIMALL(" аб ")', 'аб'),
            ('ПустаяСтрока(" ")', True), ('ISBLANKSTRING(" ")', True),
            ('ВРег("ёж abc")', 'ЁЖ ABC'), ('UPPER("ёж abc")', 'ЁЖ ABC'),
            ('НРег("ЁЖ ABC")', 'ёж abc'), ('LOWER("ЁЖ ABC")', 'ёж abc'),
            ('СтрСоединить(СтрРазделить("а,б", ","), ":")', 'а:б'),
            ('STRCONCAT(STRSPLIT("а,б", ","), ":")', 'а:б'),
        ]
        self.assert_cases(cases)

    def test_left_and_right_lengths(self):
        self.assert_cases([
            ('Left("abc", 0)', ''), ('Right("abc", 0)', ''),
            ('Left("abc", -2)', ''), ('Right("abc", -2)', ''),
            ('Left("abc", 1)', 'a'), ('Right("abc", 1)', 'c'),
            ('Left("abc", 3)', 'abc'), ('Right("abc", 3)', 'abc'),
            ('Left("abc", 99)', 'abc'), ('Right("abc", 99)', 'abc'),
            ('Left("", 2)', ''), ('Right("", 2)', ''),
            ('Right("abc", 99999999999999999999999999999999999999)', 'abc'),
        ])

    def test_mid_one_based_start_and_optional_length(self):
        self.assert_cases([
            ('Mid("abcdef", 2, 3)', 'bcd'), ('Mid("abcdef", 2)', 'bcdef'),
            ('Mid("abcdef", 0, 2)', 'ab'), ('Mid("abcdef", -4, 2)', 'ab'),
            ('Mid("abcdef", 0)', 'abcdef'), ('Mid("abcdef", -4)', 'abcdef'),
            ('Mid("abcdef", 6)', 'f'), ('Mid("abcdef", 7)', ''),
            ('Mid("abcdef", 99, 2)', ''), ('Mid("", 1)', ''),
            ('Mid("abcdef", 2, 0)', ''), ('Mid("abcdef", 2, -1)', 'bcdef'),
            ('Mid("abcdef", 2, -5)', 'bcdef'), ('Mid("abcdef", 5, 99)', 'ef'),
        ])

    def test_numeric_arguments_convert_without_binary_float(self):
        self.assert_cases([
            ('Left("abcd", 2.99)', 'ab'), ('Right("abcd", 2.99)', 'cd'),
            ('Mid("abcd", 2.99, 1.99)', 'b'), ('Left("abcd", -0.99)', ''),
            ('Mid("abcd", -0.99, 2)', 'ab'), ('Left("abcd", "2.9")', 'ab'),
            ('Right("abcd", True)', 'd'), ('Right("abcd", False)', ''),
        ])

    def test_enormous_numeric_positions_are_clamped_before_integer_conversion(self):
        code = ('Message(Left("abc", "1e1000000")); '
                'Message(Right("abc", "1e1000000")); '
                'Message(Mid("abc", "1e1000000")); '
                'Message(Mid("abc", 2, "1e1000000")); '
                'Message(Left("abc", "-1e1000000")); '
                'Message(Mid("abc", "-1e1000000", "-1e1000000"));')
        result = subprocess.run([sys.executable, '-m', 'yadinassi', '-c', code],
                                capture_output=True, text=True, encoding='utf-8',
                                cwd=Path(__file__).resolve().parents[1], timeout=5)
        self.assertEqual((result.returncode, result.stdout, result.stderr),
                         (0, 'abc\nabc\n\nbc\n\nabc\n', ''))

    def test_find_is_case_sensitive_one_based_and_returns_decimal(self):
        self.assert_cases([
            ('Find("абаба", "ба")', Decimal(2)), ('Find("abc", "X")', Decimal(0)),
            ('Find("Abc", "a")', Decimal(0)), ('Find("a", "abc")', Decimal(0)),
            ('Find("", "a")', Decimal(0)), ('Find("abc", "")', Decimal(1)),
            ('Find("", "")', Decimal(1)),
        ])

    def test_replace_is_literal_nonoverlapping_and_does_not_rescan(self):
        self.assert_cases([
            ('StrReplace("aaaaa", "aa", "x")', 'xxa'),
            ('StrReplace("aba", "a", "aa")', 'aabaa'),
            ('StrReplace("abc", "", "x")', 'abc'),
            ('StrReplace("a.b.a", ".", "$")', 'a$b$a'),
            ('StrReplace("aAa", "a", "")', 'A'),
            ('StrReplace("abc", "z", "x")', 'abc'),
            ('StrReplace("", "a", "x")', ''),
        ])

    def test_whitespace_trim_preserves_internal_characters(self):
        text = '\t\r\n\u00a0 A\t B \u00a0\r\n\t'
        self.vm.variables['text'] = text
        self.assertEqual(self.evaluate('TrimL(text)'), 'A\t B \u00a0\r\n\t')
        self.assertEqual(self.evaluate('TrimR(text)'), '\t\r\n\u00a0 A\t B')
        self.assertEqual(self.evaluate('TrimAll(text)'), 'A\t B')
        self.assertEqual(self.vm.variables['text'], text)

    def test_declared_unicode_whitespace_set_and_nonwhitespace(self):
        for character in ' \t\n\v\f\r\u0085\u00a0\u1680\u2000\u2001\u2002\u2003\u2004\u2005\u2006\u2007\u2008\u2009\u200a\u2028\u2029\u202f\u205f\u3000':
            with self.subTest(code=hex(ord(character))):
                self.vm.variables['space'] = character
                self.assertEqual(self.evaluate('TrimAll(space)'), '')
                self.assertIs(self.evaluate('IsBlankString(space)'), True)
        for character in '\x00\x1c\x1d\x1e\x1f\u200b\ufeff':
            with self.subTest(code=hex(ord(character))):
                self.vm.variables['space'] = character
                self.assertEqual(self.evaluate('TrimAll(space)'), character)
                self.assertIs(self.evaluate('IsBlankString(space)'), False)

    def test_empty_trim_and_blank(self):
        self.assert_cases([
            ('TrimL("")', ''), ('TrimR("")', ''), ('TrimAll("")', ''),
            ('IsBlankString("")', True), ('IsBlankString(" a ")', False),
            ('IsBlankString("0")', False), ('TrimAll(" a b ")', 'a b'),
        ])

    def test_upper_and_lower_preserve_numbers_punctuation_and_spaces(self):
        self.assert_cases([
            ('Upper("ёж ёлка, abc-123!")', 'ЁЖ ЁЛКА, ABC-123!'),
            ('Lower("ЁЖ ЁЛКА, ABC-123!")', 'ёж ёлка, abc-123!'),
            ('Upper("")', ''), ('Lower("")', ''),
            ('Upper("中文🙂")', '中文🙂'), ('Lower("中文🙂")', '中文🙂'),
        ])

    def test_string_arguments_use_current_string_presentation(self):
        self.assert_cases([
            ('StrLen(123)', Decimal(3)), ('StrLen(Undefined)', Decimal(0)),
            ('Left(1234, 2)', '12'), ('Right(True, 1)', 'а'),
            ('Mid(1234, 2, 2)', '23'), ('Find(1234, 23)', Decimal(2)),
            ('StrReplace(1212, 12, False)', 'НетНет'), ('TrimAll(12.50)', '12.5'),
            ('TrimL(True)', 'Да'), ('TrimR(False)', 'Нет'),
            ('IsBlankString(Undefined)', True), ('Upper(Undefined)', ''),
            ('Lower(True)', 'да'), ('StrConcat(StrSplit(1203, 0), 9)', '1293'),
        ])

    def test_split_delimiters_are_individual_characters(self):
        result = self.evaluate('StrSplit("red,green;blue|white", ",;|")')
        self.assertIsInstance(result, BSLArray)
        self.assertEqual(result.items, ['red', 'green', 'blue', 'white'])
        self.assertEqual(self.evaluate('StrSplit("a::b", "::")').items, ['a', '', 'b'])
        self.assertEqual(self.evaluate('StrSplit("a.*b", ".*")').items, ['a', '', 'b'])

    def test_split_defaults_leading_trailing_and_adjacent_delimiters(self):
        self.assertEqual(self.evaluate('StrSplit(",a,,b,", ",")').items,
                         ['', 'a', '', 'b', ''])
        self.assertEqual(self.evaluate('StrSplit(",a,,b,", ",", False)').items, ['a', 'b'])
        self.assertEqual(self.evaluate('StrSplit(" a  b ", " ", 0)').items, ['a', 'b'])
        self.assertEqual(self.evaluate('StrSplit(" a  b ", " ", 1)').items,
                         ['', 'a', '', 'b', ''])
        # Removing empty fields is not trimming nonempty fields.
        self.assertEqual(self.evaluate('StrSplit("a, ,b", ",", False)').items, ['a', ' ', 'b'])

    def test_split_empty_input_and_empty_delimiters(self):
        cases = [('StrSplit("", ",")', ['']), ('StrSplit("", ",", False)', []),
                 ('StrSplit("a b,c", "")', ['a b,c']), ('StrSplit("", "")', ['']),
                 ('StrSplit("", "", False)', []), ('StrSplit(",,", ",")', ['', '', '']),
                 ('StrSplit(",,", ",", False)', [])]
        for expression, expected in cases:
            with self.subTest(expression=expression):
                self.assertEqual(self.evaluate(expression).items, expected)

    def test_split_returns_independent_mutable_arrays(self):
        self.vm.execute('a = StrSplit("x,y", ","); b = StrSplit("x,y", ","); '
                        'a[0] = "changed"; a.Add("z");')
        self.assertEqual(self.evaluate('StrConcat(a, ":")'), 'changed:y:z')
        self.assertEqual(self.evaluate('StrConcat(b, ":")'), 'x:y')

    def test_join_default_literal_separator_and_empty_elements(self):
        self.assert_cases([
            ('StrConcat(New Array)', ''), ('StrConcat(New Array, "x")', ''),
            ('StrConcat(StrSplit("a,b", ","))', 'ab'),
            ('StrConcat(StrSplit(",a,,b,", ","), "<>")', '<>a<><>b<>'),
            ('StrConcat(StrSplit("solo", ","), "ignored")', 'solo'),
        ])

    def test_join_converts_array_elements_and_does_not_mutate(self):
        self.vm.execute('a = New Array; a.Add(12.50); a.Add(True); '
                        'a.Add(Undefined); a.Add("x"); a.Add(New Array);')
        items = list(self.vm.variables['a'].items)
        self.assertEqual(self.evaluate('StrConcat(a, "|")'), '12.5|Да||x|Массив')
        self.assertEqual(self.vm.variables['a'].items, items)

    def test_utf16_length_slices_find_and_reassembly(self):
        self.assert_cases([
            ('StrLen("A🙂B")', Decimal(4)), ('Left("A🙂B", 3)', 'A🙂'),
            ('Right("A🙂B", 3)', '🙂B'), ('Mid("A🙂B", 2, 2)', '🙂'),
            ('Mid("A🙂B", 4)', 'B'), ('Find("A🙂B", "B")', Decimal(4)),
            ('Find("A🙂B", "🙂")', Decimal(2)),
            ('Left("🙂", 1) + Right("🙂", 1)', '🙂'),
            ('StrLen(Left("🙂", 1))', Decimal(1)),
            ('StrLen(Right("🙂", 1))', Decimal(1)),
            ('StrReplace("A🙂B🙂", "🙂", "!")', 'A!B!'),
        ])
        self.assertEqual(self.evaluate('Left("🙂", 1)'), '\ud83d')
        self.assertEqual(self.evaluate('Right("🙂", 1)'), '\ude42')
        self.assertEqual(self.evaluate('Mid("A🙂B", 3, 1)'), '\ude42')

    def test_utf16_search_never_matches_unaligned_bytes(self):
        # UTF-16 LE for U+0100,U+0200 is 00 01 00 02. The bytes 01 00
        # (U+0001) exist only at an odd offset and must not count as a match.
        self.vm.variables['needle'] = '\x01'
        self.assertEqual(self.evaluate('Find("ĀȀ", needle)'), Decimal(0))
        self.assertEqual(self.evaluate('StrReplace("ĀȀ", needle, "x")'), 'ĀȀ')

    def test_utf16_split_and_join_preserve_code_unit_contract(self):
        self.assertEqual(self.evaluate('StrSplit("🙂,a", ",")').items, ['🙂', 'a'])
        # Each UTF-16 unit in the separator is independently a delimiter.
        self.assertEqual(self.evaluate('StrSplit("A🙂B", "🙂")').items, ['A', '', 'B'])
        self.vm.execute('a = New Array; a.Add(Left("🙂", 1)); a.Add(Right("🙂", 1));')
        self.assertEqual(self.evaluate('StrConcat(a)'), '🙂')
        self.assertEqual(self.evaluate('StrReplace("🙂", Left("🙂", 1), "")'), '\ude42')

    def test_combining_marks_are_not_grapheme_clusters(self):
        self.assert_cases([
            ('StrLen("é")', Decimal(2)), ('Left("é", 1)', 'e'),
            ('Right("é", 1)', '́'), ('Find("é", "é")', Decimal(0)),
        ])

    def test_bad_numeric_or_boolean_arguments_raise_catchable_bsl_errors(self):
        for expression in ['Left("x", Undefined)', 'Right("x", New Array)',
                           'Mid("x", "bad")', 'Mid("x", 1, Undefined)',
                           'StrSplit("x", ",", Undefined)', 'StrSplit("x", ",", "yes")',
                           'StrConcat("x")', 'StrConcat(Undefined)']:
            with self.subTest(expression=expression):
                with self.assertRaises(BSLError) as caught:
                    self.evaluate('\n  ' + expression)
                self.assertEqual((caught.exception.source, caught.exception.line,
                                  caught.exception.column), ('strings.bsl', 2, 3))
                self.vm.execute('Try ' + expression + '; Except Message("caught"); EndTry;')
                self.assertEqual(self.output.pop(), 'caught')

    def test_arity_errors_and_omitted_positions_remain_bsl_errors(self):
        for expression in ['StrLen()', 'Left("x")', 'Right("x", 1, 2)', 'Mid("x")',
                           'Mid("x", 1, 2, 3)', 'Find("x")', 'StrReplace("x", "a")',
                           'TrimL()', 'TrimR("x", 1)', 'TrimAll()', 'IsBlankString()',
                           'Upper()', 'Lower("x", 1)', 'StrSplit("x")',
                           'StrSplit("x", ",", True, 1)', 'StrConcat()',
                           'StrConcat(New Array, ",", 1)', 'Mid("x",,1)']:
            with self.subTest(expression=expression), self.assertRaises(BSLError):
                self.evaluate(expression)

    def test_arguments_evaluated_once_left_to_right(self):
        self.vm.execute('''
            Var n; n = 0;
            Function Next() n = n + 1; Return n; EndFunction
            Message(StrReplace(Next(), Next(), Next()));
            Message(n);
        ''')
        self.assertEqual(self.output, ['1', '3'])

    def test_string_pipeline_in_an_imported_exported_routine(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            (path / 'Names.bsl').write_text('''
                Function Normalize(Val source) Export
                    parts = StrSplit(source, ",;", False);
                    result = New Array;
                    For Each part In parts Do
                        cleaned = TrimAll(part);
                        If Not IsBlankString(cleaned) Then result.Add(Upper(cleaned)); EndIf;
                    EndDo;
                    Return StrConcat(result, " / ");
                EndFunction
            ''', encoding='utf-8')
            self.vm.execute('// #Импорт Names.bsl\n'
                            'Сообщить(Names.Normalize(" ёж,; бор, ; лес "));',
                            str(path / 'main.bsl'))
        self.assertEqual(self.output, ['ЁЖ / БОР / ЛЕС'])


if __name__ == '__main__':
    unittest.main()
