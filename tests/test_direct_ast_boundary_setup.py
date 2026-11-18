import unittest
from decimal import Decimal
from unittest.mock import patch
from yadinassi import Interpreter,python_direct
from yadinassi.syntax.parser import parse
from yadinassi.experimental_naked_boundaries import BoundaryContext,BoundaryViolation

class BoundarySetupTests(unittest.TestCase):
    def test_single_context_and_live_registry_no_throwaway_copy(self):
        vm=Interpreter();self.addCleanup(vm.close)
        plan=vm.prepare_program(parse('R=3;'))
        original=python_direct.make_boundary;created=[]
        def factory(*args,**kwargs):
            context=original(*args,**kwargs);created.append(context);return context
        with patch.object(python_direct,'make_boundary',factory):vm.execute_prepared(plan)
        self.assertEqual(len(created),1);self.assertIs(created[0]._services,vm.functions)
        self.assertEqual(vm.variables['r'],Decimal(3))
    def test_failure_before_context_restores_active_flag(self):
        vm=Interpreter();self.addCleanup(vm.close)
        plan=vm.prepare_program(parse('R=3;'))
        with patch('yadinassi.python_direct_imports.initialize',side_effect=ValueError('before context')):
            with self.assertRaisesRegex(ValueError,'before context'):vm.execute_prepared(plan)
        self.assertFalse(vm._direct_active)
        vm.execute_prepared(plan);self.assertEqual(vm.variables['r'],Decimal(3))
    def test_close_and_registry_replacement_are_live(self):
        vm=Interpreter();self.addCleanup(vm.close)
        vm.register_function('F',lambda:Decimal(1));plan=vm.prepare_program(parse('R=F();'))
        vm.execute_prepared(plan);self.assertEqual(vm.variables['r'],Decimal(1))
        vm.register_function('F',lambda:Decimal(2));vm.execute_prepared(plan)
        self.assertEqual(vm.variables['r'],Decimal(2))
        vm.register_function('F',lambda:vm.close())
        with self.assertRaises(BoundaryViolation):vm.execute_prepared(plan)

if __name__=='__main__':unittest.main()
