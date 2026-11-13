"""Closed, explicit composite constants; no inferred native defaults."""
from contextlib import closing
from decimal import Decimal
import sqlite3
import tempfile
from pathlib import Path
import unittest
from test_source_constant_store import configuration
from test_source_session_parameters import declaration
from yadinassi.configuration_source import import_source
from yadinassi.configuration_source_constants import source_constant_definitions
from yadinassi.source_constant_store import SourceConstantStore
from yadinassi.configuration_source_runtime import SourceApplication
from yadinassi.unique_identifiers import BSLUUID
from yadinassi.value_storage import BSLValueStorage
from yadinassi.values import NULL
from yadinassi.errors import BSLError

TYPES = '<v8:Type>xs:boolean</v8:Type><v8:Type>v8:UUID</v8:Type><v8:Type>v8:ValueStorage</v8:Type><v8:Type>xs:string</v8:Type><v8:StringQualifiers><v8:Length>64</v8:Length><v8:AllowedLength>Variable</v8:AllowedLength></v8:StringQualifiers>'
ID='01234567-89ab-cdef-0123-456789abcdef'


def package(types=TYPES, body='', module=''):
    files={f.path:f.content for f in configuration().files}
    files['Configuration.xml']=files['Configuration.xml'].replace(b'</ChildObjects>', b'<Constant>Choice</Constant></ChildObjects>')
    files['Constants/Choice.xml']=declaration('Choice',types).replace(b'SessionParameter',b'Constant')
    if body:files['Ext/SessionModule.bsl']=('Procedure SessionParametersSetting(Names) '+body+' EndProcedure').encode()
    if module:files['Constants/Choice/Ext/ValueManagerModule.bsl']=module.encode()
    return import_source(files)


