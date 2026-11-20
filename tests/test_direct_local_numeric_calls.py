import ast
from decimal import Decimal as D
import unittest

from yadinassi import Interpreter


class LocalNumericCallTests(unittest.TestCase):
    def test_local_integer_calls_keep_generic_exports(self):
        vm = Interpreter()
        self.addCleanup(vm.close)
        source = ('Function Add(Val A, Val B) Return A+B; EndFunction '
                  'Function Inc(Val X) Return Add(X,1); EndFunction '
                  'R=0; For I=1 To 100 Do R=R+Inc(I); EndDo;')
        plan = vm.prepare(source)
        tree = ast.parse(plan._plan.generated_source)
        loop = next(node for node in ast.walk(tree) if isinstance(node,ast.For))
        calls = [node for statement in loop.body for node in ast.walk(statement) if isinstance(node,ast.Call)]
        self.assertEqual(len(calls),1)
        self.assertTrue(calls[0].func.id.startswith('_temporary_'))
        self.assertEqual(calls[0].keywords,[])
        vm.execute_prepared(plan)
        self.assertEqual((vm.variables['i'],vm.variables['r']),(D(101),D(5150)))
        self.assertIs(type(vm.variables['r']),D)
        self.assertEqual(vm.execute('Inc(0.25)'),D('1.25'))
        self.assertEqual(vm.execute('Add("a","b")'),'ab')

    def test_local_division_stays_decimal_and_public_integer_is_decimal(self):
        vm = Interpreter()
        self.addCleanup(vm.close)
        vm.execute('Function Half(Val X) Return X/2; EndFunction R=Half(3); S=Half(4);')
        self.assertEqual((vm.variables['r'],vm.variables['s']),(D('1.5'),D(2)))
        self.assertIs(type(vm.variables['s']),D)

    def test_generic_defaults_byref_and_non_numeric_actuals(self):
        vm = Interpreter()
        self.addCleanup(vm.close)
        vm.execute('Function Add(Val A, Val B=2) Return A+B; EndFunction '
                   'Procedure SetValue(X) X=Add(X); EndProcedure R=7; SetValue(R);')
        self.assertEqual(vm.variables['r'],D(9))
        vm.execute('Function Join(Val A, Val B) Return A+B; EndFunction R=Join("a","b");')
        self.assertEqual(vm.variables['r'],'ab')
