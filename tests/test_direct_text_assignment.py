"""An explicit string assignment is evidence for BSL mixed addition."""
import unittest
from yadinassi import Interpreter


class DirectTextAssignmentTests(unittest.TestCase):
    def test_string_left_variable_uses_bsl_presentation(self):
        vm = Interpreter()
        self.addCleanup(vm.close)
        plan = vm.prepare('Before=1+2; S="value="; N=2; R=S+N; S=3; After=S+N;')
        vm.execute_prepared(plan)
        self.assertEqual(vm.variables['r'], 'value=2')
        self.assertEqual(vm.variables['after'], 5)
        self.assertIn('before = 1 + 2', plan._plan.generated_source)
        self.assertIn('after = s + n', plan._plan.generated_source)

    def test_call_can_rebind_old_string_fact(self):
        vm = Interpreter()
        self.addCleanup(vm.close)
        plan = vm.prepare('Procedure SetNumber(X) X=3; EndProcedure '
                          'S="value="; SetNumber(S); N=2; R=S+N;')
        vm.execute_prepared(plan)
        self.assertEqual(vm.variables['r'], 5)
        self.assertIn('r = s + n', plan._plan.generated_source)
