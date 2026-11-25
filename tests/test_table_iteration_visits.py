"""A read-only table iterator checks the object it reaches, not the whole table."""
from decimal import Decimal
import unittest
from unittest.mock import patch

from yadinassi import Interpreter
from yadinassi.collections.value_tables import BSLValueTable
from yadinassi.execution.codegen.direct_boundaries import BoundaryContext, BoundaryViolation
from yadinassi.execution.direct import python_direct_plain_tables as validation
from yadinassi.execution.direct.python_direct_table_iteration import resolve


class TableIterationVisitTests(unittest.TestCase):
    def setUp(self):
        self.context = BoundaryContext()
        self.context.start()

    def table(self, count=3):
        table = BSLValueTable()
        table.columns.add('X')
        table.columns.add('Y')
        for i in range(count):
            row = table.add()
            row.set_member('X', Decimal(i+1))
            row.set_member('Y', Decimal(10))
        return table

    def test_first_row_does_not_inspect_later_foreign_row(self):
        table, foreign = self.table(), self.table()
        table.rows[1] = foreign.rows[0]
        expected = table.rows[0]
        with patch.object(validation, 'row_check', wraps=validation.row_check) as checks:
            rows = resolve(self.context, table)()
            checks.assert_not_called()
            self.assertIs(next(rows),expected)
            self.assertEqual(checks.call_count,1)
            with self.assertRaises(BoundaryViolation):
                next(rows)
            self.assertEqual(checks.call_count,2)
        vm = Interpreter()
        self.addCleanup(vm.close)
        vm.variables['t'] = table
        vm.execute('For Each R In T Do F=R.X; Break; EndDo;')
        self.assertEqual(vm.variables['f'],1)

    def test_columns_check_only_the_reached_position_and_never_rows(self):
        table, foreign = self.table(), self.table()
        table.rows[1] = foreign.rows[0]
        table.columns._items[1] = foreign.columns.get(1)
        with patch.object(validation, 'row_check', side_effect=AssertionError('unrelated row')), \
             patch.object(validation, 'column_check', wraps=validation.column_check) as checks:
            columns = resolve(self.context,table.columns)()
            checks.assert_not_called()
            self.assertIs(next(columns),table.columns.get(0))
            with self.assertRaises(BoundaryViolation):
                next(columns)
            self.assertEqual(checks.call_count,2)

    def test_one_live_row_is_snapshotted_without_validating_unrelated_rows(self):
        table = self.table()
        live = table.rows[0]
        table.rows[1] = object()
        with patch.object(validation, 'row_check', wraps=validation.row_check) as checks:
            cells = resolve(self.context,live)()
            live.set_member('Y',Decimal(99))
            self.assertEqual(list(cells),[Decimal(1),Decimal(10)])
            checks.assert_called_once()

    def test_late_malformed_or_detached_item_is_rejected_before_yield(self):
        for mode in ('shape','detached','wrong_owner'):
            with self.subTest(mode=mode):
                table = self.table()
                rows = resolve(self.context,table)()
                self.assertIs(next(rows),table.rows[0])
                row = table.rows[1]
                if mode == 'shape':
                    list.pop(row)
                elif mode == 'detached':
                    table.delete(1)
                    table.rows.insert(1,row)
                else:
                    row._owner = self.table()
                with self.assertRaises(BoundaryViolation):
                    next(rows)

    def test_late_row_dict_subclass_does_not_run_a_host_hook(self):
        table = self.table()
        calls = []
        class ForeignState(dict):
            def __iter__(self):
                calls.append('iter')
                raise AssertionError('host dict hook')
        row = table.rows[1]
        row.__dict__ = ForeignState(vars(row))
        rows = resolve(self.context, table)()
        self.assertIs(next(rows),table.rows[0])
        with self.assertRaises(BoundaryViolation):
            next(rows)
        self.assertEqual(calls,[])

    def test_supported_mutations_keep_live_table_and_column_iteration(self):
        table = self.table(2)
        rows = resolve(self.context,table)()
        columns = resolve(self.context,table.columns)()
        self.assertIs(next(rows),table.rows[0])
        self.assertEqual(next(columns).name,'X')
        added_column = table.columns.add('Z')
        added_row = table.add()
        self.assertIs(next(rows),table.rows[1])
        self.assertIs(next(rows),added_row)
        self.assertEqual(next(columns).name,'Y')
        self.assertIs(next(columns),added_column)

    def test_in_flight_iterator_keeps_its_captured_list(self):
        table = self.table()
        original = table.rows
        rows = resolve(self.context,table)()
        self.assertIs(next(rows),original[0])
        # The existing adapter binds the actual list, not later host aliases.
        table.rows = [object()]
        self.assertIs(next(rows),original[1])

    def test_deleted_row_iteration_keeps_live_owner_behavior(self):
        table = self.table()
        detached = table.rows[0]
        table.delete(0)
        table.rows[1] = object()
        rows = resolve(self.context,detached)()
        self.assertIs(next(rows),table.rows[0])
        with self.assertRaises(BoundaryViolation):
            next(rows)


if __name__ == '__main__':
    unittest.main()
