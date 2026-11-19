"""Reject unproven exact Date keys without adding Date value-key semantics."""
import unittest
from unittest.mock import patch

from yadinassi import Interpreter, BSLError
from yadinassi.temporal.dates import BSLDate, MAX_TICKS, UnsupportedDateRange
from yadinassi.execution.codegen.experimental_naked_collections import _TypedMap
from yadinassi.execution.codegen.experimental_naked_boundaries import BoundaryViolation
from yadinassi.execution.direct.python_direct_plain_map import PlainMap, PlainFixedMap


class MapDateBoundaryTests(unittest.TestCase):
    def test_runtime_operations_reject_unknown_dates_in_effect_order(self):
        operations=(('M.Get(U)',[]),('M[U]',[]),('M.Insert(U,Touch());',['rhs']),
                    ('M[U]=Touch();',['rhs']),('M.Delete(U);',[]))
        for ticks in (0,MAX_TICKS):
            for operation,expected in operations:
                with self.subTest(ticks=ticks,operation=operation):
                    effects=[];vm=Interpreter(allow_extensions=True)
                    self.addCleanup(vm.close);vm.variables['u']=BSLDate(ticks,True)
                    vm.register_function('Touch',lambda:effects.append('rhs') or 3)
                    vm.execute('M=New Map;M.Insert("safe",7);')
                    with self.assertRaisesRegex(BSLError,'после выхода за диапазон'):
                        vm.execute(operation)
                    self.assertEqual(effects,expected)
                    self.assertEqual(vm.execute('M.Count()'),1)
                    self.assertEqual(vm.execute('M.Get("safe")'),7)
                    vm.execute('caught=False;Try M.Get(U);Except caught=True;EndTry;')
                    self.assertTrue(vm.variables['caught'])

    def test_all_token_operations_reject_without_mutating_map(self):
        value=BSLDate(0,True);mapping=_TypedMap();mapping['safe']=7
        operations=(lambda:mapping[value],lambda:mapping.get(value),
                    lambda:mapping.__setitem__(value,8),lambda:mapping.__delitem__(value),
                    lambda:value in mapping)
        for operation in operations:
            with self.assertRaises(UnsupportedDateRange):operation()
            self.assertEqual(list(mapping.items()),[('safe',7)])

    def test_exact_state_reads_bypass_mutated_class_hooks(self):
        unknown=BSLDate(0,True);known=BSLDate(1)
        plain=PlainMap();plain['safe']=7
        fixed=PlainFixedMap(plain)
        def hostile(*args):raise AssertionError('host hook')
        with patch.object(BSLDate,'require_known',hostile),\
             patch.object(BSLDate,'__getattribute__',hostile),\
             patch.object(BSLDate,'__hash__',hostile),\
             patch.object(BSLDate,'__eq__',hostile),\
             patch.object(BSLDate,'boundary',property(hostile)):
            with self.assertRaises(UnsupportedDateRange):_TypedMap.token(unknown)
            self.assertEqual(_TypedMap.token(known),(object,id(known)))
            for get in (plain.get, fixed.get, fixed.get_index):
                with self.assertRaises(UnsupportedDateRange):get(unknown)
                with self.assertRaisesRegex(TypeError,'requires a scalar Python value'):get(known)

    def test_missing_or_hostile_exact_boundary_state_fails_closed(self):
        class Flag:
            def __bool__(self):raise AssertionError('bool hook')
        missing=object.__new__(BSLDate)
        invalid=BSLDate(0);object.__setattr__(invalid,'boundary',Flag())
        for value in (missing,invalid):
            with self.assertRaises(BoundaryViolation):_TypedMap.token(value)

    def test_subclasses_and_foreign_spoofs_keep_opaque_identity(self):
        class Child(BSLDate):
            def __getattribute__(self,name):raise AssertionError('payload hook')
            def __hash__(self):raise AssertionError('hash hook')
        class Fake:
            @property
            def __class__(self):raise AssertionError('class spoof')
        for value in (object.__new__(Child),Fake()):
            mapping=_TypedMap();mapping[value]=3
            self.assertEqual(mapping[value],3)
        with patch('yadinassi.temporal.dates.BSLDate',Fake):
            with self.assertRaises(UnsupportedDateRange):_TypedMap.token(BSLDate(0,True))

    def test_known_dates_keep_existing_identity_limitation(self):
        # This patch does not claim to implement canonical Date value-key equality.
        first,second=BSLDate(1),BSLDate(1);mapping=_TypedMap();mapping[first]=3
        self.assertEqual(mapping[first],3);self.assertIsNone(mapping.get(second))
        mapping[first]=4;self.assertEqual(mapping[first],4)
        del mapping[first];self.assertEqual(len(mapping),0)
