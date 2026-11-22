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

    def test_reachable_or_unknown_effect_keeps_generic_route(self):
        for condition in ('True','Gate','0'):
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
