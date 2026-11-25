from decimal import Decimal
import json
from pathlib import Path
import unittest
from yadinassi import Interpreter
from yadinassi.types.errors import BSLRuntimeError
from yadinassi.execution.codegen.direct_boundaries import BoundaryViolation
from yadinassi.types.values import Reference

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

    def test_late_read_preserves_unforwarded_writes(self):
        vm=Interpreter();vm.execute('''Function Change(X,Y) X=9;Y=8;Return 2;EndFunction
&AtServer
Function F(Val A,Val B) Return A*10+B;EndFunction
X=1;Y=3;R=F(X,Change(X,Y));''')
        self.assertEqual((vm.variables['x'],vm.variables['y'],vm.variables['r']),(9,8,92))

    def test_failure_during_arguments_keeps_partial_local_write(self):
        output=[];vm=Interpreter(output.append)
        vm.execute('''Function Change(X) X=9;Raise "argument";EndFunction
&AtServer
Procedure F(Val A,Val B) Message("server");EndProcedure
X=1;Try F(X,Change(X));Except Message("caught");EndTry;''')
        self.assertEqual((vm.variables['x'],output),(9,["caught"]))

    def test_forwarded_named_parameter_and_separate_server_modules(self):
        vm=Interpreter();vm.execute('&AtServer\nProcedure S(X) X=7;EndProcedure')
        vm.execute('&AtServer\nProcedure T(X) S(X);EndProcedure')
        vm.execute('Procedure P(X) T(X);EndProcedure X=1;P(X);')
        self.assertEqual(vm.variables['x'],7)

    def test_property_index_and_forwarded_sinks_reject_without_callee_effects(self):
        for argument in ('A[0]','S.X','1'):
            for forwarded in (False,True):
                vm=Interpreter(allow_extensions=True);effects=[];vm.register_function('Effect',lambda:effects.append(1))
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
        # Both native and boxed arrays must reach the same output policy.
        for constructor in ('New Array', 'StrSplit("", ",", False)'):
            large = 'For I=1 To 6000 Do A.Add(0);EndDo;'
            for body, error in (('A.Add(A);', 'циклических коллекций'),
                                (large, 'превышен предел размера')):
                with self.subTest(constructor=constructor, error=error):
                    output = []
                    vm = Interpreter(output.append)
                    self.addCleanup(vm.close)
                    vm.execute('&AtServer\nFunction F(X,A) X=9;' + body +
                               'Message("returning");Return A;EndFunction '
                               f'X=1;A={constructor};R=17;')
                    original = vm.variables['a']
                    with self.assertRaisesRegex(BSLRuntimeError, error):
                        vm.execute('R=F(X,A);')
                    self.assertEqual(output, ['returning'])
                    self.assertEqual((vm.variables['x'], vm.variables['r']), (1, 17))
                    self.assertIs(vm.variables['a'], original)
                    self.assertEqual(vm.execution_context, 'client')
                    self.assertEqual(vm.execute('A.Count()'), 0)

            with self.subTest(constructor=constructor, error=None):
                # One 6000-element output fits. Returning it as well as copying it
                # back by reference must share the budget, not reset it per output.
                vm = Interpreter()
                self.addCleanup(vm.close)
                vm.execute('&AtServer\nFunction F(X,A) X=9;' + large +
                           'Return 23;EndFunction '
                           f'X=1;A={constructor};Original=A;R=F(X,A);')
                self.assertEqual((vm.variables['x'], vm.variables['r']), (9, 23))
                self.assertIsNot(vm.variables['a'], vm.variables['original'])
                self.assertEqual(vm.execute('Original.Count()'), 0)
                self.assertEqual(vm.execute('A.Count()'), 6000)
                self.assertEqual(vm.execution_context, 'client')

    def test_input_budget_is_shared_across_arguments(self):
        vm=Interpreter(allow_extensions=True);effects=[];vm.register_function('Effect',lambda:effects.append(1))
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
        vm=Interpreter(allow_extensions=True);vm.register_function('Close',vm.close)
        vm.execute('&AtServer\nProcedure F(X) X=9;Close();EndProcedure X=1;')
        with self.assertRaises(BoundaryViolation):vm.execute('F(X);')
        self.assertEqual(vm.variables['x'],1)

    def test_original_scalar_witness_matches_native_capture(self):
        root=Path(__file__).resolve().parents[1]
        source=(root/'scripts/native_1c_bootstrap/client_probe.bsl').read_text(encoding='utf-8')
        source=source.split('// BEGIN bounded scalar copyback measurement\n',1)[1].split('// BEGIN bounded object transfer measurement',1)[0]
        capture=json.loads((root/'integrational_tests/directive_probes/scalar_copyback_core.native.json').read_text(encoding='utf-8'))
        expected=['copyback.core.v1']
        for row in capture['observations']:
            value=row['value']
            expected.append(f'{{"B",{int(value)}}}' if type(value) is bool else f'{{"N",{value}}}')
        owner=Interpreter(compilation_profile='managed-thick-file');self.addCleanup(owner.close)
        owner.execute(source)
        self.assertEqual(list(owner.execute('RunScalarCopybackProbe()')),expected)
