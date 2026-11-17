from decimal import Decimal
from pathlib import Path
import unittest
from unittest.mock import patch
from yadinassi import Interpreter
from yadinassi.errors import BSLRuntimeError
from yadinassi.experimental_naked_boundaries import BoundaryViolation
from yadinassi.values import Reference

class DirectServerByrefTests(unittest.TestCase):
    def test_same_side_and_crossing_source_ast_prepared_without_dispatch(self):
        from yadinassi.syntax.parser import parse
        source='''&AtServer
Procedure Add(X) X=X+1;EndProcedure
&AtServer
Function F(X,Val Y=2) Add(X);X=X+Y;Return X*2;EndFunction
X=3;R=F(X);'''
        for route in ('source','ast','prepared'):
            vm=Interpreter()
            with patch.object(Interpreter,'block',side_effect=AssertionError('VM')),patch.object(Interpreter,'call_routine',side_effect=AssertionError('VM')):
                if route=='source':vm.execute(source)
                elif route=='ast':vm.execute_program(parse(source))
                else:vm.execute_prepared(vm.prepare(source))
            self.assertEqual((vm.variables['x'],vm.variables['r']),(6,12))
            vm.execute('R=F(X,3);');self.assertEqual((vm.variables['x'],vm.variables['r']),(10,20))

    def test_independent_inputs_and_rightmost_copyout_even_if_unchanged(self):
        vm=Interpreter();vm.execute('''&AtServer
Function F(A,B) A=41;Return B;EndFunction
X=1;R=F(X,X);''')
        self.assertEqual((vm.variables['x'],vm.variables['r']),(1,1))

    def test_late_read_after_all_argument_effects(self):
        vm=Interpreter();vm.execute('''Function Change(X) X=9;Return 2;EndFunction
&AtServer
Function F(A,Val B) Return A*10+B;EndFunction
X=1;R=F(X,Change(X));''')
        self.assertEqual((vm.variables['x'],vm.variables['r']),(9,92))

    def test_forwarded_named_parameter_and_separate_server_modules(self):
        vm=Interpreter();vm.execute('&AtServer\nProcedure S(X) X=7;EndProcedure')
        vm.execute('&AtServer\nProcedure T(X) S(X);EndProcedure')
        vm.execute('Procedure P(X) T(X);EndProcedure X=1;P(X);')
        self.assertEqual(vm.variables['x'],7)

    def test_property_index_and_forwarded_sinks_reject_without_callee_effects(self):
        for argument in ('A[0]','S.X','1'):
            for forwarded in (False,True):
                vm=Interpreter();effects=[];vm.register_function('Effect',lambda:effects.append(1))
                vm.execute('&AtServer\nProcedure F(X) Effect();X=9;EndProcedure\nProcedure P(X) F(X);EndProcedure A=New Array;A.Add(1);S=New Structure("X",1);')
                # An expression passed to an ordinary local byref parameter becomes
                # that routine's temporary local cell; it is then a named sink.
                if argument=='1' and forwarded:continue
                call=('P' if forwarded else 'F')+'('+argument+');'
                with self.subTest(call=call),self.assertRaises(BSLRuntimeError):vm.execute(call)
                self.assertEqual(effects,[]);self.assertEqual(vm.variables['a'],[Decimal(1)])
                self.assertEqual(vm.variables['s'].get('X'),1)

    def test_unmarked_host_reference_does_not_gain_copyback(self):
        effects=[];vm=Interpreter();vm.variables['x']=Reference(lambda:Decimal(1),lambda v:effects.append(v))
        vm.execute('&AtServer\nProcedure F(X) X=9;EndProcedure')
        with self.assertRaises(BSLRuntimeError):vm.execute('F(X);')
        self.assertEqual(effects,[])

    def test_escaping_error_discards_scalar_and_collection_outputs(self):
        vm=Interpreter();vm.execute('''&AtServer
Procedure Fail(X,A) X=9;A.Add(2);Raise "failed";EndProcedure
X=1;A=New Array;A.Add(1);Try Fail(X,A);Except Caught=True;EndTry;''')
        self.assertEqual((vm.variables['x'],vm.variables['a']),(1,[Decimal(1)]));self.assertTrue(vm.variables['caught'])
        self.assertEqual(vm.execution_context,'client')

    def test_output_validation_is_atomic_and_combines_budget(self):
        for body in ('A.Add(A);','For I=1 To 6000 Do A.Add(0);EndDo;'):
            vm=Interpreter();vm.execute('&AtServer\nFunction F(X,A) X=9;'+body+'Return A;EndFunction X=1;A=New Array;')
            with self.assertRaises(BSLRuntimeError):vm.execute('F(X,A);')
            self.assertEqual((vm.variables['x'],vm.variables['a']),(1,[]))
            self.assertEqual(vm.execution_context,'client')

    def test_input_budget_is_shared_across_arguments(self):
        vm=Interpreter();effects=[];vm.register_function('Effect',lambda:effects.append(1))
        vm.execute('&AtServer\nProcedure F(A,B) Effect();EndProcedure A=New Array;For I=1 To 6000 Do A.Add(0);EndDo;')
        with self.assertRaises(BSLRuntimeError):vm.execute('F(A,A);')
        self.assertEqual(effects,[]);self.assertEqual(len(vm.variables['a']),6000)

    def test_outputs_and_result_have_independent_collection_copies(self):
        vm=Interpreter();vm.execute('''&AtServer
Function F(A,B) A.Add(2);B=A;Return A;EndFunction
A=New Array;A.Add(1);B=New Array;R=F(A,B);A.Add(3);''')
        a,b,r=(vm.variables[k] for k in ('a','b','r'))
        self.assertEqual((a,b,r),([Decimal(1),Decimal(2),Decimal(3)],[Decimal(1),Decimal(2)],[Decimal(1),Decimal(2)]))
        self.assertIsNot(a,b);self.assertIsNot(b,r)

    def test_optional_byref_default_has_no_caller_output(self):
        vm=Interpreter();vm.execute('&AtServer\nFunction F(X=1) X=X+1;Return X;EndFunction R=F();')
        self.assertEqual(vm.variables['r'],2)

    def test_closed_owner_prevents_copyback(self):
        vm=Interpreter();vm.register_function('Close',vm.close)
        vm.execute('&AtServer\nProcedure F(X) X=9;Close();EndProcedure X=1;')
        with self.assertRaises(BoundaryViolation):vm.execute('F(X);')
        self.assertEqual(vm.variables['x'],1)

    def test_original_scalar_witness_matches_control(self):
        source=Path('scripts/native_1c_bootstrap/client_probe.bsl').read_text().split('// BEGIN bounded scalar copyback measurement\n',1)[1].split('// BEGIN bounded object transfer measurement',1)[0]
        results=[]
        for backend in ('python-direct','compiled-strict'):
            vm=Interpreter(compilation_profile='managed-thick-file',execution_backend=backend)
            vm.execute(source);results.append(list(vm.execute('RunScalarCopybackProbe()')))
        self.assertEqual([len(r) for r in results],[35,35])
        self.assertEqual(*results)
