import unittest
from unittest.mock import patch
from pathlib import Path
from yadinassi import Interpreter, BSLError
from yadinassi.execution.codegen.experimental_naked_boundaries import BoundaryViolation
from yadinassi.types.values import Reference, HostFunction

class DirectExecuteTests(unittest.TestCase):
    def test_source_ast_prepared_with_no_vm_dispatch(self):
        from yadinassi.syntax.parser import parse
        s='Saved=1;Execute("Fresh=7;Saved=Fresh;");'
        for route in ('source','ast','prepared'):
            vm=Interpreter()
            with patch.object(Interpreter,'block',side_effect=AssertionError('VM')),patch.object(Interpreter,'call_routine',side_effect=AssertionError('VM')):
                if route=='source':vm.execute(s)
                elif route=='ast':vm.execute_program(parse(s))
                else:vm.execute_prepared(vm.prepare(s))
            self.assertEqual(vm.variables['saved'],7);self.assertNotIn('fresh',vm.variables)

    def test_locals_parameters_module_and_fresh_bindings(self):
        s='''Var M;M=10;
Procedure P(X,Val Y)
 L=2;Execute("X=X+L;Y=99;L=8;M=M+1;Fresh=33;Later=42;");
 X=X+L;Later=1;
EndProcedure
X=1;Y=2;P(X,Y);'''
        rows=[]
        for backend in ('python-direct','compiled-strict'):
            v=Interpreter(execution_backend=backend);v.execute(s);rows.append(v.variables)
        self.assertEqual(*rows);self.assertEqual(rows[0]['x'],11)
        self.assertNotIn('fresh',rows[0]);self.assertNotIn('later',rows[0])

    def test_callback_observes_and_updates_live_module_storage(self):
        v=Interpreter();seen=[]
        def host():seen.append(v.variables['x']);v.variables['x']=8
        v.register_function('Host',host)
        v.execute('X=1;Execute("X=3;Host();X=X+1;");')
        self.assertEqual(seen,[3]);self.assertEqual(v.variables['x'],9)

    def test_server_dual_and_nocontext_scopes(self):
        s='''&AtServer
Var M;
&AtServer
Function S() L=1;Execute("L=L+2;M=7;Fresh=9;");Return L+M;EndFunction
&AtServerNoContext
Function N() L=2;Execute("L=L+3;Fresh=9;");Return L;EndFunction
&AtClientAtServerNoContext
Function D() L=3;Execute("L=L+4;Fresh=9;");Return L;EndFunction
A=S();B=N();C=D();'''
        v=Interpreter();v.execute(s);self.assertEqual([v.variables[k] for k in ('a','b','c')],[10,5,7])
        self.assertNotIn('fresh',v.variables)

    def test_fragment_server_copyback_and_property_forwarding_boundary(self):
        v=Interpreter();v.execute('''&AtServer
Procedure SetX(X) X=9;EndProcedure
X=1;Execute("SetX(X);");''');self.assertEqual(v.variables['x'],9)
        v.execute('Procedure Forward(P) Execute("SetX(P);");EndProcedure A=New Structure("X",1);')
        with self.assertRaises(BSLError):v.execute('Forward(A.X);')
        self.assertEqual(v.execute('A.X'),1)

    def test_current_constructor_and_registry_admission_before_fragment_effects(self):
        v=Interpreter();plan=v.prepare('Saved=1;Execute("Saved=9;A=New Array;");')
        v.register_type('Array',lambda:[])
        with self.assertRaises(BSLError):v.execute_prepared(plan)
        self.assertEqual(v.variables['saved'],1)

    def test_owner_and_restricted_context_revocation_are_not_swallowed(self):
        for action in ('close','context'):
            v=Interpreter()
            def change():
                if action=='close':v.close()
                else:v._module_context_stack[-1]=False
            v.register_function('Change',change)
            with self.assertRaises(BoundaryViolation):v.execute('Saved=1;Try Execute("Change();Saved=9;");Except Caught=True;EndTry;')
            self.assertEqual(v.variables['saved'],1)
            self.assertNotIn('caught',v.variables)

    def test_fragment_limits_and_no_outer_control_escape(self):
        for code in ('Return;', 'Break;', 'Continue;', 'Raise;', 'Goto ~outer;', 'Var Fresh;', '#If Client Then\nx=1;\n#EndIf'):
            v=Interpreter();v.variables['code']=code
            v.execute('Saved=1;Try Execute(code);Except Caught=True;EndTry;')
            self.assertEqual(v.variables['saved'],1);self.assertTrue(v.variables['caught'])
        v=Interpreter();v.variables['code']='Execute(code);'
        with self.assertRaisesRegex(BSLError,'предел вложенности'):v.execute('Execute(code);')
        v.execute('Saved=1;Execute("Saved=2;");');self.assertEqual(v.variables['saved'],2)

    def test_aliases_and_builtin_omissions_in_fragment(self):
        v=Interpreter();v.execute('R="";Выполнить("R=StrFindByRegularExpression(""a1b2"",""[0-9]"",,,2).Value;");')
        self.assertEqual(v.variables['r'],'2')

    def test_collection_aliases_and_facts_are_not_stale_after_execute(self):
        v=Interpreter();v.execute('A=New Array;A.Add(1);B=A;Execute("A.Clear();");Caught=False;Try R=B[0];Except Caught=True;EndTry;')
        self.assertIs(v.variables['a'],v.variables['b']);self.assertEqual(v.variables['a'],[]);self.assertTrue(v.variables['caught'])

    def test_unregistered_python_services_are_fail_closed(self):
        v=Interpreter()
        with self.assertRaises(BoundaryViolation):v.execute('Execute("__import__(""os"");");')

    def test_native_original_source_can_be_prepared(self):
        s=Path('scripts/native_1c_bootstrap/client_probe.bsl').read_text()
        v=Interpreter(compilation_profile='managed-thick-file');v.execute(s)
        self.assertTrue(v._direct_routine_modules)

    def test_existing_host_reference_is_live_and_not_replaced(self):
        value=[2];vm=Interpreter()
        reference=Reference(lambda:value[0],lambda x:value.__setitem__(0,x))
        vm.variables['x']=reference
        vm.execute('Execute("X=X+3;");')
        self.assertEqual(value,[5]);self.assertIs(vm.variables['x'],reference)

    def test_owned_sqlite_query_uses_current_boundary_inside_fragment(self):
        import test_python_direct_database as fixture
        owner=fixture.DirectDatabaseTests();owner.setUp()
        try:
            owner.vm.execute('R=Undefined;Execute("Q=New Query(""SELECT COUNT(*) AS N FROM Catalog.Номенклатура"");S=Q.Execute().Select();S.Next();R=S.N;");')
            self.assertEqual(owner.vm.variables['r'],0);self.assertNotIn('q',owner.vm.variables)
            owner.vm._transaction_activation_allowed=False
            with patch('yadinassi.db.database_transactions.begin',side_effect=AssertionError('transaction effect')) as begin:
                with self.assertRaises(BSLError):owner.vm.execute('Execute("BeginTransaction();");')
                begin.assert_not_called()
        finally:owner.doCleanups()

    def test_host_reference_revocation_stops_before_next_statement(self):
        for mode in ('read','write','forward'):
            vm=Interpreter()
            def get():
                if mode!='write':vm.close()
                return 2
            def set_value(value):vm.close()
            vm.variables['x']=Reference(get,set_value)
            vm.functions['readref']=HostFunction('ReadRef',lambda ref:ref.get(),reference_parameters=(0,))
            code={'read':'R=X;Saved=9;','write':'X=3;Saved=9;','forward':'ReadRef(X);Saved=9;'}[mode]
            vm.variables['code']=code
            with self.assertRaises(BoundaryViolation):vm.execute('Saved=1;Execute(code);')
            self.assertEqual(vm.variables['saved'],1)

    def test_retained_fragment_reference_cannot_outlive_boundary(self):
        vm=Interpreter();refs=[]
        vm.functions['keep']=HostFunction('Keep',lambda ref:refs.append(ref),reference_parameters=(0,))
        vm.execute('X=1;Execute("Keep(X);");')
        with self.assertRaises(BoundaryViolation):refs[0].set(9)
        vm.register_function('Stale',lambda:refs[0].set(9))
        with self.assertRaises(BoundaryViolation):vm.execute('Stale();')
        self.assertEqual(vm.variables['x'],1)

