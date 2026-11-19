import unittest
from decimal import Decimal
from unittest.mock import patch
from yadinassi import Interpreter
from yadinassi.syntax.parser import parse

class ArrayLeafReadTests(unittest.TestCase):
    def test_native_leaf_read_does_not_bind_partial(self):
        vm=Interpreter();self.addCleanup(vm.close)
        if True:
            plan=vm.prepare_program(parse('A=New Array;A.Add(7);I=0;R=A[I]+A[(0)];'))
            globals_=plan._plan.function.__globals__
            with patch.dict(globals_,{'_partial':lambda *a,**k:self.fail('unexpected partial')}):
                vm.execute_prepared(plan)
            self.assertEqual(vm.variables['r'],Decimal(14))
    def test_cached_plan_rechecks_receiver_and_decimal_index(self):
        from yadinassi.types.values import BSLArray
        vm=Interpreter();self.addCleanup(vm.close)
        plan=vm.prepare_program(parse('R=A[I];'))
        for receiver in ([Decimal(7)],BSLArray(Decimal(1))):
            vm.variables['a']=receiver;vm.variables['i']=Decimal(0)
            vm.execute_prepared(plan)
        vm.variables['a']=[Decimal(7)]
        for index in (Decimal(-1),Decimal('0.5'),Decimal(1)):
            vm.variables['i']=index
            with self.assertRaises(Exception):vm.execute_prepared(plan)
    def test_complex_index_and_receiver_effects_remain_once(self):
        vm=Interpreter();self.addCleanup(vm.close);events=[]
        vm.register_function('Receiver',lambda:events.append('receiver') or [Decimal(9)])
        vm.register_function('Index',lambda:events.append('index') or Decimal(0))
        vm.execute('R=Receiver()[Index()];')
        self.assertEqual(events,['receiver','index']);self.assertEqual(vm.variables['r'],Decimal(9))

if __name__=='__main__':unittest.main()
