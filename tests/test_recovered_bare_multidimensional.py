import unittest
from recovered_bare_fixture import Interpreter
from yadinassi.native_bare_collections import BareArray

class RecoveredBareMultidimensional(unittest.TestCase):
    def test_independent_children_at_every_level(self):
        a=BareArray(2,3,4)
        self.assertEqual(len(a),2)
        self.assertEqual([len(row) for row in a],[3,3])
        self.assertIsNot(a[0],a[1]);self.assertIsNot(a[0][0],a[0][1])
        self.assertIsNot(a[0][0]._data,a[1][0]._data)
        a[0][0][0]=7
        self.assertEqual(a[0][0][0],7)
        self.assertIsNone(a[0][1][0]);self.assertIsNone(a[1][0][0])
    def test_zero_dimensions_use_independent_empty_children(self):
        self.assertEqual(len(BareArray(0,3)),0)
        a=BareArray(2,0);self.assertEqual([len(r) for r in a],[0,0])
        self.assertIsNot(a[0],a[1])
        a[0].add(7);self.assertEqual(len(a[1]),0)
    def test_dimensions_evaluated_once_left_to_right(self):
        source='Function Size(Val N,Counter) Counter=Counter*10+N; Return N; EndFunction; C=0; A=New Array(Size(2,C),Size(3,C)); A.Get(0).Set(1,9); R=A.Get(0).Get(1); N=A.Get(1).Count();'
        for prepared in (False,True):
            vm=Interpreter()
            if prepared:vm.execute_prepared(vm.prepare(source))
            else:vm.execute(source)
            self.assertEqual((vm.variables['c'],vm.variables['r'],vm.variables['n']),(23,9,3))
            self.assertIsNone(vm.variables['a'][1][1])
    def test_dimension_type_error_is_native(self):
        with self.assertRaises(TypeError):BareArray(2,'3')
        with self.assertRaises(TypeError):BareArray('2',3)
    def test_empty_source_path_is_still_direct_constructor(self):
        p=Interpreter().prepare('A=New Array;')
        self.assertIn('_BareArray()',p.generated_source)
        self.assertNotIn('dimension',p.generated_source)
        self.assertEqual(BareArray.__init__.__code__.co_cellvars, ())
