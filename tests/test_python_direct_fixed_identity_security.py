"""Fixed collection descendants are opaque identity values, not host protocols."""
import unittest
from decimal import Decimal
from unittest.mock import patch

from yadinassi import BSLError, Interpreter
from yadinassi.types.values import BSLArray, BSLFixedArray, equal
from yadinassi.collections.structures import BSLStructure, BSLFixedStructure
from yadinassi.collections.maps import BSLMap, BSLFixedMap
from yadinassi.execution.codegen.direct_boundaries import BoundaryContext, BoundaryViolation
from yadinassi.execution.codegen import direct_scalar_semantics as scalar


class FixedIdentitySecurityTests(unittest.TestCase):

    def test_native_collection_observations(self):
        source='''A=New Array; A.Add(1); F=New FixedArray(A); G=New FixedArray(A);
        Message(F=F); Message(F=G); Message(F<>G);
        B=New Array; B.Add(F); Message(B.Find(F)); Message(B.Find(G)=Undefined);'''
        output=[];vm=Interpreter(output=output.append)
        self.addCleanup(vm.close);vm.execute(source)
        self.assertEqual(output,['Да','Нет','Да','0','Да'])

    def test_identity_does_not_admit_members_or_scalar_operations(self):
        class Fixed(BSLFixedArray):pass
        value=Fixed(BSLArray())
        boundary=BoundaryContext();boundary.start()
        with self.assertRaises(BoundaryViolation):boundary.get_member(value,'items')
        with self.assertRaises(BoundaryViolation):scalar.presentation(value)
        with self.assertRaises(BoundaryViolation):scalar._supported(value)
        vm=Interpreter();self.addCleanup(vm.close)
        vm.variables['fixed']=value
        with self.assertRaises(BSLError):
            vm.execute('R=(Fixed<Fixed);')
        self.assertNotIn('r',vm.variables)
        boundary.revoke()
        with self.assertRaises(BoundaryViolation):boundary.get_member(value,'items')
