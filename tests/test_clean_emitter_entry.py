import ast
from decimal import Decimal
import unittest
from unittest.mock import patch

from yadinassi import BSLRuntimeError, Interpreter
from yadinassi.execution.direct.python_direct import PythonDirectUnsupported


class CleanEmitterEntryTests(unittest.TestCase):
    def test_native_text_of_counted_loop_has_no_state_lookups_or_copy(self):
        vm=Interpreter()
        self.addCleanup(vm.close)
        source='R=0; For I=1 To 32768 Do R=R+I*3; EndDo;'
        plan=vm.prepare(source)
        tree=ast.parse(plan._plan.generated_source)
        loop=[node for node in ast.walk(tree) if isinstance(node,(ast.While,ast.For))]
        self.assertEqual(len(loop),1)
        self.assertFalse(any(isinstance(node,(ast.Call,ast.Subscript)) for node in ast.walk(loop[0])))
        vm.execute_prepared(plan)
        self.assertEqual(vm.variables,{'i':Decimal(32769),'r':Decimal(1610661888)})
        self.assertIs(type(vm.variables['r']),Decimal)

    def test_real_entry_has_one_generator_and_never_retries_unsupported_syntax(self):
        from yadinassi.execution.codegen import direct_emitter

        for prepared in (False,True):
            with self.subTest(prepared=prepared):
                vm=Interpreter()
                self.addCleanup(vm.close)
                execute=vm.prepare if prepared else vm.execute
                with patch.object(direct_emitter,'compile_module',
                                  wraps=direct_emitter.compile_module) as emit:
                    with self.assertRaisesRegex(PythonDirectUnsupported,'UnsupportedExample'):
                        execute('Before=1; R=New UnsupportedExample;')
                emit.assert_called_once()
                self.assertNotIn('before',vm.variables)

    def test_builtins_do_not_become_bsl_variables(self):
        vm=Interpreter()
        self.addCleanup(vm.close)
        with self.assertRaisesRegex(BSLRuntimeError, r'не определена: len'):
            vm.execute('UndefinedHostName = len;')
        self.assertNotIn('undefinedhostname',vm.variables)
        self.assertNotIn('__builtins__',vm.variables)

    def test_array_index_is_the_only_adaptation_in_the_neighboring_loop(self):
        vm=Interpreter()
        self.addCleanup(vm.close)
        source='A=New Array; A.Add(4); Failed=False; Try A[-1]; Except Failed=True; EndTry; R=1+2;'
        vm.execute(source)
        self.assertTrue(vm.variables['failed'])
        self.assertEqual(vm.variables['r'],Decimal(3))


    def test_positional_hole_uses_python_default_and_full_call_stays_positional(self):
        vm=Interpreter()
        self.addCleanup(vm.close)
        source='''Function F(Val A=10, Val B=20, Val C=30)
            Return A+B+C;
        EndFunction
        R=F(1,,3); S=F(1,2,3);
        '''
        plan=vm.prepare(source)
        tree=ast.parse(plan._plan.generated_source)
        invocation=[node for node in ast.walk(tree) if isinstance(node,ast.Call)
                    and isinstance(node.func,ast.Name) and node.func.id.startswith('_T')]
        self.assertEqual([(len(node.args), [kw.arg for kw in node.keywords])
                          for node in invocation],[(1,['c']),(3,[])])
        vm.execute_prepared(plan)
        self.assertEqual((vm.variables['r'],vm.variables['s']),(Decimal(24),Decimal(6)))

    def test_host_positional_hole_does_not_change_procedure_tail(self):
        vm=Interpreter()
        self.addCleanup(vm.close)
        for compile_first in (False,True):
            source='W=New JSONWriter; W.SetString(); WriteJSON(W,True,); W.Close()'
            result=vm.execute_prepared(vm.prepare(source)) if compile_first else vm.execute(source)
            self.assertEqual(result,'true')
        vm.execute('W=New JSONWriter; W.SetString();')

    def test_dynamic_constructor_accepts_native_int_dimensions(self):
        vm=Interpreter()
        self.addCleanup(vm.close)
        vm.execute('Args=New Array; Args.Add(3); R=New("Array",Args); S=New Array(3);')
        self.assertEqual(vm.variables['r'],[None,None,None])
        self.assertEqual(vm.variables['s'],vm.variables['r'])

    def test_raise_options_keep_bsl_diagnostic(self):
        vm=Interpreter()
        self.addCleanup(vm.close)
        vm.execute('Try Raise ("test",, "E12"); Except E=ErrorInfo(); R=E.Code; EndTry;')
        self.assertEqual(vm.variables['r'],'E12')

    def test_byref_aliases_borrow_only_the_names_passed_by_reference(self):
        vm=Interpreter()
        self.addCleanup(vm.close)
        source='''Procedure Change(A,B)
            A=10; B=B+1;
        EndProcedure
        Function F(Val X)
            Local=2; Result=5;
            Change(Local,Local);
            Return Local+Result+X;
        EndFunction
        R=F(1);
        T=New Array; T.Add(4); Change(T[0],T[0]); S=T[0];
        '''
        plan=vm.prepare(source)
        vm.execute_prepared(plan)
        self.assertEqual((vm.variables['r'],vm.variables['s']),(Decimal(17),Decimal(11)))
        generated=plan._plan.generated_source
        self.assertEqual(generated.count("_LocalStorage('local')"),1)
        self.assertNotIn("_LocalStorage('result')",generated)
        self.assertNotIn("_LocalStorage('x')",generated)
        self.assertNotIn('nonlocal ',generated)

    def test_byref_default_has_fresh_storage_per_call(self):
        vm=Interpreter()
        self.addCleanup(vm.close)
        source='''Function F(X=2)
            X=X+1; Return X;
        EndFunction
        A=F();B=F();C=5;D=F(C);
        '''
        vm.execute(source)
        self.assertEqual([vm.variables[k] for k in ('a','b','c','d')],
                         list(map(Decimal,(3,3,6,6))))


    def test_fragments_share_live_module_and_routine_slots_without_a_second_emitter(self):
        vm=Interpreter()
        self.addCleanup(vm.close)
        vm.execute('''Var Total; Total=10;
            Function Run(A)
                B=2;
                Execute("B=B+1; A=A+B; Total=Total+A;");
                Return Eval("A+B+Total");
            EndFunction
            R=1; Out=Run(R);
            Execute("Total=Total+1;");
        ''')
        self.assertEqual([vm.variables[k] for k in ('r','out','total')],
                         list(map(Decimal,(4,21,15))))

    def test_array_numeric_values_at_public_boundary_keep_identity(self):
        vm=Interpreter()
        self.addCleanup(vm.close)
        vm.execute('A=New Array; A.Add(7); A.Add(True);')
        self.assertIs(type(vm.variables['a'][0]), int)
        result=vm.execute('A')
        self.assertIs(result,vm.variables['a'])
        self.assertEqual(result,[Decimal(7),True])
        self.assertIs(type(result[0]),Decimal)
        self.assertIs(result[1],True)

    def test_client_and_server_profiles_execute_on_the_same_emitter(self):
        vm=Interpreter()
        self.addCleanup(vm.close)
        source='''&AtServerNoContext
        Function Increment(Val Amount)
            Return Amount+1;
        EndFunction
        &AtServer
        Function Indirect(Val Amount)
            Return Increment(Amount)+2;
        EndFunction
        &AtClientAtServerNoContext
        Function Encode(Val Amount)
            Return Amount*2;
        EndFunction
        &AtClient
        Function Run()
            Return Encode(Indirect(4));
        EndFunction
        R=Run();
        '''
        vm.execute(source)
        self.assertEqual(vm.variables['r'],Decimal(14))

    def test_array_operation_family_accepts_native_integer_indices(self):
        vm=Interpreter()
        self.addCleanup(vm.close)
        vm.execute('''A=New Array(2);
            A.Set(0,5); A.Insert(1,"item"); A.Delete(2);
            A.Add(); Got=A.Get(0); Found=A.Find(5.0); Limit=A.UBound();
            A.Clear(); Count=A.Count();
        ''')
        self.assertEqual([vm.variables[k] for k in ('got','found','limit','count')],
                         list(map(Decimal,(5,0,2,0))))
        self.assertEqual(vm.variables['a'],[])

    def test_map_mutations_and_count_use_native_backing_storage(self):
        vm=Interpreter()
        self.addCleanup(vm.close)
        vm.execute('''M=New Map; M.Insert("x",1); M.Insert(2,"y");
            M.Delete("x"); M.Delete("missing");
            Found=M.Get(2); Before=M.Count(); M.Clear(); After=M.Count();
        ''')
        self.assertEqual(vm.variables['found'],'y')
        self.assertEqual((vm.variables['before'],vm.variables['after']),(Decimal(1),Decimal(0)))
