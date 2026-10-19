"""Observed extended search and independent nonempty-needle algorithm checks."""
from decimal import Decimal, localcontext
import itertools
import unittest

from yadinassi import BSLError, Interpreter
from yadinassi.search_directions import BSLSearchDirection as Direction
from yadinassi.strings import str_find

BEGIN = Direction.FROM_BEGIN
END = Direction.FROM_END


class ExtendedStrFindTests(unittest.TestCase):
    def test_owner_nonempty_search_observations(self):
        cases = [
            ('abcabc', 'bc', BEGIN, 1, 1, 2),
            ('abcabc', 'bc', END, 6, 1, 5),
            ('abcabc', 'bc', BEGIN, 3, 1, 5),
            ('abcabc', 'bc', END, 5, 1, 5),
            ('abcabc', 'bc', END, 4, 1, 2),
            ('abcabcabc', 'bc', BEGIN, 3, 2, 8),
            ('abcabcabc', 'bc', END, 6, 2, 2),
            ('aaaa', 'aa', BEGIN, 1, 2, 3),
            ('aaaa', 'aa', END, 4, 2, 1),
            ('abcabc', 'bc', BEGIN, 1, 3, 0),
            ('Я😀Я😀', '😀', END, 6, 1, 5),
        ]
        for text, needle, direction, start, occurrence, expected in cases:
            with self.subTest(case=(text, needle, direction, start, occurrence)):
                actual = str_find(text, needle, direction, Decimal(start), Decimal(occurrence))
                self.assertIs(type(actual), Decimal)
                self.assertEqual(actual, expected)

    def test_owner_empty_needle_orthogonal_observations(self):
        for direction in (BEGIN, END):
            for start, count, expected in [(2, 2, 2), (3, 1, 1),
                                           (1, 3, 1), (3, 2, 3)]:
                self.assertEqual(str_find('abc', '', direction,
                                          Decimal(start), Decimal(count)), expected)
            self.assertEqual(str_find('abc', '', direction), 1)
            self.assertEqual(str_find('', '', direction, Decimal(1), Decimal(2)), 1)

    def test_inferred_zero_width_recurrence_is_bounded(self):
        # Regression for the inferred recurrence, not additional native evidence.
        for direction in (BEGIN, END):
            for count in (Decimal(3), Decimal(100), Decimal('1e99999999')):
                self.assertEqual(str_find('abc', '', direction, Decimal(3), count), 3)
            self.assertEqual(str_find('', '', direction, Decimal(1), Decimal('1e99999999')), 1)
            for start in (Decimal(0), Decimal(2)):
                with self.assertRaises(ValueError):
                    str_find('', '', direction, start, Decimal(2))
        self.assertEqual(str_find('abc', '', END, None, Decimal(2)), 3)
        self.assertEqual(str_find('abc', '', BEGIN, Decimal('2.9'), Decimal('2.9')), 2)

    def test_nonempty_algorithm_against_enumerated_positions(self):
        # Enumerate all match-start positions by slices, then greedily take
        # disjoint matches. This oracle uses neither find nor rfind.
        for length in range(1, 6):
            for letters in itertools.product('ab', repeat=length):
                text = ''.join(letters)
                for needle in ('a', 'b', 'aa', 'ab', 'ba', 'bb', 'aba'):
                    candidates = [i + 1 for i in range(length)
                                  if text[i:i + len(needle)] == needle]
                    for direction in (BEGIN, END):
                        for start in range(1, length + 1):
                            positions = []
                            available = (candidates if direction is BEGIN else reversed(candidates))
                            for position in available:
                                if direction is BEGIN:
                                    fits = position >= start and (not positions or position >= positions[-1] + len(needle))
                                else:
                                    fits = position <= start and (not positions or position + len(needle) <= positions[-1])
                                if fits:
                                    positions.append(position)
                            for occurrence in range(1, 4):
                                expected = positions[occurrence - 1] if occurrence <= len(positions) else 0
                                self.assertEqual(str_find(text, needle, direction, Decimal(start), Decimal(occurrence)), expected,
                                                 (text, needle, direction, start, occurrence))

    def test_utf16_search_start_and_surrogate_halves(self):
        text = 'Я😀Я😀'
        self.assertEqual(str_find(text, '😀', END), 5)
        self.assertEqual(str_find(text, '😀', END, Decimal(5)), 5)
        self.assertEqual(str_find(text, '\ude00', END), 6)
        self.assertEqual(str_find(text, '\ud83d', BEGIN, Decimal(3)), 5)
        self.assertEqual(str_find(text, 'Я', BEGIN, Decimal(2)), 4)
        self.assertEqual(str_find('a\0b\0', '\0', END), 4)
        self.assertEqual(str_find('é', 'e\u0301', BEGIN), 0)

    def test_observed_argument_conversion_and_defaults(self):
        self.assertEqual(str_find('abc', 'a', BEGIN, Decimal('1.9')), 1)
        self.assertEqual(str_find('abcabc', 'b', BEGIN, Decimal(1), Decimal('1.9')), 2)
        self.assertEqual(str_find('abc', 'b', BEGIN, '2'), 2)
        self.assertEqual(str_find('abcabc', 'b', BEGIN, Decimal(1), '2'), 5)
        self.assertEqual(str_find(Decimal(121), '1', END), 3)
        self.assertEqual(str_find('abc', 'b', END, None), 2)
        self.assertEqual(str_find('abc', 'b', BEGIN, Decimal(1), Decimal(-1)), 0)
        self.assertEqual(str_find('', 'a', END), 0)

    def test_invalid_direction_and_explicit_undefined_occurrence(self):
        from yadinassi.round_modes import BSLRoundMode
        for direction in (None, Decimal(0), False, 'FromBegin', BSLRoundMode.ROUND15_AS10, object()):
            with self.subTest(direction=direction), self.assertRaises(TypeError):
                str_find('abc', 'b', direction)
        with self.assertRaises(ValueError):
            str_find('abc', 'b', BEGIN, Decimal(1), None)

    def test_position_validation_precedes_early_result(self):
        for start in (Decimal(0), Decimal(-1), Decimal(4), Decimal('1e99999999')):
            for needle in ('', 'b', 'longer than source'):
                for occurrence in (Decimal(-1), Decimal(1)):
                    with self.subTest(start=start, needle=needle), self.assertRaises(ValueError):
                        str_find('abc', needle, BEGIN, start, occurrence)
        for occurrence in (Decimal(0), Decimal('0.9'), Decimal('-0.9')):
            with self.assertRaises(ValueError):
                str_find('abc', 'b', BEGIN, Decimal(1), occurrence)

    def test_huge_occurrence_is_bounded_by_input_not_requested_number(self):
        for direction in (BEGIN, END):
            self.assertEqual(str_find('a' * 10000, 'aa', direction, None, Decimal('1e99999999')), 0)
            self.assertEqual(str_find('a', 'a', direction, None, Decimal('-1e99999999')), 0)
        self.assertEqual(str_find('aa' * 2000, 'aa', BEGIN, Decimal(1), Decimal(2000)), 3999)
        self.assertEqual(str_find('aa' * 2000, 'aa', END, None, Decimal(2000)), 1)

    def test_decimal_context_is_unchanged(self):
        with localcontext() as context:
            context.prec = 1
            for signal in context.traps:
                context.traps[signal] = True
            context.clear_flags()
            for direction in (BEGIN, END):
                self.assertEqual(str_find('aaaa', 'aa', direction, None, Decimal('1.9')), 1 if direction is BEGIN else 3)
                self.assertEqual(str_find('aaaa', 'aa', direction, None, Decimal('1e99999999')), 0)
            self.assertFalse(any(context.flags.values()))

    def test_nonfinite_numeric_arguments_are_rejected(self):
        for value in ('NaN', 'sNaN', 'Infinity', '-Infinity'):
            for index in (3, 4):
                arguments = ['abc', 'b', BEGIN, Decimal(1), Decimal(1)]
                arguments[index] = Decimal(value)
                with self.subTest(value=value, index=index), self.assertRaises(ValueError):
                    str_find(*arguments)


class ExtendedStrFindRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.vm = Interpreter()

    def test_bilingual_aliases_and_optional_holes(self):
        for name in ('СтрНайти', 'StrFind', 'сТрНаЙтИ', 'sTrFiNd'):
            self.assertEqual(self.vm.execute(f'{name}("abcabc", "b", , 3)'), 5)
            self.assertEqual(self.vm.execute(f'{name}("abcabc", "b", SearchDirection.FromEnd, , 2)'), 2)
            self.assertEqual(self.vm.execute(f'{name}("abcabc", "b", , , 2)'), 5)
        self.assertEqual(self.vm.execute('СтрНайти("abcabc", "b", НаправлениеПоиска.СКонца)'), 5)

    def test_omitted_slots_are_not_explicit_undefined(self):
        for code in ('StrFind("abc", "b", Undefined)',
                     'StrFind("abc", "b", , 1, Undefined)'):
            with self.assertRaises(BSLError):
                self.vm.execute(code)
        self.assertEqual(self.vm.execute('StrFind("abc", "b", SearchDirection.FromEnd, Undefined)'), 2)

    def test_required_holes_reject_before_argument_side_effects(self):
        self.vm.execute('Function Side() calls = calls + 1; Return "b"; EndFunction Var calls; calls = 0;')
        for code in ('StrFind(, Side())', 'StrFind(Side(),, SearchDirection.FromEnd)'):
            with self.assertRaises(BSLError):
                self.vm.execute(code)
            self.assertEqual(self.vm.variables['calls'], 0)

    def test_other_builtins_and_methods_still_reject_holes(self):
        self.vm.execute('array = New Array;')
        for code in ('Find("abc", "b", , 1)', 'Mid("abc", , 1)',
                     'Round(1, , 0)', 'array.Get(, 1)'):
            with self.assertRaises(BSLError):
                self.vm.execute(code)

    def test_override_and_shadow_cannot_inherit_special_omission_policy(self):
        calls = []
        self.vm.register_function('StrFind', lambda *args: calls.append(args))
        with self.assertRaises(BSLError):
            self.vm.execute('StrFind("abc", "b", , 1)')
        self.assertEqual(calls, [])
        self.assertEqual(self.vm.execute('СтрНайти("abcabc", "b", , 3)'), 5)
        fresh = Interpreter()
        fresh.execute('StrFind = Find;')
        with self.assertRaises(BSLError):
            fresh.execute('StrFind("abc", "b", , 1)')
        fresh = Interpreter()
        fresh.execute('Function StrFind(a, b, c = 9, d = 7) Return c + d; EndFunction')
        self.assertEqual(fresh.execute('StrFind("abc", "b", , 1)'), 10)

    def test_evaluation_order_and_single_argument_evaluation(self):
        self.vm.execute('''Function Side(Val mark, Val value)
          calls = calls + mark; Return value; EndFunction Var calls; calls = "";
          found = StrFind(Side("a", "abcabc"), Side("b", "bc"), , Side("c", 3), Side("d", 1));''')
        self.assertEqual(self.vm.variables['calls'], 'abcd')
        self.assertEqual(self.vm.variables['found'], 5)

    def test_errors_are_atomic_and_recovery_eval_execute_work(self):
        self.vm.execute('''saved = 7;
          Try saved = StrFind("abc", "b", SearchDirection.FromEnd, 4); Except caught = True; EndTry;
          found = 0; Execute("found = StrFind(""abcabc"", ""b"", , 3);");''')
        self.assertEqual(self.vm.variables['saved'], 7)
        self.assertIs(self.vm.variables['caught'], True)
        self.assertEqual(self.vm.variables['found'], 5)
        self.assertEqual(self.vm.execute('Eval("StrFind(""abcabc"", ""b"", SearchDirection.FromEnd, , 2)")'), 2)

    def test_result_type_and_bidirectional_serialization(self):
        self.assertEqual(self.vm.execute('ValueToStringInternal(StrFind("abcabc", "b", , 3))'), '{"N",5}')
        self.assertEqual(self.vm.execute('ValueFromStringInternal(ValueToStringInternal(StrFind("abcabc", "b", , 3)))'), 5)
        self.assertEqual(self.vm.execute('(TypeOf(StrFind("abcabc", "b", , 3)) = Type("Number"))'), True)

    def test_invalid_arities(self):
        for code in ('StrFind()', 'StrFind("a")', 'StrFind("abc", "b", , 1, 1, 1)'):
            with self.assertRaises(BSLError):
                self.vm.execute(code)


if __name__ == '__main__':
    unittest.main()
