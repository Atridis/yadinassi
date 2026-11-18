"""Persistent routine arity reports retain the same pre-effect rejection."""
import unittest
from yadinassi import Interpreter
from yadinassi.errors import BSLError


class PersistentRoutineArityTests(unittest.TestCase):
    def test_separate_calls_report_expected_and_actual_before_effects(self):
        for declaration,call in (('Procedure P(A,B) Message("body");EndProcedure','P'),
                                 ('Процедура Работа(А,Б) Сообщить("body");КонецПроцедуры','Работа')):
            output=[];vm=Interpreter(output.append,execution_backend='python-direct');self.addCleanup(vm.close)
            vm.execute(declaration,'definition.bsl')
            for suffix,count in (('()',0),('(Message("bad"))',1),('(1,2,Message("bad"))',3)):
                with self.subTest(call=call,count=count),self.assertRaisesRegex(BSLError,f'2 аргументов, получено {count}') as caught:
                    vm.execute(call+suffix,'caller.bsl')
                self.assertEqual(caught.exception.source,'caller.bsl')
                self.assertEqual(output,[])

    def test_optional_bounds_do_not_reject_valid_calls(self):
        for backend in ('python-direct','compiled-strict'):
            vm=Interpreter(execution_backend=backend);self.addCleanup(vm.close)
            vm.execute('Function F(Val A,Val B=2) Return A+B;EndFunction')
            self.assertEqual(vm.execute('F(3)'),5);self.assertEqual(vm.execute('F(3,4)'),7)
            for call,count in (('F()',0),('F(1,2,3)',3)):
                with self.assertRaisesRegex(BSLError,f'2 аргументов, получено {count}'):vm.execute(call)

    def test_redeclared_signature_drives_new_diagnostic(self):
        vm=Interpreter(execution_backend='python-direct');self.addCleanup(vm.close)
        vm.execute('Function F(X) Return X;EndFunction');self.assertEqual(vm.execute('F(1)'),1)
        vm.execute('Function F(X,Y,Z) Return X+Y+Z;EndFunction')
        with self.assertRaisesRegex(BSLError,'3 аргументов, получено 1'):vm.execute('F(1)')
        self.assertEqual(vm.execute('F(1,2,3)'),6)
