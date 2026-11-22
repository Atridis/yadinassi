"""Closed module facts follow source-order branch reachability."""
import unittest

from yadinassi import BSLError, Interpreter
from yadinassi.execution.direct.python_direct import PythonDirectUnsupported


TABLE = '''
T=New ValueTable;
T.Columns.Add("X");
For I=1 To 20 Do Row=T.Add(); Row.X=I; EndDo;
R=0;
For I=0 To 19 Do R=R+T[I].X; EndDo;
'''


class ModuleReachabilityTests(unittest.TestCase):
    def vm(self):
        vm=Interpreter()
        self.addCleanup(vm.close)
        return vm

    def test_literal_false_and_ordered_else_if_keep_table_loop_closed(self):
        vm=self.vm()
        plan=vm.prepare(TABLE+'''
            If (False) Then
                Z=T.Copy();
            ElsIf ((True)) Then
                N=T.Count();
            ElsIf Eval("True") Then
                Z=New Array;
            Else
                Execute("Z=1");
            EndIf;
        ''')
        generated=plan._plan.generated_source
        self.assertIn('_PrivateTable()',generated)
        self.assertIn('_raw_table_value',generated)
        # The skipped arms still go through the compiler; they are emitted
        # with the generic lowering but cannot arm live synchronization.
        self.assertIn('_execute_fragment',generated)
        self.assertNotIn('_reload_module',generated)
        vm.execute_prepared(plan)
        self.assertEqual((vm.variables['r'],vm.variables['n']),(210,20))
        self.assertNotIn('z',vm.variables)

    def test_exact_scalar_expression_arms_keep_table_loop_closed(self):
        for condition in ('Not True', '1=2', 'Not (Not (1.00=2))',
                          '(1.25) >= (1.50)', 'True <= False'):
            with self.subTest(condition=condition):
                vm=self.vm()
                plan=vm.prepare(TABLE+f'''
                    If {condition} Then
                        Z=T.Copy();
                    ElsIf Not (1=2) Then
                        N=T.Count();
                    ElsIf Eval("True") Then
                        Z=T.Copy();
                    EndIf;
                ''')
                self.assertIn('_PrivateTable()',plan._plan.generated_source)
                self.assertIn('_raw_table_value',plan._plan.generated_source)
                self.assertNotIn('_reload_module',plan._plan.generated_source)
                vm.execute_prepared(plan)
                self.assertEqual((vm.variables['r'],vm.variables['n']),(210,20))
                self.assertNotIn('z',vm.variables)

    def test_unknown_and_faulting_scalar_operations_are_not_run_by_proof(self):
        for condition,succeeds in (('Eval("False")',True), ('1=0/0',False),
                                   ('"a"<1',False)):
            with self.subTest(condition=condition):
                vm=self.vm()
                plan=vm.prepare(TABLE+f'If {condition} Then Z=T.Copy(); EndIf;')
                self.assertNotIn('_PrivateTable()',plan._plan.generated_source)
                if succeeds:
                    vm.execute_prepared(plan)
                else:
                    with self.assertRaises(BSLError):
                        vm.execute_prepared(plan)
                self.assertEqual(vm.variables['r'],210)
                self.assertNotIn('z',vm.variables)

    def test_expression_proof_preserves_dead_source_validation(self):
        vm=self.vm()
        for suffix in ('If Not True Then A=New UnavailableConstructor; EndIf;',
                       'If 1=1 Then N=1; ElsIf New UnavailableConstructor Then N=2; EndIf;'):
            with self.subTest(suffix=suffix), self.assertRaises(PythonDirectUnsupported):
                vm.prepare(TABLE+suffix)
        with self.assertRaises(BSLError):
            vm.prepare(TABLE+'If 1=2 Then Break; EndIf;')
        with self.assertRaises(BSLError):
            vm.prepare('Goto ~Inner; If 1=2 Then ~Inner: R=1; EndIf;')
        self.assertNotIn('t',vm.variables)

    def test_reachable_or_unknown_effect_keeps_generic_route(self):
        for condition in ('True','Not False','1=1','Gate','0'):
            with self.subTest(condition=condition):
                vm=self.vm()
                vm.variables['gate']=True
                plan=vm.prepare(TABLE+'If '+condition+' Then Z=T.Copy(); EndIf;')
                self.assertNotIn('_PrivateTable()',plan._plan.generated_source)
                vm.execute_prepared(plan)
                self.assertEqual(vm.variables['r'],210)
                if condition=='0':
                    self.assertNotIn('z',vm.variables)
                else:
                    self.assertIsNot(vm.variables['z'],vm.variables['t'])
                    self.assertEqual(vm.variables['z'].count(),20)

    def test_unreachable_module_counter_write_does_not_disable_range(self):
        vm=self.vm()
        plan=vm.prepare('''
            R=0;
            For I=1 To 10 Do
                If False Then I=0; EndIf;
                R=R+I;
            EndDo;
        ''')
        self.assertIn('in range(1, 11):',plan._plan.generated_source)
        vm.execute_prepared(plan)
        self.assertEqual((vm.variables['r'],vm.variables['i']),(55,11))

    def test_dead_source_is_still_checked_before_effects(self):
        vm=self.vm()
        with self.assertRaises(PythonDirectUnsupported):
            vm.execute(TABLE+'If False Then A=New UnavailableConstructor; EndIf;')
        self.assertNotIn('t',vm.variables)

    def test_goto_keeps_existing_lexical_rules(self):
        vm=self.vm()
        plan=vm.prepare('''
            R=1;
            If False Then
                Goto ~Done;
            EndIf;
            R=2;
            ~Done:
            R=R+3;
        ''')
        vm.execute_prepared(plan)
        self.assertEqual(vm.variables['r'],5)
        with self.assertRaises(BSLError):
            vm.prepare('Goto ~Inner; If False Then ~Inner: R=1; EndIf;')


