"""Inline compiler parity, explicit compiled outlining, and policy traces."""
import unittest
from unittest.mock import patch
from yadinassi import Interpreter
from yadinassi.compiled_backend import Engine, CompiledUnsupported
from yadinassi.syntax.parser import parse
from tests import test_compiled_codegen as codegen
from tests import test_compiled_lifecycle as lifecycle
from tests import test_compiled_policy_abi as policy


class InlineMode:
    def setUp(self):
        super().setUp()
        self.mode = patch.object(Engine, 'INLINE', True)
        self.mode.start()
        self.addCleanup(self.mode.stop)


class InlineCodegenTests(InlineMode, codegen.StrictCodegenTests):
    def test_mutation_during_terminal_host_fault_does_not_mask_fault(self):
        vm = Interpreter(execution_backend='compiled-strict')
        program = parse('Try Boom(); Except Mark();EndTry;')
        call = program[0].body[0].expression
        fault = RuntimeError('host terminal failure')
        marks = []
        def boom():
            call.callee.name = 'Changed'
            raise fault
        vm.register_function('Boom', boom)
        vm.register_function('Mark', lambda: marks.append(True))
        with self.assertRaises(RuntimeError) as caught:
            vm.execute_program(program)
        self.assertIs(caught.exception, fault)
        self.assertEqual(marks, [])
        self.assertEqual(vm._compiled().active_frames, 0)

    def test_inline_code_size_admission_is_explicit_before_effects(self):
        vm = Interpreter(execution_backend='compiled-strict')
        vm._compiled().MAX_INLINE_UNIT_BYTES = 1
        with self.assertRaises(CompiledUnsupported):
            vm.execute('r=1;')
        self.assertNotIn('r', vm.variables)

    def test_block_last_value_and_lexical_goto_result(self):
        for source in ('1+2;', '', 'Goto ~finish; 9; ~finish: 5+2;'):
            old = Interpreter(execution_backend='interpreter').execute(source)
            new = Interpreter(execution_backend='compiled-strict').execute(source)
            self.assertEqual(new, old)

    def test_deep_expressions_outline_only_to_compiled_fragments(self):
        vm, _ = self.run_strict('r=' + '+'.join(['1'] * 40) + ';')
        self.assertEqual(vm.variables['r'], 40)
        self.assertEqual(vm.compiled_backend_stats['interpreter_fallbacks'], 0)


class InlineMutationTests(InlineMode, codegen.MetadataMutationTests):
    pass


class InlineLifecycleTests(InlineMode, lifecycle.CompiledLifecycleTests):
    pass


class InlinePolicyABITests(InlineMode, policy.PolicyABITests):
    pass


if __name__ == '__main__':
    unittest.main()

