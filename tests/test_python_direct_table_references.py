"""Exact row/column references keep the existing public mutation protocols."""
from decimal import Decimal
from pathlib import Path
import unittest
from unittest.mock import patch
from yadinassi import Interpreter, BSLError
from yadinassi.execution.codegen.direct_boundaries import BoundaryViolation
from yadinassi.syntax.parser import parse
from yadinassi.collections.value_tables import BSLValueTable,BSLValueTableRow

SETUP='T=New ValueTable;C=T.Columns.Add("A");R=T.Add();R.A=1;'


class DirectTableReferenceTests(unittest.TestCase):
    def test_source_ast_prepared_execute_eval_without_vm(self):
        body='Procedure SetValue(X) X=7;EndProcedure Procedure SetTitle(X) X="seven";EndProcedure Function SetResult(X) X=9;Return X;EndFunction SetValue(R.A);SetTitle(C.Title);SetValue(R[0]);'
        for route in ('source','ast','prepared','execute','eval'):
            vm=Interpreter();vm.execute(SETUP)
            with self.subTest(route=route):
                if route=='source':vm.execute(body)
                elif route=='ast':vm.execute_program(parse(body))
                elif route=='prepared':vm.execute_prepared(vm.prepare(body))
                else:
                    vm.execute(body)
                    if route=='execute':vm.execute('Execute("SetValue(R.A);SetTitle(C.Title);SetValue(R[0]);");')
                    else:vm.execute('Answer=Eval("SetResult(R.A)");')
            self.assertEqual(vm.execute('C.Title'),'seven');self.assertEqual(vm.execute('R.A'),9 if route=='eval' else 7)

    def test_live_alias_val_and_write_then_error_match_canonical_control(self):
        vm=Interpreter();vm.execute(SETUP)
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
            # The cells view follows the current owner. Use the raw payload
            # to detect a rejected write even after the row becomes detached.
            self.assertEqual(list(list.__iter__(row)), [1])
            if action=='delete':
                self.assertEqual(old_table.rows, [])
                self.assertTrue(row._deleted)
                with self.assertRaises(ValueError):row.get_member('A')

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
        other=BSLValueTable();other.columns.add('A')
        vm.variables['foreign']=Foreign(other,other._storage.schema,[Decimal(1)])
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

    def test_forged_offset_keys_never_run_hash_or_equality_during_reference(self):
        for stage in ('bind','after_arguments','retained'):
            vm=Interpreter(allow_extensions=True);vm.execute(SETUP+'Procedure Change(X,Y) X=2;EndProcedure');seen=[]
            row=vm.variables['r'];schema=row.schema
            class Key:
                def __hash__(self):seen.append('hash');return hash('a')
                def __eq__(self,other):seen.append('eq');raise AssertionError('hostile key')
            forged={Key():0};seen.clear()
            if stage=='bind':
                schema._offsets=forged
                with self.assertRaises(BoundaryViolation):vm.execute('Change(R.A,0);')
            elif stage=='after_arguments':
                def replace():schema._offsets=forged;return 0
                vm.register_function('Replace',replace)
                with self.assertRaises(BoundaryViolation):vm.execute('Change(R.A,Replace());')
            else:
                refs=[];vm.register_function('Capture',lambda reference:refs.append(reference))
                vm.functions['capture'].reference_parameters=frozenset({0});vm.execute('Capture(R.A);')
                schema._offsets=forged
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
            elif mutation=='items':table.columns._items=Hostile()
            elif mutation=='column':table.columns._items[0]=Hostile()
            elif mutation=='column_owner':column.table=BSLValueTable()
            else:column._name=Hostile()
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

    def test_persistent_routine_reference_writes_preserve_typing_and_indexes(self):
        from yadinassi.execution.direct import python_direct_table_references as refs

        for declaration in (None, 'A', 'B'):
            with self.subTest(declaration=declaration):
                vm=Interpreter()
                self.addCleanup(vm.close)
                vm.execute('T=New ValueTable;'
                           'T.Columns.Add("A",New TypeDescription("Number",New NumberQualifiers(3,1)));'
                           'T.Columns.Add("B");R=T.Add();R.A=1;R.B=2;'
                           'Function Read(Val X) Return X;EndFunction '
                           'Procedure Change(X) X=1.23;EndProcedure Result=Read(R.A);')
                self.assertEqual(vm.variables['result'],1)
                if declaration is not None:
                    vm.execute(f'T.Indexes.Add("{declaration}");')
                vm.execute('Old=T.FindRows(New Structure("A",1));'
                           'Unrelated=T.FindRows(New Structure("B",2));')
                row=vm.variables['r']
                self.assertEqual(vm.variables['old'].items,[row])
                self.assertEqual(vm.variables['unrelated'].items,[row])

                # Separate compilation uses the live public binding protocol,
                # not the compiler-known lexical address of a same-block call.
                with (patch.object(refs,'bind',wraps=refs.bind) as bind,
                      patch.object(refs,'_RowAddress',side_effect=AssertionError('unexpected lexical address'))):
                    vm.execute('Change(R.A);')
                bind.assert_called_once()
                self.assertIs(bind.call_args.args[1],row)
                self.assertEqual(row.get_member('A'),Decimal('1.2'))
                vm.execute('Old=T.FindRows(New Structure("A",1));'
                           'NewMatch=T.FindRows(New Structure("A",1.2));'
                           'Unrelated=T.FindRows(New Structure("B",2));')
                self.assertEqual(vm.variables['old'].items,[])
                self.assertEqual(vm.variables['newmatch'].items,[row])
                self.assertEqual(vm.variables['unrelated'].items,[row])

    def test_reference_checks_only_the_addressed_row(self):
        from yadinassi.execution.direct import python_direct_plain_tables as tables
        vm=Interpreter();self.addCleanup(vm.close)
        vm.execute(SETUP+'For I=1 To 128 Do T.Add();EndDo;')
        plan=vm.prepare('Procedure Change(X) X=X+1;EndProcedure Change(R.A);Change(R[0]);')
        target=vm.variables['r']
        with (patch.object(tables,'row_check',wraps=tables.row_check) as check,
              patch.object(tables,'hooks',side_effect=AssertionError('whole table protocol audit'))):
            vm.execute_prepared(plan)
        self.assertEqual(vm.execute('R.A'),3)
        # Address binding, actual read, and actual write each check their
        # own row, never the unrelated inventory or the whole protocol.
        self.assertEqual(check.call_count,6)
        self.assertTrue(all(call.args[0] is target for call in check.call_args_list))

    def test_reference_does_not_admit_other_rows_or_remove_iteration_validation(self):
        from yadinassi.execution.direct import python_direct_plain_tables as tables
        vm=Interpreter();self.addCleanup(vm.close)
        vm.execute(SETUP+'T.Add();')
        table=vm.variables['t']
        foreign=BSLValueTable();foreign.columns.add('A')
        table.rows[1]=foreign.add()
        vm.execute('Procedure Change(X) X=X+1;EndProcedure Change(R.A);')
        self.assertEqual(vm.execute('R.A'),2)
        with self.assertRaises(BoundaryViolation):
            tables.validate(table)

    def test_row_reference_observes_readonly_after_arguments(self):
        vm=Interpreter(allow_extensions=True);self.addCleanup(vm.close)
        vm.execute(SETUP+'Procedure Change(X,Y) X=Y;EndProcedure')
        table=vm.variables['t']
        def make_readonly():
            table._bounded_slice_read=True
            return Decimal(2)
        vm.register_function('MakeReadonly',make_readonly)
        for address in ('R.A','R[0]'):
            table._bounded_slice_read=False
            with self.subTest(address=address),self.assertRaises(BSLError):
                vm.execute('Change('+address+',MakeReadonly());')
            self.assertTrue(table._bounded_slice_read)
            self.assertEqual(vm.variables['r'].get_member('A'),1)

    def test_existing_native_table_checkpoint_preserved(self):
        from scripts.smoke_test import table_command_checkpoint,TABLE_COMMAND_LABELS
        root=Path(__file__).resolve().parents[1]
        source=(root/'integrational_tests/tests/collections.bsl').read_text(encoding='utf-8-sig')
        expected=(root/'tests/fixtures/native_windows/collections.out').read_text(encoding='utf-8-sig')
        program,expected=table_command_checkpoint(source,expected)
        output=[];Interpreter(output=output.append).execute(program)
        self.assertEqual('\n'.join(output)+'\n',expected);self.assertEqual(len(TABLE_COMMAND_LABELS),8)
