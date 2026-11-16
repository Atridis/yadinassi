"""Prepared source facts are static; namespace capabilities remain live."""
import unittest
from unittest.mock import patch
from yadinassi import Interpreter
from yadinassi.python_direct import PythonDirectUnsupported

class PreparedAdmissionTests(unittest.TestCase):
    def test_no_source_walk_parse_or_compile_during_execution(self):
        vm=Interpreter();plan=vm.prepare('Var x;Function F() Return 3;EndFunction x=F();x;')
        with patch('yadinassi.python_direct._nodes',side_effect=AssertionError('walk')),patch('yadinassi.python_direct._source_facts',side_effect=AssertionError('source admission')),patch('yadinassi.python_direct._compile',side_effect=AssertionError('compile')),patch('yadinassi.syntax.parser.parse',side_effect=AssertionError('parse')):
            self.assertEqual(vm.execute_prepared(plan),3)
            self.assertEqual(vm.execute_prepared(plan),3)
        self.assertEqual(vm.module_names,{'x'})
    def test_later_routine_registry_rejects_saved_call_before_effects(self):
        for call in ('F();','((F))();','If False Then F();EndIf;'):
            with self.subTest(call=call):
                vm=Interpreter();vm.register_function('F',lambda:1)
                plan=vm.prepare('x=1;'+call)
                vm.execute('Function F() Return 2;EndFunction')
                with self.assertRaisesRegex(PythonDirectUnsupported,'redeclare'):
                    vm.execute_prepared(plan)
                self.assertNotIn('x',vm.variables)
    def test_redeclared_routine_is_not_stale(self):
        vm=Interpreter();plan=vm.prepare('Function F() Return 3;EndFunction x=F();')
        vm.execute('Function F() Return 2;EndFunction')
        vm.execute_prepared(plan);self.assertEqual(vm.variables['x'],3)
    def test_nested_and_dead_constructor_bindings_still_checked(self):
        for source in ('Function F() Return New Array;EndFunction x=1;',
                       'x=1;If False Then a=New Array;EndIf;'):
            with self.subTest(source=source):
                vm=Interpreter();plan=vm.prepare(source)
                vm.register_type('Array',lambda:[])
                with self.assertRaisesRegex(PythonDirectUnsupported,'overridden'):
                    vm.execute_prepared(plan)
                self.assertNotIn('x',vm.variables)
    def test_unused_constructor_override_does_not_restrict_plan(self):
        vm=Interpreter();plan=vm.prepare('x=1;')
        vm.register_type('Array',lambda:[])
        vm.execute_prepared(plan);self.assertEqual(vm.variables['x'],1)
    def test_live_registry_validation_before_effects(self):
        vm=Interpreter();plan=vm.prepare('x=1;')
        vm.functions['bad']=lambda:1
        with self.assertRaisesRegex(PythonDirectUnsupported,'canonical HostFunction'):
            vm.execute_prepared(plan)
        self.assertEqual(vm.variables,{})
