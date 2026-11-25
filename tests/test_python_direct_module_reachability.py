"""Control flow, module state and table effects on the common direct path."""
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
        self.assertNotIn('_PrivateTable()',generated)
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
                self.assertNotIn('_PrivateTable()',plan._plan.generated_source)
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
                self.assertNotIn('_PrivateTable()',plan._plan.generated_source)
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
        self.assertNotIn('_PrivateTable()',plan._plan.generated_source)
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

    def test_scalar_prefix_and_declarations_do_not_hide_fresh_origin(self):
        for prefix in ('R=0;', 'Var Z;', 'Var Z; R=0;'):
            with self.subTest(prefix=prefix):
                source=prefix+TABLE+'Z=T.Copy(); R'
                vm=self.vm()
                plan=vm.prepare(source)
                self.assertNotIn('_fresh_closed_table',plan._plan.generated_source)
                self.assertEqual(vm.execute_prepared(plan),210)
                self.assertEqual((vm.variables['z'].count(),vm.execute(source)),(20,210))

    def test_literal_short_circuit_and_arithmetic_keep_proved_table_access(self):
        for condition in ('False And (1/0=0)', '1+1=3', 'Not (True Or (1/0=0))'):
            with self.subTest(condition=condition):
                source=TABLE.replace('For I=1', f'If {condition} Then Z=T.Copy(); EndIf; For I=1')+'R'
                vm=self.vm()
                plan=vm.prepare(source)
                self.assertNotIn('_fresh_closed_table',plan._plan.generated_source)
                self.assertEqual((vm.execute_prepared(plan),vm.execute(source)),(210,210))
                self.assertNotIn('z',vm.variables)

    def test_invariant_branch_proof_keeps_runtime_decimal_fault(self):
        from decimal import Clamped, localcontext

        source=TABLE.replace('For I=1', 'If 1+1=3 Then Z=T.Copy(); EndIf; For I=1')+'R'
        vm=self.vm(); plan=vm.prepare(source)
        with localcontext() as ctx:
            ctx.Emax=0; ctx.clamp=1; ctx.traps[Clamped]=True
            with self.assertRaises((BSLError,Clamped)):
                vm.execute_prepared(plan)
        self.assertEqual(vm.variables['t'].count(),0)

    def test_existing_integer_test_does_not_start_using_decimal_context(self):
        from decimal import Clamped, localcontext

        vm=self.vm()
        source='R=0; If 1+1=3 Then R=1; EndIf; R'
        with localcontext() as ctx:
            ctx.Emax=0; ctx.clamp=1; ctx.traps[Clamped]=True
            self.assertEqual(vm.execute(source),0)

    def test_default_and_qualified_columns_keep_original_conversions(self):
        from decimal import Decimal

        for column_type, body, expected in (
                ('Undefined','Row.X=I',Decimal(210)),
                ('New TypeDescription("Number")','Row.X=I',Decimal(210)),
                ('New TypeDescription("Number",New NumberQualifiers(2,0))',
                 'Row.X=I+0.6',Decimal(230))):
            with self.subTest(column_type=column_type):
                source=TABLE.replace('Add("X")',f'Add("X", {column_type})').replace('Row.X=I',body)+'R'
                vm=self.vm()
                plan=vm.prepare(source)
                self.assertNotIn('_fresh_closed_table',plan._plan.generated_source)
                self.assertEqual(vm.execute_prepared(plan),expected)
                self.assertEqual(vm.execute(source),expected)
                self.assertIs(type(vm.variables['r']),Decimal)

    def test_numeric_setup_bindings_select_the_same_real_fast_loop(self):
        loop=TABLE.split('For I=1',1)[1]
        cases=(
            ('Kind=New TypeDescription("Number"); T.Columns.Add("X",Kind);','',0),
            ('C=T.Columns; C.Add("X",New TypeDescription("Number"));','',0),
            ('If True Then T.Columns.Add("X",New TypeDescription("Number")); Else Raise "dead"; EndIf;','',0),
            ('T.Columns.Add("X",New TypeDescription("Number"),"Header",10);','Header',10),
            ('Kind=New TypeDescription("Number"); C=T.Columns; '
             'If True Then C.Add("X",Kind,"Header",10); EndIf;','Header',10),
            ('Kind=New TypeDescription("Number"); C=T.Columns; '
             'C.Add("A",Kind); If False Then Raise "dead"; ElsIf True Then C.Add("X",Kind, ,10); EndIf;','',10),
        )
        for setup,title,width in cases:
            with self.subTest(setup=setup):
                source='T=New ValueTable; '+setup+' For I=1'+loop+'R'
                vm=self.vm()
                plan=vm.prepare(source)
                self.assertNotIn('_fresh_closed_table',plan._plan.generated_source)
                self.assertEqual(vm.execute_prepared(plan),210)
                column=vm.variables['t'].columns.find('X')
                self.assertEqual((column.title,column.width),(title,width))
                self.assertEqual(vm.execute(source),210)

    def test_dynamic_descriptor_and_escaped_alias_do_not_prove_a_loop(self):
        from yadinassi.types.type_descriptions import BSLTypeDescription

        loop=TABLE.split('For I=1',1)[1]
        effects=[]
        def observe(text):
            effects.append((text,vm.variables['c'] is vm.variables['t'].columns))
            vm.variables['kind']=BSLTypeDescription('Number')

        vm=self.vm(output=observe)
        vm.variables['kind']=BSLTypeDescription('Number')
        for setup in ('C=T.Columns; C.Add("X",Kind);',
                      'Kind=New TypeDescription("Number"); C=T.Columns; Message("before"); C.Add("X",Kind);'):
            with self.subTest(setup=setup):
                source='T=New ValueTable; '+setup+' For I=1'+loop+'R'
                plan=vm.prepare(source)
                self.assertNotIn('_fresh_closed_table',plan._plan.generated_source)
                self.assertEqual(vm.execute_prepared(plan),210)
        self.assertEqual(effects,[('before',True)])

    def test_setup_error_is_not_reordered_below_admission(self):
        source=TABLE.replace('T.Columns.Add("X");','''
            Kind=New TypeDescription("Number"); C=T.Columns;
            If True Then C.Add("X",Kind,"Header",1/0); EndIf;
        ''')+'R'
        vm=self.vm()
        plan=vm.prepare(source)
        self.assertNotIn('_fresh_closed_table',plan._plan.generated_source)
        with self.assertRaises(BSLError):
            vm.execute_prepared(plan)
        self.assertEqual((vm.variables['t'].count(),vm.variables['c'].count()),(0,0))

    def test_typed_schema_publication_and_reload_precede_fast_loop(self):
        seen=[]
        vm=self.vm()

        class Retired:
            def __del__(self):
                table=vm.variables['t']
                seen.append((table.count(),table.columns.count()))
        vm.variables['zz']=Retired()
        source=TABLE.replace('T.Columns.Add("X");','ZZ=1; T.Columns.Add("X",New TypeDescription("Number"));')
        self.assertEqual(vm.execute(source+' Z=T.Copy(); R'),210)
        self.assertEqual(seen,[(0,0)])

    def test_typed_schema_cannot_reuse_earlier_scalar_slots_after_publication(self):
        vm=self.vm()
        source=TABLE.replace('T.Columns.Add("X");','R=5; T.Columns.Add("X",New TypeDescription("Number"));')
        plan=vm.prepare(source.replace('R=0;', '')+'R')
        self.assertNotIn('_fresh_closed_table',plan._plan.generated_source)
        self.assertEqual(vm.execute_prepared(plan),215)

    def test_warm_repeats_keep_one_table_origin_and_same_aliases(self):
        vm=self.vm()
        plan=vm.prepare(TABLE+'''
            Alias=T;
            Snapshot=T.Copy();
            Alias[0].X=99;
            N=Snapshot[0].X;
        ''')
        self.assertNotIn('_fresh_closed_table',plan._plan.generated_source)
        previous=None
        for _ in range(3):
            vm.execute_prepared(plan)
            table=vm.variables['t']
            self.assertIsNot(table,previous)
            self.assertIs(vm.variables['alias'],table)
            self.assertEqual((table.get_index(0).get_member('X'),vm.variables['n']),(99,1))
            self.assertIsNot(vm.variables['snapshot'],table)
            previous=table

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
        self.assertNotIn('_fresh_closed_table',plan._plan.generated_source)
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
        from unittest.mock import patch
        from yadinassi.collections.value_tables import BSLValueTable

        vm=self.vm()
        plan=vm.prepare(TABLE+'Snapshot=T.Copy();')
        self.assertNotIn('_fresh_closed_table',plan._plan.generated_source)
        copy=BSLValueTable.copy
        copied=[]
        def observe(table,*args,**kwargs):
            copied.append(table)
            return copy(table,*args,**kwargs)
        with patch.object(BSLValueTable,'copy',observe):
            vm.execute_prepared(plan)
        self.assertEqual(len(copied),1)
        self.assertIs(copied[0],vm.variables['t'])
        self.assertEqual((vm.variables['r'],vm.variables['snapshot'].count()),(210,20))
        self.assertIsNot(vm.variables['snapshot'],vm.variables['t'])

    def test_failed_prefix_and_suffix_keep_only_completed_effects(self):
        for source, row_count, value in (
                (TABLE.replace('Row.X=I','Row.Missing=I')+'Snapshot=T.Copy();',1,None),
                (TABLE+'Raise "suffix"; Snapshot=T.Copy();',20,210)):
            with self.subTest(row_count=row_count):
                vm=self.vm()
                plan=vm.prepare(source)
                self.assertNotIn('_fresh_closed_table',plan._plan.generated_source)
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
                self.assertNotIn('_fresh_closed_table',plan._plan.generated_source)
                with self.assertRaises(BSLError):
                    vm.execute_prepared(plan)
                self.assertEqual(vm.variables['t'].count(),20)
                self.assertIsNone(vm.variables['row'].get_member('X'))
                self.assertNotIn('r',vm.variables)
                self.assertNotIn('snapshot',vm.variables)

    def test_goto_and_extensions_are_not_specialized(self):
        for vm,suffix in ((self.vm(),'Goto ~Done; ~Done: Snapshot=T.Copy();'),
                          (self.vm(allow_extensions=True),'Snapshot=T.Copy();')):
            with self.subTest(extension=vm.allow_extensions,suffix=suffix):
                plan=vm.prepare(TABLE+suffix)
                self.assertNotIn('_fresh_closed_table',plan._plan.generated_source)
                vm.execute_prepared(plan)
                self.assertEqual(vm.variables['snapshot'].count(),20)

    def test_unused_table_before_loop_does_not_require_its_own_guard(self):
        for setup in ('U=New ValueTable; T.Columns.Add("X");',
                      'T.Columns.Add("X",New TypeDescription("Number")); U=New ValueTable;',
                      'U=New ValueTable; T.Columns.Add("X",New TypeDescription("Number"));'):
            with self.subTest(setup=setup):
                vm=self.vm()
                source=TABLE.replace('T.Columns.Add("X");',setup)+'Snapshot=T.Copy(); R'
                plan=vm.prepare(source)
                self.assertNotIn('_fresh_closed_table',plan._plan.generated_source)
                self.assertEqual(vm.execute_prepared(plan),210)
                self.assertEqual((vm.variables['u'].count(),vm.variables['snapshot'].count()),(0,20))
                self.assertEqual(vm.execute(source),210)

    def test_one_region_checks_each_used_table_and_keeps_live_aliases(self):
        vm=self.vm()
        source=TABLE.replace('For I=1', """
            U=New ValueTable;
            U.Columns.Add("X",New TypeDescription("Number"));
            Alias=U;
            For I=1""").replace('Row.X=I;', 'Row.X=I; Other=Alias.Add(); Other.X=I+1;')
        plan=vm.prepare(source+'One=T.Copy(); Two=U.Copy(); R')
        self.assertNotIn('_fresh_closed_table',plan._plan.generated_source)
        self.assertEqual(vm.execute_prepared(plan),210)
        self.assertIs(vm.variables['alias'],vm.variables['u'])
        self.assertIsNot(vm.variables['t'],vm.variables['u'])
        self.assertEqual(vm.variables['one'].total('X'),210)
        self.assertEqual(vm.variables['two'].total('X'),230)

    def test_fresh_later_region_after_observation_does_not_reuse_prior_facts(self):
        from yadinassi.collections.value_tables import BSLValueTable

        observations=[]
        replacement=BSLValueTable()
        def observe(text):
            observations.append((text,vm.variables['t'].count(),vm.variables['r']))
            vm.variables['t']=replacement
            vm.variables['r']=29
        vm=self.vm(output=observe)
        second=TABLE.replace('T=','U=').replace('T.','U.').replace('T[I]','U[I]').replace('R=','S=').replace('R+','S+')
        plan=vm.prepare(TABLE+'Old=T; Message("between");'+second+'Snapshot=U.Copy(); R+S')
        self.assertNotIn('_fresh_closed_table',plan._plan.generated_source)
        self.assertEqual(vm.execute_prepared(plan),239)
        self.assertEqual(observations,[('between',20,210)])
        self.assertIsNot(vm.variables['old'],vm.variables['u'])
        self.assertIsNot(vm.variables['snapshot'],vm.variables['u'])
        self.assertEqual(vm.variables['old'].count(),20)
        self.assertIs(vm.variables['t'],replacement)
        self.assertEqual(vm.variables['snapshot'].count(),20)
