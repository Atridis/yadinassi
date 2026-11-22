"""Live detached row addresses for lexically known synchronous routines."""
from decimal import Decimal
import subprocess
import sys
import unittest
from unittest.mock import patch

from yadinassi import BSLError, Interpreter
from yadinassi.collections.value_tables import BSLValueTable, BSLValueTableRow
from yadinassi.execution.codegen.experimental_naked_boundaries import BoundaryViolation
from yadinassi.execution.direct import python_direct_table_references as refs

_SETUP = ('Var T; T=New ValueTable; T.Columns.Add("X"); T.Columns.Add("Y");'
          'Row=T.Add(); Row.X=1; Row.Y=10;')
_STEP = 'Procedure Step(X,Val N) X=X+N; EndProcedure '


class LocalTableCellTests(unittest.TestCase):
    def vm(self, **options):
        vm = Interpreter(**options)
        self.addCleanup(vm.close)
        return vm

    def test_unused_reference_does_not_read_cell(self):
        vm = self.vm()
        vm.execute(_SETUP)
        plan = vm.prepare('Procedure Ignore(X) EndProcedure Ignore(Row.X); Ignore(Row[0]);')
        # Watch the actually lowered address; a no-op also prevents a
        # vacuous success where the call or address binding was eliminated.
        hits = []
        bind = refs._RowAddress.__init__.__code__
        getter = refs._RowAddress.value.fget.__code__
        def profile(frame, event, _arg):
            if event == 'call' and frame.f_code in (bind, getter):
                hits.append(frame.f_code)
        old = sys.getprofile()
        try:
            sys.setprofile(profile)
            vm.execute_prepared(plan)
        finally:
            sys.setprofile(old)
        self.assertEqual(hits, [bind, bind])

    def test_move_observed_after_binding_for_name_and_position(self):
        for address, expected in (('Row.X',(3,10)), ('Row[0]',(1,12)), ('Row["x"]',(3,10))):
            with self.subTest(address=address):
                vm = self.vm()
                vm.execute_prepared(vm.prepare(_SETUP+_STEP+'''
                    Function MoveColumn()
                        T.Columns.Move("X",1); Return 2;
                    EndFunction
                    Step('''+address+''',MoveColumn()); X=Row.X; Y=Row.Y;
                '''))
                self.assertEqual((vm.variables['x'],vm.variables['y']), expected)

    def test_rename_delete_and_address_formation_order(self):
        for edit in ('T.Columns.Find("X").Name="Z";', 'T.Columns.Delete("X");',
                     'T.Delete(T[0]);'):
            with self.subTest(edit=edit):
                vm = self.vm()
                with self.assertRaises(BSLError):
                    vm.execute(_SETUP+_STEP+'''
                        Function EditColumn()
                            '''+edit+''' Return 3;
                        EndFunction
                        Step(Row.X,EditColumn());
                    ''')
                # The real edit ran; the old address did not silently target
                # another cell or resurrect a deleted row.
                table=vm.variables['t']
                row=vm.variables['row']
                if 'T.Delete' in edit:
                    self.assertTrue(row._deleted)
                    self.assertEqual(len(table.rows),0)
                else:
                    self.assertIsNone(table.columns.find('X'))
                    self.assertEqual(row.get_member('Y'),10)

        vm = self.vm()
        with self.assertRaises(BSLError):
            vm.execute(_SETUP+_STEP+'''
                Function Effect() T.Add(); Return 0; EndFunction
                Step(Row.Missing,Effect());
            ''')
        self.assertEqual(len(vm.variables['t'].rows),1)

    def test_deleted_and_reinserted_name_is_live(self):
        vm=self.vm()
        vm.execute(_SETUP+'''
            Function ReplaceColumn()
                T.Columns.Delete("X"); T.Columns.Add("X"); Return 9;
            EndFunction
            Procedure Store(X,Val Value) X=Value; EndProcedure
            Store(Row.X,ReplaceColumn());
        ''')
        self.assertEqual(list(vm.variables['row']),[10,9])

    def test_readonly_slice_and_named_vs_positional_epoch(self):
        vm=self.vm()
        vm.execute(_SETUP)
        t=vm.variables['t']; kernel=t._storage; schema=kernel.schema
        epochs=lambda:(schema.data_epoch,kernel.epoch)
        name,position=epochs()
        vm.execute(_STEP+'Step(Row.X,1);')
        self.assertEqual(epochs(),(name+1,position))
        vm.execute(_STEP+'Step(Row[0],1);')
        self.assertEqual(epochs(),(name+1,position+1))
        t._bounded_slice_read=True
        vm.execute('Function ReadCell(X) Return X; EndFunction Out=ReadCell(Row[0]);')
        self.assertEqual(vm.variables['out'],3)
        with self.assertRaises(BSLError):vm.execute(_STEP+'Step(Row[0],1);')
        self.assertEqual(epochs(),(name+1,position+1))
        self.assertEqual(vm.variables['row'].get(0),3)

    def test_alias_function_result_and_partial_effects(self):
        vm = self.vm()
        vm.execute(_SETUP+'''
            Function Pair(A,B) A=4; B=B+A; Return A; EndFunction
            Procedure Fail(X) X=22; Raise "after"; EndProcedure
            Answer=Pair(Row.x,Row[0]);
            Try Fail(Row.X); Except EndTry;
        ''')
        self.assertEqual(vm.variables['answer'],8)
        self.assertEqual(vm.variables['row'].get_member('X'),22)

    def test_typed_and_indexed_search_keep_facade_semantics(self):
        for address in ('Row.X','Row[0]'):
            with self.subTest(address=address):
                vm = self.vm()
                vm.execute('T=New ValueTable;'
                           'T.Columns.Add("X",New TypeDescription("Number",New NumberQualifiers(3,1)));'
                           'Row=T.Add(); Row.X=1; T.Indexes.Add("X");')
                vm.execute('Procedure SetValue(X) X=1.23; EndProcedure SetValue('+address+');')
                row=vm.variables['row']
                self.assertEqual(row.get(0),Decimal('1.2'))
                vm.execute('Found=T.FindRows(New Structure("X",1.2));')
                self.assertEqual(vm.variables['found'].items,[row])

    def test_corrupt_selected_owner_or_protocol_fails_without_callbacks(self):
        vm = self.vm()
        vm.execute(_SETUP)
        plan=vm.prepare(_STEP+'Step(Row.X,2);')
        row=vm.variables['row']
        seen=[]
        def hostile(*_args):seen.append('set');raise AssertionError
        with patch.object(BSLValueTableRow,'set_member',hostile):
            with self.assertRaises(BoundaryViolation):vm.execute_prepared(plan)
        old=row.table
        row.table=BSLValueTable()
        with self.assertRaises(BoundaryViolation):vm.execute_prepared(plan)
        row.table=old
        class Key:
            def __hash__(self):return hash('x')
            def __eq__(self,_other):seen.append('eq');raise AssertionError
        offsets=row.schema._offsets
        row.schema._offsets={Key():0}
        try:
            with self.assertRaises(BoundaryViolation):vm.execute_prepared(plan)
        finally:row.schema._offsets=offsets
        self.assertEqual(seen,[])
        self.assertEqual(row.get(0),1)

    def test_bridge_import_does_not_reseal_edited_public_code(self):
        completed=subprocess.run([sys.executable,'-c','''
import sys
from yadinassi import Interpreter
from yadinassi.collections.plain_value_table_runtime import BSLValueTableRow
from yadinassi.execution.codegen.experimental_naked_boundaries import BoundaryViolation
bridge = 'yadinassi.execution.direct.python_direct_table_references'
if bridge in sys.modules:
    raise AssertionError('bridge already imported')
def edited(self, name):
    raise AssertionError('the edited public getter must not run or be admitted')
BSLValueTableRow.get_member.__code__ = edited.__code__
vm=Interpreter()
try:
    vm.execute('T=New ValueTable; T.Columns.Add("X"); Row=T.Add();'
               'Procedure Ignore(X) EndProcedure Ignore(Row.X);')
except BoundaryViolation:
    pass
else:
    raise AssertionError('lazy import blessed edited row protocol')
'''],capture_output=True,text=True,timeout=20)
        self.assertEqual(completed.returncode,0,completed.stderr)

    def test_late_malformed_description_is_not_called(self):
        from yadinassi.execution.direct.python_direct import make_boundary
        vm=self.vm()
        vm.execute(_SETUP)
        context=make_boundary(vm)
        context.enter()
        self.addCleanup(context.leave)
        context._verify_context=False
        row=vm.variables['row']
        address=refs.local_member(context,row,'X')
        seen=[]
        class Hostile:
            def __getattribute__(self,name):seen.append(name);raise AssertionError
        vm.variables['t'].columns.get(0).value_type=Hostile()
        with self.assertRaises(BoundaryViolation):address.set(9)
        self.assertEqual(seen,[])
        self.assertEqual(row.get(0),1)

    def test_corrupted_selected_spelling_cannot_readdress_a_cell(self):
        vm=self.vm()
        vm.execute(_SETUP)
        row=vm.variables['row']
        column=vm.variables['t'].columns.get(0)
        column._name=row.schema._names[0]='Forged'
        for expr in ('Row.X','Row[0]'):
            with self.subTest(expr=expr),self.assertRaises(BoundaryViolation):
                vm.execute(_STEP+'Step('+expr+',1);')
        self.assertEqual(row.get(0),1)

    def test_unrelated_columns_are_not_audited_by_positional_address(self):
        vm=self.vm()
        vm.execute(_SETUP)
        vm.variables['t'].columns._items[1]=object()
        vm.execute(_STEP+'Step(Row[0],2);')
        self.assertEqual(vm.variables['row'].get(0),3)

    def test_dynamic_calls_and_explicit_extension_mode_do_not_select_address(self):
        for extensions in (False,True):
            vm=self.vm(allow_extensions=extensions)
            vm.execute(_SETUP)
            vm.execute(_STEP)
            with patch.object(refs,'_RowAddress',side_effect=AssertionError('lexical fast path')):
                vm.execute('Step(Row.X,1);')
                if extensions:
                    vm.execute(_STEP+'Step(Row[0],1);')
            self.assertEqual(vm.variables['row'].get(0),3 if extensions else 2)