ASYNC = '''
Async Function Deferred()
    Message("start");
    X=Await 1;
    Message("resume");
    Return X+6;
EndFunction
'''


class ModuleDeclarationReachabilityTests(unittest.TestCase):
    def vm(self):
        output=[]
        vm=Interpreter(output=output.append)
        self.addCleanup(vm.close)
        return vm,output

    def test_uncalled_routines_keep_closed_module_and_publish_exports(self):
        for declaration in (ASYNC, 'Procedure Deferred() Message("start"); EndProcedure'):
            with self.subTest(declaration=declaration):
                vm,output=self.vm()
                plan=vm.prepare(TABLE+declaration)
                self.assertIn('_PrivateTable()',plan._plan.generated_source)
                vm.execute_prepared(plan)
                self.assertEqual(vm.variables['r'],210)
                self.assertEqual(output,[])
                if 'Async' in declaration:
                    self.assertIn('_AwaitRequest',plan._plan.generated_source)
                    vm.execute('P=Deferred(); Message("caller");')
                    self.assertEqual(output,['start','caller','resume'])
                    self.assertEqual(vm.variables['p'].result,7)
                else:
                    vm.execute('Deferred();')
                    self.assertEqual(output,['start'])

    def test_reachable_direct_transitive_and_opaque_calls_stay_generic(self):
        for suffix in ('P=Deferred(); Message("caller");',
                       'Procedure StartIt() Deferred(); EndProcedure StartIt(); Message("caller");',
                       'Execute("Deferred()"); Message("caller");'):
            with self.subTest(suffix=suffix):
                vm,output=self.vm()
                plan=vm.prepare(TABLE+ASYNC+suffix)
                self.assertNotIn('_PrivateTable()',plan._plan.generated_source)
                self.assertNotIn('_publish_module',plan._plan.generated_source)
                vm.execute_prepared(plan)
                self.assertEqual(vm.variables['r'],210)
                self.assertEqual(output,['start','caller','resume'])

    def test_dead_async_call_does_not_start_or_remove_any_declaration(self):
        vm,output=self.vm()
        source=TABLE+ASYNC+'''
            Function Increment(Val N) Return N+1; EndFunction
            If True Then M=Increment(2); Else Deferred(); EndIf;
        '''
        plan=vm.prepare(source)
        self.assertIn('_PrivateTable()',plan._plan.generated_source)
        vm.execute_prepared(plan)
        self.assertEqual((vm.variables['r'],vm.variables['m']),(210,3))
        self.assertEqual(output,[])
        vm.execute('P=Deferred();')
        self.assertEqual(output,['start','resume'])


