"""Product entrypoints have one compiler; retired engines are not shipped."""
import importlib.util
import unittest
from decimal import Decimal
from yadinassi import Interpreter
from yadinassi.execution.execution_policy import execution_backend_policy, ui_backend


class DirectOnlyRuntimeTests(unittest.TestCase):
    def test_removed_engines_have_no_importable_module(self):
        for name in ('compiled_backend', 'compiled_inline', 'compiled_roles',
                     'hybrid_backend', 'plain_modules', 'plain_routines',
                     'python_translation_blocks', 'python_translation_expressions'):
            self.assertIsNone(importlib.util.find_spec('yadinassi.' + name))

    def test_tree_walk_and_async_bodies_are_removed(self):
        for name in ("visit_For", "visit_Binary", "visit_Await", "iteration",
                     "_async_body", "_invoke_bound_routine", "_routine_activation"):
            self.assertNotIn(name, vars(Interpreter))
        from yadinassi.configuration.configuration_source_runtime import _SourceInterpreter
        self.assertFalse(hasattr(_SourceInterpreter, 'argument'))

    def test_old_backend_choices_rejected(self):
        for backend in ('interpreter', 'hybrid', 'compiled-strict'):
            with self.assertRaises(ValueError): Interpreter(execution_backend=backend)
            with self.assertRaises(ValueError): ui_backend(backend)
            with self.assertRaises(ValueError):
                with execution_backend_policy(backend): pass

    def test_direct_execute_prepared_and_ast(self):
        from yadinassi.syntax.parser import parse
        source = 'Function F(X) Return X+1;EndFunction;R=F(3);'
        for mode in ('execute', 'prepared', 'ast'):
            vm = Interpreter()
            if mode == 'execute': vm.execute(source)
            elif mode == 'prepared': vm.execute_prepared(vm.prepare(source))
            else: vm.execute_program(parse(source))
            self.assertEqual(vm.variables['r'], Decimal(4))
