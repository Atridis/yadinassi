"""Ordinary syntax stays native without requiring a closed-module proof."""
import ast
from decimal import Decimal, localcontext, Inexact, Rounded
import unittest

from yadinassi import BSLError, Interpreter
from yadinassi.syntax.parser import parse


class DirectScalarSyntaxTests(unittest.TestCase):
    def test_native_literals_operators_and_conditions_with_opaque_tail(self):
        messages = []
        source = ('R=?(Not (1<2 And -3>0) And ("texto"="texto"), True, False); '
                  'S=(+(2)+3-1)*2; U=Undefined; Message("tail");')
        for route in ('source', 'ast', 'prepared'):
            with self.subTest(route=route):
                vm = Interpreter(output=messages.append)
                self.addCleanup(vm.close)
                plan = vm.prepare(source)
                py = plan._plan.generated_source
                tree = ast.parse(py)
                self.assertTrue(any(isinstance(n, ast.IfExp) for n in ast.walk(tree)))
                self.assertFalse(any(isinstance(n, ast.Name) and n.id in (
                    '_truth', '_order', '_equal', '_sign', '_dynamic_sign', '_native_add')
                    for n in ast.walk(tree)), py)
                self.assertIn("'texto' == 'texto'", py)
                if route == 'source':
                    vm.execute(source)
                elif route == 'ast':
                    vm.execute_program(parse(source))
                else:
                    vm.execute_prepared(plan)
                self.assertIs(vm.variables['r'], True)
                self.assertEqual(vm.variables['s'], 8)
                self.assertIsNone(vm.variables['u'])
        self.assertEqual(messages, ['tail'] * 3)

    def test_lazy_branches_and_operands_run_once_left_to_right(self):
        events = []
        vm = Interpreter(allow_extensions=True)
        self.addCleanup(vm.close)
        def mark(tag, value):
            events.append(tag)
            return value
        vm.register_function('Mark', mark)
        source = ('A=Mark("left",1)+Mark("right",2); '
                  'B=Not (False And Mark("unreached",True)); '
                  'C=?(True Or Mark("unreached",False),Mark("chosen",7),Mark("unreached",8));')
        vm.execute_prepared(vm.prepare(source))
        self.assertEqual(events, ['left', 'right', 'chosen'])
        self.assertEqual(tuple(vm.variables[k] for k in 'abc'), (3, True, 7))

    def test_unknown_addition_has_one_python_operand_tree(self):
        vm = Interpreter(allow_extensions=True)
        self.addCleanup(vm.close)
        events = []
        vm.register_function('Mark', lambda key, value: events.append(key) or value)
        source = 'Result=Mark("a","x")+(Mark("b",1)+(Mark("c",2)+Mark("d",3)));'
        plan = vm.prepare(source)
        tree = ast.parse(plan._plan.generated_source)
        self.assertNotIn('_native_add', plan._plan.generated_source)
        additions = [node for node in ast.walk(tree)
                     if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add)
                     and isinstance(node.left, ast.IfExp)]
        self.assertEqual(len(additions), 3)
        vm.execute_prepared(plan)
        self.assertEqual(vm.variables['result'], 'x6')
        self.assertEqual(events, ['a', 'b', 'c', 'd'])

    def test_string_addition_exception_does_not_change_neighboring_lowering(self):
        vm = Interpreter(allow_extensions=True)
        self.addCleanup(vm.close)
        calls = []
        vm.register_function('ReadValue', lambda: calls.append('read') or 'prefix')
        source = ('Before=1+2; Text=ReadValue()+3; '
                  'After=0; For I=1 To 4 Do After=After+I; EndDo;')
        plan = vm.prepare(source)
        generated = plan._plan.generated_source
        tree = ast.parse(generated)
        calls_to = lambda name: [node for node in ast.walk(tree)
                                 if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                                 and node.func.id == name]
        self.assertEqual(len(calls_to('_TextAddend')), 1)
        self.assertFalse(calls_to('_publish_module'))
        self.assertFalse(calls_to('_reload_module'))
        loops = [node for node in ast.walk(tree) if isinstance(node, (ast.While, ast.For))]
        self.assertEqual(len(loops), 1)
        self.assertNotIn('_TextAddend', ast.unparse(loops[0]))
        vm.execute_prepared(plan)
        self.assertEqual(calls, ['read'])
        self.assertEqual([vm.variables[key] for key in ('before', 'text', 'after')],
                         [Decimal(3), 'prefix3', Decimal(10)])

    def test_unknown_truth_does_not_use_foreign_python_truth_hook(self):
        events = []
        class Foreign:
            def __bool__(self):
                events.append('truth')
                return True
        vm = Interpreter()
        self.addCleanup(vm.close)
        vm.variables['host'] = Foreign()
        with self.assertRaisesRegex(BSLError, 'Ожидается булево значение или число'):
            vm.execute('A=?(Host,1,2);')
        self.assertEqual(events, [])

    def test_signed_decimal_literals_are_not_rounded_and_keep_scale(self):
        with localcontext() as ambient:
            ambient.prec = 3
            ambient.traps[Inexact] = ambient.traps[Rounded] = True
            vm = Interpreter()
            self.addCleanup(vm.close)
            vm.execute('A=-123456789012345678901234567890123456789.125; B=-0; C=+1.00;')
            self.assertEqual(vm.variables['a'].as_tuple(),
                             Decimal('-123456789012345678901234567890123456789.125').as_tuple())
            self.assertEqual(vm.variables['b'].as_tuple(), Decimal('-0').as_tuple())
            self.assertEqual(vm.variables['c'].as_tuple(), Decimal('1.00').as_tuple())
