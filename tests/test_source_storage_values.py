"""Persistent UUID/ValueStorage in source scratch, never a native 1C codec."""
from contextlib import closing
from decimal import Decimal
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from test_source_constant_store import configuration
from test_source_session_parameters import declaration
from yadinassi.configuration_source_runtime import SourceApplication
from yadinassi.configuration_source_constants import source_constant_definitions
from yadinassi.source_constant_store import SourceConstantStore
from yadinassi.source_storage_codec import encode_storage, decode_storage, VERSION
from yadinassi.unique_identifiers import BSLUUID
from yadinassi.value_storage import BSLValueStorage, Snapshot
from yadinassi.values import BSLArray, BSLFixedArray, NULL
from yadinassi.structures import BSLStructure, BSLFixedStructure
from yadinassi.maps import BSLMap
from yadinassi.file_io import BSLBinaryData
from yadinassi.data_compression import BSLDeflation
from yadinassi.value_tables import BSLValueTable
from yadinassi.type_descriptions import BSLTypeDescription
from yadinassi.errors import BSLError

UUID = '01234567-89ab-cdef-0123-456789abcdef'


def package(body='', extra=None):
    source = configuration()
    files={item.path:item.content for item in source.files}
    additions = {'Storage':'ValueStorage','Identifier':'UUID'}
    children=''.join('<Constant>'+name+'</Constant>' for name in additions)
    files['Configuration.xml']=files['Configuration.xml'].replace(b'</ChildObjects>',children.encode()+b'</ChildObjects>')
    for name, kind in additions.items():
        files['Constants/'+name+'.xml']=declaration(name,'<v8:Type>v8:'+kind+'</v8:Type>').replace(b'SessionParameter',b'Constant')
    if body:files['Ext/SessionModule.bsl']=('Procedure SessionParametersSetting(Names) '+body+' EndProcedure').encode()
    files.update(extra or {})
    from yadinassi.configuration_source import import_source
    return import_source(files)


