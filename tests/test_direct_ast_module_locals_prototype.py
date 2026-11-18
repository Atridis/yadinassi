import unittest
from decimal import Decimal as D
from yadinassi import Interpreter
from yadinassi.syntax.parser import parse

class ModuleLocalsPrototypeTests(unittest.TestCase):
    def vm(self):
        vm=Interpreter();self.addCleanup(vm.close);return vm
    def test_host_callback_reads_writes_and_exception(self):
        vm=self.vm();seen=[]
        def touch():
            seen.append(vm.variables['x']);vm.variables['x']=D(9);return D(2)
        vm.register_function('Touch',touch)
        vm.execute('X=3;Y=Touch();R=X+Y;')
        self.assertEqual((seen,vm.variables['r']),([D(3)],D(11)))
        def fail():vm.variables['x']=D(20);raise ValueError('fail')
        vm.register_function('Fail',fail)
        vm.execute('X=4;Try Fail();Except R=X;EndTry;')
        self.assertEqual(vm.variables['r'],D(20))
    def test_execute_and_eval_live_state(self):
        vm=self.vm();vm.execute('X=3;Execute("X=X+4;");R=Eval("X*2");')
        self.assertEqual(vm.variables['r'],D(14))
    def test_partial_state_on_failure(self):
        vm=self.vm()
        with self.assertRaises(Exception):vm.execute('A=New Array;A.Add(3);R=7;X=A[99];After=1;')
        self.assertEqual(vm.variables['r'],D(7));self.assertNotIn('after',vm.variables)
    def test_host_reference_sync(self):
        vm=self.vm()
        def inc(ref):ref.set(ref.get()+D(1))
        vm.register_function('Inc',inc);vm.functions['inc'].reference_parameters=frozenset({0})
        vm.execute('X=3;Inc(X);R=X;');self.assertEqual(vm.variables['r'],D(4))
    def test_close_during_callback_remains_fatal(self):
        vm=self.vm();vm.register_function('Stop',lambda:vm.close())
        from yadinassi.experimental_naked_boundaries import BoundaryViolation
        with self.assertRaises(BoundaryViolation):vm.execute('X=1;Try Stop();Except Caught=True;EndTry;After=1;')
        self.assertNotIn('caught',vm.variables);self.assertNotIn('after',vm.variables)
    def test_new_slot_zero_loop_and_declared_slot(self):
        vm=self.vm();vm.execute('Var R;For I=3 To 1 Do Missing=1;EndDo;')
        self.assertIsNone(vm.variables['r']);self.assertNotIn('missing',vm.variables)

if __name__=='__main__':unittest.main()
