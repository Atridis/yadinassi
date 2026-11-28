"""Detached index handles do not own eager row copies or cached memberships."""
from decimal import Decimal as D
import unittest

from yadinassi import Interpreter
from yadinassi.collections.structures import BSLStructure
from yadinassi.collections.value_tables import BSLValueTable, BSLCollectionIndex
from yadinassi.formats.storage.serialization import value_from_string_internal, value_to_string_internal
from yadinassi.formats.storage.value_storage import BSLValueStorage, SnapshotError
from yadinassi.types.values import BSLType


class IndexHandleTests(unittest.TestCase):
    def test_prepared_move_rename_and_shared_lazy_signature(self):
        vm = Interpreter()
        self.addCleanup(vm.close)
        vm.execute('T=New ValueTable; A=T.Columns.Add("A"); B=T.Columns.Add("B"); '
                   'R=T.Add(); R.A=1; R.B=2; I=T.Indexes.Add("B,A"); J=T.Indexes.Add("A,B"); '
                   'F=T.FindRows(New Structure("A,B",1,2));')
        table, row, index = (vm.variables[name] for name in ('t', 'r', 'i'))
        self.assertIs(type(index), BSLCollectionIndex)
        self.assertIs(vm.execute('TypeOf(I)'), BSLType.COLLECTION_INDEX)
        self.assertIs(vm.execute('T.Indexes[0]'), index)
        self.assertEqual(table._search.declarations, {(0, 1)})
        self.assertEqual(table._search.builds, 1)
        vm.execute_prepared(vm.prepare('T.Columns.Move(A,1); A.Name="Renamed"; '
                                      'S=""; For Each N In I Do S=S+N;EndDo; '
                                      'T.Indexes.Delete(J); G=T.FindRows(New Structure("B,Renamed",2,1));'))
        self.assertEqual(vm.variables['s'], 'BRenamed')
        self.assertEqual(list(index), ['B', 'Renamed'])
        self.assertIs(vm.variables['g'].items[0], row)
        self.assertEqual(table._search.declarations, {(0, 1)})
        self.assertEqual(table._search.builds, 2)
        self.assertEqual(table.indexes.count(), D(1))

    def test_delete_detaches_and_clear_blanks_with_column_lifecycle(self):
        table = BSLValueTable()
        a = table.columns.add('A')
        b = table.columns.add('B')
        removed = table.indexes.add('A,B')
        attached = table.indexes.add('A,B')
        table.indexes.delete(removed)
        self.assertIs(table.indexes.get_index(0), attached)
        a.name = 'NewA'
        table.columns.delete(b)
        self.assertEqual(list(removed), ['NewA', ''])
        self.assertEqual(list(attached), ['NewA'])
        self.assertEqual(table._search.declarations, {(0,)})
        table.indexes.clear()
        self.assertEqual(list(attached), [''])
        self.assertEqual(attached.get_index(0), '')
        with self.assertRaisesRegex(ValueError, 'очищен'):
            str(attached)
        self.assertEqual(table._search.declarations, set())

    def test_duplicate_delete_preserves_warmed_signature_and_repeated_fields_are_metadata(self):
        table = BSLValueTable()
        table.columns.add('A')
        table.add().set_member('A', D(1))
        repeated = table.indexes.add('A,A')
        self.assertEqual(list(repeated), ['A', 'A'])
        selector = BSLStructure('A', D(1))
        self.assertEqual(table.find_rows(selector).items, [table.rows[0]])
        self.assertEqual(table._search.builds, 0)
        first = table.indexes.add('A')
        second = table.indexes.add('A')
        table.find_rows(selector)
        self.assertEqual(table._search.builds, 1)
        table.indexes.delete(first)
        table.find_rows(selector)
        self.assertEqual(table._search.builds, 1)
        table.indexes.delete(second)
        self.assertEqual(table._search.declarations, set())

    def test_wire_subset_and_fresh_public_handles(self):
        table = BSLValueTable()
        table.columns.add('A')
        table.columns.add('B')
        row = table.add()
        row.set_member('A', D(1))
        index = table.indexes.add('A,B')
        for restored in (value_from_string_internal(value_to_string_internal(table)),
                         BSLValueStorage(table).get()):
            clone = restored.indexes.get_index(0)
            self.assertIsNot(clone, index)
            self.assertIs(clone.table, restored)
            self.assertEqual(list(clone), ['A', 'B'])
            self.assertEqual(restored._search.builds, 0)
            selected = restored.find_rows(BSLStructure('A,B', D(1), None))
            self.assertIs(selected.items[0], restored.rows[0])
        for spec in ('B,A', 'A,A', '', 'A,B'):
            with self.subTest(spec=spec):
                extra = table.indexes.add(spec)
                with self.assertRaises(ValueError):
                    value_to_string_internal(table)
                with self.assertRaises(SnapshotError):
                    BSLValueStorage(table)
                table.indexes.delete(extra)
