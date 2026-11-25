import unittest
from decimal import Decimal as D
from yadinassi import Interpreter
from yadinassi.execution.direct.python_direct_plain_array import PlainArray

class PlainArrayTests(unittest.TestCase):
    def test_native_list_storage_and_explicit_index_tradeoff(self):
        a=PlainArray([D(10),D(20)])
        self.assertIsInstance(a,list)
        # Native Array.Get(-1) rejects rather than using Python negative indexing
        # (1C run 45423566791, array.get.minus-one).
        with self.assertRaises(IndexError):a.get(D(-1))
        self.assertEqual(a.get(D('0.9')),D(10))
    def test_foreign_index_hooks_never_run(self):
        seen=[]
        class Index:
            def __int__(self):seen.append('int');return 0
            def __index__(self):seen.append('index');return 0
        a=PlainArray([1])
        with self.assertRaises(TypeError):a.get(Index())
        with self.assertRaises(TypeError):a.set(Index(),2)
        self.assertEqual(seen,[])
    def test_all_bsl_index_paths_reject_foreign_hooks(self):
        sources=(
            'R=A[Bad()];', 'A[Bad()]=7;', 'Read(A[Bad()]);',
            'Change(A[Bad()]);',
            'S=New Structure("x",1);S.Property("x",A[Bad()]);',
            'R=A.Get(Bad());', 'A.Set(Bad(),7);',
            'F=A.Get;R=F(Bad());',
        )
        for source in sources:
            with self.subTest(source=source):
                vm=Interpreter(allow_extensions=True);self.addCleanup(vm.close);seen=[]
                class Index:
                    def __int__(self):seen.append('int');return 0
                    def __index__(self):seen.append('index');return 0
                vm.variables['a']=PlainArray([D(1)])
                vm.register_function('Bad',lambda:Index())
                vm.register_function('Read',lambda x:None)
                vm.register_function('Change',lambda x:x.set(D(3)))
                vm.functions['change'].reference_parameters=frozenset({0})
                with self.assertRaises(Exception):vm.execute(source)
                self.assertEqual(seen,[]);self.assertEqual(vm.variables['a'][0],D(1))
    def test_opaque_payload_equality_never_runs(self):
        seen=[]
        class Opaque:
            def __eq__(self,other):seen.append('eq');raise AssertionError
        payload=Opaque()
        vm=Interpreter()
        self.addCleanup(vm.close)
        vm.variables.update(a=PlainArray([payload]),b=PlainArray([payload]))
        self.assertIs(vm.execute('(A=B);'),False)
        self.assertIs(vm.execute('(A<>B);'),True)
        self.assertEqual(seen,[])
    def test_integer_induction_preserves_public_number_on_index_failure(self):
        vm=Interpreter();self.addCleanup(vm.close)
        with self.assertRaises(Exception):
            vm.execute('A=New Array;A.Add(9);For I=0 To 3 Do R=A[I];EndDo;')
        self.assertIs(type(vm.variables['i']),D);self.assertEqual(vm.variables['i'],D(1))
    def test_break_normalizes_index_only_counter_before_following_code(self):
        vm=Interpreter();self.addCleanup(vm.close)
        vm.execute('A=New Array;A.Add(7);For I=0 To 4 Do R=A[I];Break;EndDo;A.Add(I);X=I;')
        self.assertIs(type(vm.variables['i']),D);self.assertIs(type(vm.variables['x']),D)
        value = vm.execute('A[1];')
        self.assertIs(type(value), D)
        self.assertEqual(value, D(0))
    def test_counter_used_as_number_and_modified_counter(self):
        vm=Interpreter();self.addCleanup(vm.close)
        vm.execute('A=New Array;For I=0 To 4 Do A.Add(I);EndDo;R=0;For I=0 To 4 Do R=R+A[I]+I;EndDo;')
        self.assertIs(type(vm.variables['r']),D);self.assertEqual(vm.variables['r'],D(20))
        vm.execute('R=0;For I=0 To 4 Do R=R+I;I=I+1;EndDo;')
        self.assertEqual(vm.variables['r'],D(6));self.assertEqual(vm.variables['i'],D(6))
    def test_range_break_continue_and_final_counter(self):
        vm=Interpreter();self.addCleanup(vm.close)
        vm.execute('A=New Array;For I=0 To 4 Do If I=2 Then Continue;EndIf;A.Add(I);EndDo;R=A[3];')
        self.assertEqual(vm.variables['r'],D(4));self.assertEqual(vm.variables['i'],D(5))
        vm.execute('A=New Array;For I=0 To 4 Do If I=2 Then Break;EndIf;A.Add(I);EndDo;R=A[0];')
        self.assertEqual(vm.variables['i'],D(2))

if __name__=='__main__':unittest.main()
