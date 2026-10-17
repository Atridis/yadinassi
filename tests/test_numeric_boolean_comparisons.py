"""Developer Guide 8.3.27 §4.5.3 operator conversions, not lookup rules."""

from decimal import Decimal, Inexact, Rounded, localcontext
import operator
import unittest

from yadinassi import Interpreter
from yadinassi.errors import BSLRuntimeError
from yadinassi.values import BSLObject


OPERATORS = {'=': operator.eq, '<>': operator.ne, '<': operator.lt,
             '<=': operator.le, '>': operator.gt, '>=': operator.ge}


class NumericBooleanComparisonTests(unittest.TestCase):
    def setUp(self):
        self.output = []
        self.vm = Interpreter(self.output.append)

    def test_all_operators_in_both_orders_exact_numeric_conversion(self):
        for text in ['-9999999999999999999999999999999999999999', '-2', '-0.1',
                     '-0', '0', '0.000', '0.1', '0.999999999999999999999999999999999',
                     '1', '1.00', '1.000000000000000000000000000000001', '2',
                     '9999999999999999999999999999999999999999']:
            number = Decimal(text)
            for boolean in [False, True]:
                for reverse in [False, True]:
                    left, right = (boolean, number) if reverse else (number, boolean)
                    self.vm.variables.update(left=left, right=right)
                    a, b = (Decimal(int(boolean)), number) if reverse else (number, Decimal(int(boolean)))
                    for symbol, compare in OPERATORS.items():
                        with self.subTest(number=text, boolean=boolean, reverse=reverse, op=symbol):
                            self.assertIs(self.vm.execute(f'(left {symbol} right)'), compare(a, b))
                    self.assertIs(self.vm.variables['left'], left)
                    self.assertIs(self.vm.variables['right'], right)

    def test_comparisons_ignore_decimal_context_and_never_round(self):
        with localcontext() as context:
            context.prec = 1
            context.traps[Inexact] = context.traps[Rounded] = True
            context.clear_flags()
            self.test_all_operators_in_both_orders_exact_numeric_conversion()
            self.assertFalse(any(context.flags.values()))

    def test_bilingual_literals_control_flow_and_result_types(self):
        self.vm.execute('''
            Сообщить(Истина = 1); Message(0 = False);
            Сообщить(Ложь <> 0); Message(1 <> True);
            If True <= 1 And 0 >= False Then Message("branch"); EndIf;
            Message(?(0.5 < True, "fraction", "bad"));
            Message(Not False = 0); Message(Not True > 1);
            Message(TypeOf(True = 1) = Type("Boolean"));
            Message(ValueToStringInternal(True)); Message(ValueToStringInternal(1));
        ''')
        self.assertEqual(self.output, ['Да', 'Да', 'Нет', 'Нет', 'branch', 'fraction',
                                       'Нет', 'Да', 'Да', '{"B",1}', '{"N",1}'])

    def test_operands_evaluate_once_in_order_and_errors_recover(self):
        calls = []
        def left():
            calls.append('left')
            return True
        def right():
            calls.append('right')
            return Decimal('1')
        self.vm.register_function('LeftValue', left)
        self.vm.register_function('RightValue', right)
        for symbol in OPERATORS:
            calls.clear()
            self.vm.execute(f'(LeftValue() {symbol} RightValue())')
            self.assertEqual(calls, ['left', 'right'])
        self.vm.execute('value = "kept";')
        with self.assertRaises(BSLRuntimeError):
            self.vm.execute('value = True < "1";')
        self.assertEqual(self.vm.variables['value'], 'kept')
        self.assertIs(self.vm.execute('(True = 1)'), True)

    def test_no_new_string_undefined_object_or_enum_coercion(self):
        for expression in ['"1"', '"True"', 'Undefined', 'New Array',
                           'Type("Number")', 'RoundMode.Round15as10', 'RoundMode']:
            for left, right in [('True', expression), (expression, 'True'),
                                ('1', expression), (expression, '1')]:
                with self.subTest(left=left, right=right):
                    self.assertIs(self.vm.execute(f'({left} = {right})'), False)
                    self.assertIs(self.vm.execute(f'({left} <> {right})'), True)
                    for symbol in ['<', '<=', '>', '>=']:
                        with self.assertRaises(BSLRuntimeError):
                            self.vm.execute(f'({left} {symbol} {right})')

    def test_host_int_float_and_decimal_subclasses_do_not_gain_conversion(self):
        class HostDecimal(Decimal):
            pass
        class HostObject(BSLObject):
            def __int__(self):
                raise AssertionError('No host conversion')
        for host in [1, 0, 1.0, 0.0, HostDecimal('1'), HostObject()]:
            self.vm.variables['host'] = host
            for left, right in [('host', 'True'), ('True', 'host')]:
                with self.subTest(host=type(host), left=left):
                    self.assertIs(self.vm.execute(f'({left} = {right})'), False)
                    self.assertIs(self.vm.execute(f'({left} <> {right})'), True)
                    for symbol in ['<', '<=', '>', '>=']:
                        with self.assertRaises(BSLRuntimeError):
                            self.vm.execute(f'({left} {symbol} {right})')

    def test_map_keys_and_array_lookup_do_not_inherit_operator_conversion(self):
        # Map distinction is native-backed; Array.Find remains the existing
        # typed subset pending separate native evidence for mixed lookup.
        self.vm.execute('''
            m = New Map; m[True] = "boolean"; m[1] = "number";
            m[False] = "false"; m[0] = "zero";
            fixed = New FixedMap(m);
            Message(m.Count()); Message(fixed.Count());
            Message(fixed[True]); Message(fixed[1]);
            Message(fixed[False]); Message(fixed[0]);
            values = New Array; values.Add(True); values.Add(1);
            values.Add(False); values.Add(0);
            frozen = New FixedArray(values);
            Message(values.Find(True)); Message(values.Find(1));
            Message(frozen.Find(False)); Message(frozen.Find(0));
            Message(True = 1); Message(False = 0);
        ''')
        self.assertEqual(self.output, ['4', '4', 'boolean', 'number', 'false', 'zero',
                                      '0', '1', '2', '3', 'Да', 'Да'])


if __name__ == '__main__':
    unittest.main()
