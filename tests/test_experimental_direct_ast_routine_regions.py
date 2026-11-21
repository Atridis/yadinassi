"""Independent routine collection results; no retired text/region gate oracle."""
import unittest
from yadinassi import Interpreter, BSLError

class RoutineRegionsTests(unittest.TestCase):
    def execute(self,source,expected):
        for prepared in (False,True):
            with self.subTest(source=source,prepared=prepared):
                vm=Interpreter();self.addCleanup(vm.close)
                if prepared:vm.execute_prepared(vm.prepare(source))
                else:vm.execute(source)
                for name,value in expected.items():self.assertEqual(vm.variables[name],value)

    def test_straight_line_local_and_module_collections(self):
        for global_ in ('','Var T;'):
            for n in (-1,0,3):
                self.execute(global_+'Function F(Val N) T=New ValueList;For I=0 To N Do T.Add(I);EndDo;R=0;For I=0 To N Do R=R+T.Get(I).Value;EndDo;Return R;EndFunction;R=F('+str(n)+');',{'r':0 if n<0 else n*(n+1)//2})
                self.execute(global_+'Function F(Val N) T=New ValueTable;T.Columns.Add("N");For I=0 To N Do Row=T.Add();Row.N=I;EndDo;Return T.Count();EndFunction;R=F('+str(n)+');',{'r':max(0,n+1)})

    def test_partial_error_preserves_reached_rows(self):
        vm=Interpreter();self.addCleanup(vm.close)
        with self.assertRaises(BSLError):vm.execute('Var T;Function F(Val N) T=New ValueTable;T.Columns.Add("N");For I=0 To N Do Row=T.Add();Row.N=1%(2-I);EndDo;Return 0;EndFunction;R=F(3);')
        self.assertEqual(len(vm.variables['t'].rows),3);self.assertNotIn('r',vm.variables)

    def test_repeated_and_recursive_activations(self):
        self.execute('Function F(Val N) T=New ValueList;For I=0 To N Do T.Add(I);EndDo;Return T.Count();EndFunction;A=F(2);B=F(-1);C=F(0);',{'a':3,'b':0,'c':1})
        self.execute('Function F(Val N) T=New ValueList;For I=0 To N Do T.Add(I);EndDo;If N>0 Then Return F(N-1)+T.Count();EndIf;Return 1;EndFunction;R=F(3);',{'r':10})

    def test_byref_and_nested_loops(self):
        self.execute('Function F(N) T=New ValueList;For I=0 To N Do T.Add(I);EndDo;Return T.Count();EndFunction;N=2;R=F(N);',{'r':3,'n':2})
        self.execute('Function F(Val N) T=New ValueList;For I=0 To N Do For J=0 To N Do T.Add(I+J);EndDo;EndDo;Return T.Count();EndFunction;R=F(2);',{'r':9})

    def test_non_numeric_loop_bound_is_error(self):
        vm=Interpreter();self.addCleanup(vm.close)
        with self.assertRaises(BSLError):vm.execute('Function F(Val N) T=New ValueList;For I=0 To N Do T.Add(I);EndDo;Return T.Count();EndFunction;R=F("bad");')
        self.assertNotIn('r',vm.variables)

    def test_zero_trip_and_definite_rebind_do_not_replay(self):
        for n in (-1,2):
            for rebind,extra in [('',0),('Item=T.Add(9);',1)]:
                self.execute('Function F(Val N) T=New ValueList;For I=0 To N Do Item=T.Add(I);EndDo;'+rebind+'For J=0 To 2 Do Item=T.Add(J);EndDo;Return T.Count();EndFunction;R=F('+str(n)+');',{'r':max(0,n+1)+3+extra})
