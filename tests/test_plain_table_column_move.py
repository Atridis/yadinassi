"""Cold column reordering preserves the positional data and index declaration."""
from decimal import Decimal as D
import unittest

from yadinassi import Interpreter
from yadinassi.collections.value_tables import BSLValueTable
from yadinassi.types.type_descriptions import BSLTypeDescription


class ColumnMoveTests(unittest.TestCase):
    def test_prepared_bilingual_move_preserves_rows_columns_and_warm_index(self):
        vm = Interpreter()
        self.addCleanup(vm.close)
        vm.execute('T=New ValueTable; A=T.Columns.Add("A"); B=T.Columns.Add("B"); '
                   'C=T.Columns.Add("C"); R=T.Add(); R.A="one"; R.B=2; R.C="three"; '
                   'T.Indexes.Add("A,B"); Before=T.FindRows(New Structure("A,B","one",2));')
        table = vm.variables['t']
        row = vm.variables['r']
        column = vm.variables['a']
        self.assertIs(vm.variables['before'].items[0], row)
        self.assertEqual(table._search.builds, 1)
        vm.execute_prepared(vm.prepare('T.Колонки.Сдвинуть(A,2); '
                                       'After=T.FindRows(New Structure("B,A",2,"one")); '
                                       'First=R.Get(0); Last=R.A;'))
        self.assertIs(table.rows[0], row)
        self.assertIs(table.columns.get(2), column)
        self.assertEqual(tuple(row), (D(2), 'three', 'one'))
        self.assertEqual((vm.variables['first'], vm.variables['last']), (D(2), 'one'))
        self.assertEqual(table.indexes.items, [(0, 2)])
        self.assertEqual(table._search.builds, 2)
        self.assertIs(vm.variables['after'].items[0], row)

    def test_move_defaults_and_columns_follow_names(self):
        table = BSLValueTable()
        first = table.columns.add('Text')
        second = table.columns.add('N', BSLTypeDescription('Number'))
        row = table.add()
        row.set_member('Text', 'x')
        table.columns.move('n', D('-1.9'))
        self.assertEqual(table.columns.items, (second, first))
        self.assertEqual(tuple(row), (D(0), 'x'))
        self.assertEqual(tuple(table.add()), (D(0), None))
        table.columns.move(0, 1)
        self.assertEqual(table.columns.items, (first, second))
        self.assertEqual(tuple(row), ('x', D(0)))

    def test_bad_bounds_readonly_foreign_and_invalid_indexes_are_atomic(self):
        table = BSLValueTable()
        a = table.columns.add('A')
        b = table.columns.add('B')
        row = table.add()
        row.set_member('A', 'x')
        foreign = BSLValueTable().columns.add('A')
        for column, offset, error in ((a, -1, IndexError), (b, 1, IndexError),
                                      (a, D('1e9999'), IndexError), (a, True, TypeError),
                                      (a, D('NaN'), TypeError), (foreign, 1, ValueError)):
            with self.subTest(column=column, offset=offset), self.assertRaises(error):
                table.columns.move(column, offset)
        table._bounded_slice_read = True
        with self.assertRaisesRegex(ValueError, 'readonly'):
            table.columns.move(a, 1)
        table._bounded_slice_read = False

        class ForeignOffset:
            def __index__(self): raise AssertionError('index hook')
            def __eq__(self, other): raise AssertionError('eq hook')
            def __hash__(self): raise AssertionError('hash hook')

        table.indexes.items.append((ForeignOffset(),))
        before_epoch = table._storage.epoch
        with self.assertRaisesRegex(ValueError, 'noncanonical index declaration'):
            table.columns.move(a, 1)
        self.assertEqual(table._storage.epoch, before_epoch)
        self.assertEqual(table.columns.items, (a, b))
        self.assertIs(table.rows[0], row)
        self.assertEqual(tuple(row), ('x', None))
