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

    def test_straight_line_locals_and_optional_arguments_use_numeric_body(self):
        vm = Interpreter()
        self.addCleanup(vm.close)
        source = ('Function Mix(Val X=2, Val Shift=5) '
                  'A=X+1; B=A*2; A=B+Shift; Return A; EndFunction '
                  'R=0; For I=1 To 10 Do R=R+Mix(I)+Mix(,I)+Mix(); EndDo;')
        plan = vm.prepare(source)
        tree = ast.parse(plan._plan.generated_source)
        loop = next(node for node in ast.walk(tree) if isinstance(node, ast.For))
        calls = [node for statement in loop.body for node in ast.walk(statement)
                 if isinstance(node, ast.Call)]
        self.assertEqual(len(calls), 3)
        self.assertTrue(all(type(call.func) is ast.Name and not call.keywords for call in calls))
        self.assertEqual(len({call.func.id for call in calls}), 1)
        target = next(fn for fn in ast.walk(tree) if isinstance(fn, ast.FunctionDef)
                      and fn.name == calls[0].func.id)
        self.assertEqual([type(stmt) for stmt in target.body],
                         [ast.Assign, ast.Assign, ast.Assign, ast.Return])
        self.assertFalse(any(isinstance(node, ast.Call) for node in ast.walk(target)))
        vm.execute_prepared(plan)
        self.assertEqual(vm.variables['r'], D(405))
        self.assertEqual(vm.execute('Mix(0.25, 0.5)'), D('3.0'))

    def test_signed_defaults_explicit_undefined_and_module_writes_keep_semantics(self):
        vm = Interpreter()
        self.addCleanup(vm.close)
        vm.execute('Function Half(Val X=-3) Y=X/2; Return Y; EndFunction R=Half(3);')
        self.assertEqual(vm.variables['r'], D('1.5'))
        self.assertEqual(vm.execute('Half()'), D('-1.5'))
        self.assertEqual(vm.execute('Function IsMissing(Val X=2) '
                                    'Y=X; Return Y=Undefined; EndFunction IsMissing(Undefined);'), True)
        vm.execute('Var M; M=0; Function Update(Val X=2) M=X+3; Return M; EndFunction R=Update();')
        self.assertEqual((vm.variables['m'], vm.variables['r']), (D(5), D(5)))
