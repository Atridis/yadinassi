"""Source enum constant identity is application-owned, never a string coercion."""
from contextlib import closing
from pathlib import Path
from uuid import UUID
import sqlite3
import tempfile
import unittest
from test_source_constant_store import configuration
from test_source_session_parameters import declaration
from test_source_enums import xml, value, identity
from yadinassi.configuration_source import import_source
from yadinassi.configuration_source_constants import source_constant_definitions
from yadinassi.configuration_source_runtime import SourceApplication
from yadinassi.source_constant_store import SourceConstantStore
from yadinassi.enum_types import BSLEnumReference
from yadinassi.errors import BSLError


def package(body='', types=None, extra=None):
    files={f.path:f.content for f in configuration().files}
    files['Configuration.xml']=files['Configuration.xml'].replace(b'</ChildObjects>',b'<Enum>State</Enum><Enum>Mode</Enum><Constant>Choice</Constant></ChildObjects>')
    files['Enums/State.xml']=xml('Enum','State',value('Active')+value('Inactive'))
    files['Enums/Mode.xml']=xml('Enum','Mode',value('Auto'))
    raw=declaration('Choice',types or '<v8:Type>cfg:EnumRef.State</v8:Type>').replace(b'SessionParameter',b'Constant')
    files['Constants/Choice.xml']=raw.replace(b'xmlns:xs=',b'xmlns:cfg="http://v8.1c.ru/8.1/data/enterprise/current-config" xmlns:xs=')
    if body:files['Ext/SessionModule.bsl']=('Procedure SessionParametersSetting(Names) '+body+' EndProcedure').encode()
    files.update(extra or {})
    return import_source(files)


