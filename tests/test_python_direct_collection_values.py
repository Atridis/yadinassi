import unittest
from decimal import Decimal as D
from unittest.mock import patch
from yadinassi import Interpreter
from yadinassi import values as V, maps as M, structures as S
from yadinassi.python_translation_collections import CollectionRegion,trusted,UnsupportedCollection

class DirectCollectionValueTests(unittest.TestCase):
    def setUp(self):self.region=CollectionRegion()
    def test_array_bulk_mutations_index_and_alias(self):
        r=self.region;a=r.new('Array');alias=a
        for i in range(100):r.call(a,'Add',[D(i)])
        r.write_index(alias,D(2),D(999));self.assertEqual(r.read_index(a,D(2)),999)
        r.call(a,'Insert',[D(101),D(7)])
        self.assertIsNone(r.read_index(a,D(100)));self.assertEqual(r.call(a,'Count'),102)
        r.call(a,'Delete',[D(0)]);self.assertEqual(r.call(a,'UBound'),100)
        self.assertEqual(r.call(a,'Find',[D(999)]),1)
        r.call(a,'Clear');self.assertEqual(a.items,[])
    def test_array_optional_defaults_and_typed_find(self):
        r=self.region;a=r.new('Массив');r.call(a,'Добавить');r.call(a,'Add',[True]);r.call(a,'Add',[D(1)])
        self.assertEqual(r.call(a,'Найти',[D(1)]),2)
        self.assertEqual(r.call(a,'Find',[True]),1);self.assertIsNone(a.items[0])
    def test_array_bad_index_matches_existing(self):
        for index in (D(-1),D('0.5'),D(9),True,None):
            r=CollectionRegion();a=r.new('Array',[D(2)]);ordinary=V.BSLArray(D(2));errors=[]
            for action in (lambda:r.read_index(a,index),lambda:ordinary.get(index)):
                try:action()
                except Exception as error:errors.append((type(error),str(error)))
            self.assertEqual(len(errors),2);self.assertEqual(*errors)
    def test_array_gap_failure_atomic_and_dimensions(self):
        r=self.region;a=r.new('Array',[D(2),D(3)])
        self.assertTrue(r.owns(a.items[0]));self.assertIsNot(a.items[0],a.items[1])
        flat=r.new('Array');r.call(flat,'Add',[D(1)])
        with self.assertRaises(ValueError):r.call(flat,'Insert',[D('1e100000')])
        self.assertEqual(flat.items,[D(1)])
    def test_map_typed_keys_identity_and_missing(self):
        r=self.region;m=r.new('Map');a=r.new('Array');b=r.new('Array')
        for key,value in ((True,D(2)),(D(1),D(3)),(a,D(4)),(b,D(5)),(None,None)):
            r.call(m,'Insert',[key,value])
        self.assertEqual(r.call(m,'Count'),5)
        for key,value in ((True,2),(D(1),3),(a,4),(b,5)):
            self.assertEqual(r.read_index(m,key),value)
        self.assertIsNone(r.read_index(m,'absent'));r.write_index(m,True,D(8))
        self.assertEqual(r.call(m,'Get',[D(1)]),3)
    def test_map_version_replacement_and_iteration(self):
        r=self.region;m=r.new('Map');r.call(m,'Insert',['x',D(1)]);iterator=r.iterate(m)
        pair=next(iterator);self.assertEqual(r.read_attribute(pair,'Key'),'x')
        r.call(m,'Insert',['x',D(2)])
        self.assertEqual(m._version,1)
        with self.assertRaises(StopIteration):next(iterator)
        iterator=r.iterate(m);next(iterator);r.call(m,'Insert',['y',D(3)])
        with self.assertRaisesRegex(ValueError,'Изменение состава соответствия'):next(iterator)
    def test_structure_case_spelling_property_method_independence(self):
        r=self.region;s=r.new('Structure',['Count,Name',D(8),D(9)])
        self.assertEqual(r.read_attribute(s,'count'),8);self.assertEqual(r.call(s,'Count'),2)
        r.write_attribute(s,'NAME',D(10));self.assertEqual(s._items['name'][0],'Name')
        r.call(s,'Insert',['nAmE',D(11)]);self.assertEqual(s._items['name'][0],'nAmE')
        self.assertEqual(r.property(s,' name '),(True,D(11)))
        self.assertEqual(r.property(s,'absent'),(False,None))
        with self.assertRaises(ValueError):r.write_attribute(s,'absent',D(1))
    def test_structure_version_iteration_and_clear(self):
        r=self.region;s=r.new('Structure',['x',D(1)]);iterator=r.iterate(s);next(iterator)
        r.call(s,'Delete',['x'])
        with self.assertRaisesRegex(ValueError,'Изменение состава структуры'):next(iterator)
        r.call(s,'Clear');self.assertEqual(s._version,2)
    def test_foreign_and_hostile_payloads_not_accepted(self):
        r=self.region;a=r.new('Array');events=[]
        class Meta(type):
            def __eq__(cls,other):events.append('eq');return True
            __hash__=type.__hash__
        class Host(metaclass=Meta):pass
        for value in (Host(),V.BSLArray()):
            with self.assertRaises(UnsupportedCollection):r.call(a,'Add',[value])
        self.assertEqual(events,[]);self.assertEqual(a.items,[])
    def test_method_bind_fails_before_argument_effect(self):
        r=self.region;m=r.new('Map')
        with self.assertRaisesRegex(ValueError,'Метод соответствия не найден'):r.bind(m,'Add')
        with self.assertRaisesRegex(TypeError,'не имеет методов'):r.bind(D(1),'Add')
        with self.assertRaisesRegex(TypeError,'Индексирование'):r.prepare_index(D(1))
    def test_hot_operations_do_not_use_dynamic_host_lookup(self):
        r=self.region;a=r.new('Array');m=r.new('Map');s=r.new('Structure')
        with (patch.object(V.BSLObject,'get_method',side_effect=AssertionError('dispatch')),
             patch.object(M.BSLMap,'get_method',side_effect=AssertionError('dispatch')),
             patch.object(S.BSLStructure,'get_method',side_effect=AssertionError('dispatch'))):
            r.call(a,'Add',[D(1)]);r.call(m,'Insert',[D(1),D(2)]);r.call(s,'Insert',['x',D(3)])
            self.assertEqual(r.call(m,'Get',[D(1)]),2)
    def test_abi_and_constructor_replacement_declines(self):
        vm=Interpreter();self.assertTrue(trusted(vm))
        vm.register_type('Array',lambda:V.BSLArray())
        self.assertFalse(trusted(vm))
        with patch.object(V.BSLArray,'add',lambda *args:None):self.assertFalse(trusted())
    def test_lease_receives_weak_ownership(self):
        import weakref,gc
        class Lease:
            owned_values=[]
            def check(self):pass
        lease=Lease();lease.owned_values=[];r=CollectionRegion(lease)
        a=r.new('Array');reference=weakref.ref(a)
        self.assertIs(lease.owned_values[0](),a)
        del a;gc.collect();self.assertIsNone(reference())
    def test_pinned_key_and_numeric_helpers_do_not_invoke_live_patches(self):
        r=self.region;m=r.new('Map');a=r.new('Array');events=[]
        def hostile(*args):events.append(args);raise AssertionError('live helper callback')
        with patch.object(M,'_key',hostile),patch.object(V,'require_number',hostile),patch.object(V,'equal',hostile):
            r.call(m,'Insert',[True,D(1)]);r.call(m,'Insert',[D(1),D(2)])
            r.call(a,'Add',[D(4)]);self.assertEqual(r.read_index(a,D(0)),4)
            self.assertEqual(r.call(a,'Find',[D(4)]),0)
        self.assertEqual(events,[])
    def test_fresh_storage_bypasses_patched_collection_descriptors(self):
        r=self.region;a=r.new('Array');events=[]
        def hostile(*args):events.append(args);raise AssertionError('live descriptor callback')
        with patch.object(V.BSLArray,'items',property(hostile,hostile),create=True):
            r.call(a,'Add',[D(4)]);self.assertEqual(r.read_index(a,D(0)),4)
            b=r.new('Array',[D(2)]);self.assertEqual(r.call(b,'Count'),2)
        self.assertEqual(events,[])
    def test_direct_constructors_do_not_call_replaced_init_or_insert(self):
        r=self.region;events=[]
        def hostile(*args):events.append(args);raise AssertionError('live constructor callback')
        with patch.object(V.BSLArray,'__init__',hostile),patch.object(S.BSLStructure,'insert',hostile):
            a=r.new('Array',[D(2),D(3)]);s=r.new('Structure',['x,y',D(1),D(2)])
            self.assertEqual(r.call(a,'Count'),2);self.assertEqual(r.read_index(s,'y'),2)
        self.assertEqual(events,[])
    def test_constructor_rechecks_lease(self):
        class Lease:
            def __init__(self):self.owned_values=[];self.calls=0
            def check(self):self.calls+=1
        lease=Lease();r=CollectionRegion(lease)
        r.new('Array');r.new('Map');r.new('Structure')
        self.assertEqual(lease.calls,3)
