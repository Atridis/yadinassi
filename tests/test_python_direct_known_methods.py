from contextlib import contextmanager
from decimal import Decimal
import sys
import unittest
from unittest.mock import patch

from yadinassi import Interpreter
from yadinassi.execution.direct.python_direct_database import CatalogBoundary
from yadinassi.syntax.parser import parse
from yadinassi.types.errors import BSLRuntimeError


class KnownMethodTests(unittest.TestCase):
    def test_routine_local_table_alias_keeps_direct_count_after_rebind(self):
        vm=Interpreter()
        self.addCleanup(vm.close)
        source=('Function Work() Var T; T=New ValueTable; Alias=T; T=0; '
                'Return Alias.Count(); EndFunction\nWork()')
        plan=vm.prepare_program(parse(source))
        generated=plan._plan.generated_source
        self.assertNotIn('_known_detached_after_publication',generated)
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
        plan=vm.prepare_program(parse(
            'T=New ValueTable; T.Add(); A=T.Count(); U=New ТаблицаЗначений; '
            'U.Добавить(); U.Добавить(); B=U.Количество();'))
        vm.execute_prepared(plan)
        self.assertEqual((type(vm.variables['a']),type(vm.variables['b'])),(Decimal,Decimal))
        self.assertEqual((vm.variables['a'],vm.variables['b']),(1,2))


