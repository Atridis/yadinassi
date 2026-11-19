import unittest
from decimal import Decimal as D
from yadinassi import Interpreter
from yadinassi.syntax.parser import parse

class NativeCellTests(unittest.TestCase):
    def vm(self):
        vm=Interpreter();self.addCleanup(vm.close);return vm
    def test_shared_alias_and_nested_forwarding(self):
        vm=self.vm();vm.execute('Procedure Inc(X) X=X+1;EndProcedure Procedure Both(A,B) Inc(A);B=B+2;EndProcedure R=0;Both(R,R);')
        self.assertEqual(vm.variables['r'],D(3))
    def test_byvalue_local_address_is_independent(self):
        vm=self.vm();vm.execute('Procedure Inc(X) X=X+1;EndProcedure Procedure Copy(Val X) Inc(X);EndProcedure R=7;Copy(R);')
        self.assertEqual(vm.variables['r'],D(7))
    def test_defaults_and_expression_actual(self):
        vm=self.vm();vm.execute('Procedure Inc(X=2) X=X+1;EndProcedure Inc();Inc(8+1);R=3;Inc(R);')
        self.assertEqual(vm.variables['r'],D(4))
    def test_recursive_forwarding(self):
        vm=self.vm();vm.execute('Procedure Rec(X,Val N) If N>0 Then X=X+1;Rec(X,N-1);EndIf;EndProcedure R=0;Rec(R,5);')
        self.assertEqual(vm.variables['r'],D(5))
    def test_persistent_boundary_and_complex_addresses(self):
        vm=self.vm();vm.execute('Procedure Inc(X) X=X+1;EndProcedure')
        vm.execute('R=0;Inc(R);');self.assertEqual(vm.variables['r'],D(1))
        vm.execute('Procedure Inc(X) X=X+1;EndProcedure A=New Array;A.Add(4);Inc(A[0]);R=A[0];')
        self.assertEqual(vm.variables['r'],D(5))
    def test_global_var_uses_existing_address_boundary(self):
        vm=self.vm();vm.execute('Var R;Procedure Inc(X) X=X+1;EndProcedure R=0;Inc(R);')
        self.assertEqual(vm.variables['r'],D(1))
    def test_internal_generated_body_has_native_cell_access(self):
        vm=self.vm();plan=vm.prepare_program(parse('Procedure Inc(X) X=X+1;EndProcedure R=0;Inc(R);'))
        generated=plan._plan.generated_source
        self.assertNotIn('_source_reference(',generated);self.assertNotIn('_as_ref(',generated)
        self.assertIn('[0] =',generated);self.assertIn('_native_cells=True',generated)
    def test_loop_control_passed_byref_keeps_mutation_semantics(self):
        vm=self.vm();vm.execute('Procedure Jump(X) X=5;EndProcedure R=0;For I=0 To 3 Do Jump(I);R=R+1;EndDo;')
        self.assertEqual(vm.variables['r'],D(1));self.assertEqual(vm.variables['i'],D(6))
    def test_host_reference_does_not_survive_activation(self):
        from yadinassi.execution.codegen.experimental_naked_boundaries import BoundaryViolation
        vm=self.vm();saved=[]
        vm.register_function('Capture',lambda ref:saved.append(ref))
        vm.functions['capture'].reference_parameters=frozenset({0})
        vm.execute('Procedure F(X) Capture(X);EndProcedure R=1;F(R);')
        with self.assertRaises(BoundaryViolation):saved[0].set(D(9))
    def test_python_storage_models_preserve_aliases(self):
        for store in ({0:D(0),1:D(5)},[D(0),D(5)]):
            def both(a,b):
                store[a]+=1;store[b]+=2
            both(0,0);self.assertEqual(store[0],D(3))
            both(0,1);self.assertEqual((store[0],store[1]),(D(4),D(7)))
    def test_host_close_remains_fatal(self):
        from yadinassi.execution.codegen.experimental_naked_boundaries import BoundaryViolation
        vm=self.vm();vm.register_function('Stop',lambda:vm.close())
        with self.assertRaises(BoundaryViolation):vm.execute('Procedure Inc(X) X=X+1;Stop();X=X+1;EndProcedure R=0;Try Inc(R);Except Caught=True;EndTry;After=1;')
        self.assertNotIn('after',vm.variables);self.assertNotIn('caught',vm.variables)

    def test_public_index_reference_checks_close_before_write(self):
        from yadinassi.execution.direct.python_direct_plain_array import PlainArray
        from yadinassi.execution.codegen.experimental_naked_boundaries import BoundaryViolation
        vm=self.vm();array=PlainArray([D(0)]);vm.variables['a']=array
        class Opaque:
            def __add__(self,value):vm.close();return D(7)
        vm.variables['x']=Opaque()
        with self.assertRaises(BoundaryViolation):vm.execute('Procedure F(A,Val X) A=X+1;EndProcedure;F(A[0],X);')
        self.assertEqual(list(array),[D(0)])

if __name__=='__main__':unittest.main()