class FastInlineTests(InlineCodegenTests):
    def setUp(self):
        super().setUp()
        flag = patch.object(Engine, 'FAST_INLINE', True)
        flag.start()
        self.addCleanup(flag.stop)

    def test_host_equality_invalidates_future_metadata_before_write(self):
        vm = Interpreter(execution_backend='compiled-strict')
        program = parse('r=(x=x);final=1;')
        class HostValue:
            def __eq__(self, other):
                program[-1].value.value = 99
                return True
        vm.variables['x'] = HostValue()
        with self.assertRaises(CompiledUnsupported):
            vm.execute_program(program)
        self.assertNotIn('r', vm.variables)
        self.assertNotIn('final', vm.variables)

    def test_host_decimal_subclass_unary_is_opaque(self):
        from decimal import Decimal
        vm = Interpreter(execution_backend='compiled-strict')
        program = parse('r=-x;final=1;')
        class HostDecimal(Decimal):
            def copy_negate(self):
                program[-1].value.value = Decimal(99)
                return Decimal(-1)
        vm.variables['x'] = HostDecimal(1)
        with self.assertRaises(CompiledUnsupported):
            vm.execute_program(program)
        self.assertNotIn('r', vm.variables)

    def test_class_policy_override_disables_fast_path(self):
        events = []
        original = Interpreter.compiled_before
        def recording(vm, node):
            events.append(type(node).__name__)
            return original(vm, node)
        with patch.object(Interpreter, 'compiled_before', recording):
            vm = Interpreter(execution_backend='compiled-strict')
            vm.execute('r=1+2;')
            self.assertFalse(vm._compiled().fast_available())
        self.assertIn('Binary', events)
        self.assertEqual(events.count('Literal'), 2)

    def test_uninstrumented_execution_reports_entries_not_node_coverage(self):
        with patch.object(Engine, 'DETAILED_INLINE_STATS', False):
            vm = Interpreter(execution_backend='compiled-strict')
            vm.execute('r=0;For i=1 To 3 Do r=r+i;EndDo;')
            stats = vm.compiled_backend_stats
            self.assertEqual(vm.variables['r'], 6)
            self.assertEqual(stats['node_coverage'], 'unobserved')
            self.assertGreater(stats['inline_blocks'], 0)
            self.assertEqual(stats['node_kinds'], {})
            self.assertEqual(stats['emitted_executions'], 0)
            self.assertEqual(stats['helper_executions'], 0)
            self.assertEqual(stats['interpreter_fallbacks'], 0)

    def test_class_override_before_lazy_compiler_import(self):
        import subprocess, sys
        code = '''
from yadinassi import Interpreter
seen=[]
original=Interpreter.compiled_before
def before(vm,node):
    seen.append(type(node).__name__)
    return original(vm,node)
Interpreter.compiled_before=before
from yadinassi.compiled_backend import Engine
Engine.INLINE=True
Engine.FAST_INLINE=True
vm=Interpreter(execution_backend='compiled-strict')
vm.execute('r=1+2;')
assert seen.count('Literal') == 2, seen
assert not vm._compiled().fast_available()
'''
        completed = subprocess.run([sys.executable, '-c', code], capture_output=True, text=True)
        self.assertEqual(completed.returncode, 0, completed.stderr)

    def test_caught_host_bsl_error_checks_dirty_metadata_before_handler(self):
        from yadinassi.errors import BSLRuntimeError
        vm = Interpreter(execution_backend='compiled-strict')
        program = parse('Try Boom();Except Mark();EndTry; final=1;')
        marks = []
        def boom():
            program[-1].value.value = 99
            raise BSLRuntimeError('host source error', '<host>', 1, 1)
        vm.register_function('Boom', boom)
        vm.register_function('Mark', lambda: marks.append(True))
        with self.assertRaises(CompiledUnsupported):
            vm.execute_program(program)
        self.assertEqual(marks, [])
        self.assertNotIn('final', vm.variables)

    def test_for_nan_nontrapping_comparison_keeps_oracle_condition(self):
        from decimal import Decimal, localcontext, InvalidOperation
        for mode in ('interpreter', 'compiled-strict'):
            vm = Interpreter(execution_backend=mode)
            vm.variables['limit'] = Decimal('NaN')
            with localcontext() as context:
                context.traps[InvalidOperation] = False
                vm.execute('r=0;For i=1 To limit Do r=r+1;Break;EndDo;')
            self.assertEqual(vm.variables['r'], 0)

    def test_for_decimal_subclass_comparison_cannot_mutate_before_body(self):
        from decimal import Decimal
        vm = Interpreter(execution_backend='compiled-strict')
        program = parse('For i=start To 2 Do r=1;Break;EndDo;')
        class Counter(Decimal):
            def __le__(self, other):
                program[0].body[0].value.value = Decimal(99)
                return True
        vm.variables['start'] = Counter(1)
        with self.assertRaises(CompiledUnsupported):
            vm.execute_program(program)
        self.assertNotIn('r', vm.variables)

    def test_for_decimal_subclass_increment_is_opaque(self):
        from decimal import Decimal
        vm = Interpreter(execution_backend='compiled-strict')
        program = parse('For i=start To 2 Do Mark();EndDo; final=1;')
        marks = []
        class Counter(Decimal):
            def __add__(self, other):
                program[-1].value.value = Decimal(99)
                return Decimal(2)
        vm.variables['start'] = Counter(1)
        vm.register_function('Mark', lambda: marks.append(True))
        with self.assertRaises(CompiledUnsupported):
            vm.execute_program(program)
        self.assertEqual(len(marks), 1)
        self.assertNotIn('final', vm.variables)

class InlineHostTypeGuardTests(unittest.TestCase):
    def test_exact_existing_host_metaclass_date_regression(self):
        from yadinassi.execution_policy import execution_backend_policy
        from tests.test_dates import DateDefensiveTests
        with execution_backend_policy('compiled-strict'):
            case = DateDefensiveTests('test_arbitrary_host_metaclass_is_not_mistaken_for_a_date')
            result = unittest.TestResult();case.run(result)
        self.assertTrue(result.wasSuccessful(), result.errors + result.failures)

    def test_type_admission_never_calls_host_metaclass_eq_or_hash(self):
        from decimal import Decimal
        from yadinassi.errors import BSLRuntimeError
        from yadinassi.values import BSLObject
        calls=[]
        class PoisonMeta(type):
            def __eq__(cls, other): raise AssertionError('metaclass equality')
            def __hash__(cls): raise AssertionError('metaclass hash')
        class Value(BSLObject, metaclass=PoisonMeta):
            def __eq__(self, other): calls.append('value equality');return True
        vm=Interpreter(execution_backend='compiled-strict');vm.variables['x']=Value()
        self.assertIs(vm.execute('(x=x);'), True)
        self.assertEqual(calls, ['value equality'])
        for expression in ('-x;', 'Not x;', 'If x Then r=1;EndIf;', 'For i=x To 1 Do EndDo;'):
            with self.assertRaises(BSLRuntimeError):vm.execute(expression)
        self.assertEqual(calls, ['value equality'])
        self.assertEqual(vm.compiled_backend_stats['interpreter_fallbacks'], 0)
