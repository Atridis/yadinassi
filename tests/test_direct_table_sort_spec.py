"""Finite direct sort-spec grammar; native outcomes remain in test_value_table_sort."""
import unittest
from yadinassi import Interpreter, BSLError


class DirectTableSortSpecTests(unittest.TestCase):
    def table(self):
        vm = Interpreter()
        self.addCleanup(vm.close)
        vm.execute('T=New ValueTable;T.Columns.Add("Key");T.Columns.Add("Second");'
                   'R=T.Add();R.Key=2;R.Second=1;'
                   'R=T.Add();R.Key=1;R.Second=2;'
                   'R=T.Add();R.Key=1;R.Second=1;')
        return vm

    def test_empty_terms_and_unknown_direction(self):
        for order, expected in (
                ('Key Sideways', [(1,2),(1,1),(2,1)]),
                ('Key,,Second', [(1,1),(1,2),(2,1)]),
                ('Key,', [(1,2),(1,1),(2,1)]),
                (' , Key Desc, ,', [(2,1),(1,2),(1,1)])):
            with self.subTest(order=order):
                vm=self.table();vm.execute(f'T.Sort("{order}");')
                self.assertEqual([tuple(row) for row in vm.variables['t'].rows],expected)

    def test_invalid_order_is_catchable_and_preserves_rows(self):
        for order in ('', ' , , ', 'Missing', 'Key,Missing', 'Key Asc extra'):
            with self.subTest(order=order):
                vm=self.table();before=tuple(vm.variables['t'].rows)
                with self.assertRaises(BSLError):vm.execute(f'T.Sort("{order}");')
                self.assertEqual(tuple(id(row) for row in vm.variables['t'].rows),tuple(map(id,before)))
                self.assertEqual([tuple(row) for row in before],[(2,1),(1,2),(1,1)])

    def test_foreign_order_does_not_run_string_protocol(self):
        class Foreign:
            def __str__(self):raise AssertionError('foreign str')
        vm=self.table();vm.variables['order']=Foreign()
        with self.assertRaises(BSLError):vm.execute('T.Sort(Order);')
        self.assertEqual([tuple(row) for row in vm.variables['t'].rows],[(2,1),(1,2),(1,1)])

    def test_readonly_table_still_rejects_sort(self):
        vm=self.table();vm.variables['t']._bounded_slice_read=True
        with self.assertRaises(BSLError):vm.execute('T.Sort("Key,,");')
        self.assertEqual([tuple(row) for row in vm.variables['t'].rows],[(2,1),(1,2),(1,1)])

    def test_numeric_comparator_is_catchable_without_reordering(self):
        vm=self.table()
        vm.execute('Caught=False;Try T.Sort("Key",1); Except Caught=True; EndTry;')
        self.assertIs(vm.variables['caught'],True)
        self.assertEqual([tuple(row) for row in vm.variables['t'].rows],[(2,1),(1,2),(1,1)])

    def test_null_and_dates_use_canonical_ranks_and_ticks(self):
        vm=self.table()
        vm.execute('T.Get(0).Key=Date(2024,1,1);T.Get(1).Key=Null;'
                   'T.Get(2).Key=Date(2023,1,1);R=T.Get(0);T.Sort("Key Asc");'
                   'Ascending=T.Get(0).Key=Null;Same=R=T.Get(2);'
                   'T.Sort("Key Desc");Descending=R=T.Get(0);')
        for key in ('ascending','same','descending'):
            self.assertIs(vm.variables[key],True)

    def test_date_sort_validates_raw_slots_before_comparing(self):
        from unittest.mock import patch
        from yadinassi.temporal.dates import BSLDate, MAX_TICKS
        from yadinassi.collections.plain_table_storage import _sort_value

        class Foreign:
            def __bool__(self):raise AssertionError('foreign bool')
            def __lt__(self,other):raise AssertionError('foreign less-than')
            def __gt__(self,other):raise AssertionError('foreign greater-than')

        for slot,value in (('ticks',Foreign()),('ticks',True),('ticks',MAX_TICKS+1),
                           ('boundary',Foreign()),('boundary',0)):
            date=BSLDate(0)
            object.__setattr__(date,slot,value)
            with self.subTest(slot=slot,value=value),self.assertRaises(ValueError):
                _sort_value(date)
        with self.assertRaises(ValueError):_sort_value(object.__new__(BSLDate))
        with self.assertRaises(NotImplementedError):_sort_value(BSLDate(0,True))
        vm=self.table()
        table=vm.variables['t']
        invalid=BSLDate(0)
        object.__setattr__(invalid,'ticks',Foreign())
        table.rows[-1].set_member('Key',invalid)
        original=tuple(map(id,table.rows))
        epoch=table._storage.epoch
        with self.assertRaises(ValueError):table.sort('Key')
        self.assertEqual(tuple(map(id,table.rows)),original)
        self.assertEqual(table._storage.epoch,epoch)

        date=BSLDate(1)
        def foreign(self):raise AssertionError('foreign Date accessor')
        with patch.object(BSLDate,'ticks',property(foreign)),patch.object(BSLDate,'boundary',property(foreign)):
            self.assertEqual(_sort_value(date),(1,3,1))
