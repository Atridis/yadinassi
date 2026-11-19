import unittest
from dataclasses import replace
from decimal import Decimal as D
from yadinassi import Interpreter, value_storage as storage
from yadinassi.plain_value_table_runtime import BSLValueTable
from yadinassi.structures import BSLStructure
from yadinassi.type_descriptions import BSLTypeDescription
from yadinassi.type_qualifiers import BSLNumberQualifiers

class DirectTableSnapshot(unittest.TestCase):
    def table(self, typed=False):
        t=BSLValueTable()
        t.columns.add('K',BSLTypeDescription('Number',BSLNumberQualifiers(D(8),D(2))) if typed else None)
        t.columns.add('V')
        for value in (D(1),D(2),D(1)):
            r=t.add();r.set_member('K',value);r.set_member('V','x')
        t.indexes.add('K');return t
    def test_untyped_and_conformant_typed_roundtrip(self):
        for typed in (False,True):
            source=self.table(typed);source.find_rows(BSLStructure('K',D(1)))
            store=storage.BSLValueStorage(source);result=store.get()
            self.assertIsNot(result,source);self.assertEqual(result.indexes.items,[(0,)])
            self.assertEqual(result._search.cache,{});self.assertEqual(result._search.builds,0)
            matches=result.find_rows(BSLStructure('K',D(1))).items
            self.assertIs(matches[0],result.rows[0]);self.assertIs(matches[1],result.rows[2])
            result.rows[0].set_member('K',D(3))
            self.assertEqual(result.find_rows(BSLStructure('K',D(1))).items,[result.rows[2]])
            self.assertEqual(source.rows[0].get_member('K'),D(1))
            self.assertEqual(store.get()._search.cache,{})
    def test_cache_never_read(self):
        class Hostile:
            def __iter__(self):raise AssertionError('cache iteration')
            def items(self):raise AssertionError('cache items')
        t=self.table();t._search.cache=Hostile()
        self.assertEqual(storage.BSLValueStorage(t).get().indexes.items,[(0,)])
    def test_malformed_runtime_fields_fail_closed(self):
        for change in ('row_owner','row_schema','width','index_type','index_bool','index_duplicate','foreign_column'):
            t=self.table()
            if change=='row_owner':t.rows[0]._owner=object()
            elif change=='row_schema':t.rows[0].schema=object()
            elif change=='width':list.pop(t.rows[0])
            elif change=='index_type':t.indexes.items=[object()]
            elif change=='index_bool':t.indexes.items=[(True,)]
            elif change=='index_duplicate':t.indexes.items=[(0,),(0,)]
            else:t.columns._items[0].table=object()
            with self.subTest(change=change),self.assertRaises(storage.SnapshotError):storage.capture(t)
    def test_nonconformant_typed_is_not_coerced(self):
        t=self.table(True);t.rows[0].set_member('K',D('1.234'))
        with self.assertRaises(storage.SnapshotError):storage.capture(t)
    def test_bsl_created_table_host_storage(self):
        vm=Interpreter();vm.execute('T=New ValueTable;T.Columns.Add("K");R=T.Add();R.K=1;T.Indexes.Add("K");')
        restored=storage.BSLValueStorage(vm.variables['t']).get()
        self.assertEqual(restored.find_rows(BSLStructure('K',D(1))).items,[restored.rows[0]])
    def test_source_seals_new_storage_classes_and_slots(self):
        from unittest.mock import patch
        from yadinassi import value_storage_table as codec
        from yadinassi import python_direct_source_value_storage as direct
        from yadinassi.experimental_naked_boundaries import BoundaryViolation
        for name in ('Schema','TableStorage','SearchIndexes'):
            cls=getattr(codec,name)
            with patch.object(codec,name,type('Replacement',(),{})):
                with self.assertRaises(BoundaryViolation):direct.check_factories()
            with patch.object(cls,'_codec_probe',property(lambda _:self.fail('descriptor called')),create=True):
                with self.assertRaises(BoundaryViolation):direct.check_factories()
        with patch.object(codec.Schema,'validate',side_effect=AssertionError('new method dispatch')):
            # Host capture is self-contained; source sealing rejects the patch.
            storage.capture(self.table())
            with self.assertRaises(BoundaryViolation):direct.check_factories()
    def test_names_with_commas_not_snapshot_admitted(self):
        t=BSLValueTable();t.columns.add('A,B')
        with self.assertRaises(storage.SnapshotError):storage.capture(t)
    def test_declarations_bounded_before_elements(self):
        from yadinassi import value_storage_table as codec
        t=self.table();t._search.declarations=set((i,) for i in range(codec.MAX_INDEXES+1))
        with self.assertRaises(storage.SnapshotError):storage.capture(t)
