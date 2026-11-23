"""Exact primitive values have no BSL property or method protocol."""
from contextlib import closing
from decimal import Decimal
import unittest

from yadinassi import Interpreter
from yadinassi.types.errors import BSLRuntimeError


class ScalarMemberTests(unittest.TestCase):
    def test_reads_and_calls_are_source_aware_and_catchable(self):
        for value in (1, Decimal('1.25'), True, 'текст'):
            for prepared in (False, True):
                with self.subTest(kind=type(value), prepared=prepared):
                    output = []
                    with closing(Interpreter(output.append)) as vm:
                        vm.variables['input'] = value
                        source = '''Function Argument()
    Message("argument evaluated"); Return 1;
EndFunction
Try R = Input.Length; Except ReadError = ErrorDescription(); EndTry;
Try C = Input.Count(Argument()); Except CallError = ErrorDescription(); EndTry;
After = 17;'''
                        if prepared:
                            vm.execute_prepared(vm.prepare(source, 'scalar-member.bsl'))
                        else:
                            vm.execute(source, 'scalar-member.bsl')
                        self.assertEqual(output, [])
                        self.assertNotIn('r', vm.variables)
                        self.assertNotIn('c', vm.variables)
                        for line, key in ((4, 'readerror'), (5, 'callerror')):
                            self.assertRegex(vm.variables[key], rf'^scalar-member\.bsl:{line}:\d+: .*не имеет методов или свойств')
                        self.assertEqual(vm.variables['after'], 17)
                        self.assertEqual(vm.execute('X=New Structure("Length",7); X.Length'), 7)

    def test_uncaught_literal_member_reports_original_source(self):
        with closing(Interpreter()) as vm:
            with self.assertRaisesRegex(BSLRuntimeError, 'не имеет методов или свойств') as caught:
                vm.execute('\n(1.25).Value', 'scalar-literal-member.bsl')
            self.assertEqual((caught.exception.source,caught.exception.line), ('scalar-literal-member.bsl',2))
