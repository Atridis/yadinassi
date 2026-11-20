import ast
from decimal import Decimal as D
import unittest

from yadinassi import Interpreter


class DirectArrayForeachNumericTests(unittest.TestCase):
    def test_known_array_is_direct_python_for_and_storage_is_decimal(self):
        vm = Interpreter()
        self.addCleanup(vm.close)
        plan = vm.prepare('A=New Array; For I=0 To 4 Do A.Add(I); EndDo; '
                          'R=0; For Each X In A Do R=R+X; EndDo;')
        loops = [node for node in ast.walk(ast.parse(plan._plan.generated_source)) if type(node) is ast.For]
        self.assertEqual(len(loops),2)
        self.assertEqual(sum(type(loop.iter) is ast.Name for loop in loops),1)
        self.assertNotIn('next(',plan._plan.generated_source)
        vm.execute_prepared(plan)
        self.assertEqual(vm.variables['r'],D(10))
        self.assertEqual(vm.variables['x'],D(4))
        self.assertTrue(all(type(value) is D for value in vm.variables['a']))

    def test_empty_and_break_preserve_last_actual_loop_value(self):
        vm = Interpreter()
        self.addCleanup(vm.close)
        for initial, expected in (('',99),('A.Add(1); A.Add(2);',1)):
            vm.execute('A=New Array; X=99; '+initial+' For Each X In A Do Break; EndDo;')
            self.assertEqual(vm.variables['x'],D(expected))
