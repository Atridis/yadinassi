"""Public direct array loop behavior, independent of retired generator source."""
import unittest
from yadinassi import Interpreter

class ArraySpecializationTests(unittest.TestCase):
    def test_numeric_loop_and_count_bound(self):
        source='A=New Array;For I=0 To 99 Do A.Add(I);EndDo;R=0;For J=0 To A.Count()-1 Do R=R+A.Get(J);EndDo;'
        for prepared in (False, True):
            with self.subTest(prepared=prepared):
                vm=Interpreter();self.addCleanup(vm.close)
                if prepared:vm.execute_prepared(vm.prepare(source))
                else:vm.execute(source)
                self.assertEqual(vm.variables['r'],4950)
                self.assertEqual(len(vm.variables['a']),100)

    def test_negative_index_and_counter_write_are_finite(self):
        vm=Interpreter();self.addCleanup(vm.close)
        vm.execute('A=New Array;A.Add(7);For I=0 To 0 Do I=-1;R=A.Get(I);Break;EndDo;')
        self.assertEqual(vm.variables['r'],7)
        self.assertEqual(vm.variables['i'],-1)
