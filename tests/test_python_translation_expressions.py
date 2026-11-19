"""Behavior retained from retired translation engines; only the direct backend runs.

Implementation-only registry, fusion emitter, instrumentation and inline-budget
checks belonged to deleted engines and are retired, not skipped or emulated.
Unsupported behavioral cases deliberately remain ordinary failing tests.
"""
import unittest
from decimal import Decimal
from unittest.mock import patch
from yadinassi import Interpreter, BSLError
class DirectExpressionBehavior(unittest.TestCase):

    def expression(self, source, vm=None):
        if vm is None:
            vm = Interpreter()
            self.addCleanup(vm.close)
        vm.execute('result=' + source + ';')
        return (vm.variables['result'], ())

    def test_arithmetic_and_boolean_decimal(self):
        for source, expected in [('2+3*4', 14), ('Истина=1', True), ('1/4', Decimal('.25')), ('7%3', 1), ('-(2+3)', -5), ('"x"+2', 'x2')]:
            with self.subTest(source=source):
                self.assertEqual(self.expression(source)[0], expected)

    def test_short_circuit_and_conditional(self):
        for source, expected in [('Ложь И Boom()', False), ('Истина Или Boom()', True), ('?(Истина,7,Boom())', 7)]:
            self.assertEqual(self.expression(source)[0], expected)

    def test_nested_builtin_calls(self):
        self.assertEqual(self.expression('СтрДлина(СокрЛП(" abc "))')[0], 3)

    def test_host_order_and_once(self):
        vm = Interpreter()
        events = []
        vm.register_function('Tick', lambda x: events.append(x) or x)
        vm.register_function('Pair', lambda a, b: 10 * a + b)
        self.assertEqual(self.expression('Pair(Tick(1),Tick(2))', vm)[0], 12)
        self.assertEqual(events, [1, 2])

    def test_new_and_method(self):
        vm = Interpreter()
        vm.variables['a'] = self.expression('Новый Массив(3)', vm)[0]
        self.assertEqual(self.expression('a.Количество()', vm)[0], 3)

    def test_eval_rejects_bad_arity_before_argument_effect(self):
        from yadinassi import BSLError
        vm = Interpreter()
        events = []
        vm.register_function('Tick', lambda: events.append(1))
        with self.assertRaises(BSLError):
            self.expression('Eval(Tick(),Tick())', vm)
        self.assertEqual(events, [])

    def test_host_reference_variable_and_index(self):
        from yadinassi.types.values import HostFunction, BSLArray
        vm = Interpreter()
        vm.variables['x'] = Decimal(1)
        vm.execute('a=New Array(1);')

        def set_value(reference):
            reference.set(Decimal(9))
            return reference.get()
        vm.functions['setvalue'] = HostFunction('SetValue', set_value, reference_parameters=frozenset({0}))
        self.assertEqual(self.expression('SetValue(x)', vm)[0], 9)
        self.assertEqual(vm.variables['x'], 9)
        self.assertEqual(self.expression('SetValue(a[0])', vm)[0], 9)
        self.assertEqual(vm.variables['a'][0], 9)

    def test_reference_constructor_effects_once(self):
        from yadinassi.types.values import HostFunction, BSLArray
        vm = Interpreter()
        events = []
        array = [None]
        vm.register_function('Receiver', lambda: events.append('receiver') or array)
        vm.register_function('Index', lambda: events.append('index') or Decimal(0))
        vm.functions['setvalue'] = HostFunction('SetValue', lambda ref: ref.set(Decimal(3)), reference_parameters=frozenset({0}))
        self.expression('SetValue(Receiver()[Index()])', vm)
        self.assertEqual(events, ['receiver', 'index'])
        self.assertEqual(array[0], 3)
