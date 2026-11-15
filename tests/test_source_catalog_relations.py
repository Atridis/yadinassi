import tempfile
import unittest
from pathlib import Path
from uuid import UUID, uuid4
from test_source_catalog_definitions import config, attribute
from test_source_defined_type_constants import xml
from yadinassi.configuration_source import import_source
from yadinassi.configuration_source_runtime import SourceApplication
from yadinassi.source_catalog_store import SourceCatalogStore
from yadinassi.source_constant_store import SourceConstantStore
from yadinassi.source_catalog_definitions import source_catalog_definitions
from yadinassi.errors import BSLError


def source(body='',target='Groups',constant=False):
    base=config(children=attribute('Category','<v8:Type>cfg:CatalogRef.'+target+'</v8:Type>'))
    files={e.path:e.content for e in base.files}
    files['Catalogs/Items.xml']=files['Catalogs/Items.xml'].replace(b'xmlns:xs=',b'xmlns:cfg="http://v8.1c.ru/8.1/data/enterprise/current-config" xmlns:xs=')
    group={e.path:e.content for e in config().files}['Catalogs/Items.xml'].replace(b'<Name>Items</Name>',b'<Name>Groups</Name>').replace(b'00000000-0000-0000-0000-000000000002',b'00000000-0000-0000-0000-000000000003')
    files['Catalogs/Groups.xml']=group
    if body:files['Ext/SessionModule.bsl']=('Procedure SessionParametersSetting(Names) '+body+' EndProcedure').encode()
    if constant:
        files['Configuration.xml']=files['Configuration.xml'].replace(b'</Configuration>',b'<ChildObjects><Constant>Choice</Constant></ChildObjects></Configuration>')
        files['Constants/Choice.xml']=xml('Choice','<v8:Type>cfg:CatalogRef.Groups</v8:Type>','Constant')
    return import_source(files)

CREATE='G=Catalogs.Groups.CreateItem(); G.Code="G"; G.Description="Group"; G.Write(); I=Catalogs.Items.CreateItem(); I.Code="I"; I.Description="Item"; I.Category=G.Ref; I.Write(); '