class EnumConstantsTests(unittest.TestCase):
    def setUp(self):
        directory=tempfile.TemporaryDirectory();self.addCleanup(directory.cleanup)
        self.path=Path(directory.name)/'scratch.sqlite'

    def store(self,source=None):
        store=SourceConstantStore.create(self.path,source or package());self.addCleanup(store.close);return store

    def enum(self,store,name='State'):
        return store._definition('Choice').enum_namespace.get_member(name)

    def test_exact_definition_identity(self):
        defs,unsupported,_=source_constant_definitions(package());d=next(d for d in defs if d.name=='Choice')
        self.assertEqual(d.kind,'enum_ref');self.assertEqual(d.qualifiers[0],identity('EnumState'));self.assertNotIn('choice',unsupported)

    def test_roundtrip_and_empty(self):
        store=self.store();manager=self.enum(store)
        for ref in (*manager._values,manager._empty):
            store.set('Choice',ref);self.assertIs(store.get('Choice'),ref)

    def test_reopen_rebinds_reference(self):
        store=self.store();old=self.enum(store)._values[0];store.set('Choice',old);store.close()
        reopened=SourceConstantStore.reopen(self.path,package());self.addCleanup(reopened.close)
        ref=reopened.get('Choice');self.assertEqual(ref.reference_uuid,old.reference_uuid);self.assertNotEqual(ref,old)
        self.assertIs(ref,self.enum(reopened)._values[0])

    def test_foreign_application_same_metadata_rejected(self):
        store=self.store();app=SourceApplication(package());self.addCleanup(app.close)
        with self.assertRaises(TypeError):store.set('Choice',app.enumerations.get_member('State')._values[0])

    def test_wrong_enum_rejected(self):
        store=self.store()
        with self.assertRaises(TypeError):store.set('Choice',self.enum(store,'Mode')._values[0])

    def test_forged_reference_uuid_rejected(self):
        store=self.store();m=self.enum(store)
        ref=BSLEnumReference(m._value_type,UUID(int=123),m._metadata)
        with self.assertRaises(TypeError):store.set('Choice',ref)

    def test_no_coercion_or_default(self):
        store=self.store()
        with self.assertRaisesRegex(ValueError,'uninitialized'):store.get('Choice')
        for v in (None,'Active',identity('Active'),True):
            with self.assertRaises(TypeError):store.set('Choice',v)

    def test_bsl_app_identity(self):
        source=package('Constants.Choice.Set(Enums.State.Active); Message(Constants.Choice.Get()=Enums.State.Active);')
        output=[];app=SourceApplication(source,scratch_database=self.path,output=output.append);self.addCleanup(app.close);app.start()
        self.assertEqual(output,['Да'])
        self.assertIs(app.constant_store.get('Choice'),app.enumerations.get_member('State')._values[0])

    def test_bsl_set_and_manager(self):
        source=package('S=Constants.CreateSet("Choice"); S.Choice=Enums.State.Active; S.Write(); M=Constants.Choice.CreateValueManager(); M.Read(); M.Value=Enums.State.Inactive; M.Write();')
        app=SourceApplication(source,scratch_database=self.path);self.addCleanup(app.close);app.start()
        self.assertIs(app.constant_store.get('Choice'),app.enumerations.get_member('State')._values[1])

    def test_union_multiple_enum_families(self):
        source=package(types='<v8:Type>cfg:EnumRef.State</v8:Type><v8:Type>cfg:EnumRef.Mode</v8:Type><v8:Type>xs:boolean</v8:Type>')
        store=self.store(source)
        for ref in (self.enum(store)._values[0],self.enum(store,'Mode')._empty,True,None):
            store.set('Choice',ref);self.assertEqual(store.get('Choice'),ref)

    def test_unsupported_enum_whole_union_refused(self):
        for types in ('<v8:Type>cfg:EnumRef.Missing</v8:Type>', '<v8:Type>cfg:EnumRef.State</v8:Type><v8:Type>cfg:EnumRef.Missing</v8:Type>', '<v8:Type>cfg:EnumRef.State</v8:Type><v8:Type>cfg:EnumRef.State</v8:Type>'):
            _,unsupported,_=source_constant_definitions(package(types=types));self.assertIn('choice',unsupported)

    def test_transaction_rollback(self):
        store=self.store();a,b=self.enum(store)._values;store.set('Choice',a);store.begin_transaction();store.set('Choice',b);store.rollback_transaction();self.assertEqual(store.get('Choice'),a)

    def test_corrupt_identity_refused(self):
        store=self.store();store.set('Choice',self.enum(store)._values[0]);store.close()
        with closing(sqlite3.connect(self.path)) as db,db:
            db.execute("UPDATE constant_value SET value_json=? WHERE identity=(SELECT identity FROM constant_schema WHERE name='Choice')",('["enum_ref",["'+identity('EnumState')+'","00000000-0000-0000-0000-000000000123"]]',))
        with self.assertRaises(ValueError):SourceConstantStore.reopen(self.path,package())

    def test_compatible_source_update_preserves_identity(self):
        store=self.store();old=self.enum(store)._values[0];store.set('Choice',old);store.close()
        source=package('Message("updated");');SourceConstantStore.update_source(self.path,source)
        store=SourceConstantStore.reopen(self.path,source);self.addCleanup(store.close)
        self.assertEqual(store.get('Choice').reference_uuid,old.reference_uuid)

    def test_enum_removal_and_reidentity_update_refused(self):
        store=self.store();store.set('Choice',self.enum(store)._values[0]);store.close();before=self.path.read_bytes()
        for changed in (xml('Enum','State',value('Inactive')),xml('Enum','State',value('Active',uid=identity('replacement'))+value('Inactive'))):
            with self.assertRaises(ValueError):SourceConstantStore.update_source(self.path,package(extra={'Enums/State.xml':changed}))
            self.assertEqual(self.path.read_bytes(),before)

    def test_namespace_mismatch_before_destination_creation(self):
        app=SourceApplication(package(extra={'Enums/State.xml':xml('Enum','State',value('Inactive'))}));self.addCleanup(app.close)
        with self.assertRaises(ValueError):SourceConstantStore.create(self.path,package(),enum_namespace=app.enumerations)
        self.assertFalse(self.path.exists())
