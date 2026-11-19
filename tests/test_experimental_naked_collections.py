"""Live collection contracts, independent of the retired repair experiment."""
from decimal import Decimal
import unittest
from yadinassi import Interpreter
from yadinassi.types.errors import BSLRuntimeError


class DirectCollectionContracts(unittest.TestCase):
    def run_source(self, source):
        vm = Interpreter()
        self.addCleanup(vm.close)
        vm.execute(source)
        return vm

    def test_direct_loop_and_routine(self):
        vm = self.run_source('Function Inc(Val x) Return x+1;EndFunction a=New Array;For i=1 To 10 Do a.Add(Inc(i));EndDo;s=0;For Each x In a Do s=s+x;EndDo;')
        self.assertEqual(vm.variables['s'], Decimal(65))

    def test_partial_state_survives_error(self):
        vm = Interpreter()
        self.addCleanup(vm.close)
        with self.assertRaises(BSLRuntimeError):
            vm.execute('x=1;y=1/0;')
        self.assertEqual(vm.variables['x'], Decimal(1))

    def test_typed_map_keys_are_distinct(self):
        vm = self.run_source('m=New Map;m.Insert(True,1);m.Insert(1,2);n=m.Count();a=m.Get(True);b=m.Get(1);')
        self.assertEqual(tuple(vm.variables[n] for n in ('n','a','b')), (2,1,2))

    def test_collection_map_key_is_identity(self):
        vm = self.run_source('a=New Array;b=New Array;m=New Map;m.Insert(a,7);n=m.Get(a);other=m.Get(b);')
        self.assertEqual(vm.variables['n'], Decimal(7))
        self.assertIsNone(vm.variables['other'])

    def test_invalid_indices_rejected(self):
        for index in ('-1', 'True', '0.5'):
            with self.subTest(index=index):
                vm = Interpreter()
                self.addCleanup(vm.close)
                with self.assertRaises(BSLRuntimeError):
                    vm.execute('a=New Array;a.Add(7);n=a['+index+'];')

    def test_insert_extends_with_undefined(self):
        vm = self.run_source('a=New Array;a.Insert(3,7);n=a.Count();')
        self.assertEqual(vm.variables['n'], Decimal(4))
        self.assertEqual(vm.variables['a'], [None,None,None,Decimal(7)])

    def test_negative_constructor_size_rejected(self):
        vm = Interpreter()
        self.addCleanup(vm.close)
        with self.assertRaises(BSLRuntimeError):
            vm.execute('a=New Array(-1);')
