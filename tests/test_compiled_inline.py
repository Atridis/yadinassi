"""Live behavior migrated from retired compiled-engine tests.

No legacy oracle or fallback. Unsupported live behavior must fail normally.
Engine flags, registry layouts, tier counters and old node-visitor ABI are retired.
"""
from decimal import Decimal
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from yadinassi import Interpreter
from yadinassi.syntax.parser import parse
from yadinassi.types.errors import BSLRuntimeError

class DirectHostValueTests(unittest.TestCase):
    def test_for_nan_nontrapping_comparison_keeps_oracle_condition(self):
        from decimal import Decimal, localcontext, InvalidOperation
        for mode in ('python-direct',):
            vm = Interpreter(execution_backend=mode)
            vm.variables['limit'] = Decimal('NaN')
            with localcontext() as context:
                context.traps[InvalidOperation] = False
                vm.execute('r=0;For i=1 To limit Do r=r+1;Break;EndDo;')
            self.assertEqual(vm.variables['r'], 0)

    def test_exact_existing_host_metaclass_date_regression(self):
        from yadinassi.execution.execution_policy import execution_backend_policy
        from tests.test_dates import DateDefensiveTests
        with execution_backend_policy('python-direct'):
            case = DateDefensiveTests('test_arbitrary_host_metaclass_is_not_mistaken_for_a_date')
            result = unittest.TestResult();case.run(result)
        self.assertTrue(result.wasSuccessful(), result.errors + result.failures)

    def test_type_admission_never_calls_host_metaclass_eq_or_hash(self):
        from decimal import Decimal
        from yadinassi.types.errors import BSLRuntimeError
        from yadinassi.types.values import BSLObject
        calls=[]
        class PoisonMeta(type):
            def __eq__(cls, other): raise AssertionError('metaclass equality')
            def __hash__(cls): raise AssertionError('metaclass hash')
        class Value(BSLObject, metaclass=PoisonMeta):
            def __eq__(self, other): calls.append('value equality');return True
        vm=Interpreter(execution_backend='python-direct');vm.variables['x']=Value()
        self.assertIs(vm.execute('(x=x);'), True)
        self.assertEqual(calls, ['value equality'])
        for expression in ('-x;', 'Not x;', 'If x Then r=1;EndIf;', 'For i=x To 1 Do EndDo;'):
            with self.assertRaises(BSLRuntimeError):vm.execute(expression)
        self.assertEqual(calls, ['value equality'])