class CompositeConstantsTests(unittest.TestCase):
    def setUp(self):
        directory=tempfile.TemporaryDirectory();self.addCleanup(directory.cleanup)
        self.path=Path(directory.name)/'scratch.sqlite'

    def store(self, source=None):
        store=SourceConstantStore.create(self.path,source or package());self.addCleanup(store.close);return store

    def test_admission(self):
        defs,unsupported,_=source_constant_definitions(package())
        definition=next(d for d in defs if d.name=='Choice')
        self.assertEqual(definition.kind,'composite');self.assertEqual(len(definition.qualifiers),4)
        self.assertNotIn('choice',unsupported)

    def test_all_members_and_undefined_roundtrip(self):
        store=self.store()
        for value in (None,True,False,'hello',BSLUUID(ID),BSLValueStorage('payload')):
            store.set('Choice',value);got=store.get('Choice')
            if type(value) is BSLValueStorage:self.assertEqual(got.get(),'payload')
            elif type(value) is BSLUUID:self.assertEqual(got.text,ID)
            else:self.assertEqual(got,value)

    def test_no_guessed_default(self):
        with self.assertRaisesRegex(ValueError,'uninitialized'):self.store().get('Choice')

    def test_unsupported_value_leaves_prior_value(self):
        store=self.store();store.set('Choice','old')
        for value in (NULL,Decimal(1),object(),'x'*65):
            with self.assertRaises((ValueError,TypeError)):store.set('Choice',value)
            self.assertEqual(store.get('Choice'),'old')

    def test_number_date_qualifiers(self):
        from yadinassi.dates import BSLDate
        types='<v8:Type>xs:decimal</v8:Type><v8:NumberQualifiers><v8:Digits>8</v8:Digits><v8:FractionDigits>2</v8:FractionDigits><v8:AllowedSign>Nonnegative</v8:AllowedSign></v8:NumberQualifiers><v8:Type>xs:dateTime</v8:Type><v8:DateQualifiers><v8:DateFractions>DateTime</v8:DateFractions></v8:DateQualifiers>'
        store=self.store(package(types))
        for value in (Decimal('12.25'), BSLDate(0), None):
            store.set('Choice',value);self.assertEqual(store.get('Choice'),value)
        for value in (Decimal('-1'),Decimal('1.001'),True):
            with self.assertRaises((ValueError,TypeError)):store.set('Choice',value)

    def test_reopen(self):
        store=self.store();store.set('Choice',None);store.close()
        store=SourceConstantStore.reopen(self.path,package());self.addCleanup(store.close)
        self.assertIsNone(store.get('Choice'))

    def test_transaction_rollback(self):
        store=self.store();store.set('Choice','old');store.begin_transaction();store.set('Choice',None);store.rollback_transaction()
        self.assertEqual(store.get('Choice'),'old')

    def test_bsl_set_and_manager_and_set_buffer(self):
        source=package(body='Constants.Choice.Set(Undefined); M=Constants.Choice.CreateValueManager(); M.Read(); M.Value=True; M.Write(); S=Constants.CreateSet("Choice"); S.Read(); S.Choice="new"; S.Write();')
        app=SourceApplication(source,scratch_database=self.path);self.addCleanup(app.close);app.start()
        self.assertEqual(app.constant_store.get('Choice'),'new')

    def test_handlers_receive_composite_value(self):
        source=package(body='Constants.Choice.Set(True);', module='Procedure BeforeWrite(Cancel) Value="changed"; EndProcedure')
        app=SourceApplication(source,scratch_database=self.path);self.addCleanup(app.close);app.start()
        self.assertEqual(app.constant_store.get('Choice'),'changed')

    def test_bad_handler_value_rollback(self):
        source=package(body='Constants.Choice.Set(True);', module='Procedure BeforeWrite(Cancel) Value=42; EndProcedure')
        app=SourceApplication(source,scratch_database=self.path);self.addCleanup(app.close)
        with self.assertRaises(BSLError):app.start()
        store=SourceConstantStore.reopen(self.path,source);self.addCleanup(store.close)
        with self.assertRaisesRegex(ValueError,'uninitialized'):store.get('Choice')

    def test_invalid_union_members_are_not_partially_admitted(self):
        for types in (TYPES+'<v8:Type>cfg:CatalogRef.Unknown</v8:Type>',TYPES+'<v8:Type>xs:boolean</v8:Type>',TYPES+'<v8:Unknown/>',TYPES.replace('v8:UUID','xs:UUID'),TYPES.replace('<v8:Length>64','<v8:Length>0')):
            _,unsupported,_=source_constant_definitions(package(types))
            self.assertIn('choice',unsupported)

    def test_corrupt_nested_record_refused(self):
        for raw in ('["composite", ["undefined", false]]','["composite", ["number", "2"]]','["composite", ["uuid", "bad"]]','["composite", ["composite", null]]','["composite", ["boolean", 1]]'):
            with self.subTest(raw=raw):
                path=self.path
                if path.exists():path.unlink()
                store=self.store();store.set('Choice',True);store.close()
                with closing(sqlite3.connect(path)) as db,db:db.execute("UPDATE constant_value SET value_json=? WHERE identity=(SELECT identity FROM constant_schema WHERE name='Choice')",(raw,))
                with self.assertRaises(ValueError):SourceConstantStore.reopen(path,package())

    def test_compatible_update_preserves_composite_values(self):
        store=self.store();store.set('Choice',BSLUUID(ID));store.close()
        source=package(body='Message("changed");')
        SourceConstantStore.update_source(self.path,source)
        store=SourceConstantStore.reopen(self.path,source);self.addCleanup(store.close)
        self.assertEqual(store.get('Choice').text,ID)

    def test_update_union_change_refused_without_mutation(self):
        store=self.store();store.set('Choice','old');store.close();before=self.path.read_bytes()
        with self.assertRaises(ValueError):SourceConstantStore.update_source(self.path,package(TYPES.replace('<v8:Type>xs:boolean</v8:Type>','')))
        self.assertEqual(self.path.read_bytes(),before)
