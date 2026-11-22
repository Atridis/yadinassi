from decimal import Decimal
import unittest
from unittest.mock import patch

from yadinassi import Interpreter
from yadinassi.execution.direct.python_direct_database import CatalogBoundary
from yadinassi.syntax.parser import parse


class KnownMethodTests(unittest.TestCase):
    def test_routine_local_table_alias_keeps_direct_count_after_rebind(self):
        vm=Interpreter()
        self.addCleanup(vm.close)
        source=('Function Work() Var T; T=New ValueTable; Alias=T; T=0; '
                'Return Alias.Count(); EndFunction\nWork()')
        plan=vm.prepare_program(parse(source))
        generated=plan._plan.generated_source
        self.assertIn('.count()',generated)
        self.assertNotIn('_known_detached_after_publication',generated)
        with patch.object(CatalogBoundary,'resolve_member',side_effect=AssertionError('generic count')):
            self.assertEqual(vm.execute(source),Decimal(0))
            self.assertEqual(vm.execute_prepared(plan),Decimal(0))

    def test_routine_reference_escape_does_not_bind_to_old_receiver(self):
        vm=Interpreter()
        self.addCleanup(vm.close)
        source=('Procedure Swap(Value) Value=New Array; Value.Add(1); EndProcedure\n'
                'Function Work() T=New ValueTable; Swap(T); Return T.Count(); EndFunction\nWork()')
        plan=vm.prepare_program(parse(source))
        self.assertNotIn('_known_construct_table',plan._plan.generated_source)
        self.assertEqual(vm.execute(source),Decimal(1))
        self.assertEqual(vm.execute_prepared(plan),Decimal(1))

    def test_named_tables_use_normal_decimal_count(self):
        vm=Interpreter()
        self.addCleanup(vm.close)
        plan=vm.prepare_program(parse('T=New ValueTable; A=T.Count(); U=New ТаблицаЗначений; B=U.Количество();'))
        original=CatalogBoundary.resolve_member
        visited=[]
        def observe(context,value,name):
            visited.append(name.casefold())
            return original(context,value,name)
        with patch.object(CatalogBoundary,'resolve_member',observe):
            vm.execute_prepared(plan)
        self.assertFalse({'count','количество'} & set(visited))
        self.assertEqual((type(vm.variables['a']),type(vm.variables['b'])),(Decimal,Decimal))
        self.assertEqual((vm.variables['a'],vm.variables['b']),(0,0))


