"""Public direct brackets use native storage without data-flow assumptions."""
import ast
from contextlib import closing
from decimal import Decimal
import unittest
from unittest.mock import patch

from yadinassi import Interpreter
from yadinassi.types.errors import BSLRuntimeError


class OrdinarySubscriptTests(unittest.TestCase):
    def test_one_prepared_plan_uses_native_brackets_for_exact_data(self):
        with closing(Interpreter()) as vm:
            plan = vm.prepare('A[K]=Value; A[K];')
            tree = ast.parse(plan._plan.generated_source)
            self.assertTrue(any(type(node) is ast.Subscript and type(node.ctx) is ast.Store
                                for node in ast.walk(tree)))
            with patch.dict(plan._plan.function.__globals__, {
                    '_ordinary_bracket_reader': lambda *args: self.fail('non-native index adapter')}):
                for setup in (
                        'A=New Array(2); K=0.5;',
                        'A=New Map; K=True; A[1]=99;',
                        'A=New Structure("Original",0); K="ORIGINAL";'):
                    with self.subTest(setup=setup):
                        vm.execute(setup)
                        vm.variables['value'] = 17
                        self.assertEqual(vm.execute_prepared(plan), 17)
                        if 'Map' in setup:
                            self.assertEqual(vm.execute('A[1];'), 99)
                            self.assertIsNone(vm.execute('A["missing"];'))
                        elif 'Structure' in setup:
                            self.assertEqual(vm.execute('A["original"];'), 17)
                            with self.assertRaises(BSLRuntimeError):
                                vm.execute('A["missing"]=14;')

    def test_noncanonical_host_mapping_preserves_missing_and_fixed_bounds(self):
        with closing(Interpreter()) as vm:
            plan = vm.prepare('A[K];', 'index.bsl')
            vm.variables.update(a={},k='unmapped')
            self.assertIsNone(vm.execute_prepared(plan))
            vm.execute('A=New FixedArray(New Array(1));')
            vm.variables['k'] = Decimal(0)
            self.assertIsNone(vm.execute_prepared(plan))
            vm.variables['k'] = Decimal('0.5')
            with self.assertRaises(BSLRuntimeError) as caught:
                vm.execute_prepared(plan)
            self.assertEqual(caught.exception.source, 'index.bsl')

    def test_nested_actual_is_compiled_and_evaluated_once(self):
        output = []
        with closing(Interpreter(output.append)) as vm:
            vm.execute('Function Key() Message("key"); Return 0.5; EndFunction;'
                       ' A=New Map; A[0.5]=1; B=New Array(2); B[1]=91;')
            plan = vm.prepare('B[A[Key()]];')
            self.assertEqual(vm.execute_prepared(plan), 91)
            self.assertEqual(output, ['key'])

    def test_write_keeps_captured_receiver_and_defers_index_validation(self):
        for prepared in (False, True):
            output = []
            with self.subTest(prepared=prepared), closing(Interpreter(output.append)) as vm:
                vm.execute('Var A; A=New Array(1); Old=A;'
                           'Function Index(Val K) Message("index"); A=New Array(1); Return K; EndFunction;'
                           'Function Value() Message("value"); Return 31; EndFunction;')
                def run(source):
                    if prepared:
                        return vm.execute_prepared(vm.prepare(source))
                    return vm.execute(source)

                run('Try A[Index(-0.5)]=Value(); Except Message("caught"); EndTry;')
                self.assertEqual(output, ['index', 'value', 'caught'])
                self.assertIsNot(vm.variables['a'],vm.variables['old'])
                self.assertIsNone(vm.execute('Old[0];'))
                self.assertIsNone(vm.execute('A[0];'))
                output.clear()
                run('A=Old; A[Index(0.5)]=Value();')
                self.assertEqual(output, ['index', 'value'])
                self.assertEqual(vm.execute('Old[0];'),31)
                self.assertIsNone(vm.execute('A[0];'))
