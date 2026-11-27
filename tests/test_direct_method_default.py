import ast
from decimal import Decimal
import unittest

from yadinassi import Interpreter
from yadinassi.execution.codegen.direct_boundaries import BoundaryViolation
from yadinassi.execution.direct.python_direct_plain_map import PlainMap


class DirectMethodDefaultTests(unittest.TestCase):
    def test_ordinary_calls_emit_python_methods_not_a_resolver(self):
        vm = Interpreter()
        self.addCleanup(vm.close)
        plan = vm.prepare(
            'M=New Map;M.Вставить(1,2);A=New Array;A.Add(M.Получить(1));'
            'S=New Structure;S.Insert("number",A.Get(0));R=S.number;'
        )
        tree = ast.parse(plan._plan.generated_source)
        call_names = [node.func.id for node in ast.walk(tree)
                      if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)]
        self.assertNotIn('_Member', call_names)
        method_calls = [node.func for node in ast.walk(tree)
                        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)]
        receiver_calls = [node for node in method_calls
                          if isinstance(node.value, ast.Call)
                          and isinstance(node.value.func, ast.Name)
                          and node.value.func.id == '_MethodReceiver']
        self.assertEqual({node.attr for node in receiver_calls},
                         {'_bsl_proc_insert', '_bsl_proc_add', '_bsl_value_get'})
        self.assertTrue(all(len(node.value.args) == 1 and not node.value.keywords
                            for node in receiver_calls))
        vm.execute_prepared(plan)
        self.assertEqual(vm.variables['r'], Decimal(2))

    def test_foreign_objects_do_not_run_method_hooks(self):
        seen = []

        class Foreign(PlainMap):
            def __getattribute__(self, name):
                seen.append(name)
                raise AssertionError('foreign attribute hook ran')

        vm = Interpreter()
        self.addCleanup(vm.close)
        vm.variables['m'] = Foreign()
        with self.assertRaises(BoundaryViolation):
            vm.execute('R=M.Get(1);')
        self.assertEqual(seen, [])