class KnownQueryLoopTests(unittest.TestCase):
    from test_main_demo_runtime import MainDemoRuntimeTests
    setUp=MainDemoRuntimeTests.setUp
    del MainDemoRuntimeTests

    QUERY='Q=New Query("SELECT TOP 3 Code FROM Catalog.Склады ORDER BY Code");S=Q.Execute().Select();'

    def seed(self):
        self.vm.execute('For I=1 To 3 Do W=Catalogs.Склады.CreateItem();'
                        'W.Code=String(I);W.Description="Test";W.Write();EndDo;')

    def methods(self):
        original=CatalogBoundary.resolve_member_call
        reached=[]
        def observe(context,value,name,**kwargs):
            if name.casefold() in ('next','следующий'):reached.append(name)
            return original(context,value,name,**kwargs)
        return reached,patch.object(CatalogBoundary,'resolve_member_call',observe)

    def test_query_cursor_facts_survive_while_and_for_backedges(self):
        from test_query_ordered_top_pushdown import OrderedTopMainDemoTests
        self.seed()
        programs=(
            self.QUERY+'R=0;While S.Next() Do R=R+1;EndDo;',
            self.QUERY+'R=0;For N=1 To 4 Do If S.Next() Then R=R+1;EndIf;EndDo;',
            self.QUERY+'R=0;While S.Next() Do R=R+1;If R=1 Then Continue;EndIf;'
                       'If R=2 Then Break;EndIf;EndDo;If S.Next() Then R=R+1;EndIf;',
            'Function Work() Var Q,S,R;'+self.QUERY+
            'R=0;While S.Next() Do R=R+1;EndDo;Return R;EndFunction\nR=Work();',
        )
        for source in programs:
            with self.subTest(source=source):
                plan=self.vm.prepare_program(parse(source))
                self.assertIn('.next()',plan._plan.generated_source)
                self.vm.execute_prepared(plan)  # warm the owned query connection
                for prepared in (False,True):
                    trace,traced=OrderedTopMainDemoTests.actual_trace(self)
                    reached,methods=self.methods()
                    with traced,methods:
                        if prepared:self.vm.execute_prepared(plan)
                        else:self.vm.execute(source)
                    self.assertEqual(self.vm.variables['r'],Decimal(3))
                    self.assertEqual(reached,[])
                    self.assertEqual(len(trace),1,trace)
                    self.assertIn('LIMIT 3',trace[0])

    def test_next_remains_generic_when_rebind_occurs_on_continue(self):
        self.seed()
        self.vm.execute('OtherQuery=New Query("SELECT TOP 1 Code FROM Catalog.Склады ORDER BY Code");Other=OtherQuery.Execute().Select();')
        source=self.QUERY+'R=0;While S.Next() Do R=R+1;If R=1 Then S=Other;Continue;EndIf;EndDo;'
        plan=self.vm.prepare_program(parse(source))
        self.assertNotIn('.next()',plan._plan.generated_source)
        reached,methods=self.methods()
        with methods:self.vm.execute_prepared(plan)
        self.assertEqual(self.vm.variables['r'],Decimal(2))
        self.assertEqual(len(reached),3)

    def test_loop_effect_and_byref_alias_keep_dynamic_dispatch(self):
        self.seed()
        original=self.vm
        observed=[]
        def message(text):
            observed.append(text)
            if len(observed)==1:vm.variables['s']=vm.variables['other']
        vm=Interpreter(database_context=original.database_context,output=message)
        self.addCleanup(vm.close)
        other='OtherQuery=New Query("SELECT TOP 1 Code FROM Catalog.Склады ORDER BY Code");Other=OtherQuery.Execute().Select();'
        body='R=0;While S.Next() Do R=R+1;Message(R);EndDo;'
        vm.execute(other)
        plan=vm.prepare_program(parse(self.QUERY+body))
        self.assertNotIn('.next()',plan._plan.generated_source)
        reached,methods=self.methods()
        with methods:vm.execute_prepared(plan)
        self.assertEqual(observed,['1','2'])
        self.assertEqual(vm.variables['r'],Decimal(2))
        self.assertEqual(len(reached),3)

        source=('Procedure Swap(Cursor, Val Replacement) Cursor=Replacement;EndProcedure\n'
                +other+self.QUERY+'R=0;While S.Next() Do R=R+1;'
                'If R=1 Then Swap(S,Other);EndIf;EndDo;')
        plan=original.prepare_program(parse(source))
        self.assertNotIn('.next()',plan._plan.generated_source)
        original.execute_prepared(plan)
        self.assertEqual(original.variables['r'],Decimal(2))

    def test_same_spelling_column_keeps_field_and_method_semantics(self):
        self.seed()
        source=self.QUERY.replace('TOP 3 Code','TOP 3 Code AS Next')+(
            'R=0;Before=S.Next;While S.Next() Do Last=S.Next;R=R+1;EndDo;'
            'After=S.Next;')
        plan=self.vm.prepare_program(parse(source))
        self.assertNotIn('.next()',plan._plan.generated_source)
        self.vm.execute_prepared(plan)
        state=self.vm.variables
        self.assertEqual((state['r'],state['before'],state['last'],state['after']),
                         (Decimal(3),None,'3','3'))

    def test_module_loop_retains_existing_in_body_query_origin_lowering(self):
        self.seed()
        source=('R=0;For N=1 To 2 Do '+self.QUERY+
                'If S.Next() Then R=R+1;EndIf;EndDo;')
        plan=self.vm.prepare_program(parse(source))
        self.assertIn('.next()',plan._plan.generated_source)
        reached,methods=self.methods()
        with methods:self.vm.execute_prepared(plan)
        self.assertEqual(self.vm.variables['r'],Decimal(2))
        self.assertEqual(reached,[])

    def test_nested_opaque_loops_bound_speculative_analysis(self):
        from yadinassi.execution.direct import python_direct_known_methods as known
        self.seed()
        depth=18
        source=(self.QUERY+''.join(f'For I{i}=1 To 1 Do ' for i in range(depth))
                +'Message("opaque");'+'EndDo;'*depth+'R=S.Next();')
        original=known._common_facts
        intersections=0

        def count(left,right):
            nonlocal intersections
            intersections+=1
            return original(left,right)

        with patch.object(known,'_common_facts',count):
            plan=self.vm.prepare_program(parse(source))
        generated=plan._plan.generated_source
        self.assertGreater(intersections,0)
        self.assertLess(intersections,32*depth)
        self.assertIn('.select()',generated)
        self.assertNotIn('.next()',generated)
        reached,methods=self.methods()
        with methods:self.vm.execute_prepared(plan)
        self.assertIs(self.vm.variables['r'],True)
        self.assertEqual(reached,['Next'])
