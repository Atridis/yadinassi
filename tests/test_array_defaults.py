"""EDT-documented optional values of existing Array methods."""
from decimal import Decimal
import unittest

from yadinassi import BSLError, Interpreter
from yadinassi.values import BSLArray
from yadinassi.serialization import value_to_string_internal, value_from_string_internal


class ArrayDefaultTests(unittest.TestCase):
    def setUp(self):
        self.vm = Interpreter(output=lambda message: None)

    def test_host_methods_default_to_undefined(self):
        a = BSLArray()
        a.add()
        a.insert(Decimal(0))
        self.assertEqual(a.items, [None, None])

    def test_add_aliases_and_repeated_calls(self):
        for method in ('Добавить', 'Add', 'дОбАвИтЬ', 'aDd'):
            with self.subTest(method=method):
                self.vm.execute(f'a = New Array; a.{method}(); a.{method}();')
                self.assertEqual(self.vm.execute('a').items, [None, None])
                self.assertEqual(self.vm.execute('a.Count()'), Decimal(2))
                self.assertEqual(self.vm.execute('a.UBound()'), Decimal(1))
                self.assertEqual(self.vm.execute('a.Find(Undefined)'), Decimal(0))

    def test_insert_aliases_shift_without_overwrite(self):
        for method in ('Вставить', 'Insert', 'вСтАвИтЬ', 'iNsErT'):
            with self.subTest(method=method):
                self.vm.execute(f'a = New Array; a.Add("A"); a.Add("B"); a.{method}(1);')
                self.assertEqual(self.vm.execute('a').items, ['A', None, 'B'])
                self.vm.execute(f'a.{method}(0); a.{method}(a.Count());')
                self.assertEqual(self.vm.execute('a').items, [None, 'A', None, 'B', None])

    def test_insert_into_empty_array(self):
        self.vm.execute('a = New Array; a.Insert(0);')
        self.assertEqual(self.vm.execute('a').items, [None])

    def test_omitted_and_explicit_undefined_have_same_serialization(self):
        self.vm.execute('a = New Array; a.Add(); a.Insert(0); '
                        'b = New Array; b.Add(Undefined); b.Insert(0, Undefined);')
        a, b = self.vm.execute('a'), self.vm.execute('b')
        self.assertEqual(value_to_string_internal(a), value_to_string_internal(b))
        self.assertEqual(value_from_string_internal(value_to_string_internal(a)).items, [None, None])
        self.assertEqual(self.vm.execute('TypeOf(a[0])'), self.vm.execute('TypeOf(Undefined)'))

    def test_explicit_values_preserve_identity(self):
        self.vm.execute('a = New Array; child = New Array; a.Add(child); a.Insert(0, child);')
        a, child = self.vm.execute('a'), self.vm.execute('child')
        self.assertIs(a.items[0], child)
        self.assertIs(a.items[1], child)
        self.vm.execute('child.Add();')
        self.assertEqual(a.items[0].items, [None])

    def test_defaults_remain_writable_and_collection_aliases_are_live(self):
        self.vm.execute('a = New Array; alias = a; a.Add(); alias.Insert(0); '
                        'a[0] = 7; alias.Set(1, "B");')
        self.assertIs(self.vm.execute('a'), self.vm.execute('alias'))
        self.assertEqual(self.vm.execute('alias.Get(0)'), Decimal(7))
        self.assertEqual(self.vm.execute('a[1]'), 'B')

    def test_mutation_through_routine_parameters_and_element_references(self):
        self.vm.execute('''
            Procedure Append(Val a) a.Add(); a.Insert(0); EndProcedure
            Procedure SetValue(x) x = "changed"; EndProcedure
            a = New Array; Append(a);
        ''')
        self.assertEqual(self.vm.execute('a').items, [None, None])
        with self.assertRaisesRegex(BSLError, 'по ссылке пока не поддерживается'):
            self.vm.execute('SetValue(a[1]);')
        self.assertEqual(self.vm.execute('a').items, [None, None])

    def test_fixed_snapshot_and_fixed_methods_unchanged(self):
        self.vm.execute('a = New Array; a.Add(); f = New FixedArray(a); a.Insert(0); a[1] = 7;')
        self.assertEqual(self.vm.execute('f').items, (None,))
        for call in ('f.Add()', 'f.Insert(0)', 'f.Добавить()', 'f.Вставить(0)'):
            with self.subTest(call=call), self.assertRaises(BSLError):
                self.vm.execute(call)
        self.assertEqual(self.vm.execute('f').items, (None,))

    def test_invalid_calls_preserve_contents_and_recover(self):
        # Index coercions and sparse insertion are not expanded in this change.
        for call in ('a.Insert()', 'a.Add(1, 2)', 'a.Insert(0, 1, 2)',
                     'a.Insert(-1)', 'a.Insert(3)', 'a.Insert(0.5)',
                     'a.Insert(Undefined)', 'a.Insert("0")', 'a.Set(0)'):
            with self.subTest(call=call):
                self.vm.execute('a = New Array; a.Add("old");')
                with self.assertRaises(BSLError):
                    self.vm.execute(call)
                self.assertEqual(self.vm.execute('a').items, ['old'])
                self.vm.execute('Try ' + call + '; Except a.Add(); EndTry;')
                self.assertEqual(self.vm.execute('a').items, ['old', None])

    def test_explicit_empty_slots_still_rejected_before_mutation(self):
        for call in ('a.Add(,)', 'a.Insert(0,)', 'a.Insert(, 1)'):
            with self.subTest(call=call):
                self.vm.execute('a = New Array; a.Add("old");')
                with self.assertRaises(BSLError):
                    self.vm.execute(call)
                self.assertEqual(self.vm.execute('a').items, ['old'])
