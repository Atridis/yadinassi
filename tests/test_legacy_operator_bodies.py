"""Legacy operators avoid compiler-helper frames without semantic drift."""
import ast
from decimal import Decimal
from pathlib import Path
import unittest
from yadinassi import Interpreter


class LegacyOperatorBodiesTests(unittest.TestCase):
    def test_direct_operator_tails_match_compiler_value_helpers(self):
        tree = ast.parse((Path(__file__).resolve().parents[1] /
                          'yadinassi/runtime.py').read_text(encoding='utf-8'))
        cls = next(n for n in tree.body if isinstance(n, ast.ClassDef)
                   and n.name == 'Interpreter')
        methods = {n.name: n for n in cls.body if isinstance(n, ast.FunctionDef)}
        helpers = {n.name: n for n in tree.body if isinstance(n, ast.FunctionDef)}
        # Unary consumes its operand first; Binary retains short-circuit handling
        # before the eager value helper's identical operation tail.
        for visitor, helper, offset in (
                ('visit_Unary', 'unary_value', 1),
                ('visit_Binary', 'binary_values', 5)):
            body = methods[visitor].body[offset:]
            if visitor == 'visit_Unary':
                class Normalize(ast.NodeTransformer):
                    def visit_Attribute(self, node):
                        if (isinstance(node.value, ast.Name) and
                                node.value.id == 'node' and node.attr == 'operator'):
                            return ast.Name(id='operator', ctx=ast.Load())
                        return self.generic_visit(node)
                body = [Normalize().visit(n) for n in body]
            self.assertEqual(ast.dump(ast.Module(body=body, type_ignores=[])),
                             ast.dump(ast.Module(body=helpers[helper].body,
                                                 type_ignores=[])))

    def test_operators_order_short_circuit_and_errors_in_both_backends(self):
        source = '''
        x = A() * B() + 9 - 2;
        y = Ложь И A(); z = Истина Или B();
        n = -x; p = +x; q = Не Ложь;
        Попытка bad = 1 / 0; Исключение caught = Истина; КонецПопытки;
        '''
        for mode in ('interpreter', 'compiled-strict'):
            with self.subTest(mode=mode):
                calls=[]
                vm=Interpreter(execution_backend=mode)
                vm.register_function('A', lambda: calls.append('a') or Decimal(3))
                vm.register_function('B', lambda: calls.append('b') or Decimal(4))
                vm.execute(source)
                self.assertEqual(calls,['a','b'])
                self.assertEqual([vm.variables[k] for k in ('x','n','p','q','caught')],
                                 [Decimal(19),Decimal(-19),Decimal(19),True,True])
