"""Explicit expression-list entry points are compiled before their first effect."""
import unittest
from decimal import Decimal
from unittest.mock import patch
from yadinassi import Interpreter
from yadinassi.compiled_backend import CompiledUnsupported
from yadinassi.syntax.parser import parse
from yadinassi.syntax import ast
from yadinassi.owned_syntax import origin_node as syntax_origin

def finish(generator):
    try:
        next(generator)
    except StopIteration as done:
        return done.value
    raise AssertionError('unexpected suspension')

class ExplicitGeneratedBlockTests(unittest.TestCase):
    def vm(self):
        vm=Interpreter(execution_backend='compiled-strict');self.addCleanup(vm.close);return vm

    def test_metadata_becomes_explicit_entry_only_on_request(self):
        vm=self.vm();engine=vm._compiled();call=parse('Unused(1+2,4+5);')[0].expression
        engine.prepare_node(call)
        self.assertTrue(engine.has_block(call.arguments))
        self.assertFalse(engine.has_executable_block(call.arguments))
        original=Interpreter.compiled_before;seen=[]
        def before(instance,node):
            seen.append(id(syntax_origin(node)));return original(instance,node)
        with patch.object(Interpreter,'compiled_before',before), patch.object(Interpreter,'visit_Binary',side_effect=AssertionError('AST adapter')):
            result=finish(vm.block(call.arguments))
        self.assertEqual(result,Decimal(9))
        self.assertTrue(engine.has_executable_block(call.arguments))
        for node in call.arguments:self.assertEqual(seen.count(id(node)),1)
        before_count=engine.stats['prepared_units']
        self.assertEqual(finish(vm.block(call.arguments)),Decimal(9))
        self.assertEqual(engine.stats['prepared_units'],before_count)
        self.assertEqual(engine.stats['interpreter_fallbacks'],0)

    def test_explicit_await_block_suspends_and_closes_balanced(self):
        for close in (False,True):
            with self.subTest(close=close):
                vm=self.vm();engine=vm._compiled();literal=parse('x=1;')[0].value
                body=[ast.Await(literal.token,literal)];engine.prepare(body)
                frame=vm.block(body);self.assertEqual(next(frame).value,Decimal(1))
                self.assertGreater(engine.active_frames,0)
                with self.assertRaises(RuntimeError):engine.release()
                if close:frame.close()
                else:
                    with self.assertRaises(StopIteration) as done:frame.send(Decimal(7))
                    self.assertEqual(done.exception.value,Decimal(7))
                self.assertEqual(engine.active_frames,0)

    def test_entry_preparation_budget_failure_precedes_effects_and_rolls_back(self):
        vm=self.vm();engine=vm._compiled();effects=[]
        vm.register_function('Tick',lambda:effects.append(1) or Decimal(3))
        call=parse('Unused(Tick());')[0].expression;engine.prepare_node(call)
        self.assertFalse(engine.has_executable_block(call.arguments))
        units=dict(engine._python_units);nodes=dict(engine._nodes)
        engine.MAX_INLINE_UNIT_BYTES=0
        with self.assertRaises(CompiledUnsupported):finish(vm.block(call.arguments))
        self.assertEqual(effects,[])
        self.assertEqual(engine._python_units,units);self.assertEqual(engine._nodes,nodes)
        self.assertFalse(engine.has_executable_block(call.arguments))

    def test_generated_residual_lookup_does_not_compile_missing_entry(self):
        vm=self.vm();engine=vm._compiled();call=parse('Unused(1+2);')[0].expression;engine.prepare_node(call)
        before=engine.stats['prepared_units']
        with self.assertRaises(CompiledUnsupported):finish(engine.run_block(call.arguments))
        self.assertEqual(engine.stats['prepared_units'],before)
        self.assertFalse(engine.has_executable_block(call.arguments))

    def test_foreign_metadata_is_not_executable_in_another_engine(self):
        vm=self.vm();other=self.vm();call=parse('Unused(1+2);')[0].expression;vm._compiled().prepare_node(call)
        view=vm._compiled()._owned.existing(call.arguments)
        self.assertFalse(other._compiled().has_executable_block(view))
