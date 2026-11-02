"""Returned slice fences must not leak into shared ordinary ValueTree helpers."""
from decimal import Decimal
import unittest

from yadinassi.type_descriptions import BSLTypeDescription
from yadinassi.value_tables import BSLValueTable, BSLValueTableColumn
from yadinassi.value_trees import BSLValueTree


class SliceOwnerBoundaryTests(unittest.TestCase):
    def test_tree_column_shared_reader_without_slice_flag(self):
        tree = BSLValueTree()
        value_type = BSLTypeDescription('String')
        column = tree.columns.add('A', value_type, 'Title', Decimal(12))
        self.assertFalse(hasattr(tree, '_bounded_slice_read'))
        for name, expected in (('Name', 'A'), ('Имя', 'A'),
                               ('Title', 'Title'), ('Заголовок', 'Title'),
                               ('Width', Decimal(12)), ('Ширина', Decimal(12)),
                               ('ValueType', value_type), ('ТипЗначения', value_type)):
            with self.subTest(name=name):
                self.assertEqual(column.get_member(name), expected)
        column.set_member('Title', 'Changed')
        self.assertEqual(column.get_member('Title'), 'Changed')

    def test_non_table_owner_never_reads_slice_marker(self):
        class ForeignOwner:
            @property
            def _bounded_slice_read(self):
                raise AssertionError('foreign owner marker must not be inspected')
        column = BSLValueTableColumn(ForeignOwner(), 'A', BSLTypeDescription(), '', Decimal(0))
        self.assertEqual(column.get_member('Name'), 'A')

    def test_ordinary_table_and_bounded_slice_remain_distinct(self):
        table = BSLValueTable()
        period = table.columns.add('Период', BSLTypeDescription('Date'))
        value = table.columns.add('Value')
        row = table.add()
        row.set_index('Value', 'original')
        self.assertFalse(table._bounded_slice_read)
        value.set_member('Title', 'Allowed')
        self.assertEqual(value.get_member('Title'), 'Allowed')
        table._bounded_slice_read = True
        self.assertEqual(period.get_member('ValueType'), period.value_type)
        self.assertEqual(value.get_member('Name'), 'Value')
        self.assertEqual(row.get_index('Value'), 'original')
        for action in (lambda: value.get_member('ValueType'),
                       lambda: value.get_member('Title'),
                       lambda: value.set_member('Title', 'Denied'),
                       lambda: table.columns.get_method('Add'),
                       lambda: row.set(Decimal(1), 'Denied'),
                       lambda: row.set_index('Value', 'Denied')):
            with self.assertRaises(ValueError):
                action()
        self.assertEqual(row.get_index('Value'), 'original')
