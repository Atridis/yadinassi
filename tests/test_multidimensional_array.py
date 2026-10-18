"""Documented nested-array constructor; conversion edges are local policy."""
from decimal import Decimal, Inexact, localcontext
import unittest
from unittest.mock import patch

from yadinassi import Interpreter, BSLError
from yadinassi.values import BSLArray
from yadinassi.serialization import value_to_string_internal, value_from_string_internal


class MultidimensionalArrayTests(unittest.TestCase):
    def test_names_shape_and_undefined_leaves(self):
        for name in ('Массив', 'Array', 'мАсСиВ', 'aRrAy'):
            vm = Interpreter()
            vm.execute(f'a = New {name}(2, 3, 4);')
            self.assertEqual(vm.execute('a.Count()'), Decimal(2))
            self.assertEqual(vm.execute('a[1].Count()'), Decimal(3))
            self.assertEqual(vm.execute('a[1][2].UBound()'), Decimal(3))
            self.assertIsNone(vm.execute('a[1][2][3]'))
            self.assertTrue(vm.execute('(TypeOf(a[1][2]) = Type("Array"))'))

    def test_every_branch_is_independent_and_mutable(self):
        vm = Interpreter()
        vm.execute('a = New Array(2, 2, 2); alias = a[0][0]; alias[1] = 9; a[1][1].Add(7);')
        self.assertEqual(vm.execute('a[0][0][1]'), Decimal(9))
        for expression in ('a[0][1][1]', 'a[1][0][1]', 'a[1][1][1]'):
            self.assertIsNone(vm.execute(expression))
        self.assertEqual(vm.execute('a[0][0].Count()'), Decimal(2))
        self.assertEqual(vm.execute('a[1][1].Count()'), Decimal(3))
        branches = [row for plane in vm.execute('a').items for row in plane.items]
        self.assertEqual(len({id(branch) for branch in branches}), 4)

    def test_zero_dimensions_and_existing_default(self):
        vm = Interpreter()
        for expression in ('New Array', 'New Array()', 'New Array(0)', 'New Array(0, 4)'):
            self.assertEqual(vm.execute(expression).items, [])
        vm.execute('a = New Array(2, 0, 4);')
        self.assertEqual(vm.execute('a.Count()'), Decimal(2))
        self.assertEqual(vm.execute('a[0].Count()'), Decimal(0))
        self.assertIsNot(vm.execute('a[0]'), vm.execute('a[1]'))
        vm.execute('a[0].Add(7);')
        self.assertEqual(vm.execute('a[1].Count()'), Decimal(0))
        self.assertEqual(BSLArray(Decimal(0), Decimal('1e1000000')).items, [])
        self.assertEqual(BSLArray(Decimal(2), Decimal(0), Decimal('1e1000000')).items[0].items, [])

    def test_fixed_constructor_and_snapshot_preserved(self):
        vm = Interpreter()
        vm.execute('a = New Array(2, 2); a[0][1] = 7; f = New FixedArray(a); b = New Array(f); a[0][1] = 8; b[0][1] = 9;')
        self.assertEqual(vm.execute('f[0][1]'), Decimal(7))
        self.assertEqual(vm.execute('a[0][1]'), Decimal(8))
        self.assertEqual(vm.execute('b[0][1]'), Decimal(9))
        self.assertIsNone(vm.execute('b[1][1]'))
        with self.assertRaises(BSLError):
            vm.execute('New Array(f, 2)')

    def test_both_serialization_directions(self):
        vm = Interpreter()
        vm.execute('a = New Array(2, 2); a[0][1] = "Я";')
        original = vm.execute('a')
        text = value_to_string_internal(original)
        copy = value_from_string_internal(text)
        self.assertEqual(value_to_string_internal(copy), text)
        self.assertEqual(copy.items[0].items, [None, 'Я'])
        copy.items[0].items[0] = Decimal(3)
        self.assertIsNone(copy.items[1].items[0])
        self.assertIsNone(original.items[0].items[0])
        vm.execute('b = ValueFromStringInternal(ValueToStringInternal(a)); b[0][0] = 3;')
        self.assertTrue(vm.execute('(b[0][1] = "Я")'))
        self.assertIsNone(vm.execute('b[1][0]'))

    def test_validation_and_catchable_recovery(self):
        vm = Interpreter()
        for arguments in ('2, -1', '2, 1.5', '2, "3"', '2, True', '2, Undefined',
                          '0, -1', '0, "3"', '0, Undefined', '2, , 3'):
            with self.subTest(arguments=arguments):
                vm.execute('saved = 7;')
                with self.assertRaises(BSLError):
                    vm.execute(f'saved = New Array({arguments});')
                self.assertEqual(vm.execute('saved'), Decimal(7))
                vm.execute(f'Try New Array({arguments}); Except saved = 9; EndTry;')
                self.assertEqual(vm.execute('saved'), Decimal(9))
                self.assertEqual(vm.execute('New Array(1, 1)').items[0].items, [None])
        for value in ('NaN', 'Infinity', '-Infinity', 'sNaN'):
            with self.assertRaises(ValueError):
                BSLArray(Decimal(0), Decimal(value))

    def test_cumulative_budget_counts_nested_empty_arrays(self):
        # Small patched limit tests exact accounting without large allocations.
        with patch('yadinassi.values._MAX_ARRAY_CONSTRUCTION', 10):
            self.assertEqual(len(BSLArray(Decimal(10)).items), 10)
            self.assertEqual(len(BSLArray(Decimal(2), Decimal(3)).items), 2)  # 2+2+6
            self.assertEqual(len(BSLArray(Decimal(5), Decimal(0)).items), 5)  # 5+5
            for sizes in ((11,), (2, 4), (6, 0), (2, 3, 0)):
                with self.assertRaisesRegex(ValueError, 'предел ресурсов'):
                    BSLArray(*(Decimal(size) for size in sizes))
        self.assertEqual(len(BSLArray(Decimal(1000000)).items), 1000000)
        for sizes in ((Decimal(1000001),), (Decimal('1e1000000'),),
                      (Decimal(1000), Decimal(1000))):
            with self.assertRaisesRegex(ValueError, 'предел ресурсов'):
                BSLArray(*sizes)

    def test_dimension_limit_and_decimal_context(self):
        value = BSLArray(*([Decimal(1)] * 64))
        for _ in range(63):
            value = value.items[0]
        self.assertEqual(value.items, [None])
        with self.assertRaisesRegex(ValueError, 'измерений'):
            BSLArray(*([Decimal(0)] * 65))
        with localcontext() as context:
            context.prec = 1
            context.traps[Inexact] = True
            array = BSLArray(Decimal(12), Decimal(11))
            self.assertEqual(len(array.items[0].items), 11)
            self.assertFalse(context.flags[Inexact])

    def test_failed_reinitialization_is_atomic(self):
        array = BSLArray(Decimal(2))
        array.items[0] = 'old'
        with self.assertRaises(ValueError):
            array.__init__(Decimal(2), Decimal('1e1000000'))
        self.assertEqual(array.items, ['old', None])

    def test_dimensions_evaluate_once_left_to_right(self):
        vm = Interpreter()
        vm.execute('''
Перем Порядок;
Функция Размер(Знач Номер)
    Порядок = Порядок + Строка(Номер);
    Возврат Номер;
КонецФункции
Порядок = "";
a = New Array(Размер(2), Размер(3));
''')
        self.assertEqual(vm.execute('Порядок'), '23')
        self.assertEqual(len(vm.execute('a').items[1].items), 3)
