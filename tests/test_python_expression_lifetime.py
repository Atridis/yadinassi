"""Direct generated expression suspension keeps its admitted code alive."""
import unittest
from decimal import Decimal
from yadinassi import Interpreter
from yadinassi.syntax import ast
from yadinassi.syntax.parser import parse

class GeneratedExpressionLifetimeTests(unittest.TestCase):
    def admitted(self):
        vm = Interpreter(execution_backend='compiled-strict')
        self.addCleanup(vm.close)
        engine = vm._compiled()
        literal = parse('r=1;')[0].value
        node = ast.Await(literal.token, literal)
        engine.prepare_node(node)
        return vm, engine, node

    def test_resume_retains_plans_and_balances_frames(self):
        vm, engine, node = self.admitted()
        frame = engine.run_node(node)
        self.assertEqual(next(frame).value, Decimal(1))
        self.assertEqual(engine.active_frames, 1)
        with self.assertRaisesRegex(RuntimeError, 'active frames'): engine.release()
        with self.assertRaises(StopIteration) as done: frame.send(Decimal(7))
        self.assertEqual(done.exception.value, Decimal(7))
        self.assertEqual(engine.active_frames, 0)
        engine.release()
        self.assertEqual(engine._nodes, {})
        self.assertEqual(engine.stats['interpreter_fallbacks'], 0)

    def test_close_and_throw_balance_without_releasing_other_frame(self):
        for outcome in ('close', 'throw'):
            with self.subTest(outcome=outcome):
                vm, engine, node = self.admitted()
                first, second = engine.run_node(node), engine.run_node(node)
                next(first); next(second)
                self.assertEqual(engine.active_frames, 2)
                if outcome == 'close': first.close()
                else:
                    marker = ValueError('cancelled')
                    with self.assertRaises(ValueError) as caught: first.throw(marker)
                    self.assertIs(caught.exception, marker)
                self.assertEqual(engine.active_frames, 1)
                with self.assertRaises(RuntimeError): engine.release()
                second.close()
                self.assertEqual(engine.active_frames, 0)
                engine.release()

    def test_expression_error_and_normal_completion_balance(self):
        for source, error in (('r=1+2;', None), ('r=1/0;', Exception)):
            with self.subTest(source=source):
                vm = Interpreter(); self.addCleanup(vm.close)
                engine = vm._compiled(); node = parse(source)[0].value
                engine.prepare_node(node)
                if error:
                    with self.assertRaises(error): vm._scheduler.run_inline(engine.run_node(node))
                else: self.assertEqual(vm._scheduler.run_inline(engine.run_node(node)), Decimal(3))
                self.assertEqual(engine.active_frames, 0)
                engine.release()

    def test_direct_name_reference_getter_cannot_release_live_plan(self):
        from yadinassi.values import Reference
        for fails in (False, True):
            with self.subTest(fails=fails):
                vm = Interpreter(); self.addCleanup(vm.close)
                engine = vm._compiled(); node = parse('r=x;')[0].value
                events = []
                marker = ValueError('getter failed')
                def getter():
                    events.append(engine.active_frames)
                    with self.assertRaises(RuntimeError): engine.release()
                    if fails: raise marker
                    return Decimal(7)
                vm.locals = {'x': Reference(getter, lambda value: None)}
                engine.prepare_node(node)
                if fails:
                    with self.assertRaises(ValueError) as caught:
                        vm._scheduler.run_inline(engine.run_node(node))
                    self.assertIs(caught.exception, marker)
                else:
                    self.assertEqual(vm._scheduler.run_inline(engine.run_node(node)), Decimal(7))
                self.assertEqual(events, [1])
                self.assertEqual(engine.active_frames, 0)
                engine.release()
