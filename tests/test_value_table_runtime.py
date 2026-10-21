"""Interpreter dispatch and full-native command transport for ValueTable."""
from decimal import Decimal
from pathlib import Path
import unittest

from yadinassi import BSLError, Interpreter
from scripts.smoke_test import table_command_checkpoint, TABLE_COMMAND_LABELS

ROOT = Path(__file__).resolve().parents[1]


class ValueTableRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.vm = Interpreter()
        self.vm.execute('t = New ValueTable(); c = t.Columns.Add("Name"); r = t.Add();')

    def test_bilingual_types_and_dynamic_construction(self):
        self.assertTrue(self.vm.execute('(TypeOf(t) = Type("ТаблицаЗначений"))'))
        self.assertTrue(self.vm.execute('(TypeOf(r) = Type("ValueTableRow"))'))
        self.vm.execute('other = New("ТаблицаЗначений");')
        self.assertEqual(self.vm.execute('other.Count()'), Decimal(0))
        for name in ('ValueTableRow', 'ValueTableColumn', 'ValueTableColumnCollection'):
            with self.assertRaises(BSLError):
                self.vm.execute('x = New ' + name + '();')

    def test_property_index_and_reference_assignments(self):
        self.vm.execute('Procedure SetValue(x) x = "changed"; EndProcedure '
                        'SetValue(r.Name); SetValue(c.Title);')
        self.assertEqual(self.vm.execute('r["NAME"]'), 'changed')
        self.assertEqual(self.vm.execute('c.Title'), 'changed')
        self.vm.execute('r[0] = "indexed"; SetValue(r[0]);')
        self.assertEqual(self.vm.execute('r.Get(0)'), 'changed')
        self.assertTrue(self.vm.execute('(t[0] = r)'))
        with self.assertRaises(BSLError):
            self.vm.execute('t[0] = r;')
        with self.assertRaises(BSLError):
            self.vm.execute('t.Columns[0] = c;')

    def test_optional_holes_for_named_receivers(self):
        self.vm.execute('n = t.Columns.Add("N", , "Title", 12); '
                        'cols = t.Columns; z = cols.Insert(0, "Z", , "Z title"); '
                        'copy = t.Copy(, "Name,N");')
        self.assertEqual(self.vm.execute('n.Title'), 'Title')
        self.assertEqual(self.vm.execute('copy.Columns.Count()'), Decimal(2))
        self.assertEqual(self.vm.execute('copy.Count()'), Decimal(1))

    def test_omitted_column_slots_use_defaults_not_undefined(self):
        self.vm.execute('a = t.Columns.Add(, , "Title"); '
                        'b = t.Columns.Add("B", , , 4); '
                        'd = t.Columns.Insert(0, "D", , "Title");')
        self.assertEqual(self.vm.execute('a.Title'), 'Title')
        self.assertEqual(self.vm.execute('b.Width'), Decimal(4))
        self.assertEqual(self.vm.execute('d.Width'), Decimal(0))
        with self.assertRaises(BSLError):
            self.vm.execute('t.Columns.Add(Undefined);')

    def test_required_holes_reject_before_argument_effects(self):
        self.vm.execute('Var count; count = 0; Function Touch() count = count + 1; Return 1; EndFunction')
        for code in ('t.Columns.Insert(, Touch());', 't.FillValues(, Touch());',
                     't.Get(, Touch());'):
            with self.assertRaises(BSLError):
                self.vm.execute(code)
        self.assertEqual(self.vm.execute('count'), Decimal(0))

    def test_computed_receiver_holes_are_bounded_without_effects(self):
        self.vm.execute('Var count; count = 0; Function GetTable() count = count + 1; Return New ValueTable(); EndFunction')
        with self.assertRaises(BSLError):
            self.vm.execute('GetTable().Copy(, "Name");')
        self.assertEqual(self.vm.execute('count'), Decimal(0))
        self.vm.execute('copy = GetTable().Copy();')
        self.assertEqual(self.vm.execute('count'), Decimal(1))

    def test_row_method_name_column_and_no_host_attributes(self):
        self.vm.execute('t.Columns.Add("Owner"); r.Owner = 7;')
        self.assertEqual(self.vm.execute('r.Owner'), Decimal(7))
        self.assertTrue(self.vm.execute('(r.Owner() = t)'))
        for code in ('t.rows', 'r.cells', 'c.table', 't.__dict__'):
            with self.assertRaises(BSLError):
                self.vm.execute(code)

    def test_bounded_compact_command_matches_fresh_owner_output(self):
        program = (ROOT / 'integrational_tests/tests/collections.bsl').read_text(encoding='utf-8-sig')
        expected = (ROOT / 'tests/fixtures/native_windows/collections.out').read_text(encoding='utf-8-sig')
        program, expected = table_command_checkpoint(program, expected)
        output = []
        Interpreter(output=output.append).execute(program)
        # Exact selected records from genuine owner commit f28dcc51; the full
        # native suite separately compares every record without selection.
        self.assertEqual('\n'.join(output) + '\n', expected)
        self.assertEqual(len(TABLE_COMMAND_LABELS), 8)
        self.assertLess(len(program.encode('utf-16-le')) // 2 + 1024, 32767)
