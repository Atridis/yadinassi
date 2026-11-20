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