class LiveTablePrefixTests(unittest.TestCase):
    def vm(self, **kwargs):
        vm=Interpreter(**kwargs)
        self.addCleanup(vm.close)
        return vm

    def test_warm_repeats_keep_one_table_origin_and_same_aliases(self):
        from unittest.mock import Mock, patch

        vm=self.vm()
        plan=vm.prepare(TABLE+'''
            Alias=T;
            Snapshot=T.Copy();
            Alias[0].X=99;
            N=Snapshot[0].X;
        ''')
        namespace=plan._plan.function.__globals__
        admitted=Mock(wraps=namespace['_fresh_closed_table'])
        previous=None
        with patch.dict(namespace,_fresh_closed_table=admitted):
            for _ in range(3):
                vm.execute_prepared(plan)
                table=vm.variables['t']
                self.assertIsNot(table,previous)
                self.assertIs(vm.variables['alias'],table)
                self.assertEqual((table.get_index(0).get_member('X'),vm.variables['n']),(99,1))
                self.assertIsNot(vm.variables['snapshot'],table)
                previous=table
        self.assertEqual(admitted.call_count,3)
        self.assertEqual(len({id(call.args[1]) for call in admitted.call_args_list}),3)

    def test_exact_copy_does_not_move_module_publication_before_finalizer(self):
        from decimal import Decimal

        vm=self.vm()
        observed=[]
        class Retired:
            def __del__(self):
                try:
                    state=vm.variables
                    observed.append((state['t'] is state['alias'], state['snapshot'].count()))
                    state['t'].get_index(0).set_member('X',Decimal(999))
                except Exception as error:
                    observed.append(type(error))
        vm.variables['zz']=Retired()
        plan=vm.prepare(TABLE+'Alias=T; ZZ=1; Snapshot=T.Copy();')
        self.assertIn('_fresh_closed_table',plan._plan.generated_source)
        vm.execute_prepared(plan)
        self.assertEqual(observed,[(True,20)])
        self.assertEqual(vm.variables['t'].get_index(0).get_member('X'),999)
        self.assertEqual(vm.variables['snapshot'].get_index(0).get_member('X'),1)

    def test_actual_observer_and_execute_see_and_can_replace_registers(self):
        from decimal import Decimal
        from yadinassi.collections.value_tables import BSLValueTable

        observed=[]
        replacement=BSLValueTable()
        def output(text):
            self.assertEqual(text,'observe')
            state=vm.variables
            observed.append((state['t'] is state['alias'],type(state['r']),state['r']))
            state['r']=Decimal(8)
            state['t']=replacement
        vm=self.vm(output=output)
        plan=vm.prepare(TABLE+'''
            Alias=T;
            Message("observe");
            Execute("R=R+7; Alias[0].X=18;");
            N=T.Count();
        ''')
        vm.execute_prepared(plan)
        self.assertEqual(observed,[(True,Decimal,210)])
        self.assertEqual((vm.variables['r'],vm.variables['n']),(15,0))
        self.assertIs(vm.variables['t'],replacement)
        self.assertEqual(vm.variables['alias'].get_index(0).get_member('X'),18)

    def test_declined_origin_uses_same_generic_path_without_retry(self):
        from unittest.mock import Mock, patch

        vm=self.vm()
        plan=vm.prepare(TABLE+'Snapshot=T.Copy();')
        namespace=plan._plan.function.__globals__
        declined=Mock(return_value=False)
        with patch.dict(namespace,_fresh_closed_table=declined):
            vm.execute_prepared(plan)
        declined.assert_called_once()
        self.assertEqual((vm.variables['r'],vm.variables['snapshot'].count()),(210,20))
        self.assertIs(declined.call_args.args[1],vm.variables['t'])

    def test_failed_prefix_and_suffix_keep_only_completed_effects(self):
        for source, row_count, value in (
                (TABLE.replace('Row.X=I','Row.Missing=I')+'Snapshot=T.Copy();',1,None),
                (TABLE+'Raise "suffix"; Snapshot=T.Copy();',20,210)):
            with self.subTest(row_count=row_count):
                vm=self.vm()
                plan=vm.prepare(source)
                self.assertIn('_fresh_closed_table',plan._plan.generated_source)
                with self.assertRaises(BSLError):
                    vm.execute_prepared(plan)
                self.assertEqual((vm.variables['t'].count(),vm.variables.get('r')),(row_count,value))
                self.assertNotIn('snapshot',vm.variables)

    def test_unassigned_cell_uses_ordinary_bsl_truth_and_order(self):
        for condition in ('Row.X', 'Row.X < 1'):
            with self.subTest(condition=condition):
                vm=self.vm()
                plan=vm.prepare(TABLE.split('R=0;')[0].replace('Row.X=I;', '')+f'''
                    If {condition} Then R=99; EndIf;
                    Snapshot=T.Copy();
                ''')
                self.assertIn('_fresh_closed_table',plan._plan.generated_source)
                with self.assertRaises(BSLError):
                    vm.execute_prepared(plan)
                self.assertEqual(vm.variables['t'].count(),20)
                self.assertIsNone(vm.variables['row'].get_member('X'))
                self.assertNotIn('r',vm.variables)
                self.assertNotIn('snapshot',vm.variables)

    def test_goto_extensions_and_second_constructor_are_not_specialized(self):
        for vm,suffix in ((self.vm(),'Goto ~Done; ~Done: Snapshot=T.Copy();'),
                          (self.vm(allow_extensions=True),'Snapshot=T.Copy();'),
                          (self.vm(),'Snapshot=T.Copy();')):
            with self.subTest(extension=vm.allow_extensions,suffix=suffix):
                prefix=TABLE if vm.allow_extensions or suffix.startswith('Goto') else TABLE.replace(
                    'T.Columns.Add("X");','U=New ValueTable; T.Columns.Add("X");')
                plan=vm.prepare(prefix+suffix)
                self.assertNotIn('_fresh_closed_table',plan._plan.generated_source)
                vm.execute_prepared(plan)
                self.assertEqual(vm.variables['snapshot'].count(),20)
