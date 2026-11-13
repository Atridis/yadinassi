"""Neutral source references do not create records or activate their readers."""
import tempfile
import unittest
from pathlib import Path
from uuid import UUID
from test_source_manager_modules import configuration
from test_source_defined_type_constants import xml
from yadinassi.configuration_source import import_source
from yadinassi.configuration_source_runtime import SourceApplication
from yadinassi.source_constant_store import SourceConstantStore
from yadinassi.source_references import SourceReferenceManager, SourceReferenceCall
from yadinassi.unique_identifiers import BSLUUID
from yadinassi.errors import BSLError

ID='01234567-89ab-cdef-0123-456789abcdef'


def package(call='', family='Catalog', constant=True, body=None):
    folder='Catalogs' if family=='Catalog' else 'Documents'
    source=configuration(call,body=body,family=family,folder=folder)
    files={e.path:e.content for e in source.files}
    if constant:
        files['Configuration.xml']=files['Configuration.xml'].replace(b'<ChildObjects/>', b'<ChildObjects><Constant>Choice</Constant></ChildObjects>').replace(b'<ChildObjects />', b'<ChildObjects><Constant>Choice</Constant></ChildObjects>')
        if b'<Constant>Choice</Constant>' not in files['Configuration.xml']:
            files['Configuration.xml']=files['Configuration.xml'].replace(b'</Configuration>', b'<ChildObjects><Constant>Choice</Constant></ChildObjects></Configuration>')
        files['Constants/Choice.xml']=xml('Choice','<v8:Type>cfg:'+family+'Ref.Items</v8:Type>','Constant')
    return import_source(files)


