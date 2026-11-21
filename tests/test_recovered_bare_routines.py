import unittest
from recovered_bare_fixture import Interpreter
from yadinassi.execution.direct.python_direct import PythonDirectUnsupported
class RecoveredRoutines(unittest.TestCase):
    def test_calls_by_value_and_byref_both_routes(self):
        source='Function Double(Val X) X=X*2; Return X; EndFunction; Procedure Inc(X) X=X+1; EndProcedure; R=3; S=Double(R); Inc(R);'
        for prepared in (False,True):
            vm=Interpreter()
            if prepared:vm.execute_prepared(vm.prepare(source))
            else:vm.execute(source)
            self.assertEqual((vm.variables['r'],vm.variables['s']),(4,6))
    def test_aliasing_and_forwarding(self):
        vm=Interpreter();vm.execute('Procedure Both(A,B) A=A+1; B=B+2; EndProcedure; Procedure Forward(X) Both(X,X); EndProcedure; R=1; Forward(R);')
        self.assertEqual(vm.variables['r'],4)
    def test_byvalue_passed_byref_boxes_once(self):
        vm=Interpreter();vm.execute('Procedure Inc(A) A=A+1; EndProcedure; Function F(Val X) Inc(X); Return X; EndFunction; R=2; S=F(R);')
        self.assertEqual((vm.variables['r'],vm.variables['s']),(2,3))
    def test_recursion_and_local_variables(self):
        vm=Interpreter();vm.execute('Function F(Val N) If N=0 Then Return 1; EndIf; X=F(N-1); Return N*X; EndFunction; R=F(5);')
        self.assertEqual(vm.variables['r'],120)
    def test_explicit_unsupported_free_and_indexed_refs(self):
        for source in ('Function F() Return Global; EndFunction; R=F();', 'Procedure F(X) X=1; EndProcedure; A=New Array(1); F(A[0]);'):
            with self.assertRaises(PythonDirectUnsupported):Interpreter().prepare(source)
    def test_generated_simple_cells_not_helpers(self):
        p=Interpreter().prepare('Procedure Inc(X) X=X+1; EndProcedure; R=0; Inc(R);')
        self.assertIn('_v_78[0] = (_v_78[0] + 1)',p.generated_source)
        self.assertIn('_f_696e63(_v_72)',p.generated_source)
        self.assertNotIn('adapt',p.generated_source)