class KnownQueryLoopTests(unittest.TestCase):
    from test_main_demo_runtime import MainDemoRuntimeTests
    setUp=MainDemoRuntimeTests.setUp
    del MainDemoRuntimeTests

    QUERY='Q=New Query("SELECT TOP 3 Code FROM Catalog.Склады ORDER BY Code");S=Q.Execute().Select();'

    def seed(self):
        self.vm.execute('For I=1 To 3 Do W=Catalogs.Склады.CreateItem();'
                        'W.Code=String(I);W.Description="Test";W.Write();EndDo;')

    @contextmanager
    def next_steps(self):
        # Observe work at the cursor, regardless of how its method was bound.
        from yadinassi.db.query.queries import BSLQueryResultSelection
        next_code=BSLQueryResultSelection.next.__code__
        steps=[]
        previous=sys.getprofile()
        def called(frame,event,arg):
            if event=='call' and frame.f_code is next_code:steps.append(None)
        sys.setprofile(called)
        try:
            yield steps
        finally:
            sys.setprofile(previous)

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
                self.vm.execute_prepared(plan)  # warm the owned query connection
                for prepared in (False,True):
                    trace,traced=OrderedTopMainDemoTests.actual_trace(self)
                    with traced,self.next_steps() as steps:
                        if prepared:self.vm.execute_prepared(plan)
                        else:self.vm.execute(source)
                    self.assertEqual(self.vm.variables['r'],Decimal(3))
                    self.assertEqual(len(steps),3 if 'Break;' in source else 4)
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

    def test_column_reads_keep_cursor_proof_across_alias_and_loop_edges(self):
        from test_query_ordered_top_pushdown import OrderedTopMainDemoTests
        self.seed()
        prefix=self.QUERY+'Alias=S;S=0;Before=Alias.Код;R=0;'
        body=('While Alias.Следующий() Do Last=Alias.Code;R=R+1;'
              'If R=1 Then Continue;EndIf;EndDo;After=Alias.Код;'
              'Exhausted=Alias.Next();Again=Alias.Code;')
        wrapped=('Function Work() Var Q,S,Alias,Before,R,Last,After,Exhausted,Again;'
                 +prefix+body+'Return Again;EndFunction\nAnswer=Work();')
        for source in (prefix+body,wrapped):
            plan=self.vm.prepare_program(parse(source))
            generated=plan._plan.generated_source
            self.assertNotIn('_known_selection_read_protocol',generated)
            self.vm.execute_prepared(plan)
            for prepared in (False,True):
                trace,traced=OrderedTopMainDemoTests.actual_trace(self)
                with traced,self.next_steps() as steps:
                    if prepared:self.vm.execute_prepared(plan)
                    else:self.vm.execute(source)
                self.assertEqual(len(trace),1,trace)
                state=self.vm.variables
                self.assertEqual(len(steps),5)
                if source is wrapped:self.assertEqual(state['answer'],'3')
                else:self.assertEqual((state['r'],state['before'],state['last'],state['after'],
                                       state['exhausted'],state['again']),
                                      (Decimal(3),None,'3','3',False,'3'))

    def test_empty_named_column_and_missing_alias_keep_public_errors(self):
        self.seed()
        src=self.QUERY.replace('Code FROM','Code AS Token FROM').replace(' ORDER BY',' WHERE Code = ""absent"" ORDER BY')+'R=S.Token;B=S.Next();'
        self.vm.execute(src)
        self.assertIsNone(self.vm.variables['r'])
        self.assertIs(self.vm.variables['b'],False)
        with self.assertRaisesRegex(BSLRuntimeError,'Code'):
            self.vm.execute(src+'R=S.Code;')
        with self.assertRaisesRegex(BSLRuntimeError,'Unknown'):
            self.vm.execute(self.QUERY+'S.Next();R=S.Unknown;')

    def test_closed_selection_addition_and_dead_branches_keep_live_cursor(self):
        from test_query_ordered_top_pushdown import OrderedTopMainDemoTests
        self.seed()
        cases=(
            ('R=S.Code + "";', '3'),
            ('V=S.Code;R=V+"";', '3'),
            ('R=R+S.Code;', '123'),
            ('R=S.Code; If False Then Message(R); EndIf;', '3'),
        )
        for body,expected in cases:
            loop=self.QUERY+'R="";While S.Next() Do '+body+'EndDo;'
            routine='Function Work() Var Q,S,R,V;'+loop+'Return R;EndFunction\nAnswer=Work();'
            for source,key in ((loop,'r'),(routine,'answer')):
                with self.subTest(body=body,key=key):
                    plan=self.vm.prepare_program(parse(source))
                    generated=plan._plan.generated_source
                    self.assertNotIn('_known_selection_',generated)
                    self.vm.execute_prepared(plan)  # warm the SQLite handle
                    for prepared in (False,True):
                        trace,traced=OrderedTopMainDemoTests.actual_trace(self)
                        with traced,self.next_steps() as steps:
                            if prepared:self.vm.execute_prepared(plan)
                            else:self.vm.execute(source)
                        self.assertEqual(self.vm.variables[key],expected)
                        self.assertEqual(len(steps),4)
                        self.assertEqual(len(trace),1,trace)

    def test_opaque_selection_operand_runs_once_and_revokes_live_cursor(self):
        from yadinassi.db.query import query_pushdown
        self.seed()
        source=self.QUERY+'R="";While S.Next() Do R=S.Code+"";EndDo;'
        for src in (source,'Function Work() Var Q,S,R;'+source+'Return R;EndFunction\nR=Work();'):
            with self.subTest(source=src):
                actual=query_pushdown.try_ordered_select
                effects=[]
                class Opaque:
                    def __add__(self, other):
                        effects.append(other)
                        return 'opaque'
                def result(*args,**kwargs):
                    found=actual(*args,**kwargs)
                    if found is not None:
                        found._rows=((Opaque(),),*found._rows[1:])
                    return found
                plan=self.vm.prepare_program(parse(src))
                with self.next_steps() as steps,patch.object(query_pushdown,'try_ordered_select',result):
                    self.vm.execute_prepared(plan)
                self.assertEqual(effects,[''])
                self.assertEqual(len(steps),4)
                self.assertEqual(self.vm.variables['r'],'3')

    def test_cursor_reachability_does_not_skip_dead_branch_admission(self):
        from yadinassi.execution.direct.python_direct import PythonDirectUnsupported
        source=self.QUERY+'While S.Next() Do R=S.Code;If False Then New FormGroup;EndIf;EndDo;'
        with self.assertRaisesRegex(PythonDirectUnsupported,'constructor FormGroup'):
            self.vm.prepare_program(parse(source))

    def test_replaced_selection_member_runs_once_and_disarms_method_proof(self):
        from yadinassi.db.query.queries import BSLQueryResultSelection
        self.seed()
        source=self.QUERY+'R=0;While S.Next() Do Last=S.Code;R=R+1;EndDo;'
        for src in (source,'Function Work() Var Q,S,R,Last;'+source+'Return R;EndFunction\nR=Work();'):
            visited=[]
            original=BSLQueryResultSelection.get_member
            def replacement(cursor,name):
                visited.append((cursor._position,name))
                return original(cursor,name)
            plan=self.vm.prepare_program(parse(src))
            with self.next_steps() as steps,patch.object(BSLQueryResultSelection,'get_member',replacement):
                self.vm.execute_prepared(plan)
            self.assertEqual(visited,[(0,'Code'),(1,'Code'),(2,'Code')])
            self.assertEqual(len(steps),4)
            self.assertEqual(self.vm.variables['r'],Decimal(3))

    def test_selection_protocol_guard_does_not_bind_replacement_descriptor(self):
        from yadinassi.db.query.queries import BSLQueryResultSelection
        from yadinassi.types.values import BSLObject
        self.seed()
        source=self.QUERY+'R=0;While S.Next() Do Last=S.Code;R=R+1;EndDo;'
        for owner in (BSLQueryResultSelection,BSLObject):
            with self.subTest(owner=owner):
                plan=self.vm.prepare_program(parse(source))
                original=vars(owner)['get_member']
                bindings=[]
                class TrackingDescriptor:
                    def __get__(self, receiver, kind):
                        bindings.append(receiver is None)
                        return original.__get__(receiver,kind)
                with self.next_steps() as steps,patch.object(owner,'get_member',TrackingDescriptor()):
                    self.vm.execute_prepared(plan)
                # A projected column binds only the concrete instance descriptor.
                self.assertEqual(bindings,[False]*3 if owner is BSLQueryResultSelection else [])
                self.assertEqual(len(steps),4)  # includes the final false result
                self.assertEqual((self.vm.variables['r'],self.vm.variables['last']),(Decimal(3),'3'))

    def test_same_spelling_column_keeps_field_and_method_semantics(self):
        self.seed()
        source=self.QUERY.replace('TOP 3 Code','TOP 3 Code AS Next')+(
            'R=0;Before=S.Next;While S.Next() Do Last=S.Next;R=R+1;EndDo;'
            'After=S.Next;')
        plan=self.vm.prepare_program(parse(source))
        with self.next_steps() as steps:self.vm.execute_prepared(plan)
        self.assertEqual(len(steps),4)
        state=self.vm.variables
        self.assertEqual((state['r'],state['before'],state['last'],state['after']),
                         (Decimal(3),None,'3','3'))

    def test_module_loop_retains_existing_in_body_query_origin_lowering(self):
        self.seed()
        source=('R=0;For N=1 To 2 Do '+self.QUERY+
                'If S.Next() Then R=R+1;EndIf;EndDo;')
        plan=self.vm.prepare_program(parse(source))
        with self.next_steps() as steps:self.vm.execute_prepared(plan)
        self.assertEqual(self.vm.variables['r'],Decimal(2))
        self.assertEqual(len(steps),2)

    def test_nested_opaque_loops_keep_one_effect_and_live_selection(self):
        self.seed()
        depth=18
        source=(self.QUERY+''.join(f'For I{i}=1 To 1 Do ' for i in range(depth))
                +'Message("opaque");'+'EndDo;'*depth+'R=S.Next();')
        plan=self.vm.prepare_program(parse(source))
        reached,methods=self.methods()
        with methods:self.vm.execute_prepared(plan)
        self.assertIs(self.vm.variables['r'],True)
        self.assertEqual(reached,['Next'])

    def test_query_parameter_write_preserves_only_query_provenance(self):
        from test_query_ordered_top_pushdown import OrderedTopMainDemoTests
        OrderedTopMainDemoTests.seed_folded_codes(self, size=3)
        for lexical in (False, True):
            for filtered in (False, True):
                where=' WHERE DeletionMark=&Deleted' if filtered else ''
                source=('Q=New Запрос("SELECT TOP 3 Code FROM Catalog.Склады'+where+' ORDER BY Code");'
                        'Alias=Q; Flag=False; Alias.УстановитьПараметр("Deleted",Flag);Alias=0;'
                        'S=Q.Execute().Select(); R=0; While S.Next() Do R=R+1; EndDo;')
                if lexical:
                    source=('Function Work() Var Q,Alias,Flag,S,R;'+source+
                            'Return R;EndFunction\nR=Work();')
                with self.subTest(lexical=lexical,filtered=filtered):
                    plan=self.vm.prepare_program(parse(source))
                    generated=plan._plan.generated_source
                    self.assertNotIn('_known_query_execute(',generated)
                    self.vm.execute_prepared(plan)
                    for prepared in (False,True):
                        trace,traced=OrderedTopMainDemoTests.actual_trace(self)
                        with traced,self.next_steps() as steps:
                            if prepared:self.vm.execute_prepared(plan)
                            else:self.vm.execute(source)
                        self.assertEqual(self.vm.variables['r'],Decimal(2 if filtered else 3))
                        self.assertEqual(len(steps),3 if filtered else 4)
                        self.assertEqual(len(trace),1,trace)

    def test_opaque_parameter_actual_keeps_bind_order_and_dynamic_execution(self):
        self.seed()
        source=(
            'Function Parameter(Receiver) '
            'Receiver=New Query("SELECT TOP 1 Code FROM Catalog.Склады ORDER BY Code");'
            'Return False;EndFunction\n'
            'Q=New Query("SELECT TOP 3 Code FROM Catalog.Склады WHERE DeletionMark=&Deleted ORDER BY Code");'
            'Old=Q;Q.SetParameter("Deleted",Parameter(Q));'
            'S=Q.Execute().Select(); R=0; While S.Next() Do R=R+1; EndDo;'
            'S=Old.Execute().Select(); N=0; While S.Next() Do N=N+1; EndDo;')
        plan=self.vm.prepare_program(parse(source))
        self.assertNotIn('_known_query_execute(',plan._plan.generated_source)
        self.assertNotIn('.next()',plan._plan.generated_source)
        for prepared in (False,True):
            if prepared:self.vm.execute_prepared(plan)
            else:self.vm.execute(source)
            # The actual changes Q after SetParameter has bound the method
            # on Old. Old receives the filter; Q is a separate TOP 1.
            state=self.vm.variables
            self.assertEqual((state['r'],state['n']),(Decimal(1),Decimal(3)))
            self.assertEqual(state['old']._parameters,{'deleted':False})
            self.assertEqual(state['q']._parameters,{})

    def test_invalid_query_parameter_stops_before_execute(self):
        from test_query_ordered_top_pushdown import OrderedTopMainDemoTests
        self.seed()
        source=(self.QUERY.split('S=')[0]+'Q.SetParameter("",False);'
                'S=Q.Execute().Select();R=S.Next();')
        plan=self.vm.prepare_program(parse(source))
        self.assertNotIn('_known_query_execute(',plan._plan.generated_source)
        for prepared in (False,True):
            trace,traced=OrderedTopMainDemoTests.actual_trace(self)
            with traced,self.assertRaises(BSLRuntimeError):
                if prepared:self.vm.execute_prepared(plan)
                else:self.vm.execute(source)
            self.assertEqual(trace,[])
            self.assertNotIn('r',self.vm.variables)

    def test_parameter_hint_does_not_certify_overridden_query_dispatch(self):
        from yadinassi.db.query.queries import BSLQuery
        self.seed()
        source=(self.QUERY.replace('S=','Q.SetParameter("Unused",False);S=',1)+
                'R=0; While S.Next() Do R=R+1; EndDo;')
        plan=self.vm.prepare_program(parse(source))
        self.assertNotIn('_known_query_execute(',plan._plan.generated_source)
        original=BSLQuery.get_method
        set_parameter=BSLQuery.set_parameter
        for prepared in (False,True):
            observed=[]
            def dispatch(query,name):
                observed.append(('bind',name.casefold()))
                return original(query,name)
            def set_value(query,name,value):
                observed.append(('set',name,value))
                return set_parameter(query,name,value)
            with (self.next_steps() as steps,
                  patch.object(BSLQuery,'get_method',dispatch),
                  patch.object(BSLQuery,'set_parameter',set_value)):
                if prepared:self.vm.execute_prepared(plan)
                else:self.vm.execute(source)
            self.assertEqual(observed,[('set','Unused',False),('bind','execute')])
            self.assertEqual(len(steps),4)
            self.assertEqual(self.vm.variables['r'],Decimal(3))
