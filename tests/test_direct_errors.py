"""Experiment source mapping restores diagnostics without hot node wrappers."""
import unittest
import os
from unittest.mock import patch
from decimal import Decimal
from types import CodeType
from yadinassi.syntax.parser import parse
from yadinassi.types.errors import BSLRuntimeError
from yadinassi.execution.codegen.direct_errors import convert_error

class DirectErrorConversionTests(unittest.TestCase):

    def test_authority_and_control_failures_remain_outside_conversion(self):
        from yadinassi.execution.codegen.direct_boundaries import BoundaryViolation
        for error in (BoundaryViolation('denied'), KeyboardInterrupt(), SystemExit(), PermissionError('denied')):
            self.assertIs(convert_error(error, 'original.bsl', ''), error)

    def test_existing_bsl_error_identity_preserved(self):
        error = BSLRuntimeError('original', 'x', 2, 3)
        self.assertIs(convert_error(error, 'original.bsl', ''), error)

class DirectPortableDiagnosticsTests(unittest.TestCase):

    def test_prepared_nested_error_preserves_bsl_line_and_effects(self):
        from yadinassi import Interpreter
        source = 'Function Fail()\n  x=1;\n  Return 1/0;\nEndFunction\nbefore=7; result=Fail();'
        vm = Interpreter()
        plan = vm.prepare(source, 'portable.bsl')
        with self.assertRaises(BSLRuntimeError) as caught:
            vm.execute_prepared(plan)
        error = caught.exception
        self.assertEqual(error.line, 3)
        self.assertEqual(error.source_line, '  Return 1/0;')
        self.assertEqual(error.column, 11 if hasattr(CodeType, 'co_positions') else 1)
        self.assertEqual(error.message, 'Деление на ноль')
        self.assertEqual(vm.variables['before'], 7)
        self.assertNotIn('result', vm.variables)

    def test_host_error_uses_bsl_call_line(self):
        from yadinassi import Interpreter
        vm = Interpreter(allow_extensions=True)

        def fail():
            raise ValueError('host failure')
        vm.register_function('Fail', fail)
        source = 'before=1;\n\nFail();'
        with self.assertRaises(BSLRuntimeError) as caught:
            vm.execute(source, 'host.bsl')
        self.assertEqual(caught.exception.line, 3)
        self.assertEqual(caught.exception.source_line, 'Fail();')
        self.assertEqual(caught.exception.column, 1)
        self.assertEqual(vm.variables['before'], 1)

    def test_try_handles_runtime_error_without_masking_authority(self):
        from yadinassi import Interpreter
        from yadinassi.execution.codegen.direct_boundaries import BoundaryViolation
        vm = Interpreter(allow_extensions=True)
        vm.execute('caught=False; Try x=1/0; Except caught=True; EndTry;')
        self.assertTrue(vm.variables['caught'])

        def deny():
            raise BoundaryViolation('closed')
        vm.register_function('Deny', deny)
        with self.assertRaises(BoundaryViolation):
            vm.execute('caught=False; Try Deny(); Except caught=True; EndTry;')
        self.assertFalse(vm.variables['caught'])

class DirectPermissionErrors(unittest.TestCase):

    def test_permission_error_is_not_swallowed_by_bsl_try(self):
        from yadinassi import Interpreter
        vm = Interpreter(allow_extensions=True)
        self.addCleanup(vm.close)

        def denied():
            raise PermissionError('denied')
        vm.register_function('Host', denied)
        from yadinassi.execution.codegen.direct_boundaries import BoundaryViolation
        with self.assertRaisesRegex(BoundaryViolation, 'denied'):
            vm.execute('caught=False;Try Host();Except caught=True;EndTry;')
        self.assertIs(vm.variables['caught'], False)
