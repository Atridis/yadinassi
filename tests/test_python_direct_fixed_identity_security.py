"""Fixed collection descendants are opaque identity values, not host protocols."""
import unittest
from decimal import Decimal
from unittest.mock import patch

from yadinassi import Interpreter
from yadinassi.types.values import BSLArray, BSLFixedArray, equal
from yadinassi.collections.structures import BSLStructure, BSLFixedStructure
from yadinassi.collections.maps import BSLMap, BSLFixedMap
from yadinassi.execution.codegen.experimental_naked_boundaries import BoundaryContext, BoundaryViolation
from yadinassi.execution.codegen import experimental_naked_scalar_semantics as scalar


class FixedIdentitySecurityTests(unittest.TestCase):
    def test_all_repaired_equality_variants_match_canonical_identity_without_hooks(self):
        effects=[]
        class Meta(type):
            @property
            def __mro__(cls):raise AssertionError('metaclass descriptor hook')
            def __getattribute__(cls,name):
                if name in ('__mro__','__bases__'):raise AssertionError('metaclass hook')
                return super().__getattribute__(name)
            def __eq__(cls,other):raise AssertionError('metaclass equality')
            def __hash__(cls):raise AssertionError('metaclass hash')
        class Hostile:
            def __eq__(self,other):raise AssertionError('payload equality')
            def __ne__(self,other):raise AssertionError('payload inequality')
            def __hash__(self):raise AssertionError('payload hash')
            def __getattribute__(self,name):
                if name in ('__class__','items','_items'):raise AssertionError('payload inspection')
                return super().__getattribute__(name)
        operators=[(scalar.array_equal,scalar.array_not_equal),
                   (scalar.structure_equal,scalar.structure_not_equal),
                   (scalar.collection_equal,scalar.collection_not_equal)]
        operators.extend(scalar.map_identity_operators(array=a,structure=s)
                         for a in (False,True) for s in (False,True))
        for base in (BSLFixedArray,BSLFixedStructure,BSLFixedMap):
            class Fixed(Hostile,base,metaclass=Meta):pass
            first,second=object.__new__(Fixed),object.__new__(Fixed)
            other=object()
            for left,right in ((first,first),(first,second),(first,other),(other,first)):
                expected=equal(left,right)
                for eq,ne in operators:
                    self.assertIs(eq(left,right),expected)
                    self.assertIs(ne(left,right),not expected)
            self.assertEqual(scalar.typed_find([first],first),Decimal(0))
            self.assertIsNone(scalar.typed_find([first],second))
        self.assertEqual(effects,[])

    def test_native_collection_observations_match_both_backends(self):
        source='''A=New Array; A.Add(1); F=New FixedArray(A); G=New FixedArray(A);
        Message(F=F); Message(F=G); Message(F<>G);
        B=New Array; B.Add(F); Message(B.Find(F)); Message(B.Find(G)=Undefined);'''
        for backend in ('python-direct','compiled-strict'):
            output=[];vm=Interpreter(output=output.append,execution_backend=backend)
            self.addCleanup(vm.close);vm.execute(source)
            self.assertEqual(output,['Да','Нет','Да','0','Да'])

    def test_identity_does_not_admit_members_or_scalar_operations(self):
        class Fixed(BSLFixedArray):pass
        value=Fixed(BSLArray())
        boundary=BoundaryContext();boundary.start()
        with self.assertRaises(BoundaryViolation):boundary.get_member(value,'items')
        with self.assertRaises(BoundaryViolation):scalar.presentation(value)
        with self.assertRaises(BoundaryViolation):scalar._supported(value)
        with self.assertRaises(TypeError):scalar.order(value,value,'<')
        boundary.revoke()
        with self.assertRaises(BoundaryViolation):boundary.get_member(value,'items')

    def test_public_marker_rebinding_does_not_change_identity_domain(self):
        class Fixed(BSLFixedArray):
            def __eq__(self,other):raise AssertionError('hook')
        value=Fixed(BSLArray())
        with patch('yadinassi.types.values.BSLFixedCollection',object):
            self.assertTrue(scalar.collection_equal(value,value))
            self.assertIsNone(scalar.typed_find([value],Fixed(BSLArray())))

    def test_unrelated_host_equality_contract_is_unchanged(self):
        calls=[]
        class Host:
            def __eq__(self,other):calls.append('eq');return True
            def __ne__(self,other):calls.append('ne');return False
        left,right=Host(),Host()
        self.assertTrue(scalar.collection_equal(left,right))
        self.assertFalse(scalar.collection_not_equal(left,right))
        self.assertEqual(calls,['eq','ne'])
