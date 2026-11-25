"""Successful native scopes do not check dynamic recovery state."""
from decimal import Decimal
import unittest

from yadinassi import Interpreter


class SyncRecoveryTests(unittest.TestCase):
    def test_standalone_does_not_generate_collection_and_operator_checks(self):
        source = ('Function F(Val A,Val B) A[0]=B;Return A[0]+B;EndFunction '
                  'X=New Array;For I=1 To 5 Do X.Add(I);EndDo;F(X,3);')
        for standalone in (False, True):
            with self.subTest(standalone=standalone):
                vm = Interpreter(allow_extensions=not standalone)
                self.addCleanup(vm.close)
                plan = vm.prepare(source)
                self.assertEqual(vm.execute_prepared(plan), Decimal(6))

    def test_standalone_still_publishes_live_values_for_eval(self):
        vm = Interpreter()
        self.addCleanup(vm.close)
        plan = vm.prepare('X=1;Try Eval("X/0");Except X=Eval("X+2");EndTry;X;')
        self.assertEqual(vm.execute_prepared(plan), Decimal(3))

    def test_pure_scope_reuses_local_state(self):
        vm = Interpreter()
        self.addCleanup(vm.close)
        plan = vm.prepare('R=0;For I=1 To 4 Do R=R+I;EndDo;R;')
        self.assertEqual(vm.execute_prepared(plan), Decimal(10))

    def test_callback_effects_are_visible_in_bsl_handler(self):
        vm = Interpreter(allow_extensions=True)
        self.addCleanup(vm.close)
        seen = []

        def fail():
            seen.append(vm.variables['x'])
            vm.variables['x'] = Decimal(9)
            raise ValueError('callback failed')

        vm.register_function('Fail', fail)
        plan = vm.prepare('X=1;Try R=Fail();Except Y=X;EndTry;Y;')
        self.assertEqual(vm.execute_prepared(plan), Decimal(9))
        self.assertEqual(seen, [Decimal(1)])
        self.assertNotIn('r', vm.variables)
