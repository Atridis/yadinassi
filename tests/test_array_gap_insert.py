"""Array.Insert extension documented by EDT Insert771 and Array example."""
from decimal import Decimal, localcontext, Inexact
import unittest
from unittest.mock import patch

from yadinassi import Interpreter, BSLError
from yadinassi.values import BSLArray
from yadinassi.serialization import value_to_string_internal, value_from_string_internal


class ArrayGapInsertTests(unittest.TestCase):
    def setUp(self):
        self.vm = Interpreter(output=lambda message: None)

    def test_aliases_empty_and_nonempty_gap(self):
        for method in ('Insert', 'Вставить', 'iNsErT', 'вСтАвИтЬ'):
            for initial in ('', 'a.Add("old");'):
                with self.subTest(method=method, initial=initial):
                    self.vm.execute(f'a = New Array; {initial} a.{method}(3, "new");')
                    expected = ['old', None, None, 'new'] if initial else [None]*3 + ['new']
                    self.assertEqual(self.vm.execute('a').items, expected)
                    self.assertEqual(self.vm.execute('a.Count()'), Decimal(4))
                    self.assertEqual(self.vm.execute('a.UBound()'), Decimal(3))
                    self.assertEqual(self.vm.execute('TypeOf(a[2])'), self.vm.execute('TypeOf(Undefined)'))

    def test_documented_array_example(self):
        self.vm.execute('a = New Array(4); a.Delete(2); a.Add("text"); a.Add(123.45); a.Insert(8, "tail");')
        self.assertEqual(self.vm.execute('a').items, [None]*3 + ['text', Decimal('123.45')] + [None]*3 + ['tail'])

    def test_omitted_and_explicit_undefined(self):
        self.vm.execute('a = New Array; a.Insert(3); b = New Array; b.Insert(3, Undefined);')
        self.assertEqual(self.vm.execute('a').items, [None]*4)
        self.assertEqual(value_to_string_internal(self.vm.execute('a')), value_to_string_internal(self.vm.execute('b')))

    def test_repeated_gap_and_inrange_shift(self):
        self.vm.execute('a = New Array; a.Insert(2, "A"); a.Insert(5, "B"); a.Insert(1, "C"); a.Insert(a.Count(), "D");')
        self.assertEqual(self.vm.execute('a').items, [None, 'C', None, 'A', None, None, 'B', 'D'])

    def test_alias_snapshot_write_find_and_iteration(self):
        self.vm.execute('a = New Array; alias = a; f = New FixedArray(a); alias.Insert(3, "tail"); '
                        'a[0] = "head"; a.Set(2, 7); seen = New Array; For Each v In a Do seen.Add(v); EndDo;')
        self.assertIs(self.vm.execute('a'), self.vm.execute('alias'))
        self.assertEqual(self.vm.execute('f').items, ())
        self.assertEqual(self.vm.execute('a.Find(Undefined)'), Decimal(1))
        self.assertEqual(self.vm.execute('seen').items, ['head', None, Decimal(7), 'tail'])
        self.vm.execute('f = New FixedArray(a); b = New Array(f); a.Clear();')
        self.assertEqual(self.vm.execute('b').items, ['head', None, Decimal(7), 'tail'])
        with self.assertRaises(BSLError):
            self.vm.execute('f.Insert(7)')

    def test_inserted_identity_and_self_reference(self):
        self.vm.execute('a = New Array; child = New Array; a.Insert(2, child); a.Insert(4, a); child.Add(7);')
        a = self.vm.execute('a')
        self.assertIs(a.items[2], self.vm.execute('child'))
        self.assertIs(a.items[4], a)

    def test_serialization_both_directions(self):
        self.vm.execute('a = New Array; a.Insert(3, "tail");')
        a = self.vm.execute('a')
        serialized = value_to_string_internal(a)
        restored = value_from_string_internal(serialized)
        self.assertEqual(restored.items, [None, None, None, 'tail'])
        self.assertEqual(value_to_string_internal(restored), serialized)

    def test_invalid_indices_are_atomic_and_catchable(self):
        for expression in ('-1', '0.5', 'Undefined', 'True', '"3"', 'New Array', '100000000000000000000'):
            with self.subTest(expression=expression):
                self.vm.execute('a = New Array; a.Add("old");')
                with self.assertRaises(BSLError):
                    self.vm.execute(f'a.Insert({expression}, "new");')
                self.assertEqual(self.vm.execute('a').items, ['old'])
                self.vm.execute(f'Try a.Insert({expression}); Except a.Insert(2, "recovered"); EndTry;')
                self.assertEqual(self.vm.execute('a').items, ['old', None, 'recovered'])

    def test_growth_boundary_before_mutation(self):
        with patch('yadinassi.values._MAX_INSERT_GROWTH', 4):
            a = BSLArray(); a.add('old')
            a.insert(Decimal(4), 'tail')
            self.assertEqual(a.items, ['old', None, None, None, 'tail'])
            before = a.items[:]
            with self.assertRaisesRegex(ValueError, 'предел роста'):
                a.insert(Decimal(9), 'bad')
            self.assertEqual(a.items, before)
            a.insert(Decimal(0), 'head')
            self.assertEqual(a.items, ['head'] + before)

    def test_host_huge_and_nonfinite_decimal_rejected(self):
        a = BSLArray(); a.add('old')
        for value in ('1E+999999999', '-1E+999999999', 'NaN', 'sNaN', 'Infinity', '-Infinity'):
            with self.subTest(value=value), self.assertRaises((ValueError, IndexError)):
                a.insert(Decimal(value))
            self.assertEqual(a.items, ['old'])
        with localcontext() as context:
            context.prec = 1
            context.traps[Inexact] = True
            a.insert(Decimal(12), 'tail')
        self.assertEqual(a.items, ['old'] + [None]*11 + ['tail'])

    def test_read_set_delete_do_not_extend(self):
        for call in ('a.Get(3)', 'a[3]', 'a.Set(3, 7)', 'a[3] = 7', 'a.Delete(3)'):
            self.vm.execute('a = New Array; a.Add("old");')
            with self.subTest(call=call), self.assertRaises(BSLError):
                self.vm.execute(call)
            self.assertEqual(self.vm.execute('a').items, ['old'])
