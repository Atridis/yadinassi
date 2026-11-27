from contextlib import closing
import ast
import unittest

from yadinassi import Interpreter
from yadinassi.execution.codegen.direct_boundaries import BoundaryViolation


class DirectPropertyTests(unittest.TestCase):
    def test_structure_properties_are_python_subscripts(self):
        with closing(Interpreter()) as vm:
            plan = vm.prepare('S=New Structure("Value",1);S.Value=2;R=S.VALUE;')
            tree = ast.parse(plan._plan.generated_source)
            fields = [node for node in ast.walk(tree)
                      if isinstance(node, ast.Subscript)
                      and isinstance(node.slice, ast.Constant)
                      and node.slice.value.casefold() == 'value']
            self.assertEqual({type(node.ctx) for node in fields}, {ast.Load, ast.Store})
            self.assertNotIn('_GetField', plan._plan.generated_source)
            self.assertNotIn('_SetField', plan._plan.generated_source)
            vm.execute_prepared(plan)
            self.assertEqual(vm.variables['r'], 2)

    def test_unintegrated_receiver_does_not_run_python_field_hooks(self):
        calls = []

        class Foreign:
            @property
            def value(self):
                calls.append('property')

            def get_member(self, name):
                calls.append('get_member')

            def set_member(self, name, value):
                calls.append('set_member')

            def __getitem__(self, key):
                calls.append('getitem')

            def __setitem__(self, key, value):
                calls.append('setitem')

        with closing(Interpreter()) as vm:
            vm.variables['x'] = Foreign()
            for code in ('R=X.Value;', 'X.Value=1;'):
                with self.subTest(code=code), self.assertRaises(BoundaryViolation):
                    vm.execute(code)
        self.assertEqual(calls, [])
