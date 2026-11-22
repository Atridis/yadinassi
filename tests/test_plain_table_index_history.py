"""Native-backed exact index order, not a contract for partial/opaque keys."""
from decimal import Decimal
from unittest import TestCase
from unittest.mock import patch

from yadinassi import Interpreter
from yadinassi.collections import plain_table_search as search
from yadinassi.collections.structures import BSLStructure
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
