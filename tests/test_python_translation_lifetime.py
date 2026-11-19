"""Public lifetime and dynamic-code behavior, without deleted unit registries."""
import gc
import unittest
import weakref
from decimal import Decimal
from yadinassi import Interpreter, BSLError

class DirectLifetimeBehavior(unittest.TestCase):
    def test_discarded_host_result_is_released(self):
        class Resource: pass
        refs=[]
        def create():
            value=Resource();refs.append(weakref.ref(value));return value
        vm=Interpreter();self.addCleanup(vm.close)
        vm.register_function('Resource',create)
        vm.execute('Resource();')
        gc.collect();self.assertIsNone(refs[0]())

    def test_execute_mutates_existing_names_not_fragment_locals(self):
        vm=Interpreter();self.addCleanup(vm.close)
        vm.execute('x=1;Execute "x=x+1;localnew=9;";')
        self.assertEqual(vm.variables['x'],2)
        self.assertNotIn('localnew',vm.variables)
        self.assertIsNone(vm.locals);self.assertEqual(vm._execute_depth[0],0)

    def test_invalid_fragment_has_no_partial_effect(self):
        vm=Interpreter();self.addCleanup(vm.close);effects=[]
        vm.register_function('Tick',lambda:effects.append(1))
        with self.assertRaises(BSLError):vm.execute('Execute "Tick();If";')
        self.assertEqual(effects,[]);self.assertEqual(vm._execute_depth[0],0)

    def test_repeated_dynamic_execution_keeps_retained_default(self):
        vm=Interpreter();self.addCleanup(vm.close)
        vm.execute('Function F(Val X=7) Return X;EndFunction x=0;')
        for i in range(30):
            vm.execute('r=Eval("Eval(""1+2"")");Execute "x=x+1;localnew=9;";')
        self.assertEqual(vm.variables['r'],3);self.assertEqual(vm.variables['x'],30)
        self.assertNotIn('localnew',vm.variables)
        vm.execute('r=F();');self.assertEqual(vm.variables['r'],7)
        self.assertEqual(vm._eval_depth[0],0);self.assertEqual(vm._execute_depth[0],0)
