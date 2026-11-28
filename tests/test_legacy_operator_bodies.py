"""Retained observable operator contracts on the active generated engine."""
from decimal import Decimal, localcontext
import unittest

from yadinassi import Interpreter


class LegacyOperatorBodiesTests(unittest.TestCase):
    def execute(self, vm, source, prepared):
        if prepared:
            vm.execute_prepared(vm.prepare(source))
        else:
            vm.execute(source)

    def test_direct_operators_preserve_values_and_scalar_coercion(self):
        source = '''
        n=-Input; p=+Input; nz=-SignedZero; pz=+SignedZero;
        zero=Not 0; nonzero=Not 2; already=Not False;
        same=(True=1); different=(False<>0); ordered=(True<2) And (2>True);
        saved="old"; caught=False;
        Try saved=Not "0"; Except caught=True; EndTry;
        '''
        for prepared in (False, True):
            with self.subTest(prepared=prepared):
                vm = Interpreter()
                self.addCleanup(vm.close)
                vm.variables.update(input=Decimal('51.239800'), signedzero=Decimal('0.000'))
                with localcontext() as context:
                    context.prec = 3
                    self.execute(vm, source, prepared)
                for name, expected in (('n','-51.239800'), ('p','51.239800'),
                                       ('nz','-0.000'), ('pz','0.000')):
                    result = vm.variables[name]
                    self.assertIs(type(result), Decimal)
                    self.assertEqual(result.as_tuple(), Decimal(expected).as_tuple())
                for name, expected in (('zero', True), ('nonzero', False), ('already', True),
                                       ('same', True), ('different', False), ('ordered', True),
                                       ('caught', True)):
                    self.assertIs(vm.variables[name], expected)
                self.assertEqual(vm.variables['saved'], 'old')

    def test_operators_order_short_circuit_and_errors_in_direct_execution(self):
        source = '''
        x = A() * B() + 9 - 2;
        y = Ложь И A(); z = Истина Или B();
        n = -x; p = +x; q = Не Ложь;
        Попытка bad = 1 / 0; Исключение caught = Истина; КонецПопытки;
        '''
        for prepared in (False, True):
            with self.subTest(prepared=prepared):
                calls=[]
                vm=Interpreter(allow_extensions=True)
                self.addCleanup(vm.close)
                vm.register_function('A', lambda: calls.append('a') or Decimal(3))
                vm.register_function('B', lambda: calls.append('b') or Decimal(4))
                self.execute(vm, source, prepared)
                self.assertEqual(calls,['a','b'])
                for name, expected in (('x',19),('n',-19),('p',19)):
                    self.assertIs(type(vm.variables[name]),Decimal)
                    self.assertEqual(vm.variables[name],Decimal(expected))
                for name, expected in (('q',True),('caught',True),('y',False),('z',True)):
                    self.assertIs(vm.variables[name],expected)
                self.assertNotIn('bad',vm.variables)
