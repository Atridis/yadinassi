import unittest
from unittest.mock import patch
from types import SimpleNamespace
from decimal import Decimal
from yadinassi.formats.storage import value_storage as storage
from yadinassi.execution.direct.source import python_direct_source_value_storage as direct
from yadinassi.execution.codegen.direct_collections import _TypedMap
from yadinassi.execution.codegen.direct_structure import new_structure
from yadinassi.types.unique_identifiers import BSLUUID
from yadinassi.types.values import HostFunction
from yadinassi.execution.codegen.direct_boundaries import BoundaryViolation


class SourceValueStorageSecurity(unittest.TestCase):
    def boundary(self):
        factory=HostFunction('ValueStorage',storage.BSLValueStorage)
        return SimpleNamespace(_check=lambda:None,vm=SimpleNamespace(types={name:factory for name in direct.CONSTRUCTOR_NAMES}))

    def test_map_snapshot_and_default_capture_scope(self):
        value=_TypedMap();value[True]='bool';value[Decimal(1)]='number'
        value['nested']=[new_structure('Value',Decimal(7))]
        with self.assertRaises(storage.SnapshotError):storage.capture(value)
        instance=direct.resolve_constructor(self.boundary(),'valuestorage')(value)
        value[True]='changed'
        restored=instance.get()
        self.assertEqual(restored.get(True),'bool');self.assertEqual(restored.get(Decimal(1)),'number')
        self.assertEqual(restored.get('nested').items[0].get_member('Value'),Decimal(7))

    def test_map_cycles_collision_and_host_key_rejected(self):
        cyclic=_TypedMap();cyclic['self']=cyclic
        with self.assertRaises(storage.SnapshotError):storage.capture(cyclic,_source_direct=True)
        value=_TypedMap();value[BSLUUID('00000000-0000-0000-0000-000000000001')]=1
        value[BSLUUID('00000000-0000-0000-0000-000000000001')]=2
        # Values are BSL Numbers, not arbitrary Python ints.
        for token,(key,item) in list(dict.items(value)):dict.__setitem__(value,token,(key,Decimal(item)))
        with self.assertRaisesRegex(storage.SnapshotError,'colliding'):storage.capture(value,_source_direct=True)
        class Host:
            def __hash__(self):raise AssertionError('hash callback')
            def __eq__(self,other):raise AssertionError('equals callback')
        value=_TypedMap();value[Host()]=None
        with self.assertRaises(storage.SnapshotError):storage.capture(value,_source_direct=True)

    def test_constructor_alias_and_codec_replacement_before_call(self):
        boundary=self.boundary();create=direct.resolve_constructor(boundary,'valuestorage');calls=[]
        boundary.vm.types['хранилищезначения']=HostFunction('other',lambda v:calls.append(v))
        with self.assertRaises(BoundaryViolation):create('value')
        with patch.object(storage,'capture',lambda *a,**kw:calls.append('capture')):
            with self.assertRaises(BoundaryViolation):direct.resolve_constructor(self.boundary(),'valuestorage')
        self.assertEqual(calls,[])

    def test_saved_get_snapshot_retarget_and_nonscalar_refusal(self):
        boundary=self.boundary();create=direct.resolve_constructor(boundary,'valuestorage')
        value=create('value');saved=direct.get(boundary,value,'Get');bound=direct.captured(boundary,saved)
        self.assertEqual(bound(),'value')
        value._snapshot=storage.capture('other')
        with self.assertRaises(BoundaryViolation):bound()
        value=create([])
        with patch.object(storage.BSLArray,'__init__',side_effect=AssertionError('factory callback')):
            with self.assertRaises(BoundaryViolation):direct.resolve(boundary,value,'Get')()

    def test_storage_factory_and_field_descriptor_guards(self):
        boundary=self.boundary();create=direct.resolve_constructor(boundary,'valuestorage');calls=[]
        with patch.object(storage.BSLValueStorage,'_from_snapshot',classmethod(lambda cls,s:calls.append(s))):
            with self.assertRaises(BoundaryViolation):create('value')
        with patch.object(storage.BSLValueStorage,'_snapshot',property(lambda s:calls.append('field'))):
            with self.assertRaises(BoundaryViolation):create('value')
        self.assertEqual(calls,[])

    def test_nested_storage_denied_before_snapshot_hooks(self):
        boundary=self.boundary();create=direct.resolve_constructor(boundary,'valuestorage')
        nested=storage.BSLValueStorage('inner')
        with self.assertRaisesRegex(storage.SnapshotError,'nested ValueStorage'):create(nested)
        self.assertEqual(storage.restore(storage.capture(nested)).get(),'inner')
        calls=[]
        class Bad:
            def __eq__(self,other):calls.append('eq');return False
        nested._snapshot=storage.Snapshot((Bad(),))
        with self.assertRaisesRegex(storage.SnapshotError,'nested ValueStorage'):create([nested])
        self.assertEqual(calls,[])

    def test_malformed_get_snapshot_no_host_comparison(self):
        calls=[]
        class Bad:
            def __eq__(self,other):calls.append('eq');return False
        value=storage.BSLValueStorage._from_snapshot(storage.Snapshot((Bad(),)))
        with self.assertRaises(BoundaryViolation):direct.resolve(self.boundary(),value,'Get')
        self.assertEqual(calls,[])

    def test_bookkeeping_descriptors_and_scalar_factory_hooks(self):
        boundary=self.boundary();create=direct.resolve_constructor(boundary,'valuestorage');calls=[]
        descriptor=property(lambda self:calls.append('get'),lambda self,value:calls.append('set'))
        for cls,name in ((storage._Capture,'source_direct'),(storage._Restore,'budget')):
            with patch.object(cls,name,descriptor,create=True):
                with self.assertRaises(BoundaryViolation):create('value')
        for cls in (storage.BSLDate,storage.BSLUUID):
            with patch.object(cls,'__init__',lambda *args:calls.append('init')):
                with self.assertRaises(BoundaryViolation):create('value')
        self.assertEqual(calls,[])

    def test_capture_receiver_descriptors_and_table_bindings(self):
        from yadinassi.formats.storage import value_storage_table as tables
        boundary=self.boundary();create=direct.resolve_constructor(boundary,'valuestorage')
        array=storage.BSLArray();calls=[]
        descriptor=property(lambda self:calls.append('field') or [])
        for cls,name in ((storage.BSLArray,'items'),(storage.BSLFixedArray,'items'),
                         (storage.BSLStructure,'_items'),(storage.BSLFixedStructure,'_items'),
                         (storage.BSLMap,'_items'),(storage.BSLFixedMap,'_items'),
                         (storage.BSLBinaryData,'_data'),(storage.BSLValueTable,'_rows'),
                         (tables.BSLValueTableRow,'_values'),
                         (tables.BSLValueTableColumn,'_title'),
                         (tables.BSLTypeDescription,'_types')):
            with self.subTest(cls=cls.__name__,field=name),patch.object(cls,name,descriptor,create=True):
                with self.assertRaises(BoundaryViolation):create(array)
        with patch.object(tables,'BSLValueTableRow',lambda *args:calls.append('factory')):
            with self.assertRaises(BoundaryViolation):create(array)
        self.assertEqual(calls,[])
        self.assertEqual(create(array).get().items,[])
        for name in ('_field','_integer','_count'):
            with patch.object(tables,name,lambda *args:calls.append('helper')):
                with self.assertRaises(BoundaryViolation):create(array)
        self.assertEqual(calls,[])
