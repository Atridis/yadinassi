"""Working lightweight table contract, not full legacy compatibility."""
from decimal import Decimal
import unittest
from unittest.mock import patch
from yadinassi import Interpreter, BSLError
from yadinassi.collections.value_tables import BSLValueTable
from yadinassi.collections.plain_value_table_runtime import BSLValueTable as PlainTable
from yadinassi.execution.direct.python_direct_plain_tables import validate
from yadinassi.execution.codegen.experimental_naked_boundaries import BoundaryViolation

class PlainTableRuntimeTests(unittest.TestCase):
    def table(self):
        t=BSLValueTable();t.columns.add('N');return t
    def test_actual_bsl_constructor_without_vm(self):
        vm=Interpreter()
        with patch.object(Interpreter,'block',side_effect=AssertionError('VM')),patch.object(Interpreter,'call_routine',side_effect=AssertionError('VM')):
            vm.execute('T=New ValueTable;T.Columns.Add("N");For I=0 To 4 Do R=T.Add();R.N=I;EndDo;S=0;For I=0 To 4 Do S=S+T.Get(I).N;EndDo;')
        self.assertIs(type(vm.variables['t']),PlainTable)
        self.assertEqual(vm.variables['s'],Decimal(10))
        self.assertTrue(validate(vm.variables['t']))
    def test_working_operations(self):
        t=self.table()
        for n in (3,1,2):t.add().set_member('n',Decimal(n))
        t.sort('N');self.assertEqual([r.get_member('N') for r in t.rows],[1,2,3])
        c=t.copy();self.assertEqual(c.total('N'),6)
        t.move(t.rows[0],Decimal(2));self.assertEqual(t.rows[-1].get_member('N'),1)
        t.columns.rename(t.columns.get(0),'X');self.assertEqual(t.total('X'),6)
        t.delete(0);self.assertEqual(t.count(),2)
    def test_opaque_arguments_do_not_call_host_hooks(self):
        class Hostile:
            def __eq__(self,other):raise AssertionError('equality callback')
            def __int__(self):raise AssertionError('integer callback')
        t=self.table();t.add()
        with self.assertRaises(TypeError):t.copy_columns(Hostile())
        with self.assertRaises(TypeError):t.move(0,Hostile())
    def test_foreign_owner_rejected(self):
        a=self.table();b=self.table();r=a.add();r.table=b
        with self.assertRaises(BoundaryViolation):validate(a)
    def test_hostile_dict_keys_rejected_before_lookup(self):
        class Key:
            def __hash__(self):return hash('n')
            def __eq__(self,other):raise AssertionError('callback')
        t=self.table();t.add();t._storage.schema._offsets={Key():0}
        with self.assertRaises(BoundaryViolation):validate(t)
    def test_cells_are_readonly_inspection_snapshot(self):
        t=self.table();r=t.add();c=t.columns.get(0)
        with self.assertRaises(TypeError):r.cells[c]=1
        self.assertIsNone(r.get_member('N'))
    def test_explicit_parked_operations(self):
        t=self.table()
        with self.assertRaises(NotImplementedError):t.group_by('N')
        t.indexes.add('N')
        self.assertEqual(t.indexes.count(), 1)
        self.assertEqual(t._search.builds, 0)
        with self.assertRaises(NotImplementedError):t.columns.move(0,1)
    def test_row_identity_comparison_never_compares_payloads(self):
        class Hostile:
            def __eq__(self,other):raise AssertionError('payload equality')
            def __ne__(self,other):raise AssertionError('payload inequality')
        t=self.table();a=t.add();b=t.add()
        a.set_member('N',Hostile());b.set_member('N',Hostile())
        self.assertFalse(a==b);self.assertTrue(a!=b)
        self.assertTrue(a==a);self.assertFalse(a!=a)
    def test_added_builtin_shadow_is_rejected_without_callback(self):
        import yadinassi.collections.plain_value_table_runtime as runtime
        t=self.table();seen=[]
        with patch.object(runtime,'len',lambda *args:seen.append(args),create=True):
            with self.assertRaises(BoundaryViolation):validate(t)
        self.assertEqual(seen,[])
    def test_deleted_indexed_row_access_rejects(self):
        t=self.table();r=t.add();t.delete(r)
        with self.assertRaises(ValueError):r.get(0)
        with self.assertRaises(ValueError):r.set(0,1)
    def test_bounded_slice_rejects_writes(self):
        t=self.table();r=t.add();t._bounded_slice_read=True
        for action in (lambda:r.set_member('N',1),lambda:r.set(0,1),lambda:t.add(),lambda:t.clear(),lambda:t.columns.add('X')):
            with self.assertRaises(ValueError):action()
        self.assertIsNone(r.get_member('N'));self.assertEqual(t.count(),1)
    def test_growth_limits_fail_before_mutation(self):
        import yadinassi.collections.plain_value_table_runtime as runtime
        t=self.table();t.add()
        with patch.object(runtime,'_MAX_ROWS',1):
            with self.assertRaises(ValueError):t.add()
            with self.assertRaises(ValueError):t.insert(0)
        with patch.object(runtime,'_MAX_COLUMNS',1):
            with self.assertRaises(ValueError):t.columns.add('X')
        with patch.object(runtime,'_MAX_CELLS',1):
            with self.assertRaises(ValueError):t.add()
            with self.assertRaises(ValueError):t.columns.add('X')
        self.assertEqual(t.count(),1);self.assertEqual(t.columns.count(),1)
    def test_retained_rows_follow_schema_and_row_order(self):
        t=self.table();a=t.add();b=t.add()
        a.set_member('N',Decimal(1));b.set_member('N',Decimal(2))
        inserted=t.insert(0);self.assertIs(t.get(1),a)
        t.move(a,1);self.assertIs(t.get(2),a)
        t.delete(inserted);self.assertIs(t.get(1),a)
        t.columns.add('Other');a.set_member('Other',Decimal(7))
        t.columns.rename(t.columns.find('N'),'Renamed')
        self.assertEqual(a.get_member('Renamed'),1)
        self.assertEqual(a.get_member('Other'),7)
        t.columns.delete('Renamed')
        self.assertEqual(a.get_member('Other'),7);self.assertEqual(a.get(0),7)
        self.assertTrue(validate(t))
    def test_copy_has_independent_rows_schema_and_defaults(self):
        t=self.table();a=t.add();a.set_member('N',Decimal(1))
        copied=t.copy();other=copied.get(0)
        self.assertIsNot(a,other);self.assertIsNot(t._storage.schema,copied._storage.schema)
        other.set_member('N',Decimal(9));copied.columns.rename(copied.columns.find('N'),'X')
        copied.columns.add('Extra');copied.add()
        self.assertEqual(a.get_member('N'),1);self.assertEqual(t.columns.count(),1)
        self.assertEqual(t.count(),1);self.assertEqual(other.get_member('X'),9)
        self.assertTrue(validate(t));self.assertTrue(validate(copied))
    def test_removed_payload_reentry_fails_closed_during_schema_transition(self):
        events=[];t=self.table();r=t.add();t.columns.add('Keep')
        class Payload:
            def __del__(self):
                try:validate(t)
                except BoundaryViolation:events.append('rejected')
                else:events.append('admitted')
        r.set_member('N',Payload());t.columns.delete('N')
        self.assertEqual(events,['rejected']);self.assertTrue(validate(t))
    def test_actual_list_row_indexed_byref_and_readonly(self):
        vm=Interpreter();vm.execute('T=New ValueTable;T.Columns.Add("N");R=T.Add();Procedure Change(X) X=7;EndProcedure Change(R[0]);')
        self.assertEqual(vm.variables['r'].get(0),7)
        vm.variables['t']._bounded_slice_read=True
        with self.assertRaises(BSLError):vm.execute('Change(R[0]);')
        self.assertEqual(vm.variables['r'].get(0),7)
    def test_actual_addcolumn_and_named_read_reject_hostile_offsets(self):
        seen=[]
        class Key:
            def __hash__(self):return hash('new')
            def __eq__(self,other):seen.append('eq');raise AssertionError('callback')
        vm=Interpreter();vm.execute('T=New ValueTable;T.Columns.Add("N");R=T.Add();')
        schema=vm.variables['t']._storage.schema
        schema._offsets={Key():0}
        with self.assertRaises(BSLError):vm.execute('T.Columns.Add("new");')
        with self.assertRaises(BSLError):vm.execute('X=R.new;')
        self.assertEqual(seen,[])