class ExecutePreparationReuseTests(unittest.TestCase):
    def test_repeated_fragment_prepares_once_but_reads_current_locals(self):
        from yadinassi.syntax import parser
        with patch.object(parser,'parse_fragment',wraps=parser.parse_fragment) as parse:
            vm=Interpreter();vm.execute('Function F() S=0;For I=1 To 20 Do Execute("S=S+1;");EndDo;Return S;EndFunction R=F();')
        self.assertEqual(vm.variables['r'],20)
        self.assertEqual(parse.call_count,1)

    def test_cached_constructor_facts_are_admitted_again(self):
        vm=Interpreter()
        def change():vm.register_type('Array',lambda:[])
        vm.register_function('Change',change)
        with self.assertRaises(BSLError):
            vm.execute('Saved=0;Execute("Saved=Saved+1;A=New Array;");Change();Execute("Saved=Saved+1;A=New Array;");')
        self.assertEqual(vm.variables['saved'],1)

    def test_private_names_are_fresh_on_cache_hit(self):
        vm=Interpreter();seen=[];vm.register_function('Seen',seen.append)
        vm.execute('For I=1 To 3 Do Execute("Try Seen(Private);Except Seen(0);EndTry;Private=9;");EndDo;')
        self.assertEqual(seen,[0,0,0])

    def test_entries_are_bounded_and_activation_local(self):
        from yadinassi.syntax import parser
        vm=Interpreter();sources=['X='+str(i)+';' for i in range(17)]
        vm.variables['fragments']=sources+[sources[0]]
        with patch.object(parser,'parse_fragment',wraps=parser.parse_fragment) as parse:
            vm.execute('For Each Fragment In fragments Do Execute(Fragment);EndDo;')
            self.assertEqual(parse.call_count,18)
            vm.execute('Execute("X=0;");')
            self.assertEqual(parse.call_count,19)

    def test_text_budget_evicts_even_below_entry_limit(self):
        from yadinassi.syntax import parser
        a='//'+('a'*33000)+'\nX=1;';b='//'+('b'*33000)+'\nX=2;'
        vm=Interpreter();vm.variables.update(a=a,b=b)
        with patch.object(parser,'parse_fragment',wraps=parser.parse_fragment) as parse:
            vm.execute('Execute(a);Execute(b);Execute(a);')
        self.assertEqual(parse.call_count,3)

    def test_limits_rechecked_after_cache_hit(self):
        vm=Interpreter()
        with patch('yadinassi.runtime.EXECUTE_MAX_SOURCE',65536):
            def shrink():
                import yadinassi.runtime as runtime
                runtime.EXECUTE_MAX_SOURCE=1
            vm.register_function('Shrink',shrink)
            with self.assertRaisesRegex(BSLError,'предел текста'):
                vm.execute('X=0;Execute("X=X+1;");Shrink();Execute("X=X+1;");')
        self.assertEqual(vm.variables['x'],1)

    def test_cached_unit_does_not_keep_scope_or_vm_alive(self):
        import weakref,gc
        import yadinassi.execution.direct.python_direct_execute as fragments
        refs=[];contexts=[];units=[];original=fragments.FragmentScope.__init__
        def track(scope,*args):
            original(scope,*args);refs.append(weakref.ref(scope))
            contexts.append(weakref.ref(scope.context))
            units.extend(scope.context._execute_units.values())
        vm=Interpreter();vmref=weakref.ref(vm)
        with patch.object(fragments.FragmentScope,'__init__',track):
            vm.execute('X=0;For I=1 To 3 Do Execute("X=X+1;");EndDo;')
        vm.close();del vm;gc.collect()
        self.assertTrue(units)
        self.assertIsNone(vmref());self.assertTrue(all(ref() is None for ref in refs+contexts))
