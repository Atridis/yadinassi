from decimal import Decimal
import unittest
from unittest.mock import patch
from yadinassi import Interpreter
from yadinassi import serialization,strings
from yadinassi.serialization import _direct_value_to_string_internal as encode,value_from_string_internal as decode
from yadinassi.values import BSLArray
from yadinassi.maps import BSLMap
from yadinassi.experimental_naked_collections import _TypedMap
from yadinassi.experimental_naked_structure import new_structure
from yadinassi.experimental_naked_boundaries import BoundaryViolation

class DirectStringsParityTests(unittest.TestCase):
    def test_search_holes_aliases_and_canonical_host_alias(self):
        vm=Interpreter();vm.register_function('SearchAlias',strings.str_find)
        for name in ('StrFind','СтрНайти','SearchAlias'):
            self.assertEqual(vm.execute(name+'("abcabc","b",,,2)'),5)
            self.assertEqual(vm.execute(name+'("abcabc","b",SearchDirection.FromEnd,,2)'),2)

    def test_required_holes_arity_and_overrides_before_effects(self):
        for source in ('StrFind(,Effect())','StrFind(Effect())','StrFind(Effect(),"b",,,,,)'):
            vm=Interpreter();seen=[];vm.register_function('Effect',lambda:seen.append(1) or 'abc')
            vm.execute('Try '+source+';Except Caught=True;EndTry;')
            self.assertTrue(vm.variables['caught']);self.assertEqual(seen,[])
        vm=Interpreter();seen=[];vm.register_function('StrFind',lambda *args:seen.append(args))
        vm.execute('Try StrFind("a","a",,);Except Caught=True;EndTry;')
        self.assertTrue(vm.variables['caught']);self.assertEqual(seen,[])

    def test_bound_search_mutation_and_close(self):
        for close in (False,True):
            vm=Interpreter();seen=[];function=vm.functions['strfind']
            def effect():
                if close:vm.close()
                else:function.function=lambda *args:seen.append(args)
                return 'abc'
            vm.register_function('Effect',effect)
            with self.assertRaises(BoundaryViolation):vm.execute('StrFind(Effect(),"b",,)')
            self.assertEqual(seen,[])

    def test_direct_canonical_mixed_graph_roundtrip(self):
        vm=Interpreter();vm.execute('A=New Array;A.Add(SearchDirection.FromBegin);M=New Map;M.Insert(SearchDirection.FromEnd,A);S=New Structure("Value",M);')
        a=vm.variables['a'];m=vm.variables['m'];s=vm.variables['s']
        canonical=BSLArray();canonical.items=list(a)
        self.assertEqual(encode(a),encode(canonical))
        canonical_map=BSLMap();canonical_map.insert(next(iter(m.items()))[0],canonical)
        self.assertEqual(encode(m),encode(canonical_map))
        self.assertEqual(encode(decode(encode(s))),encode(s))
        self.assertIs(next(iter(m.items()))[1],a)
        canonical.items.append(m)
        self.assertEqual(encode(decode(encode(canonical))),encode(canonical))

    def test_typed_keys_and_repeated_aliases(self):
        m=_TypedMap();m[True]='boolean';m[Decimal(1)]='number'
        decoded=decode(encode(m));self.assertEqual(decoded.get(True),'boolean');self.assertEqual(decoded.get(Decimal(1)),'number')
        child=[Decimal(1)];a=[child,child];encode(a)
        self.assertIs(a[0],a[1])

    def test_cycles_across_direct_and_canonical_owners(self):
        a=[];a.append(a)
        canonical=BSLArray();mixed=[canonical];canonical.items.append(mixed)
        m=_TypedMap();m['self']=m
        s=new_structure('Self');s['Self']=s
        for value in (a,mixed,m,s):
            with self.assertRaisesRegex(ValueError,'циклические'):encode(value)

    def test_shared_limits_and_unknown_subclasses(self):
        canonical=BSLArray();canonical.items=[Decimal(1),Decimal(2)]
        for value in ([Decimal(1),Decimal(2)],canonical):
            with patch.object(serialization,'_MAX_NODES',2):
                with self.assertRaises(ValueError):encode(value)
            with patch.object(serialization,'_MAX_DEPTH',0):
                with self.assertRaises(ValueError):encode(value)
            with patch.object(serialization,'_MAX_TEXT',5):
                with self.assertRaises(ValueError):encode(value)
        class Child(list):
            def __iter__(self):raise AssertionError('subclass hook')
        for value in ({},Child(),object()):
            with self.assertRaises(TypeError):encode(value)

    def test_decoded_map_index_protocol_and_owner_checks(self):
        vm=Interpreter();vm.execute('M=New Map;M.Insert(True,"b");M.Insert(1,"n");R=ValueFromStringInternal(ValueToStringInternal(M));R[1]="changed";A=R[True];B=R[1];C=R[2];')
        self.assertEqual(vm.variables['a'],'b');self.assertEqual(vm.variables['b'],'changed');self.assertIsNone(vm.variables['c'])
        class SubMap(BSLMap):pass
        vm.variables['bad']=SubMap()
        with self.assertRaises(BoundaryViolation):vm.execute('Bad[1];')

    def test_canonical_api_stays_closed_and_service_override(self):
        with self.assertRaises(TypeError):serialization.value_to_string_internal([])
        vm=Interpreter();vm.register_function('ValueToStringInternal',lambda value:'custom')
        self.assertEqual(vm.execute('ValueToStringInternal(New Array)'),'custom')
        vm=Interpreter();original=vm.functions['valuetostringinternal'];seen=[]
        def mutate():original.function=lambda x:seen.append(x);return []
        vm.register_function('Mutate',mutate)
        with self.assertRaises(BoundaryViolation):vm.execute('ValueToStringInternal(Mutate());')
        self.assertEqual(seen,[])

    def test_mutated_module_function_does_not_gain_omission_capability(self):
        seen=[]
        with patch.object(strings,'str_find',lambda *args:seen.append(args)):
            vm=Interpreter();vm.register_function('Alias',strings.str_find)
            vm.execute('Try Alias("a","b",,);Except Caught=True;EndTry;')
            self.assertTrue(vm.variables['caught']);self.assertEqual(seen,[])
