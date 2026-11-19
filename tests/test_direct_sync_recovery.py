"""Successful native scopes do not check dynamic recovery state."""
import ast
from decimal import Decimal
import unittest

from yadinassi import Interpreter


class SyncRecoveryTests(unittest.TestCase):
    def test_pure_scope_has_no_reload_or_dynamic_depth(self):
        vm = Interpreter()
        self.addCleanup(vm.close)
        plan = vm.prepare('R=0;For I=1 To 4 Do R=R+I;EndDo;R;')
        generated = plan._plan.generated_source
        self.assertNotIn('_dynamic_depth', generated)
        self.assertNotIn('_reload_module', generated)
        self.assertEqual(vm.execute_prepared(plan), Decimal(10))

    def test_callback_failure_reloads_before_bsl_handler(self):
        vm = Interpreter()
        self.addCleanup(vm.close)
        seen = []

        def fail():
            seen.append(vm.variables['x'])
            vm.variables['x'] = Decimal(9)
            raise ValueError('callback failed')

        vm.register_function('Fail', fail)
        plan = vm.prepare('X=1;Try R=Fail();Except Y=X;EndTry;Y;')
        tree = ast.parse(plan._plan.generated_source)
        # Dynamic recovery belongs only to exception handlers, not finally
        # on every successful operation; end-of-module publication remains.
        recoveries = [
            node for node in ast.walk(tree)
            if isinstance(node, ast.ExceptHandler)
            and any(isinstance(n, ast.Name) and n.id == '_reload_module' for n in ast.walk(node))
        ]
        self.assertTrue(recoveries)
        self.assertEqual(vm.execute_prepared(plan), Decimal(9))
        self.assertEqual(seen, [Decimal(1)])
        self.assertNotIn('r', vm.variables)
