import unittest
from decimal import Decimal
from yadinassi import Interpreter
from yadinassi.temporal.dates import BSLDate, MAX_TICKS

class ReflectedDateDiagnosticTests(unittest.TestCase):
    def test_exact_numbers_reject_without_reading_boundary(self):
        for date in (BSLDate(0),BSLDate(0,True),BSLDate(MAX_TICKS,True)):
            for number in (1,Decimal(1)):
                with self.assertRaisesRegex(TypeError,'^Ожидается число$'):number+date
    def test_other_left_kinds_keep_python_rejection(self):
        date=BSLDate(0)
        for value in (True,False,'1',1.0,object()):
            self.assertIs(date.__radd__(value),NotImplemented)
            with self.assertRaises(TypeError):value+date
        self.assertEqual(1+2,3)
        self.assertEqual(Decimal(1)+Decimal(2),Decimal(3))
        self.assertEqual((date+Decimal(1)).ticks,10000)
        with self.assertRaisesRegex(TypeError,'ожидается число секунд'):date+True
    def test_direct_prepared_preserve_target_and_catch(self):
        source='saved=Date(2024,2,29);Try saved=1+saved;Except error=ErrorDescription();EndTry;'
        for prepared in (False,True):
            vm=Interpreter()
            if prepared:vm.execute_prepared(vm.prepare(source))
            else:vm.execute(source)
            self.assertIn('Ожидается число',vm.variables['error'])
            self.assertEqual(vm.variables['saved'],Interpreter().execute('Date(2024,2,29)'))
