"""Storage-only contracts; these tests do not grant interpreted receiver access."""
import unittest
from decimal import Decimal as D
from yadinassi.collections.plain_table_storage import Schema, RowStorage, TableStorage, StorageError
from yadinassi.types.values import BSLObject


class PublicRow(RowStorage, BSLObject):
    def __init__(self, owner, schema, values=None):
        RowStorage.__init__(self, owner, schema, values)
        self.table = owner

    def owner(self):
        return self._owner


class PlainTableStorageTests(unittest.TestCase):
    def storage(self, row_factory=RowStorage):
        owner = object()
        table = TableStorage(owner, row_factory)
        table.add_column('Name', {'opaque': 'metadata'}, '')
        table.add_column('Amount', None, D(0))
        return table

    def test_canonical_public_row_is_the_storage_object(self):
        table = self.storage(PublicRow)
        row = table.add()
        self.assertIs(type(row), PublicRow)
        self.assertIs(table.rows[0], row)
        self.assertIs(row.table, table.owner)
        self.assertIs(row.owner(), table.owner)
        row.set_value('AMOUNT', D(4))
        self.assertEqual(list.__getitem__(row, 1), D(4))
        table.validate()

    def test_defaults_and_metadata_are_opaque_and_retained(self):
        table = TableStorage(object())
        value, metadata = object(), object()
        table.add_column('Payload', metadata, value)
        first, second = table.add(), table.add()
        self.assertIs(first.get_value('payload'), value)
        self.assertIs(second.get_value('payload'), value)
        self.assertIs(table.schema.metadata[0], metadata)
        self.assertEqual(table.schema.offset('PAYLOAD'), 0)
        self.assertEqual(table.schema.names, ['Payload'])

    def test_insert_move_delete_clear_and_retained_rows(self):
        table = self.storage()
        a, b = table.add(), table.add()
        c = table.insert(1)
        self.assertEqual([id(r) for r in table.rows], [id(a), id(c), id(b)])
        table.move(2, -2)
        self.assertEqual([id(r) for r in table.rows], [id(b), id(a), id(c)])
        self.assertIs(table.delete(1), a)
        with self.assertRaises(StorageError):a.get_value('Name')
        table.clear()
        self.assertEqual(table.rows, [])
        self.assertTrue(b._deleted);self.assertTrue(c._deleted)

    def test_indices_are_python_internal_not_bsl_coercion(self):
        table = self.storage();table.add()
        for index in (True, D(0), -1, 1, 10**100):
            with self.subTest(index=index), self.assertRaises((TypeError,IndexError)):
                table.get(index)
        with self.assertRaises(IndexError):table.move(0, 1)
        self.assertEqual(len(table.rows),1)

    def test_schema_add_rename_delete_preserves_row_identity(self):
        table = self.storage();row = table.add();row.set_value('Amount', D(7))
        table.add_column('Extra', default=False)
        self.assertIs(table.get(0),row);self.assertIs(row.get_value('extra'),False)
        table.rename_column('amount','Total')
        self.assertEqual(row.get_value('total'), D(7))
        self.assertEqual(table.schema.keys, ['name','total','extra'])
        self.assertEqual(table.schema.offset('TOTAL'), 1)
        with self.assertRaises(StorageError):row.get_value('amount')
        table.delete_column('Name');table.delete_column('Extra');table.delete_column('Total')
        self.assertEqual(table.rows,[]);self.assertTrue(row._deleted)

    def test_rename_duplicate_and_missing_operations_are_atomic(self):
        table = self.storage();row=table.add();before=list(row);version=table.schema.version
        for action in (lambda:table.rename_column('Name','Amount'),
                       lambda:table.add_column('NAME'),
                       lambda:table.delete_column('Missing'),
                       lambda:table.fill(3,['Name','Missing'])):
            with self.assertRaises(StorageError):action()
            self.assertEqual(list(row),before)
            self.assertEqual(table.schema.version,version)

    def test_empty_names_have_explicit_unique_column_policy(self):
        table = TableStorage(object());table.add_column('')
        with self.assertRaises(StorageError):table.add_column('')

    def test_fill_find_copy_share_payload_but_not_storage(self):
        table=self.storage(PublicRow)
        for number in (D(2),D(1),D(3)):
            row=table.add();row.set_value('Amount',number)
        table.fill('same',['Name'])
        found=table.find(D(1),'Amount')
        self.assertIs(found,table.rows[1])
        other=table.copy(object(),['Amount'])
        self.assertIs(type(other.rows[0]),PublicRow)
        self.assertEqual([r.get_value('Amount') for r in other.rows],[D(2),D(1),D(3)])
        self.assertIsNot(other.rows[0],table.rows[0])
        other.rows[0].set_value('amount',D(99))
        self.assertEqual(table.rows[0].get_value('amount'),D(2))
        self.assertIsNone(table.find(True,'Amount'))

    def test_sort_is_stable_with_multiple_exact_scalar_keys(self):
        table=self.storage()
        for name,amount in [('b',D(1)),('a',D(2)),('a',D(1)),('a',D(1))]:
            row=table.add();row.set_value('Name',name);row.set_value('Amount',amount)
        identities=list(table.rows)
        table.sort([('Name',False),('Amount',True)])
        self.assertEqual([r.get_value('Name') for r in table.rows],['a','a','a','b'])
        self.assertEqual([r.get_value('Amount') for r in table.rows],[D(2),D(1),D(1),D(1)])
        self.assertIs(table.rows[1],identities[2]);self.assertIs(table.rows[2],identities[3])

    def test_russian_sort_key_is_stable_in_both_directions(self):
        table = self.storage()
        values = ['Жук', 'Ёлка', 'Ель', 'ёлка', 'ель', 'Я', 'A', 'a', 'á', 'ѐ', '😀']
        original = {}
        for value in values:
            row = table.add()
            row.set_value('Name', value)
            original[value] = row
        rows = table.rows
        for descending, russian in (
                (False, ['Ель', 'ель', 'Ёлка', 'ёлка', 'Жук', 'Я']),
                (True, ['Я', 'Жук', 'Ёлка', 'ёлка', 'Ель', 'ель'])):
            table.sort([('Name', descending)])
            self.assertIs(table.rows, rows)
            sorted_values = [row.get_value('Name') for row in rows]
            self.assertEqual([v for v in sorted_values if v in russian], russian)
            self.assertEqual([v for v in sorted_values if v not in russian],
                             sorted(['A', 'a', 'á', 'ѐ', '😀'], reverse=descending))
            for row in rows:
                self.assertIs(row, original[row.get_value('Name')])

    def test_value_table_object_sort_matches_observed_order_and_keeps_rows(self):
        from yadinassi import Interpreter

        source = """
            T=New ValueTable; T.Columns.Add("Key"); T.Columns.Add("ID");
            First=T.Add(); First.Key=New Structure("A",2); First.ID=1;
            Row=T.Add(); Row.Key=New Array; Row.ID=2;
            Row=T.Add(); Row.Key=New Structure("A",1); Row.ID=3;
            Row=T.Add(); Row.Key=New Array; Row.ID=4;
            Row=T.Add(); Row.Key=Type("Number"); Row.ID=5;
            Row=T.Add(); Row.Key=Type("String"); Row.ID=6;
            T.Sort("Key");
            IDs=""; For Each Row In T Do IDs=IDs+String(Row.ID); EndDo;
            SameRow=(T[2]=First);
        """
        # Native Windows collections.out table.ops.sort.objects.
        for prepared in (False, True):
            with self.subTest(prepared=prepared):
                vm=Interpreter()
                self.addCleanup(vm.close)
                if prepared:
                    vm.execute_prepared(vm.prepare(source))
                else:
                    vm.execute(source)
                self.assertEqual(vm.variables['ids'], '241365')
                self.assertIs(vm.variables['samerow'], True)
                vm.execute('T.Sort("Key, ID Desc"); '
                           'IDs=""; For Each Row In T Do IDs=IDs+String(Row.ID); EndDo;')
                self.assertEqual(vm.variables['ids'], '423165')

    def test_mixed_object_and_scalar_sort_keys_do_not_publish_any_rows(self):
        for values in (([], D(1)), (D(1), [])):
            table = self.storage()
            for value in values:
                table.add().set_value('Amount', value)
            before = tuple(table.rows)
            epoch = table.epoch
            with self.assertRaises(NotImplementedError):
                table.sort([('Amount', False)])
            self.assertEqual(table.epoch, epoch)
            self.assertTrue(all(left is right for left, right in zip(table.rows, before)))

    def test_opaque_comparison_and_sort_fail_without_hooks_or_reordering(self):
        effects=[]
        class Hostile:
            def __eq__(self,other):effects.append('eq');raise AssertionError
            def __lt__(self,other):effects.append('lt');raise AssertionError
            def __hash__(self):effects.append('hash');raise AssertionError
        table=self.storage();a=table.add();b=table.add();a.set_value('Amount',Hostile())
        for operation in (lambda:table.find(D(3),'Amount'),lambda:table.sort([('Amount',False)])):
            with self.assertRaises(NotImplementedError):operation()
        self.assertIs(table.rows[0],a);self.assertIs(table.rows[1],b)
        self.assertEqual(effects,[])

    def test_hostile_metaclass_is_not_called_by_scalar_classification(self):
        effects=[]
        class Meta(type):
            def __eq__(self,other):effects.append('meta eq');raise AssertionError
            def __hash__(self):effects.append('meta hash');raise AssertionError
        class Payload(metaclass=Meta):pass
        table=self.storage();table.add().set_value('Amount',Payload())
        with self.assertRaises(NotImplementedError):table.find(D(1),'Amount')
        for operation in (lambda: table.fill(1, Payload()),
                          lambda: table.copy(object(), Payload()),
                          lambda: table.sort(Payload())):
            with self.assertRaises(TypeError): operation()
        self.assertEqual(effects,[])

    def test_hostile_name_rejected_before_key_hooks(self):
        effects=[]
        class Name(str):
            def casefold(self):effects.append('fold');raise AssertionError
            def __hash__(self):effects.append('hash');raise AssertionError
        table=self.storage();row=table.add()
        for action in (lambda:table.add_column(Name('X')),lambda:row.get_value(Name('Name')),
                       lambda:row.set_value(Name('Name'),1)):
            with self.assertRaises(TypeError):action()
        self.assertEqual(effects,[])

    def test_raw_hostile_schema_key_rejected_before_dictionary_lookup(self):
        effects=[]
        class Key:
            def __hash__(self):return hash('amount')
            def __eq__(self,other):effects.append('eq');raise AssertionError
        table=self.storage();row=table.add()
        table.schema._offsets.clear();table.schema._offsets[Key()]=1
        for action in (table.validate,):
            with self.assertRaises(StorageError):action()
        self.assertEqual(effects,[])

    def test_foreign_row_and_corrupted_offsets_rejected(self):
        table=self.storage();other=self.storage();row=other.add();table.rows.append(row)
        with self.assertRaises(StorageError):table.validate()
        table.rows.clear();table.schema._offsets['name']=True
        with self.assertRaises(StorageError):table.validate()

    def test_row_initial_data_requires_exact_shape(self):
        table=self.storage()
        row=RowStorage(table.owner,table.schema,['x',D(1)])
        self.assertEqual(row.get_value('NAME'),'x')
        with self.assertRaises(StorageError):RowStorage(table.owner,table.schema,[1])

    def test_add_column_extends_shared_lists_without_rebuild_or_scan(self):
        from unittest.mock import patch
        table = self.storage(); row = table.add(); schema = table.schema
        containers = (schema._names, schema._keys, schema._metadata,
                      schema._defaults, schema._offsets)
        with patch.object(TableStorage, 'validate', side_effect=AssertionError('scan')):
            table.add_column('Third', default=7)
            table.rename_column('Third', 'Renamed')
            row.set_value('Renamed', 8)
        for before, after in zip(containers, (schema._names, schema._keys,
                schema._metadata, schema._defaults, schema._offsets)):
            self.assertIs(before, after)
        self.assertEqual(list(row), ['', D(0), 8])
        table.validate()

    def test_raw_row_length_mutation_rejected_at_explicit_boundary(self):
        table = self.storage(); row = table.add()
        list.append(row, object())
        with self.assertRaises(StorageError): table.validate()

    def test_reordered_copy_uses_projected_offsets(self):
        table = self.storage(); row = table.add()
        row.set_value('Name', 'x'); row.set_value('Amount', D(5))
        other = table.copy(object(), ['Amount', 'Name'])
        self.assertEqual(list(other.rows[0]), [D(5), 'x'])
        other.validate()


if __name__=='__main__':unittest.main()