class SourceReferenceTests(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory();self.addCleanup(tmp.cleanup);self.path=Path(tmp.name)/'scratch.sqlite'

    def app(self, source=None, reopen=False):
        out=[]
        kwargs={'existing_scratch_database' if reopen else 'scratch_database':self.path}
        app=SourceApplication(source or package(),output=out.append,**kwargs);self.addCleanup(app.close)
        return app,out

    def test_catalog_empty(self):
        app,out=self.app(package('Message(Catalogs.Items.EmptyRef().IsEmpty());'))
        app.start();self.assertEqual(out,['Да'])

    def test_document_empty(self):
        app,out=self.app(package('Message(Documents.Items.EmptyRef().IsEmpty());','Document'))
        app.start();self.assertEqual(out,['Да'])

    def test_uuid_round_trip(self):
        app,out=self.app(package('R=Catalogs.Items.GetRef(New UUID("'+ID+'")); Message(R.UUID()); Message(R.IsEmpty());'))
        app.start();self.assertEqual(out,[ID,'Нет'])

    def test_russian_alias(self):
        app,out=self.app(package('Сообщить(Справочники.Items.ПустаяСсылка().Пустая());'))
        app.start();self.assertEqual(out,['Да'])

    def test_metadata(self):
        app,out=self.app(package('Message(Catalogs.Items.Metadata().Name); Message(Catalogs.Items.EmptyRef().Metadata().Name);'))
        app.start();self.assertEqual(out,['Items','Items'])

    def test_no_fake_get_object(self):
        app,_=self.app(package('Catalogs.Items.EmptyRef().GetObject();'))
        with self.assertRaisesRegex(BSLError,'unavailable'):app.start()

    def test_no_fake_create(self):
        app,_=self.app(package('Catalogs.Items.CreateItem();'))
        with self.assertRaisesRegex(BSLError,'storage operations are not activated'):app.start()

    def test_no_fake_description(self):
        app,_=self.app(package('Message(Catalogs.Items.GetRef(New UUID("'+ID+'")));'))
        with self.assertRaisesRegex(BSLError,'presentation is unavailable'):app.start()

    def test_no_implicit_getref_default(self):
        app,_=self.app(package('Catalogs.Items.GetRef();'))
        with self.assertRaisesRegex(BSLError,'explicit UUID'):app.start()

    def test_wrong_uuid(self):
        app,_=self.app(package('Catalogs.Items.GetRef("'+ID+'");'))
        with self.assertRaisesRegex(BSLError,'explicit UUID'):app.start()

    def test_exported_manager_routine_survives(self):
        app,out=self.app(package('Message(Catalogs.Items.Answer()); Message(Catalogs.Items.EmptyRef().IsEmpty());',body='Function Answer() Export Return 42; EndFunction'))
        app.start();self.assertEqual(out,['42','Да'])

    def test_unused_invalid_manager_not_compiled_for_identity(self):
        app,out=self.app(package('Message(Catalogs.Items.EmptyRef().IsEmpty());',body='broken ???'))
        app.start();self.assertEqual(out,['Да'])

    def test_store_reopen(self):
        source=package();app,_=self.app(source);ref=app.references.ref('Catalog','Items',UUID(ID));app.constant_store.set('Choice',ref);app.close()
        app,_=self.app(source,reopen=True);read=app.constant_store.get('Choice')
        self.assertEqual(read.reference_uuid,UUID(ID));self.assertEqual(read.value_type,app.references.definition('Catalog','Items')[1])

    def test_foreign_reference_rejected(self):
        app,_=self.app();other=SourceApplication(package());self.addCleanup(other.close)
        with self.assertRaises(TypeError):app.constant_store.set('Choice',other.references.ref('Catalog','Items',UUID(ID)))

    def test_bsl_constant_roundtrip(self):
        app,out=self.app(package('Constants.Choice.Set(Catalogs.Items.GetRef(New UUID("'+ID+'"))); Message(Constants.Choice.Get().UUID());'))
        app.start();self.assertEqual(out,[ID])

    def test_explicit_rollback(self):
        app,_=self.app();store=app.constant_store;empty=app.references.ref('Catalog','Items',UUID(int=0));store.set('Choice',empty)
        store.begin_transaction();store.set('Choice',app.references.ref('Catalog','Items',UUID(ID)));store.rollback_transaction();self.assertTrue(store.get('Choice').is_empty())

    def test_no_guessed_default(self):
        app,_=self.app()
        with self.assertRaisesRegex(ValueError,'uninitialized'):app.constant_store.get('Choice')

    def test_manager_marker_cannot_run_directly(self):
        app,_=self.app();manager=SourceReferenceManager(app,'Catalog','Items')
        with self.assertRaises(ValueError):SourceReferenceCall(manager,'empty')()

    def test_closed_application(self):
        app,_=self.app();manager=SourceReferenceManager(app,'Catalog','Items');app.close()
        with self.assertRaises(ValueError):manager.authorize(app.interpreter)

    def test_wrong_caller(self):
        app,_=self.app();other=SourceApplication(package());self.addCleanup(other.close);other.start()
        with self.assertRaises(ValueError):SourceReferenceManager(app,'Catalog','Items').authorize(other.interpreter)

    def test_composite_catalog_document(self):
        files={e.path:e.content for e in package().files}
        files['Documents/Items.xml']=xml('Items','<v8:Type>xs:boolean</v8:Type>','Document')
        # Configuration admission requires globally distinct metadata identities.
        files['Documents/Items.xml']=files['Documents/Items.xml'].replace(b'00000000-0000-0000-0000-000000000002',b'00000000-0000-0000-0000-000000000003')
        files['Constants/Choice.xml']=xml('Choice','<v8:Type>cfg:CatalogRef.Items</v8:Type><v8:Type>cfg:DocumentRef.Items</v8:Type>','Constant')
        app,_=self.app(import_source(files))
        for family in ('Catalog','Document'):
            value=app.references.ref(family,'Items',UUID(ID));app.constant_store.set('Choice',value)
            self.assertEqual(app.constant_store.get('Choice'),value)

    def test_wire_integrity(self):
        from yadinassi.source_constant_store import _decode
        app,_=self.app();definition=app.constant_store._definition('Choice')
        for raw in ('["object_ref",["Document","bad","'+ID+'"]]',
                    '["object_ref",["Catalog","00000000-0000-0000-0000-000000000002","notuuid"]]'):
            with self.assertRaises(ValueError):_decode(raw,definition)

    def test_target_reidentity_update_refused(self):
        source=package();app,_=self.app(source);app.constant_store.set('Choice',app.references.ref('Catalog','Items',UUID(ID)));app.close()
        before=self.path.read_bytes();files={e.path:e.content for e in source.files}
        files['Catalogs/Items.xml']=files['Catalogs/Items.xml'].replace(b'00000000-0000-0000-0000-000000000002',b'00000000-0000-0000-0000-000000000099')
        with self.assertRaises(ValueError):SourceConstantStore.update_source(self.path,import_source(files))
        self.assertEqual(self.path.read_bytes(),before)
