"""Depth outlining keeps per-node authority and lifetime boundaries intact."""
import unittest
from types import SimpleNamespace

from yadinassi import Interpreter, translated_access
from yadinassi.syntax.parser import parse
from yadinassi import python_translation_expression_fusion as fusion
from yadinassi.python_translation_expressions import prepare_expressions
from tests.test_python_translation_expressions import finish


def compile_nested(node):
    lines = ['def fused(_s):', ' vm = _s.vm', ' if False: yield None']
    nodes = []
    serial = [0]
    def bind(value):
        nodes.append(value)
        return f'_nodes[{len(nodes)-1}]'
    def temp():
        serial[0] += 1
        return f't{serial[0]}'
    def emit(depth, line):
        lines.append(' ' * depth + line)
    emitter = fusion.ExpressionEmitter(bind, emit, temp, compact_leaves=True)
    # Emulate a statement nested in the generated loop/try scaffolding.
    for depth in range(1, 8):
        emit(depth, 'if True:')
    result = emitter.emit_expression(node, 8)
    emit(8, 'return ' + result)
    lines[3:3] = [' ' * d + text for d, text in emitter.helper_lines]
    source = '\n'.join(lines)
    namespace = {'_nodes': tuple(nodes), '_PE': fusion}
    exec(compile(source, '<nested-fusion-test>', 'exec'), namespace)
    return namespace['fused'], source


class SynchronousFusionTests(unittest.TestCase):
    def compare(self, source, fail_guard=None):
        node = parse('r=' + source + ';')[0].value
        traces, outcomes = [], []
        for outlined in (False, True):
            trace = []
            vm = Interpreter()
            vm.variables.update(a=2, b=3)
            vm.compiled_before = lambda n: trace.append(('before', id(n)))
            vm.compiled_after = lambda n, v: (trace.append(('after', id(n))), v)[1]
            def exception(n, error):
                trace.append(('exception', id(n), type(error)))
                return error
            vm.compiled_exception = exception
            def guard(n):
                trace.append(('guard', id(n)))
                if fail_guard is not None and len(trace) >= fail_guard:
                    raise RuntimeError('authority revoked')
            execution = prepare_expressions([node]).bind(vm, guard=guard, access=translated_access)
            try:
                if outlined:
                    function, generated = compile_nested(node)
                    self.assertIn('def _fused_sync_', generated)
                    self.assertNotIn('.evaluate(', generated)
                    execution.evaluate = lambda n: self.fail('generator registry used')
                    value = finish(function(SimpleNamespace(vm=vm, expressions=execution)))
                else:
                    value = finish(execution.evaluate(node))
                outcomes.append(('value', value))
            except Exception as error:
                outcomes.append(('error', type(error), str(error)))
            traces.append(trace)
        self.assertEqual(outcomes[0], outcomes[1])
        self.assertEqual(traces[0], traces[1])
        return outcomes[0]

    def test_nested_scalar_shapes_and_short_circuit(self):
        for source in ('1+2*3-7', '?(True,(1+2)*3,1/0)',
                       'False And 1/0', 'True Or 1/0', '-(1+2)',
                       '"a"+1', '1/0', 'True=1'):
            with self.subTest(source=source):
                self.compare(source)

    def test_authority_checked_inside_outlined_expression(self):
        for position in range(1, 20):
            with self.subTest(position=position):
                self.compare('1+2*3-7', position)

    def test_deep_expression_uses_multiple_bounded_sync_helpers(self):
        self.assertEqual(self.compare('+'.join('1' for _ in range(25))), ('value', 25))

    def test_suspending_call_keeps_service_route(self):
        node = parse('r=F()+1;')[0].value
        _, source = compile_nested(node)
        self.assertIn('.evaluate(', source)
        self.assertNotIn('def _fused_sync_', source)

class SynchronousFusionIntegrationTests(unittest.TestCase):
    def test_real_loop_uses_helpers_and_keeps_mutating_name_hooks(self):
        from unittest.mock import patch
        results = []
        source = 'a=1;r=0;For i=1 To 3 Do r=r+a*3-1;EndDo;'
        for outlined in (False, True):
            vm = Interpreter(execution_backend='compiled-strict')
            seen = []
            def before(node):
                from yadinassi.owned_syntax import syntax_kind
                from yadinassi.syntax import ast
                if syntax_kind(node) is ast.Name and node.name.casefold() == 'a':
                    vm.variables['a'] += 1
                    seen.append(vm.variables['a'])
            vm.compiled_before = before
            original = fusion.ExpressionEmitter._outline
            calls = []
            def outline(emitter, node, depth):
                calls.append(node)
                return original(emitter, node, depth)
            if outlined:
                with patch.object(fusion.ExpressionEmitter, '_outline', outline):
                    vm.execute(source)
                self.assertTrue(calls)
            else:
                with patch.object(fusion.ExpressionEmitter, '_synchronous', return_value=False):
                    vm.execute(source)
            results.append((vm.variables['r'], seen))
        self.assertEqual(results[0], results[1])
        self.assertEqual(results[1], (24, [2, 3, 4]))

    def test_retained_helpers_do_not_capture_unrelated_literal(self):
        import gc
        import weakref
        class Payload: pass
        vm = Interpreter(execution_backend='compiled-strict')
        program = parse('Function F() r=0;For i=1 To 3 Do r=r+i*3-1;EndDo;Return r;EndFunction x=0;')
        value = Payload()
        reference = weakref.ref(value)
        program[-1].value.value = value
        vm.execute_program(program)
        del program, value
        vm.variables.pop('x')
        gc.collect()
        self.assertIsNone(reference())
        for _ in range(3):
            vm.execute('other=1;')
        vm.execute('r=F();')
        self.assertEqual(vm.variables['r'], 15)
        self.assertEqual(vm.compiled_backend_stats['interpreter_fallbacks'], 0)

    def test_helper_source_charged_to_function_and_unit_budgets(self):
        from yadinassi.compiled_backend import CompiledUnsupported
        source = 'r=0;For i=1 To 3 Do r=r+i*3-1;EndDo;'
        for limit in ('MAX_INLINE_FUNCTION_BYTES', 'MAX_PLAIN_SOURCE_BYTES'):
            vm = Interpreter(execution_backend='compiled-strict')
            setattr(vm._compiled(), limit, 100)
            with self.assertRaises(CompiledUnsupported):
                vm.execute(source)
            self.assertNotIn('r', vm.variables)
