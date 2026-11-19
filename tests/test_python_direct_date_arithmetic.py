"""Native Python operators reuse measured Date tick algorithms, not VM dispatch."""
from decimal import Decimal, localcontext, Rounded, Inexact
import unittest
from unittest.mock import patch
from yadinassi import Interpreter
from yadinassi.temporal.dates import BSLDate, MAX_TICKS, UnsupportedDateRange, shift_date, date_difference

class DirectDateArithmeticTests(unittest.TestCase):
    def test_python_ticks_match_existing_algorithms(self):
        value=BSLDate(123456789)
        for seconds in ('1','-1','0.00005','-0.00005','0.12345','123.45678'):
            delta=Decimal(seconds)
            self.assertEqual(value+delta,shift_date(value,delta))
            self.assertEqual(value-delta,shift_date(value,delta.copy_negate()))
        self.assertEqual(value-BSLDate(123450000),date_difference(value,BSLDate(123450000)))
    def test_direct_and_reference_program_values_and_order(self):
        source='a=Date(2024,1,1);b=a+0.12345;c=b-0.00005;elapsed=c-a;'
        results=[]
        for backend in ('interpreter','python-direct'):
            vm=Interpreter(execution_backend=backend, allow_extensions=True)
            try:
                vm.execute(source)
                results.append((vm.variables['b'].ticks,vm.variables['c'].ticks,vm.variables['elapsed']))
            finally:vm.close()
        self.assertEqual(*results)
        vm=Interpreter(allow_extensions=True);seen=[]
        vm.register_function('Left',lambda:seen.append('left') or BSLDate(10000))
        vm.register_function('Right',lambda:seen.append('right') or Decimal(1))
        try:
            with patch.object(Interpreter,'visit_Binary',side_effect=AssertionError('VM dispatch')):
                vm.execute('result=Left()+Right();')
            self.assertEqual(seen,['left','right']);self.assertEqual(vm.variables['result'].ticks,20000)
        finally:vm.close()
    def test_wrong_types_do_not_invoke_reflected_host_callbacks(self):
        class Foreign:
            def __radd__(self,other):raise AssertionError('host callback')
            def __rsub__(self,other):raise AssertionError('host callback')
        for operand in (True,1,'1',Foreign()):
            with self.assertRaisesRegex(TypeError,'число секунд'):BSLDate(10000)+operand
            with self.assertRaisesRegex(TypeError,'число секунд'):BSLDate(10000)-operand
    def test_range_markers_and_decimal_context_remain_exact(self):
        for value,delta in ((BSLDate(0),Decimal(-1)),(BSLDate(MAX_TICKS),Decimal(1))):
            marked=value+delta
            self.assertTrue(marked.boundary)
            with self.assertRaises(UnsupportedDateRange):marked+Decimal(0)
        with self.assertRaises(UnsupportedDateRange):BSLDate(0)-Decimal('0.0001')
        with localcontext() as context:
            context.prec=1;context.traps[Rounded]=True;context.traps[Inexact]=True
            self.assertEqual((BSLDate(123456789)-Decimal('0.1234')).ticks,123455555)
