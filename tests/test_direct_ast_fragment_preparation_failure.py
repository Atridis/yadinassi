"""Unsupported fragment compilation is fatal, unlike reached BSL errors."""
import unittest
from unittest.mock import patch
from yadinassi import Interpreter
from yadinassi.experimental_naked_collections import UnsupportedNakedSyntax

class FragmentPreparationFailureTests(unittest.TestCase):
    def test_execute_and_eval_preparation_failure_never_enters_bsl_handler(self):
        for expression in ('Execute("Effect();New UnsupportedConstructor;")',
                           'Eval("New UnsupportedConstructor(Effect())")'):
            vm=Interpreter();effects=[]
            vm.register_function('Effect',lambda:effects.append(1))
            source='Try '+expression+';Except Caught=True;EndTry;After=True;'
            plan=vm.prepare(source)
            for _ in range(2):
                with patch('yadinassi.experimental_naked_collections.prepare',create=True,side_effect=AssertionError('old compiler')):
                    with self.assertRaises(UnsupportedNakedSyntax):vm.execute_prepared(plan)
                self.assertEqual(effects,[])
                self.assertNotIn('caught',vm.variables);self.assertNotIn('after',vm.variables)
            vm.execute('R=Eval("2+3");');self.assertEqual(vm.variables['r'],5)
            vm.close()

    def test_known_runtime_constructor_error_remains_catchable(self):
        vm=Interpreter();effects=[];vm.register_function('Effect',lambda:effects.append(1))
        vm.execute('Try Execute("New SearchDirection(Effect());");Except Caught=True;EndTry;')
        self.assertTrue(vm.variables['caught']);self.assertEqual(effects,[]);vm.close()
