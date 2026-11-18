import unittest
# Standalone contract tests deliberately do not import the legacy package graph.
import importlib.util
from pathlib import Path
spec = importlib.util.spec_from_file_location('recovered_bare_table', Path(__file__).resolve().parents[1] / 'yadinassi/native_bare_table.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
BareTable, BareRow = module.BareTable, module.BareRow


class RecoveredBareTableTests(unittest.TestCase):
    def table(self):
        table = BareTable()
        table.add_column('N')
        return table

    def test_storage_and_native_positional_access(self):
        table = self.table()
        row = table.add()
        self.assertEqual(table.schema, {'n': 0})
        self.assertEqual(table.rows, [[None]])
        self.assertIs(BareRow.get, list.__getitem__)
        self.assertIs(BareRow.set, list.__setitem__)
        row.set(0, 7)
        self.assertEqual(row.get_member('n'), 7)
        row.set_member('n', 9)
        self.assertEqual(row.get(0), 9)
        with self.assertRaises(TypeError):
            row.get('n')
        with self.assertRaises(KeyError):
            row.get_member('missing')

    def test_columns_are_lazy_and_shared(self):
        table = self.table()
        row = table.add()
        table.columns.add('Second')
        self.assertEqual(row, [None, None])
        table.columns.get(0).set_member('name', 'Renamed')
        self.assertEqual(table.schema, {'second': 1, 'renamed': 0})
        self.assertEqual(table.columns.get(0).name, 'renamed')
        self.assertEqual([column.name for column in table.columns], ['renamed', 'second'])
        self.assertIsNone(table.columns.find('missing'))
        with self.assertRaises(ValueError):
            table.add_column('SECOND')
        self.assertFalse(hasattr(table, '__dict__'))
        self.assertIsNot(table.columns, table.columns)

    def test_builtin_russian_aliases_do_not_translate_user_fields(self):
        table = BareTable()
        columns = table.get_member('колонки')
        column = columns.add('Имя')
        table.add_column('name')
        self.assertEqual(column.get_member('имя'), 'имя')
        self.assertEqual(column.get_member('name'), 'имя')
        row = table.add()
        self.assertIs(row.owner(), table)
        row.set_member('имя', 'russian field')
        row.set_member('name', 'english field')
        self.assertEqual(row.get_member('имя'), 'russian field')
        self.assertEqual(row.get_member('name'), 'english field')
        column.set_member('имя', 'НовоеИмя')
        self.assertEqual(table.get_member('columns').get(0).get_member('имя'), 'новоеимя')
        self.assertEqual(row.get_member('новоеимя'), 'russian field')
        self.assertEqual(row.get_member('name'), 'english field')

    def test_insert_delete_and_iteration(self):
        table = self.table()
        table.add().set(0, 2)
        table.insert(0).set(0, 1)
        self.assertEqual([row[0] for row in table], [1, 2])
        table.set(0, 0, 3)
        removed = table.get(0)
        table.delete(0)
        self.assertEqual(removed, [3])
        self.assertEqual(table.count(), 1)
        table.clear()
        self.assertEqual(len(table), 0)

    def test_copy_rows_and_schema_are_independent(self):
        table = self.table()
        table.add().set(0, 5)
        copy = table.copy()
        copy[0].set_member('n', 6)
        copy.add_column('x')
        self.assertEqual(table.rows, [[5]])
        self.assertEqual(copy.rows, [[6, None]])
        self.assertIs(copy[0].table, copy)
        self.assertEqual(table.copy_columns().rows, [])

    def test_find_sort_and_total(self):
        table = self.table()
        for value in (3, 1, 2):
            table.add().set(0, value)
        self.assertIs(table.find(1, 'N'), table[1])
        self.assertIsNone(table.find(8, 'n'))
        table.sort('n')
        self.assertEqual([row[0] for row in table], [1, 2, 3])
        self.assertEqual(table.total('n'), 6)
        table.sort('n', reverse=True)
        self.assertEqual([row[0] for row in table], [3, 2, 1])


if __name__ == '__main__':
    unittest.main()