class SourceCatalogRelationTests(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory();self.addCleanup(tmp.cleanup);self.path=Path(tmp.name)/'relations.sqlite'
    def app(self,package=None):
        out=[];app=SourceApplication(package or source(),scratch_database=self.path,source_catalog_records=True,output=out.append);self.addCleanup(app.close);return app,out
    def run_body(self,body,**kwargs):
        app,out=self.app(source(body,**kwargs));app.start();return app,out
    def values(self,category):return {'code':'I','description':'Item','deletionmark':False,'category':category}
    def test_reference_schema(self):
        definitions,errors=source_catalog_definitions(source());self.assertFalse(errors);field=definitions['items'].fields[-1]
        self.assertEqual(field.kind,'object_ref');self.assertEqual(field.qualifiers[:2],('Catalog','00000000-0000-0000-0000-000000000003'))
    def test_missing_target_refused_per_catalog(self):
        definitions,errors=source_catalog_definitions(source(target='Missing'));self.assertIn('items',errors);self.assertIn('groups',definitions)
    def test_real_object_navigation(self):
        _,out=self.run_body(CREATE+'Message(I.Ref.GetObject().Category.GetObject().Description);');self.assertEqual(out,['Group'])
    def test_explicit_empty_reference(self):
        _,out=self.run_body('I=Catalogs.Items.CreateItem(); I.Code="I"; I.Category=Catalogs.Groups.EmptyRef(); I.Write(); Message(I.Ref.GetObject().Category.IsEmpty());');self.assertEqual(out,['Да'])
    def test_no_default_reference(self):
        with self.assertRaises(BSLError):self.run_body('I=Catalogs.Items.CreateItem(); I.Code="I"; I.Write();')
    def test_self_reference_roundtrip(self):
        _,out=self.run_body('I=Catalogs.Items.CreateItem(); I.Code="I"; I.Category=Catalogs.Items.EmptyRef(); I.Write(); I.Category=I.Ref; I.Write(); Message(I.Ref.GetObject().Category=I.Ref);',target='Items');self.assertEqual(out,['Да'])
    def test_foreign_application_reference_rejected(self):
        app,_=self.app();other=SourceApplication(source());self.addCleanup(other.close)
        with self.assertRaises(TypeError):app.constant_store.write_record('Items',uuid4(),0,self.values(other.references.ref('Catalog','Groups',uuid4())))
    def test_wrong_target_reference_rejected(self):
        app,_=self.app()
        with self.assertRaises(TypeError):app.constant_store.write_record('Items',uuid4(),0,self.values(app.references.ref('Catalog','Items',uuid4())))
    def test_wrong_scalar_rejected(self):
        app,_=self.app()
        with self.assertRaises(TypeError):app.constant_store.write_record('Items',uuid4(),0,self.values('not-reference'))
    def test_reopen_current_snapshot(self):
        package=source();app,_=self.app(package);key=uuid4();target=uuid4();app.constant_store.write_record('Items',key,0,self.values(app.references.ref('Catalog','Groups',target)));app.close()
        reopened=SourceApplication(package,existing_scratch_database=self.path,source_catalog_records=True);self.addCleanup(reopened.close)
        value=reopened.constant_store.read_records('Items',key)[0][2]['category'];self.assertEqual(value.reference_uuid,target);self.assertIs(value.value_type,reopened.references.definition('Catalog','Groups')[1])
    def test_dangling_identity_not_fabricated_record(self):
        with self.assertRaisesRegex(BSLError,'not found'):
            self.run_body('I=Catalogs.Items.CreateItem(); I.Code="I"; I.Category=Catalogs.Groups.GetRef(New UUID("01234567-89ab-cdef-0123-456789abcdef")); I.Write(); I.Category.GetObject();')
    def test_query_join_relation(self):
        _,out=self.run_body(CREATE+'Q=New Query("SELECT G.Description AS Name FROM Catalog.Items AS I INNER JOIN Catalog.Groups AS G ON I.Category=G.Ref"); S=Q.Execute().Select(); S.Next(); Message(S.Name);');self.assertEqual(out,['Group'])
    def test_query_relation_unload(self):
        _,out=self.run_body(CREATE+'Q=New Query("SELECT Category AS Link FROM Catalog.Items"); T=Q.Execute().Unload(); Message(T.Get(0).Link=G.Ref);');self.assertEqual(out,['Да'])
    def test_query_mismatched_target(self):
        with self.assertRaises(BSLError):self.run_body(CREATE+'Q=New Query("SELECT I.Code FROM Catalog.Items AS I INNER JOIN Catalog.Groups AS G ON I.Category=I.Ref"); Q.Execute();')
    def test_select_relation(self):
        _,out=self.run_body(CREATE+'S=Catalogs.Items.Select(); S.Next(); Message(S.Category=G.Ref);');self.assertEqual(out,['Да'])
    def test_relation_transaction_rollback(self):
        _,out=self.run_body(CREATE+'BeginTransaction(); I.Category=Catalogs.Groups.EmptyRef(); I.Write(); RollbackTransaction(); I.Read(); Message(I.Category=G.Ref);');self.assertEqual(out,['Да'])
    def test_target_reidentity_update_preserves_bytes(self):
        package=source();app,_=self.app(package);app.close();before=self.path.read_bytes();files={e.path:e.content for e in package.files}
        files['Catalogs/Groups.xml']=files['Catalogs/Groups.xml'].replace(b'00000000-0000-0000-0000-000000000003',b'00000000-0000-0000-0000-000000000004')
        with self.assertRaises(ValueError):SourceCatalogStore.update_source(self.path,import_source(files))
        self.assertEqual(self.path.read_bytes(),before)
    def test_host_store_constants_and_fields_share_scope(self):
        store=SourceCatalogStore.create(self.path,source(constant=True));self.addCleanup(store.close);scope=store._definition('Choice').reference_scope
        ref=scope.ref('Catalog','Groups',uuid4());store.set('Choice',ref);key=uuid4();store.write_record('Items',key,0,self.values(store.get('Choice')));self.assertEqual(store.read_records('Items',key)[0][2]['category'],ref)
    def test_empty_field_query(self):
        _,out=self.run_body('I=Catalogs.Items.CreateItem(); I.Code="I"; I.Category=Catalogs.Groups.EmptyRef(); I.Write(); Q=New Query("SELECT Category AS Link FROM Catalog.Items"); S=Q.Execute().Select(); S.Next(); Message(S.Link.IsEmpty());');self.assertEqual(out,['Да'])
    def test_two_catalogs_transaction_is_atomic(self):
        _,out=self.run_body('BeginTransaction(); '+CREATE+'RollbackTransaction(); S=Catalogs.Items.Select(); Message(S.Next()); S=Catalogs.Groups.Select(); Message(S.Next());');self.assertEqual(out,['Нет','Нет'])
