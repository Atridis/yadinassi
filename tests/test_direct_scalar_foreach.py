"""Scalar iteration is a BSL type error, not a database receiver operation."""
from decimal import Decimal
import unittest

from yadinassi import Interpreter
from yadinassi.types.errors import BSLRuntimeError


class ScalarForEachTests(unittest.TestCase):
    def test_numeric_boolean_receivers_are_catchable_without_entering_the_body(self):
        source = '''
Try
    For Each Item In Input Do
        Message("loop body");
    EndDo;
Except
    Diagnostic = ErrorDescription();
EndTry;
After = 17;
'''
        for value in (1, Decimal('1.25'), True, False):
            for prepared in (False, True):
                with self.subTest(value=value, type=type(value), prepared=prepared):
                    output = []
                    vm = Interpreter(output.append)
                    self.addCleanup(vm.close)
                    vm.variables['input'] = value
                    if prepared:
                        vm.execute_prepared(vm.prepare(source, 'scalar-loop.bsl'))
                    else:
                        vm.execute(source, 'scalar-loop.bsl')
                    self.assertEqual(output, [])
                    self.assertNotIn('item', vm.variables)
                    self.assertEqual(vm.variables['after'], 17)
                    self.assertRegex(vm.variables['diagnostic'],
                                     r'^scalar-loop\.bsl:3:\d+: .*ожидает массив или коллекцию')

    def test_literal_rejection_keeps_source_location(self):
        vm = Interpreter()
        self.addCleanup(vm.close)
        with self.assertRaisesRegex(BSLRuntimeError, 'ожидает массив или коллекцию') as caught:
            vm.execute('\nFor Each Item In 1 Do EndDo;', 'scalar-literal.bsl')
        self.assertEqual((caught.exception.source, caught.exception.line), ('scalar-literal.bsl', 2))
