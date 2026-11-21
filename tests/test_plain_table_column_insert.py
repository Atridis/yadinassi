"""Cold schema insertion over live positional table rows."""
from decimal import Decimal
import unittest

from yadinassi import Interpreter
from yadinassi.collections.value_tables import BSLValueTable
from yadinassi.types.type_descriptions import BSLTypeDescription


class PlainTableColumnInsertTests(unittest.TestCase):
    def test_positional_insert_preserves_live_rows_and_warmed_index(self):
        vm = Interpreter()
        vm.execute('T=New ValueTable; T.Columns.Add("A"); T.Columns.Add("B"); '
                   'R=T.Add(); R.A=1; R.B="x"; T.Indexes.Add("A,B"); '
                   'Before=T.FindRows(New Structure("B,A","x",1));')
        table = vm.variables['t']
        row = vm.variables['r']
        self.assertIs(vm.variables['before'].items[0], row)
        self.assertEqual(table._search.builds, 1)
        vm.execute_prepared(vm.prepare('C=T.Columns.Insert(1,"NewCol"); '
                                       'After=T.FindRows(New Structure("A,B",1,"x"));'))
        self.assertEqual(tuple(c.name for c in table.columns.items), ('A','NewCol','B'))
        self.assertIs(table.rows[0], row)
        self.assertEqual(tuple(row), (Decimal(1), None, 'x'))
        self.assertIs(vm.variables['after'].items[0], row)
        self.assertEqual(table.indexes.items, [(0,2)])
        self.assertEqual(table._search.builds, 2)

    def test_blank_cells_defaults_and_native_append_indices(self):
        table = BSLValueTable()
        table.columns.add('A')
        row = table.add()
        number = BSLTypeDescription('Number')
        table.columns.insert(Decimal('0.9'), 'N', number, 'Header', Decimal(8))
        table.columns.insert(-1, 'Negative')
        table.columns.insert(100, 'Past')
        self.assertEqual(tuple(c.name for c in table.columns.items), ('N','A','Negative','Past'))
        self.assertEqual(tuple(row), (Decimal(0), None, None, None))
        self.assertEqual(table.columns.get(0).title, 'Header')
        self.assertEqual(table.columns.get(0).width, Decimal(8))

    def test_invalid_indices_duplicate_name_and_readonly_refuse_before_changes(self):
        table = BSLValueTable()
        column = table.columns.add('A')
        row = table.add()
        for index in (True, Decimal('NaN'), '0'):
            with self.assertRaises(TypeError):
                table.columns.insert(index, 'B')
        with self.assertRaises(ValueError):
            table.columns.insert(0, 'a')
        table._bounded_slice_read = True
        with self.assertRaises(ValueError):
            table.columns.insert(0, 'B')
        self.assertEqual(table.columns.items, (column,))
        self.assertIs(table.rows[0], row)
        self.assertEqual(tuple(row), (None,))
