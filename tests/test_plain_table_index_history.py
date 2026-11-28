"""Native-backed exact index order, not a contract for partial/opaque keys."""
from decimal import Decimal
from unittest import TestCase
from unittest.mock import patch

from yadinassi import Interpreter
from yadinassi.collections import plain_table_search as search
from yadinassi.collections.structures import BSLStructure
from yadinassi.types.unique_identifiers import BSLUUID
from test_value_table_indexes import found, supplement_sample
from test_value_table_indexes_checkpoint import observations, ROOT, source


class PlainTableIndexHistoryTests(TestCase):
    def test_original_owner_observations(self):
        expected=(ROOT/'tests/fixtures/native_windows/collections.out').read_text(encoding='utf-8-sig')
        output=[]
        vm=Interpreter(output=output.append)
        self.addCleanup(vm.close)
        vm.execute(source().split('#Область МассивыИСтруктуры',1)[0])
        labels={'indexes.extra.edit-order','indexes.extra.selection','indexes.extra.reorder'}
        for observation in observations():
            label,expression=(arg.value for arg in observation.arguments)
            if label not in labels:continue
            labels.remove(label)
            with self.subTest(label=label):
                output.clear()
                verbatim=expression.replace('"','""')
                vm.execute(f'НаблюдатьТаблицы("{label}","{verbatim}")')
                opening=f'table.{label}: [\n'
                block=expected.split(opening,1)[1].split('\n]\n',1)[0]
                self.assertEqual(output,[opening+block+'\n]'])
        self.assertFalse(labels)

    def test_exact_array_aliases_follow_declared_index_order(self):
        table = supplement_sample()
        first, second, third = table.rows
        shared, other = [1], [1]
        first.set_member('Key', shared)
        second.set_member('Key', shared)
        third.set_member('Key', other)
        table.indexes.add('Key')
        self.assertEqual(found(table, Key=shared), [first, second])
        self.assertIs(table.find(shared, 'Key'), first)
        first.set_member('Key', shared)
        self.assertEqual(found(table, Key=shared), [second, first])
        self.assertIs(table.find(shared, 'Key'), second)
        self.assertEqual(found(table, Key=other), [third])
        self.assertEqual(found(table, Key=[1]), [])
        shared.append(2)
        self.assertEqual(found(table, Key=shared), [second, first])
        first.set_member('Key', other)
        self.assertEqual(found(table, Key=shared), [second])
        self.assertEqual(found(table, Key=other), [third, first])

    def test_direct_find_and_findrows_treat_mutable_arrays_by_identity(self):
        vm = Interpreter()
        self.addCleanup(vm.close)
        vm.execute('T=New ValueTable; T.Columns.Add("Key"); T.Columns.Add("ID"); '
                   'A=New Array; A.Add(1); B=New Array; B.Add(1); '
                   'R=T.Add(); R.Key=0; R.ID=1; '
                   'R=T.Add(); R.Key=A; R.ID=2; '
                   'R=T.Add(); R.Key=B; R.ID=3; '
                   'Before=T.Find(A).ID; T.Indexes.Add("Key"); '
                   'After=T.Find(A,"Key").ID; RS=T.FindRows(New Structure("Key",A)); '
                   'CountFound=RS.Count(); FoundID=RS.Get(0).ID; '
                   'C=New Array; C.Add(1); Miss=T.Find(C,"Key");')
        self.assertEqual([vm.variables[k] for k in ('before','after','countfound','foundid')],
                         [2, 2, 1, 2])
        self.assertIsNone(vm.variables['miss'])

    def test_uuid_and_array_search_agree_with_and_without_index(self):
        array = [1]
        uuid = BSLUUID('b21d8b75-3968-44b3-8f27-031209b936ac')
        for indexed in (False, True):
            for nonmatch, wanted in ((array, uuid), (uuid, array)):
                with self.subTest(indexed=indexed, wanted=type(wanted).__name__):
                    table = supplement_sample()
                    first, second, third = table.rows
                    first.set_member('Key', nonmatch)
                    second.set_member('Key', wanted)
                    third.set_member('Key', nonmatch)
                    if indexed:
                        table.indexes.add('Key')
                    self.assertIs(table.find(wanted, 'Key'), second)
                    matches = found(table, Key=wanted)
                    self.assertEqual(len(matches), 1)
                    self.assertIs(matches[0], second)

    def test_malformed_uuid_raises_when_compared_with_array(self):
        array = [1]
        broken = object.__new__(BSLUUID)
        for indexed in (False, True):
            for cell, wanted in ((array, broken), (broken, array)):
                with self.subTest(indexed=indexed, cell=type(cell).__name__):
                    table = supplement_sample()
                    table.rows[0].set_member('Key', cell)
                    if indexed:
                        table.indexes.add('Key')
                    with self.assertRaisesRegex(TypeError, 'invalid exact UUID table value'):
                        table.find(wanted, 'Key')
                    with self.assertRaisesRegex(TypeError, 'invalid exact UUID table value'):
                        found(table, Key=wanted)

    def test_array_subclasses_remain_outside_table_search_without_hooks(self):
        table = supplement_sample()

        class ForeignArray(list):
            def __eq__(self, other):
                self.fail_comparison()

            def __hash__(self):
                self.fail_comparison()

            @staticmethod
            def fail_comparison():
                raise AssertionError('foreign array hook')

        table.rows[0].set_member('Key', ForeignArray([1]))
        table.indexes.add('Key')
        with self.assertRaises(NotImplementedError):
            table.find([1], 'Key')
        with self.assertRaises(NotImplementedError):
            found(table, Key=ForeignArray([1]))

    def test_cold_history_does_not_build_or_compare_keys_on_writes(self):
        table=supplement_sample()
        first,second,third=table.rows
        with patch.object(search,'token',side_effect=AssertionError('eager key work')):
            old=table.indexes.add('Key')
            first.set(0,'a')
            table.indexes.add('Key')
            second.set_member('Second',Decimal(2)) # not part of Key
        self.assertEqual(found(table,Key='a'),[second,third,first])
        self.assertIs(table.find('a','Key'),second)
        table.indexes.delete(old)
        self.assertEqual(found(table,Key='a'),[first,second,third])

    def test_warm_ordered_find_reuses_key_buckets_until_mutation(self):
        table=supplement_sample()
        first,second,third=table.rows
        table.indexes.add('Key')
        first.set_member('Key','a')
        with patch.object(search,'token',wraps=search.token) as tokenize:
            self.assertEqual(found(table,Key='a'),[second,third,first])
            self.assertEqual(tokenize.call_count,4)  # wanted key + three rows
            self.assertIs(table.find('a','Key'),second)
            self.assertEqual(tokenize.call_count,5)  # wanted key only
            second.set_member('Key','a')
            self.assertEqual(tokenize.call_count,5)
            self.assertEqual(found(table,Key='a'),[third,first,second])
            self.assertEqual(tokenize.call_count,9)

    def test_order_survives_column_remap_and_partial_column_load(self):
        table=supplement_sample()
        first,second,third=table.rows
        table.indexes.add('Key')
        first.set_member('Key','a')
        table.columns.insert(0,'New')
        table.columns.move('Key',1)
        table.columns.delete('New')
        self.assertEqual(found(table,Key='a'),[second,third,first])
        table.load_column(['a','a'],'Key')
        self.assertEqual(found(table,Key='a'),[third,first,second])
        table.delete(first)
        self.assertEqual(found(table,Key='a'),[third,second])

    def test_no_index_row_setters_do_not_enter_search(self):
        table=supplement_sample()
        first=table.rows[0]
        class UnusedSearch:
            def __getattribute__(self,name):
                raise AssertionError('no-index write entered search')
        with patch.object(table,'_search',UnusedSearch()):
            first.set_member('Key','named')
            first.set(1,Decimal(2))
        self.assertEqual(first.get_member('Key'),'named')
        self.assertEqual(first.get(1),Decimal(2))

    def test_raw_numeric_write_region_guard_kept_for_no_index_only(self):
        from yadinassi.execution.direct.python_direct_plain_tables import validate
        vm=Interpreter()
        self.addCleanup(vm.close)
        vm.execute('T=New ValueTable; T.Columns.Add("N"); '
                   'For I=0 To 2 Do Row=T.Add(); Row.N=1; EndDo;')
        table=vm.variables['t']
        for row in table.rows:row.set_member('N',Decimal(1))
        self.assertTrue(validate(table,pure=True))
        vm.execute('T.Indexes.Add("N");')
        self.assertFalse(validate(table,pure=True))
        vm.execute('For I=0 To 0 Do Row=T.Get(I); Row.N=1; EndDo;')
        rows=table.find_rows(BSLStructure('N',Decimal(1))).items
        self.assertEqual(rows,table.rows[1:]+table.rows[:1])
