"""Exact row/column references keep the existing public mutation protocols."""
from decimal import Decimal
from pathlib import Path
import unittest
from unittest.mock import patch
from yadinassi import Interpreter, BSLError
from yadinassi.execution.codegen.experimental_naked_boundaries import BoundaryViolation
from yadinassi.syntax.parser import parse
from yadinassi.collections.value_tables import BSLValueTable,BSLValueTableRow

SETUP='T=New ValueTable;C=T.Columns.Add("A");R=T.Add();R.A=1;'


class DirectTableReferenceTests(unittest.TestCase):
    def test_source_ast_prepared_execute_eval_without_vm(self):
        body='Procedure SetValue(X) X=7;EndProcedure Procedure SetTitle(X) X="seven";EndProcedure Function SetResult(X) X=9;Return X;EndFunction SetValue(R.A);SetTitle(C.Title);SetValue(R[0]);'
        for route in ('source','ast','prepared','execute','eval'):
            vm=Interpreter();vm.execute(SETUP)
            with self.subTest(route=route),patch.object(Interpreter,'block',side_effect=AssertionError('VM')),patch.object(Interpreter,'call_routine',side_effect=AssertionError('VM')):
                if route=='source':vm.execute(body)
                elif route=='ast':vm.execute_program(parse(body))
                elif route=='prepared':vm.execute_prepared(vm.prepare(body))
                else:
                    vm.execute(body)
                    if route=='execute':vm.execute('Execute("SetValue(R.A);SetTitle(C.Title);SetValue(R[0]);");')
                    else:vm.execute('Answer=Eval("SetResult(R.A)");')
            self.assertEqual(vm.execute('C.Title'),'seven');self.assertEqual(vm.execute('R.A'),9 if route=='eval' else 7)

    def test_live_alias_val_and_write_then_error_match_canonical_control(self):
        for backend in ('python-direct','compiled-strict'):
            vm=Interpreter(execution_backend=backend);vm.execute(SETUP)
            vm.execute('Procedure Pair(X,Y) X=3;Y=Y+X;EndProcedure Procedure ValOnly(Val X) X=99;EndProcedure Procedure Fail(X) X=11;Raise "after";EndProcedure Pair(R.A,R[0]);ValOnly(R.A);Before=R.A;Try Fail(R.A);Except EndTry;After=R.A;')
            self.assertEqual((vm.variables['before'],vm.variables['after']),(6,11))

    def test_binding_failure_precedes_later_argument_effects(self):
        vm=Interpreter(allow_extensions=True);vm.execute(SETUP+'Procedure Change(X,Y) X=2;EndProcedure');seen=[]
        vm.register_function('Effect',lambda:seen.append('later'))
        for address in ('R.Missing','R[4]','C.NoSuchField','R.cells','C.table'):
            with self.subTest(address=address),self.assertRaises(BSLError):vm.execute('Change('+address+',Effect());')
            self.assertEqual(seen,[])
        vm.execute('T.Delete(R);')
        with self.assertRaises(BSLError):vm.execute('Change(R.A,Effect());')
        self.assertEqual(seen,[])

    def test_readonly_reference_is_readable_and_fails_only_when_written(self):
        vm=Interpreter(allow_extensions=True);vm.execute(SETUP+'Function Read(X) Return X;EndFunction Procedure Write(X,Y) X=Y;EndProcedure')
        vm.execute('Q=Read(C.ValueType);');self.assertIs(vm.variables['q'],vm.variables['c'].value_type)
        seen=[];vm.register_function('Effect',lambda:seen.append('rhs') or 2)
        with self.assertRaises(BSLError):vm.execute('Write(C.ValueType,Effect());')
        self.assertEqual(seen,['rhs'])

    def test_owner_replacement_deleted_rows_and_closed_runtime(self):
        for action in ('owner','delete','close'):
            vm=Interpreter(allow_extensions=True);vm.execute(SETUP+'Procedure Change(X,Y) X=2;EndProcedure');row=vm.variables['r'];old_table=row.table
            def effect():
                if action=='owner':row.table=BSLValueTable()
                elif action=='delete':old_table.delete(row)
                else:vm.close()
                return 0
            vm.register_function('Effect',effect)
            error=BSLError if action=='delete' else BoundaryViolation
            with self.subTest(action=action),self.assertRaises(error):vm.execute('Change(R.A,Effect());')
            self.assertEqual(row.cells,{} ) if action=='delete' else self.assertEqual(next(iter(row.cells.values())),1)

    def test_retained_host_references_recheck_owner_and_lifetime(self):
        for address in ('R.A','R[0]','C.Title'):
            vm=Interpreter(allow_extensions=True);vm.execute(SETUP);refs=[]
            vm.register_function('Capture',lambda reference:refs.append(reference))
            vm.functions['capture'].reference_parameters=frozenset({0})
            vm.execute('Capture('+address+');');ref=refs[0]
            ref.set('four' if address=='C.Title' else Decimal(4));self.assertEqual(ref.get(),'four' if address=='C.Title' else 4)
            vm.close()
            for operation in (ref.get,lambda:ref.set(5)):
                with self.assertRaises(BoundaryViolation):operation()

    def test_slice_guard_and_foreign_subclass_are_not_bypassed(self):
        vm=Interpreter();vm.execute(SETUP+'Procedure Change(X) X=2;EndProcedure');table=vm.variables['t'];table._bounded_slice_read=True
        with self.assertRaises(BSLError):vm.execute('Change(R.A);')
        self.assertEqual(vm.variables['r'].get_index('A'),1)
        calls=[]
        class Foreign(BSLValueTableRow):
            def get_member(self,name):calls.append('get');raise AssertionError
        vm.variables['foreign']=Foreign(BSLValueTable())
        with self.assertRaises(BoundaryViolation):vm.execute('Change(Foreign.A);')
        self.assertEqual(calls,[])

    def test_receiver_and_index_evaluated_once_left_to_right(self):
        vm=Interpreter(allow_extensions=True);vm.execute(SETUP+'Procedure Change(X,Y) X=Y;EndProcedure');seen=[]
        vm.register_function('Receiver',lambda:seen.append('receiver') or vm.variables['r'])
        vm.register_function('Index',lambda:seen.append('index') or Decimal(0))
        vm.register_function('Value',lambda:seen.append('value') or 8)
        vm.execute('Change(Receiver()[Index()],Value());')
        self.assertEqual(seen,['receiver','index','value']);self.assertEqual(vm.execute('R.A'),8)

    def test_late_receiver_hooks_and_instance_overrides_are_rejected(self):
        for mode in ('class','instance'):
            vm=Interpreter(allow_extensions=True);vm.execute(SETUP);refs=[];seen=[]
            vm.register_function('Capture',lambda reference:refs.append(reference))
            vm.functions['capture'].reference_parameters=frozenset({0})
            vm.execute('Capture(R.A);');row=vm.variables['r']
            def hostile(*args):seen.append('hook');raise AssertionError
            if mode=='class':
                with patch.object(BSLValueTableRow,'set_member',hostile):
                    with self.assertRaises(BoundaryViolation):refs[0].set(2)
            else:
                row.set_member=hostile
                with self.assertRaises(BoundaryViolation):refs[0].set(2)
            self.assertEqual(seen,[]);self.assertEqual(next(iter(row.cells.values())),1)

    def test_hostile_index_does_not_gain_protocol_and_retained_owner_is_fixed(self):
        vm=Interpreter(allow_extensions=True);vm.execute(SETUP+'Procedure Change(X) X=2;EndProcedure');seen=[]
        class Hostile:
            def __index__(self):seen.append('index');raise AssertionError
            def __hash__(self):seen.append('hash');raise AssertionError
            def __eq__(self,other):seen.append('eq');raise AssertionError
        vm.variables['badindex']=Hostile()
        with self.assertRaises(BSLError):vm.execute('Change(R[BadIndex]);')
        self.assertEqual(seen,[])
        refs=[];vm.register_function('Capture',lambda reference:refs.append(reference))
        vm.functions['capture'].reference_parameters=frozenset({0});vm.execute('Capture(R.A);')
        vm.variables['r'].table=BSLValueTable()
        for action in (refs[0].get,lambda:refs[0].set(2)):
            with self.assertRaises(BoundaryViolation):action()

    def test_forged_cell_keys_never_run_hash_or_equality_during_reference(self):
        for stage in ('bind','after_arguments','retained'):
            vm=Interpreter(allow_extensions=True);vm.execute(SETUP+'Procedure Change(X,Y) X=2;EndProcedure');seen=[]
            row=vm.variables['r'];column=vm.variables['c']
            class Key:
                def __hash__(self):return hash(column)
                def __eq__(self,other):seen.append('eq');raise AssertionError('hostile key')
            forged={Key():Decimal(1)}
            if stage=='bind':
                row.cells=forged
                with self.assertRaises(BoundaryViolation):vm.execute('Change(R.A,0);')
            elif stage=='after_arguments':
                def replace():row.cells=forged;return 0
                vm.register_function('Replace',replace)
                with self.assertRaises(BoundaryViolation):vm.execute('Change(R.A,Replace());')
            else:
                refs=[];vm.register_function('Capture',lambda reference:refs.append(reference))
                vm.functions['capture'].reference_parameters=frozenset({0});vm.execute('Capture(R.A);')
                row.cells=forged
                for action in (refs[0].get,lambda:refs[0].set(2)):
                    with self.assertRaises(BoundaryViolation):action()
            self.assertEqual(seen,[])

    def test_forged_column_graph_is_rejected_before_public_lookup(self):
        for mutation in ('collection','items','column','column_owner','column_name'):
            vm=Interpreter();vm.execute(SETUP+'Procedure Change(X) X=2;EndProcedure');seen=[]
            class Hostile:
                def __getattribute__(self,name):seen.append(name);raise AssertionError('hostile field')
                def __iter__(self):seen.append('iter');raise AssertionError
            table=vm.variables['t'];column=vm.variables['c']
            if mutation=='collection':table.columns=Hostile()
            elif mutation=='items':table.columns.items=Hostile()
            elif mutation=='column':table.columns.items=[Hostile()]
            elif mutation=='column_owner':column.table=BSLValueTable()
            else:column.name=Hostile()
            with self.subTest(mutation=mutation),self.assertRaises(BoundaryViolation):vm.execute('Change(R.A);')
            self.assertEqual(seen,[])

    def test_write_delegate_replacements_reject_without_host_hooks(self):
        for delegate in ('indexes','description'):
            for stage in ('after_arguments','retained'):
                vm=Interpreter(allow_extensions=True);vm.execute(SETUP+'Procedure Change(X,Y) X=2;EndProcedure');seen=[]
                row=vm.variables['r'];table=vm.variables['t'];column=vm.variables['c']
                class Hostile:
                    def __getattribute__(self,name):seen.append(name);raise AssertionError('hostile delegate')
                def replace():
                    if delegate=='indexes':table.indexes=Hostile()
                    else:column.value_type=Hostile()
                    return 0
                if stage=='after_arguments':
                    vm.register_function('Replace',replace)
                    with self.assertRaises(BoundaryViolation):vm.execute('Change(R.A,Replace());')
                else:
                    refs=[];vm.register_function('Capture',lambda ref:refs.append(ref))
                    vm.functions['capture'].reference_parameters=frozenset({0});vm.execute('Capture(R.A);');replace()
                    with self.assertRaises(BoundaryViolation):refs[0].set(2)
                self.assertEqual(seen,[]);self.assertEqual(next(iter(row.cells.values())),1)

    def test_typed_and_indexed_reference_writes_are_explicitly_unsupported(self):
        for kind in ('typed','indexed'):
            vm=Interpreter()
            if kind=='typed':vm.execute('T=New ValueTable;C=T.Columns.Add("A",New TypeDescription("Number"));R=T.Add();R.A=1;')
            else:vm.execute(SETUP+'T.Indexes.Add("A");')
            vm.execute('Function Read(Val X) Return X;EndFunction Procedure Change(X) X=2;EndProcedure Result=Read(R.A);')
            self.assertEqual(vm.variables['result'],1)
            with self.assertRaisesRegex(BoundaryViolation,kind):vm.execute('Change(R.A);')
            self.assertEqual(vm.execute('R.A'),1)
            vm.execute('R.A=3;');self.assertEqual(vm.execute('R.A'),3)

    def test_existing_native_table_checkpoint_preserved(self):
        from scripts.smoke_test import table_command_checkpoint,TABLE_COMMAND_LABELS
        root=Path(__file__).resolve().parents[1]
        source=(root/'integrational_tests/tests/collections.bsl').read_text(encoding='utf-8-sig')
        expected=(root/'tests/fixtures/native_windows/collections.out').read_text(encoding='utf-8-sig')
        program,expected=table_command_checkpoint(source,expected)
        output=[];Interpreter(output=output.append).execute(program)
        self.assertEqual('\n'.join(output)+'\n',expected);self.assertEqual(len(TABLE_COMMAND_LABELS),8)
