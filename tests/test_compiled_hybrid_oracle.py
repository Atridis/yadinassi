"""Retained numeric/effect examples, now with explicit direct behavioral outcomes.

The deleted hybrid/interpreter subprocess oracle and engine counters are retired.
"""
from decimal import Decimal
import unittest
from yadinassi import Interpreter

class DirectNumericBehaviorTests(unittest.TestCase):
    def test_numeric_loop_and_effect_examples(self):
        cases = [
            ('r=0; Для i=1 По 20 Цикл r=r+i*3-7; КонецЦикла;',490,[]),
            ('r=0; Для i=1 По 10 Цикл i=i+1;r=r+i;КонецЦикла;',30,[]),
            ('n=3;r=0;Для i=1 По n Цикл n=0;r=r+1;КонецЦикла;',3,[]),
            ('Для i=0.5 По 3.7 Цикл r=i;КонецЦикла;',Decimal('3.5'),[]),
            ('Функция f() Сообщить(7);Возврат 2;КонецФункции Для i=f() По f()+1 Цикл r=i;КонецЦикла;',3,['7','7']),
        ]
        for source,expected,messages in cases:
            with self.subTest(source=source):
                output=[];vm=Interpreter(execution_backend='python-direct',output=output.append)
                vm.execute(source)
                self.assertEqual(vm.variables['r'],expected)
                self.assertEqual(output,messages)
    def test_fault_retains_prior_loop_effect(self):
        vm=Interpreter(execution_backend='python-direct')
        with self.assertRaises(Exception):
            vm.execute('r=0;Для i=1 По 2 Цикл r=r+1;z=1/0;КонецЦикла;')
        self.assertEqual(vm.variables['r'],1)
        self.assertNotIn('z',vm.variables)
