"""Detached table iteration preserves ownership, row snapshot timing and authority."""
from decimal import Decimal
import unittest
from unittest.mock import patch

from yadinassi import Interpreter, BSLError
from yadinassi.collections.value_tables import BSLValueTable, BSLValueTableRow, BSLValueTableColumnCollection, BSLValueTableColumn
from yadinassi.execution.codegen.experimental_naked_boundaries import BoundaryContext, BoundaryViolation
from yadinassi.execution.direct.python_direct_table_iteration import resolve
from yadinassi.syntax.parser import parse


class DirectTableIterationTests(unittest.TestCase):
    def vm(self):
        vm=Interpreter();self.addCleanup(vm.close);return vm
    def table(self):
        t=BSLValueTable();t.columns.add('X');t.columns.add('Y')
        r=t.add();r.set_member('X',Decimal(1));r.set_member('Y',Decimal(2))
        return t
    def context(self):
        c=BoundaryContext();c.start();return c

    def test_source_ast_prepared_columns_rows_cells_without_vm(self):
        source='''T=New ValueTable;T.Columns.Add("X");T.Columns.Add("Y");R=T.Add();R.X=1;R.Y=2;
Names="";For Each C In T.Columns Do Names=Names+C.Name;EndDo;
Total=0;For Each Row In T Do For Each Cell In Row Do Total=Total+Cell;EndDo;EndDo;'''
        for route in ('source','ast','prepared'):
            vm=self.vm()
            with patch.object(Interpreter,'block',side_effect=AssertionError('VM')),patch.object(Interpreter,'call_routine',side_effect=AssertionError('VM')):
                if route=='source':vm.execute(source)
                elif route=='ast':vm.execute_program(parse(source))
                else:vm.execute_prepared(vm.prepare(source))
            self.assertEqual(vm.variables['names'],'XY');self.assertEqual(vm.variables['total'],3)

    def test_row_cells_snapshot_and_deleted_row_owner_iteration(self):
        source='''T=New ValueTable;T.Columns.Add("X");T.Columns.Add("Y");R=T.Add();R.X=1;R.Y=2;
S=0;For Each V In R Do S=S+V;R.Y=10;EndDo;
Other=T.Add();Other.X=7;T.Delete(R);N=0;For Each Live In R Do N=N+Live.X;EndDo;'''
        vm=self.vm();vm.execute(source)
        self.assertEqual((vm.variables['s'],vm.variables['n']),(3,7))

    def test_live_list_append_and_delete_match_canonical_iterators(self):
        for kind in ('table','columns'):
            for adapted in (False,True):
                t=self.table();value=t if kind=='table' else t.columns
                it=resolve(self.context(),value)() if adapted else iter(value)
                first=next(it)
                if kind=='table':added=t.add()
                else:added=t.columns.add('Z')
                rest=list(it)
                self.assertIs(rest[-1],added)
                self.assertIs(first,t.rows[0] if kind=='table' else t.columns.items[0])

    def test_boundaries_rechecked_before_resolution_invocation_and_each_next(self):
        t=self.table();c=self.context();invoke=resolve(c,t);c.revoke()
        with self.assertRaises(BoundaryViolation):invoke()
        c=self.context();it=resolve(c,t)();next(it);c.revoke()
        with self.assertRaises(BoundaryViolation):next(it)
        c=self.context();it=resolve(c,t.columns)();next(it);t.columns.table=self.table()
        with self.assertRaises(BoundaryViolation):next(it)

    def test_receiver_and_payload_hooks_are_not_invoked(self):
        events=[]
        class Evil:
            def __getattribute__(self,name):events.append(name);raise AssertionError(name)
        t=self.table();r=t.rows[0];value=Evil();r.cells[t.columns.items[0]]=value
        def hook(*args):events.append('hook');raise AssertionError('hook')
        with patch.object(BSLValueTable,'__iter__',hook),patch.object(BSLValueTableRow,'__getattribute__',hook),patch.object(BSLValueTableColumnCollection,'__iter__',hook):
            self.assertEqual(len(list(resolve(self.context(),t)())),1)
            self.assertEqual(len(list(resolve(self.context(),t.columns)())),2)
            self.assertIs(list(resolve(self.context(),r)())[0],value)
        self.assertEqual(events,[])

    def test_foreign_items_subclasses_and_malformed_storage_reject(self):
        class Child(BSLValueTable):pass
        vm=self.vm();vm.variables['t']=Child()
        with self.assertRaises(BoundaryViolation):vm.execute('For Each R In T Do EndDo;')
        for mode in ('row','column','cells','rows_container'):
            t=self.table();other=self.table();value=t
            if mode=='row':t.rows[:]=other.rows
            elif mode=='column':t.columns.items[:]=other.columns.items;value=t.columns
            elif mode=='cells':t.rows[0].cells={other.columns.items[0]:1};value=t.rows[0]
            else:t.rows=iter(t.rows)
            with self.assertRaises(BoundaryViolation):list(resolve(self.context(),value)())

    def test_forged_equality_hooks_are_rejected_without_descriptor_execution(self):
        t=self.table();events=[]
        class EvilDescriptor:
            def __get__(self,*args):events.append('descriptor');raise AssertionError('descriptor')
        with patch.object(BSLValueTableColumn,'__eq__',EvilDescriptor(),create=True):
            with self.assertRaises(BoundaryViolation):resolve(self.context(),t.rows[0])()
        self.assertEqual(events,[])

    def test_bounded_slice_allows_read_iteration_not_mutation(self):
        t=self.table();t._bounded_slice_read=True;vm=self.vm();vm.variables['t']=t
        vm.execute('S=0;For Each R In T Do For Each V In R Do S=S+V;EndDo;EndDo;')
        self.assertEqual(vm.variables['s'],3)
        with self.assertRaises(BSLError):vm.execute('For Each R In T Do R.X=9;EndDo;')
        self.assertEqual(t.rows[0].get_member('X'),1)

    def test_iterated_foreign_catalog_value_does_not_gain_authority(self):
        from pathlib import Path
        from tempfile import TemporaryDirectory
        from yadinassi.configuration.configuration_main_demo import PROFILE,import_main_demo_configuration
        from yadinassi.db.database_context import SQLiteDBContext
        from test_main_demo_configuration import source
        with TemporaryDirectory() as folder:
            context=SQLiteDBContext.create_main_demo(Path(folder)/'db.sqlite',import_main_demo_configuration(source(),profile=PROFILE))
            try:
                owner=Interpreter(database_context=context);other=Interpreter(database_context=context)
                try:
                    owner.execute('A=Catalogs.Склады.CreateItem();A.Description="original";')
                    table=BSLValueTable();table.columns.add('Foreign');table.add().set_member('Foreign',owner.variables['a'])
                    other.variables['t']=table
                    with self.assertRaises(BoundaryViolation):other.execute('For Each R In T Do For Each V In R Do V.Description="bad";EndDo;EndDo;')
                    self.assertEqual(owner.variables['a'].get_member('Description'),'original')
                finally:owner.close();other.close()
            finally:context.close()

    def test_definition_identities_survive_pre_lazy_rebinding(self):
        import subprocess,sys,textwrap
        script=textwrap.dedent('''
            from unittest.mock import patch
            from yadinassi.collections import value_tables as tables
            from yadinassi.execution.codegen.experimental_naked_boundaries import BoundaryContext
            root=tables.BSLValueTable();root.columns.add('X');root.add().set_member('X',7)
            class Fake:pass
            with patch.object(tables,'BSLValueTable',Fake),patch.object(tables,'BSLValueTableColumnCollection',Fake),patch.object(tables,'BSLValueTableRow',Fake):
                from yadinassi.execution.direct.python_direct_table_iteration import owns,resolve
                c=BoundaryContext();c.start()
                if owns(Fake()):raise AssertionError('counterfeit admitted')
                row=next(resolve(c,root)())
                if list(resolve(c,row)())!=[7]:raise AssertionError('lost canonical iteration')
        ''')
        result=subprocess.run([sys.executable]+(['-O'] if not __debug__ else [])+['-c',script],text=True,capture_output=True)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)
