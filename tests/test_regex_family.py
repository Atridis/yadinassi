"""Bounded regex subset: ordinary workflows, not invented native goldens."""
from decimal import Decimal
from types import SimpleNamespace
import unittest
from unittest import mock

from yadinassi import Interpreter
from yadinassi import regex_functions as api, regex_parser as limits
from yadinassi.regex_parser import Parser, Budget, RegexLimitError
from yadinassi.regex_vm import Program, run
from yadinassi.search_directions import BSLSearchDirection as Direction
from yadinassi.values import BSLType
from yadinassi import type_values, serialization


class RegexFamilyTests(unittest.TestCase):
    def output(self, source):
        out = []; Interpreter(out.append).execute(source); return out

    def test_four_global_functions_and_aliases(self):
        self.assertEqual(self.output('''
Сообщить(СтрПодобнаПоРегулярномуВыражению("abc123", "[a-z]+[0-9]+"));
R=StrFindByRegularExpression("abc123def", "([0-9]+)");
Message(R.Value); Message(R.StartIndex); Message(R.Length);
Message(StrFindAllByRegularExpression("a1b2", "[0-9]").Count());
Message(СтрЗаменитьПоРегулярномуВыражению("a1b2", "([0-9])", "<$1>"));
'''), ['Да', '123', '4', '3', '2', 'a<1>b<2>'])

    def test_no_match_and_empty_all(self):
        result = api.str_find('abc', '[0-9]+')
        self.assertEqual((result._value, result._position, result._length), ('', 0, 0))
        self.assertEqual(result.get_groups().items, [])
        self.assertEqual(api.str_find_all('abc', '[0-9]+').items, [])

    def test_capture_values_positions_and_array_independence(self):
        result = api.str_find('xxab12yy', '(ab)([0-9]+)')
        groups = result.get_groups()
        self.assertEqual([(g._value, g._position, g._length) for g in groups.items], [('ab', 3, 2), ('12', 5, 2)])
        groups.items.clear()
        self.assertEqual(len(result.get_groups().items), 2)
        missing = api.str_find('b', '(a)?b').get_groups().items[0]
        self.assertEqual((missing._value, missing._position, missing._length), ('', 0, 0))

    def test_results_readonly_and_type_guards(self):
        self.assertEqual(self.output('''R=StrFindByRegularExpression("a", "(a)");
G=R.GetGroups()[0];
Message(TypeOf(R)=Type("ResultOfSearchByRegularExpression"));
Message(TypeOf(G)=Type("ResultOfSearchByRegularExpressionGroup"));
Try R.Value="b"; Except Message("result-readonly"); EndTry;
Try G.Length=5; Except Message("group-readonly"); EndTry;
Try ValueToStringInternal(R); Except Message("codec-blocked"); EndTry;
Try New ResultOfSearchByRegularExpression; Except Message("not-constructible"); EndTry;'''),
                         ['Да', 'Да', 'result-readonly', 'group-readonly', 'codec-blocked', 'not-constructible'])

    def test_group_and_result_codec_reject_explicitly(self):
        r = api.str_find('a', '(a)')
        for value in (r, r.get_groups().items[0]):
            with self.assertRaises((ValueError, TypeError)): serialization.value_to_string_internal(value)

    def test_greedy_lazy_alternation_and_non_capture(self):
        for pattern, expected in [('a+', 'aaa'), ('a+?', 'a'), ('a|aa', 'a'), ('aa|a', 'aa'), ('(?:aa|a)+', 'aaa')]:
            self.assertEqual(api.str_find('aaa', pattern)._value, expected)
        self.assertEqual(api.str_find('aaa', '(a)+').get_groups().items[0]._position, 3)

    def test_repeat_ranges_and_escaped_literals(self):
        for pattern in ('a{2}', 'a{1,3}', 'a{1,}', r'\x61\u0061'):
            self.assertTrue(api.str_like('aa', pattern))
        self.assertTrue(api.str_like('a+b?', r'a\+b\?'))
        self.assertTrue(api.str_like('b', '[^a]'))
        self.assertTrue(api.str_like('-', '[-a]'))

    def test_flags_and_unicode_provisional_semantics(self):
        self.assertTrue(api.str_like('ЁЖ', 'ёж', True))
        self.assertFalse(api.str_like('ЁЖ', 'ёж'))
        self.assertEqual(api.str_find_all('a\nb', '^.', False, True).items[1]._value, 'b')
        r = api.str_find('😀abc', '(ab)')
        self.assertEqual((r._position, r._length), (3, 2))
        self.assertEqual(api.str_find('😀', '.')._length, 2)

    def test_direction_start_and_nth(self):
        self.assertEqual(api.str_find('a1b2c3', '[0-9]', start=Decimal(3))._value, '2')
        self.assertEqual(api.str_find('a1b2c3', '[0-9]', occurrence=Decimal(2))._value, '2')
        self.assertEqual(api.str_find('a1b2c3', '[0-9]', Direction.FROM_END)._value, '3')
        self.assertEqual(api.str_find('a1b2c3', '[0-9]', Direction.FROM_END, Decimal(4))._value, '2')
        self.assertEqual(api.str_find('a1b2c3', '[0-9]', Direction.FROM_END, occurrence=Decimal(2))._value, '2')

    def test_optional_holes_do_not_change_other_host_calls(self):
        self.assertEqual(self.output('Message(StrFindByRegularExpression("a1b2", "[0-9]", , , 2).Value);'), ['2'])
        self.assertEqual(self.output('Try StrLikeByRegularExpression(,"a"); Except Message("required"); EndTry;'), ['required'])
        self.assertEqual(self.output('Try StrLen(,); Except Message("other"); EndTry;'), ['other'])

    def test_zero_width_and_nullable_loops_terminate(self):
        self.assertEqual(api.str_find_all('ab', '').items, [])
        self.assertEqual(api.str_find_all('', '').items, [])
        self.assertEqual(api.str_replace('ab', '', '-'), '-a-b-')
        for pattern in ('(a?)*', '(?:)*', '(a*)*', '(a?)*?'):
            self.assertTrue(api.str_like('aa' if 'a' in pattern else '', pattern))
        self.assertTrue(api.str_like('aaaa', '(?:a?)*'))

    def test_replacement_groups_dollars_and_empty(self):
        self.assertEqual(api.str_replace('a1b2', '([a-z])([0-9])', '$2$1:$0;'), '1a:a1;2b:b2;')
        self.assertEqual(api.str_replace('a', '(a)', '$$-$1'), '$$-a')
        self.assertEqual(api.str_replace('b', '(a)?b', '$1x'), 'x')
        self.assertEqual(api.str_replace('abc', '[0-9]', 'x'), 'abc')
        with self.assertRaises(ValueError): api.str_replace('a', '(a)', '$2')

    def test_unsupported_extensions_reject_instead_of_reinterpretation(self):
        for pattern in (r'(a)\1', '(?=a)', '(?!a)', '(?<=a)', '(?P<n>a)', '(?<n>a)', '(?i)a', r'\p{L}', 'a++', '(?>a)', r'\Qabc\E', r'\k<n>'):
            with self.subTest(pattern=pattern), self.assertRaises(ValueError): api.str_find('a', pattern)

    def test_invalid_patterns_are_catchable(self):
        for pattern in ('(', '[', '\\', 'a{', 'a{3,2}', '*a', '[z-a]', 'a**', 'a{a}'):
            with self.subTest(pattern=pattern), self.assertRaises(ValueError): api.str_find('a', pattern)
        self.assertEqual(self.output('Try StrFindByRegularExpression("a", "("); Except Message("caught"); EndTry;'), ['caught'])

    def test_types_positions_and_arity(self):
        for call in (lambda: api.str_like(3, 'a'), lambda: api.str_like('a', 3),
                     lambda: api.str_find('a', 'a', 'FromBegin'), lambda: api.str_find('a', 'a', start=Decimal(0)),
                     lambda: api.str_find('a', 'a', occurrence=Decimal(0)),
                     lambda: api.str_find('a', 'a', start=Decimal('1e100000'))):
            with self.assertRaises((ValueError, TypeError)): call()
        with self.assertRaises(TypeError): api.str_like('a')

    def test_numeric_arguments_do_not_use_unbounded_shared_coercion(self):
        for value in ('1', '1'*10000, True, object()):
            with self.assertRaises(TypeError): api.str_find('a', 'a', start=value)
        for value in (Decimal('1e100000'), Decimal('1e-100000'), Decimal('NaN')):
            with self.assertRaises(ValueError): api.str_find('a', 'a', start=value)
        with self.assertRaises(RegexLimitError):
            api.str_find('a', 'a', start=Decimal('1.' + '0'*500))
        with mock.patch.object(limits, 'MAX_DECIMAL_BYTES', 0):
            with self.assertRaises(RegexLimitError): api.str_find('a', 'a', start=Decimal(1))
        with mock.patch.object(api.sys, 'implementation', SimpleNamespace(name='other')):
            with self.assertRaises(RegexLimitError): api.str_find('a', 'a', start=Decimal(1))
        self.assertEqual(api.str_find('ab', '.', start=Decimal('1.9'))._value, 'a')
        with self.assertRaises(TypeError): api.str_like('a', 'a', Decimal(1))

    def test_pattern_text_depth_group_and_repeat_bounds(self):
        for text, pattern in [('a', 'x'*(limits.MAX_PATTERN+1)), ('x'*(limits.MAX_TEXT+1), 'a'),
                              ('a', '('*(limits.MAX_DEPTH+1)+'a'+')'*(limits.MAX_DEPTH+1)),
                              ('a', '(a)'*(limits.MAX_GROUPS+1)), ('a', 'a{1025}')]:
            with self.assertRaises(RegexLimitError): api.str_find(text, pattern)

    def test_compilation_budget_before_growth(self):
        with mock.patch.object(limits, 'MAX_CODE', 8):
            with self.assertRaises(RegexLimitError): api.str_find('abc', '(abc){3}')
        with mock.patch.object(limits, 'MAX_LOOPS', 1):
            with self.assertRaises(RegexLimitError): api.str_find('a', 'a*b*')

    def test_global_work_budget_not_reset_per_match(self):
        op = api.Operation('aaaa', 'a', False, False)
        before = op.budget.remaining
        iterator = op.matches(); next(iterator); after = op.budget.remaining
        next(iterator); self.assertLess(op.budget.remaining, after); self.assertLess(after, before)
        op.budget.remaining = 1
        with self.assertRaises(RegexLimitError): next(iterator)
        with mock.patch.object(limits, 'MAX_WORK', 5):
            with self.assertRaises(RegexLimitError): api.str_find_all('aaaa', 'a')

    def test_result_and_output_and_stack_limits(self):
        with mock.patch.object(limits, 'MAX_MATCHES', 2):
            with self.assertRaises(RegexLimitError): api.str_find_all('aaa', 'a')
        with mock.patch.object(limits, 'MAX_OBJECTS', 2):
            with self.assertRaises(RegexLimitError): api.str_find_all('aa', '(a)')
            with self.assertRaises(RegexLimitError): api.str_replace('aa', 'a', '$0$0')
        with mock.patch.object(limits, 'MAX_OUTPUT', 4):
            with self.assertRaises(RegexLimitError): api.str_replace('aa', 'a', 'xxx')
        with mock.patch.object(limits, 'MAX_STATES', 1):
            with self.assertRaises(RegexLimitError): api.str_like('aaaa', 'a*')

    def test_limits_raise_catchable_error_not_partial_array(self):
        with mock.patch.object(limits, 'MAX_MATCHES', 2):
            self.assertEqual(self.output('R="unchanged";Try R=StrFindAllByRegularExpression("aaa","a");Except Message("limited");EndTry;Message(R);'), ['limited','unchanged'])


if __name__ == '__main__': unittest.main()
