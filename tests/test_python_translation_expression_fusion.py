"""Expression outcomes retained; fusion helpers and generator registry retired."""
import unittest
from yadinassi import Interpreter, BSLError

class DirectExpressionCompositions(unittest.TestCase):
    def test_attributes_indices_and_nested_condition(self):
        vm=Interpreter();self.addCleanup(vm.close)
        vm.execute('a=New Array;a.Add(4);s=New Structure("n",3);r=a[0]+s.n;t=?(1<2,(3+4)*5,9);')
        self.assertEqual(vm.variables['r'],7);self.assertEqual(vm.variables['t'],35)
    def test_nested_call_effect_order(self):
        vm=Interpreter(allow_extensions=True);self.addCleanup(vm.close);events=[]
        vm.register_function('Tick',lambda n:events.append(n) or n)
        vm.execute('r=Tick(1)+Tick(2)*Tick(3);')
        self.assertEqual(vm.variables['r'],7);self.assertEqual(events,[1,2,3])
    def test_division_failure_remains_visible(self):
        vm=Interpreter();self.addCleanup(vm.close)
        with self.assertRaises(BSLError):vm.execute('r=1/0;')