class SourceStorageValueTests(unittest.TestCase):
    def setUp(self):
        directory=tempfile.TemporaryDirectory();self.addCleanup(directory.cleanup)
        self.path=Path(directory.name)/'scratch.sqlite'

    def store(self, source=None):
        store=SourceConstantStore.create(self.path, source or package());self.addCleanup(store.close);return store

    def app(self,body,extra=None):
        app=SourceApplication(package(body,extra),scratch_database=self.path);self.addCleanup(app.close);return app

    def corrupt(self,payload):
        with closing(sqlite3.connect(self.path)) as db,db:
            db.execute("UPDATE constant_value SET value_json=? WHERE identity=(SELECT identity FROM constant_schema WHERE name='Storage')",(payload,))

    def test_source_type_admission_exact_namespace(self):
        definitions,unsupported,names=source_constant_definitions(package())
        kinds={d.name:d.kind for d in definitions}
        self.assertEqual(kinds['Storage'],'value_storage');self.assertEqual(kinds['Identifier'],'uuid')
        self.assertIn('unsupported',unsupported)

    def test_wrong_namespace_and_qualifiers_not_admitted(self):
        original=package();xml=next(x.content for x in original.files if x.path=='Constants/Storage.xml')
        for changed in (xml.replace(b'v8:ValueStorage',b'xs:ValueStorage'),xml.replace(b'</Type>',b'<v8:StringQualifiers/></Type>')):
            definitions,unsupported,_=source_constant_definitions(package(extra={'Constants/Storage.xml':changed}))
            self.assertIn('storage',unsupported)

    def test_uuid_roundtrip_after_reopen(self):
        store=self.store();store.set('Identifier',BSLUUID(UUID));store.close()
        reopened=SourceConstantStore.reopen(self.path,package());self.addCleanup(reopened.close)
        self.assertEqual(reopened.get('Identifier').text,UUID)

    def test_uuid_rejects_string_coercion(self):
        store=self.store()
        with self.assertRaises(TypeError):store.set('Identifier',UUID)

    def test_new_kinds_have_no_guessed_defaults(self):
        store=self.store()
        for name in ('Identifier','Storage'):
            with self.assertRaisesRegex(ValueError,'uninitialized'):store.get(name)

    def test_structures_arrays_and_independent_gets(self):
        store=self.store();array=BSLArray();array.items=[Decimal('3'),True,None,NULL,BSLUUID(UUID)]
        struct=BSLStructure();struct.insert('Items',array)
        store.set('Storage',BSLValueStorage(struct));array.items[0]=Decimal('99')
        first=store.get('Storage').get();first.get_member('Items').items[0]=Decimal('7')
        second=store.get('Storage').get()
        self.assertEqual(second.get_member('Items').items[0],Decimal('3'))
        self.assertEqual(second.get_member('Items').items[-1].text,UUID)

    def test_binary_and_fixed_nested_storage_roundtrip(self):
        store=self.store();array=BSLArray();array.items=[BSLBinaryData.from_bytes(b'\x00\xff'),BSLValueStorage('inner')]
        store.set('Storage',BSLValueStorage(BSLFixedArray(array)))
        got=store.get('Storage').get()
        self.assertIs(type(got),BSLFixedArray);self.assertEqual(got.items[0]._data,b'\x00\xff');self.assertEqual(got.items[1].get(),'inner')

    def test_map_keys_and_value_copy(self):
        store=self.store();value=BSLMap();value.insert(BSLUUID(UUID),'uuid');value.insert('key',Decimal('2'))
        store.set('Storage',BSLValueStorage(value));got=store.get('Storage').get()
        self.assertEqual(got.get(BSLUUID(UUID)),'uuid');self.assertEqual(got.get('key'),Decimal('2'))

    def test_typed_table_and_index_roundtrip(self):
        store=self.store();table=BSLValueTable();table.columns.add('Flag',BSLTypeDescription('Boolean'));table.add().set_member('Flag',True);table.indexes.add('Flag')
        store.set('Storage',BSLValueStorage(table));got=store.get('Storage').get()
        self.assertTrue(got.rows[0].get_member('Flag'));self.assertEqual(len(got.indexes.items),1)
        got.rows[0].set_member('Flag',False)
        self.assertTrue(store.get('Storage').get().rows[0].get_member('Flag'))

    def test_compressed_storage_survives_reopen(self):
        store=self.store();store.set('Storage',BSLValueStorage('a'*100000,BSLDeflation(Decimal(9))));store.close()
        reopened=SourceConstantStore.reopen(self.path,package());self.addCleanup(reopened.close)
        self.assertEqual(reopened.get('Storage').get(),'a'*100000)

    def test_large_uncompressed_payload_refused_without_overwrite(self):
        store=self.store();store.set('Storage',BSLValueStorage('original'))
        with self.assertRaisesRegex(ValueError,'bound'):store.set('Storage',BSLValueStorage('x'*65536))
        self.assertEqual(store.get('Storage').get(),'original')

    def test_wrong_runtime_type_is_not_wrapped_implicitly(self):
        store=self.store()
        with self.assertRaises(TypeError):store.set('Storage',BSLStructure())

    def test_atomic_set_uuid_and_storage(self):
        app=self.app('S=Constants.CreateSet("Identifier,Storage"); S.Identifier=New UUID("'+UUID+'"); S.Storage=New ValueStorage(New Structure("Enabled",True)); S.Write();')
        app.start();self.assertEqual(app.constant_store.get('Identifier').text,UUID);self.assertTrue(app.constant_store.get('Storage').get().get_member('Enabled'))

    def test_transaction_rollback_covers_new_kinds(self):
        store=self.store();store.begin_transaction();store.set('Identifier',BSLUUID(UUID));store.set('Storage',BSLValueStorage('pending'));store.rollback_transaction()
        for name in ('Identifier','Storage'):
            with self.assertRaisesRegex(ValueError,'uninitialized'):store.get(name)

    def test_storage_handler_can_transform_value(self):
        app=self.app('Constants.Storage.Set(New ValueStorage("before"));',{'Constants/Storage/Ext/ValueManagerModule.bsl':b'Procedure BeforeWrite(Cancel) Value=New ValueStorage("after"); EndProcedure'})
        app.start();self.assertEqual(app.constant_store.get('Storage').get(),'after')

    def test_cancelled_storage_handler_preserves_prior_value(self):
        app=self.app('Try Constants.Storage.Set(New ValueStorage("new")); Except EndTry;',{'Constants/Storage/Ext/ValueManagerModule.bsl':b'Procedure OnWrite(Cancel) Cancel=True; EndProcedure'})
        app.start()
        with self.assertRaisesRegex(ValueError,'uninitialized'):app.constant_store.get('Storage')

    def test_unknown_codec_version_refused(self):
        store=self.store();store.set('Storage',BSLValueStorage('valid'))
        self.corrupt(json.dumps(['value_storage',['unknown',['t',[]]]]))
        with self.assertRaisesRegex(ValueError,'integrity'):store.get('Storage')

    def test_unknown_snapshot_tag_is_not_loaded(self):
        store=self.store();store.set('Storage',BSLValueStorage('valid'))
        self.corrupt(json.dumps(['value_storage',[VERSION,['t',[['s','__reduce__'],['s','os.system']]]]]))
        with self.assertRaisesRegex(ValueError,'integrity'):store.get('Storage')

    def test_deep_json_normalized_to_integrity_error(self):
        store=self.store();store.set('Storage',BSLValueStorage('valid'))
        self.corrupt('['*1500+'0'+']'*1500)
        with self.assertRaisesRegex(ValueError,'integrity'):store.get('Storage')

    def test_invalid_snapshot_boolean_not_coerced(self):
        store=self.store();store.set('Storage',BSLValueStorage(True))
        self.corrupt(json.dumps(['value_storage',[VERSION,['t',[['s','boolean'],['i','1']]]]]))
        with self.assertRaisesRegex(ValueError,'integrity'):store.get('Storage')

    def test_invalid_base64_refused(self):
        store=self.store();store.set('Storage',BSLValueStorage(True))
        self.corrupt(json.dumps(['value_storage',[VERSION,['t',[['s','binary'],['x','!!!']]]]]))
        with self.assertRaisesRegex(ValueError,'integrity'):store.get('Storage')

    def test_noncanonical_payload_refused(self):
        store=self.store();store.set('Storage',BSLValueStorage(Decimal('2')))
        self.corrupt(json.dumps(['value_storage',[VERSION,['t',[['s','number'],['n','2e0']]]]]))
        with self.assertRaisesRegex(ValueError,'integrity'):store.get('Storage')

    def test_malformed_storage_prevents_reopen(self):
        store=self.store();store.set('Storage',BSLValueStorage('ok'));store.close()
        self.corrupt('["value_storage",[]]')
        with self.assertRaisesRegex(ValueError,'integrity'):SourceConstantStore.reopen(self.path,package())

    def test_failed_storage_read_aborts_existing_transaction(self):
        store=self.store();store.set('Storage',BSLValueStorage('ok'));self.corrupt('["value_storage",[]]')
        store.begin_transaction();store.set('Identifier',BSLUUID(UUID))
        with self.assertRaises(ValueError):store.get('Storage')
        self.assertFalse(store.transaction_active)
        with self.assertRaisesRegex(ValueError,'uninitialized'):store.get('Identifier')

    def test_host_snapshot_object_hooks_not_invoked(self):
        class Trap:
            def __str__(self):raise AssertionError('must not invoke')
        storage=BSLValueStorage._from_snapshot(Snapshot(('string',Trap())))
        with self.assertRaises(TypeError):encode_storage(storage)

    def test_host_snapshot_bad_depth_refused(self):
        node=('undefined',)
        for _ in range(200):node=('array',(node,))
        with self.assertRaisesRegex(ValueError,'bound'):encode_storage(BSLValueStorage._from_snapshot(Snapshot(node)))
