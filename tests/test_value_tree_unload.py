"""Local UnloadColumn resource/integrity policy, not extra native measurements."""
from decimal import Decimal as D
import unittest
from unittest import mock
import yadinassi.value_trees as tree
from yadinassi.values import BSLArray, NULL
from yadinassi.structures import BSLStructure


class UnloadColumnTests(unittest.TestCase):
    def setUp(self):
        self.tree = tree.BSLValueTree()
        self.id = self.tree.columns.add('Id')
        self.value = self.tree.columns.add('Value')
        self.a = self.tree.rows.add()
        self.b = self.tree.rows.add()
        self.c = self.a.rows.add()
        for row, value in ((self.a, 1), (self.b, 2), (self.c, 3)):
            row.set_member('Id', D(value))

    def test_local_order_and_empty(self):
        self.assertEqual(self.tree.rows.unload_column('Id').items, [D(1), D(2)])
        self.assertEqual(self.a.rows.unload_column('Id').items, [D(3)])
        self.assertEqual(self.c.rows.unload_column('Id').items, [])
        self.tree.rows.items.reverse()
        self.assertEqual(self.tree.rows.unload_column('Id').items, [D(2), D(1)])

    def test_name_index_object_and_aliases(self):
        for selector in ('iD', D(0), D('0.5'), self.id):
            self.assertEqual(self.tree.rows.unload_column(selector).items, [D(1), D(2)])
        self.assertEqual(self.tree.rows.unload_column(D(1)).items, [None, None])
        for alias in ('UnloadColumn', 'ВыгрузитьКолонку'):
            self.assertIsNotNone(self.tree.rows.get_method(alias))

    def test_shallow_membership_and_identity(self):
        cell = BSLStructure('Mark', 'base')
        self.a.set_member('Value', cell)
        result = self.tree.rows.unload_column('Value')
        self.assertIs(type(result), BSLArray)
        self.assertIs(result.items[0], cell)
        cell.set_member('Mark', 'source')
        self.assertEqual(result.items[0].get_member('Mark'), 'source')
        result.items[0].set_member('Mark', 'result')
        self.assertEqual(self.a.get_member('Value').get_member('Mark'), 'result')
        result.items.pop()
        self.assertEqual(len(self.tree.rows.items), 2)
        self.tree.rows.add()
        self.assertEqual(len(result.items), 1)

    def test_nullish_and_boolean_cells_preserved(self):
        for first, second in ((None, NULL), (D(1), True)):
            self.a.set_member('Value', first); self.b.set_member('Value', second)
            result = self.tree.rows.unload_column('Value')
            self.assertIs(result.items[0], first); self.assertIs(result.items[1], second)

    def test_invalid_selectors_fail_even_empty(self):
        foreign = tree.BSLValueTree().columns.add('Id')
        for rows in (self.tree.rows, self.c.rows):
            for selector in ('missing', None, NULL, True, False, D(-1), D(2), foreign):
                with self.subTest(selector=repr(selector)), self.assertRaises((TypeError, ValueError, IndexError)):
                    rows.unload_column(selector)
        for selector in ('Id', D(0), D('0.5')):
            with self.assertRaises((ValueError, IndexError)):
                tree.BSLValueTree().rows.unload_column(selector)

    def test_method_local_truncation_and_other_index_contract_unchanged(self):
        for selector in (D('0.5'), D('-0.5')):
            self.assertEqual(self.tree.rows.unload_column(selector).items, [D(1), D(2)])
        for selector in (D('1.5'), D('1.9')):
            self.assertEqual(self.tree.rows.unload_column(selector).items, [None, None])
        # Local generalization of the measured rule, not additional native cases.
        for selector in (D('0.1'), D('0.9'), D('-0.9'), D('-0'), D('1e-999999999')):
            self.assertEqual(self.tree.rows.unload_column(selector).items, [D(1), D(2)])
        for selector in (D('-1.1'), D('2.1')):
            with self.assertRaises(IndexError): self.tree.rows.unload_column(selector)
        with self.assertRaises(TypeError): self.tree.columns.get(D('0.5'))
        with self.assertRaises(TypeError): self.tree.rows.get(D('0.5'))

    def test_numeric_resource_bounds_and_nonfinite(self):
        for selector in (D('NaN'), D('sNaN'), D('Infinity'), D('1e999999999'), D('9'*10001)):
            with self.subTest(selector_type=type(selector).__name__), self.assertRaises((TypeError, ValueError, IndexError)):
                self.tree.rows.unload_column(selector)

    def test_unknown_selector_never_converts_or_compares(self):
        class Hostile:
            def __str__(self): raise AssertionError('str')
            def __eq__(self, other): raise AssertionError('eq')
            def __int__(self): raise AssertionError('int')
        with self.assertRaises(TypeError): self.tree.rows.unload_column(Hostile())
        class Text(str):
            def casefold(self): raise AssertionError('casefold')
        with self.assertRaises(TypeError): self.tree.rows.unload_column(Text('Id'))

    def test_opaque_cell_never_introspected(self):
        class Hostile:
            def __str__(self): raise AssertionError('str')
            def __eq__(self, other): raise AssertionError('eq')
            def __copy__(self): raise AssertionError('copy')
        cell = Hostile()
        self.a.cells[self.value] = cell
        self.assertIs(self.tree.rows.unload_column(self.value).items[0], cell)

    def test_text_and_schema_work_bounds(self):
        with mock.patch.object(tree, '_MAX_SEARCH_TEXT', 2), self.assertRaises(ValueError):
            self.tree.rows.unload_column('Value')
        with mock.patch.object(tree, '_MAX_SEARCH_WORK', 3), self.assertRaises(ValueError):
            self.tree.rows.unload_column('Id')
        with mock.patch.object(tree, '_MAX_COLUMNS', 1), self.assertRaises(ValueError):
            self.tree.rows.unload_column(self.id)
        with mock.patch.object(tree, '_MAX_ROWS', 1), self.assertRaises(ValueError):
            self.tree.rows.unload_column(self.id)

    def test_detached_rows_and_columns_rejected(self):
        self.tree.rows.delete(self.a)
        with self.assertRaises(ValueError): self.a.rows.unload_column('Id')
        self.tree.columns.delete(self.id)
        with self.assertRaises(ValueError): self.tree.rows.unload_column(self.id)

    def test_corrupted_storage_and_ownership_fail_closed(self):
        with mock.patch.object(self.tree.rows, 'items', tuple(self.tree.rows.items)), self.assertRaises(ValueError):
            self.tree.rows.unload_column('Id')
        with mock.patch.object(self.tree.columns, 'items', (self.id,)), self.assertRaises(ValueError):
            self.tree.rows.unload_column('Id')
        with mock.patch.object(self.a, 'collection', self.c.rows), self.assertRaises(ValueError):
            self.tree.rows.unload_column('Id')
        with mock.patch.object(self.a, 'cells', []), self.assertRaises(ValueError):
            self.tree.rows.unload_column('Id')
        foreign = tree.BSLValueTree().columns.add('Id')
        with mock.patch.object(self.tree.columns, 'items', [foreign]), self.assertRaises(ValueError):
            self.tree.rows.unload_column('Id')


if __name__ == '__main__': unittest.main()
