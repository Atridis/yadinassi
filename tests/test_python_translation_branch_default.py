"""Behavior retained from retired translation engines; only the direct backend runs.

Implementation-only registry, fusion emitter, instrumentation and inline-budget
checks belonged to deleted engines and are retired, not skipped or emulated.
Unsupported behavioral cases deliberately remain ordinary failing tests.
"""
import unittest
from decimal import Decimal
from unittest.mock import patch
from yadinassi import Interpreter, BSLError

class DirectDefaultBehavior(unittest.TestCase):
    def test_default_and_family(self):
        vm=Interpreter();self.addCleanup(vm.close)
        child=Interpreter(family_owner=vm)
        self.assertEqual(vm.execution_backend,'python-direct')
        self.assertEqual(child.execution_backend,'python-direct')
        vm.execute('x=0;For i=1 To 3 Do x=x+i;EndDo;')
        self.assertEqual(vm.variables['x'],6)
    def test_retained_routine_defaults(self):
        vm=Interpreter();self.addCleanup(vm.close)
        vm.execute('Function F(Val x=7) Return x+1;EndFunction')
        for i in range(10):vm.execute('z=1;')
        vm.execute('r=F();')
        self.assertEqual(vm.variables['r'],8)
    def test_direct_routine_collection_composition(self):
        vm=Interpreter();self.addCleanup(vm.close)
        self.assertEqual(vm.execution_backend,'python-direct')
        vm.execute('Function F(x) Return x+1;EndFunction a=New Array;For i=1 To 3 Do a.Add(F(i));EndDo;r=a[2];')
        self.assertEqual(vm.variables['r'],4)
