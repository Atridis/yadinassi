"""FixedMap canonical snapshots without losing direct keys or mutable aliases."""
import unittest
from decimal import Decimal
from unittest.mock import patch
from yadinassi import Interpreter, BSLError
from yadinassi.syntax.parser import parse
from yadinassi.maps import BSLMap, BSLFixedMap
from yadinassi.unique_identifiers import BSLUUID
from yadinassi.experimental_naked_collections import _TypedMap
from yadinassi.experimental_naked_boundaries import BoundaryContext, BoundaryViolation
from yadinassi.python_direct_services import ServicesBoundary

class DirectFixedMapTests(unittest.TestCase):
    def test_routes_typed_keys_snapshot_and_missing_index(self):
        source='M=New Map;M.Insert(True,"bool");M.Insert(1,"number");M.Insert("1",Undefined);F=New ФиксированноеСоответствие(M);M.Insert(1,"changed");'
        for route in ('source','ast','prepared'):
            vm=Interpreter()
            with patch.object(Interpreter,'block',side_effect=AssertionError('VM')),patch.object(Interpreter,'call_routine',side_effect=AssertionError('VM')):
                if route=='source':vm.execute(source)
                elif route=='ast':vm.execute_program(parse(source))
                else:vm.execute_prepared(vm.prepare(source))
            self.assertIs(type(vm.variables['f']),BSLFixedMap)
            self.assertEqual(vm.execute('F.Count()'),3)
            self.assertEqual(vm.execute('F[True]'),'bool');self.assertEqual(vm.execute('F[1]'),'number')
            self.assertIsNone(vm.execute('F["1"]'));self.assertIsNone(vm.execute('F.Get("absent")'))
            with self.assertRaises(BSLError):vm.execute('F["absent"]')

    def test_object_identity_and_shallow_values(self):
        vm=Interpreter();vm.execute('K=New Array;V=New Array;M=New Map;M.Insert(K,V);F=New FixedMap(M);K.Add(1);V.Add(2);M.Clear();R=F.Get(K);')
        self.assertIs(vm.variables['r'],vm.variables['v']);self.assertEqual(vm.execute('R[0]'),2)
        self.assertIsNone(vm.variables['f'].get([]))
        entries=list(vm.variables['f']);self.assertIs(entries[0].key,vm.variables['k'])
        self.assertIs(entries[0].value,vm.variables['v'])

    def test_equal_canonical_keys_cannot_silently_drop_direct_entries(self):
        vm=Interpreter();a=BSLUUID('11111111-1111-1111-1111-111111111111');b=BSLUUID(str(a))
        mapping=_TypedMap();mapping[a]=1;mapping[b]=2;vm.variables.update(m=mapping,saved=7)
        with self.assertRaises(BSLError):vm.execute('Saved=New FixedMap(M);')
        self.assertEqual(vm.variables['saved'],7);self.assertEqual(len(mapping),2)
        del mapping[b];vm.execute('F=New FixedMap(M);')
        self.assertEqual(vm.variables['f'].get(b),1)

    def test_hostile_object_keys_do_not_call_hash_or_equality(self):
        class Key:
            def __hash__(self):raise AssertionError('hash')
            def __eq__(self,other):raise AssertionError('equality')
        a=Key();b=Key();source=_TypedMap();source[a]=1;source[b]=2
        vm=Interpreter();vm.variables['m']=source;vm.execute('F=New FixedMap(M);')
        self.assertEqual(vm.variables['f'].get(a),1);self.assertEqual(vm.variables['f'].get(b),2)

    def test_canonical_source_and_noncanonical_roots(self):
        vm=Interpreter();mapping=BSLMap();mapping.insert('x',1);vm.variables['m']=mapping
        vm.execute('F=New FixedMap(M);');mapping.insert('x',2);self.assertEqual(vm.execute('F.Get("x")'),1)
        class Child(_TypedMap):pass
        for bad in ({},Child(),vm.variables['f']):
            vm.variables['bad']=bad
            with self.assertRaises(BSLError):vm.execute('New FixedMap(Bad)')

    def test_readonly_iteration_and_private_fields(self):
        vm=Interpreter();vm.execute('M=New Map;M.Insert("x",1);F=New FixedMap(M);S=0;For Each P In F Do S=S+P.Value;EndDo;')
        self.assertEqual(vm.variables['s'],1)
        for text in ('F["x"]=3','F.Insert("x",3)','F.Clear()','F._items','P.Value=2'):
            with self.assertRaises(BSLError):vm.execute(text)
        self.assertEqual(vm.execute('F["x"]'),1)

    def test_constructor_binding_and_policy_are_live(self):
        vm=Interpreter();factory=vm.types['fixedmap'];seen=[]
        def change():factory.function=lambda *a:seen.append(1);return _TypedMap()
        vm.register_function('Change',change)
        with self.assertRaises(BoundaryViolation):vm.execute('New FixedMap(Change())')
        self.assertEqual(seen,[])
        class Boundary(ServicesBoundary,BoundaryContext):pass
        vm=Interpreter();events=[]
        context=Boundary(policy=lambda op,name:events.append((op,name)) or False);context.vm=vm;context.start()
        with self.assertRaises(BoundaryViolation):context.resolve_service('new:fixedmap')(_TypedMap())
        self.assertEqual(events,[('call_value',vm.types['fixedmap'].name.casefold())])
