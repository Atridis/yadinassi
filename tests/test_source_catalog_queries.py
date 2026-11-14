import tempfile
import unittest
from pathlib import Path
from uuid import uuid4
from test_source_catalog_records import package
from yadinassi.configuration_source_runtime import SourceApplication
from yadinassi.source_catalog_store import SourceCatalogStore
from yadinassi.errors import BSLError

class SourceCatalogQueryTests(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory();self.addCleanup(tmp.cleanup);self.path=Path(tmp.name)/'q.sqlite'
    def run_body(self,body, *, rows=True, constants=False):
        source=package(body)
        if constants:
            from test_source_constant_store import configuration
            from yadinassi.configuration_source import import_source
            files={e.path:e.content for e in configuration().files}
            files.update({e.path:e.content for e in source.files if e.path!='Configuration.xml'})
            source=import_source(files)
        store=SourceCatalogStore.create(self.path,source)
        if constants:store.set('Flag',True)
        self.ids=[uuid4(),uuid4()]
        if rows:
            for i,key in enumerate(self.ids):store.write_record('Items',key,0,{'code':str(i+1),'description':['Alpha','Beta'][i],'deletionmark':False})
        store.close();out=[];app=SourceApplication(source,existing_scratch_database=self.path,source_catalog_records=True,output=out.append);self.addCleanup(app.close);app.start();return app,out
    def query(self,text,tail='While S.Next() Do Message(S.X); EndDo;',**kwargs):
        return self.run_body('Q=New Query("'+text.replace(chr(34),chr(34)*2)+'"); S=Q.Execute().Select(); '+tail,**kwargs)
    def test_scalar_select(self):
        _,out=self.query('SELECT Description AS X FROM Catalog.Items ORDER BY Code');self.assertEqual(out,['Alpha','Beta'])
    def test_russian_fields(self):
        _,out=self.query('ВЫБРАТЬ Наименование КАК X ИЗ Справочник.Items УПОРЯДОЧИТЬ ПО Код');self.assertEqual(out,['Alpha','Beta'])
    def test_filter(self):
        _,out=self.query("SELECT Description AS X FROM Catalog.Items WHERE Code = \"2\"");self.assertEqual(out,['Beta'])
    def test_count_empty(self):
        _,out=self.query('SELECT COUNT(*) AS X FROM Catalog.Items',rows=False);self.assertEqual(out,['0'])
    def test_count(self):
        _,out=self.query('SELECT COUNT(*) AS X FROM Catalog.Items');self.assertEqual(out,['2'])
    def test_self_join(self):
        _,out=self.query('SELECT A.Description AS X FROM Catalog.Items AS A INNER JOIN Catalog.Items AS B ON A.Ref=B.Ref ORDER BY A.Code');self.assertEqual(out,['Alpha','Beta'])
    def test_union(self):
        _,out=self.query("SELECT Description AS X FROM Catalog.Items WHERE Code=\"1\" UNION ALL SELECT Description AS X FROM Catalog.Items WHERE Code=\"2\"");self.assertEqual(out,['Alpha','Beta'])
    def test_derived(self):
        _,out=self.query('SELECT D.X AS X FROM (SELECT Description AS X FROM Catalog.Items) AS D ORDER BY X');self.assertEqual(out,['Alpha','Beta'])
    def test_ref_is_typed(self):
        app,out=self.query('SELECT Ref AS X FROM Catalog.Items ORDER BY Code','S.Next(); Message(S.X.UUID()); Message(S.X.GetObject().Description);')
        self.assertEqual(out,[str(self.ids[0]),'Alpha'])
    def test_ref_unload(self):
        _,out=self.run_body('Q=New Query("SELECT Ref AS R, Description AS D FROM Catalog.Items ORDER BY Code"); T=Q.Execute().Unload(); Message(T.Get(0).R.UUID()); Message(T.Get(1).D);')
        self.assertEqual(out,[str(self.ids[0]),'Beta'])
    def test_scalar_unload(self):
        _,out=self.run_body('Q=New Query("SELECT Description AS D FROM Catalog.Items ORDER BY Code"); T=Q.Execute().Unload(); Message(T.Get(0).D);');self.assertEqual(out,['Alpha'])
    def test_transaction_query_sees_own_write_then_rollback(self):
        _,out=self.run_body('BeginTransaction(); O=Catalogs.Items.CreateItem(); O.Code="3"; O.Write(); Q=New Query("SELECT COUNT(*) AS X FROM Catalog.Items"); S=Q.Execute().Select(); S.Next(); Message(S.X); RollbackTransaction(); S=Q.Execute().Select(); S.Next(); Message(S.X);');self.assertEqual(out,['3','2'])
    def test_unknown_field(self):
        with self.assertRaises(BSLError):self.query('SELECT Missing AS X FROM Catalog.Items')
    def test_no_fake_document(self):
        with self.assertRaises(BSLError):self.query('SELECT A.Code AS X FROM Catalog.Items AS A INNER JOIN Document.Missing AS B ON A.Ref=B.Ref')
    def test_no_sections(self):
        with self.assertRaises(BSLError):self.query('SELECT Code AS X FROM Catalog.Items.Rows')
    def test_into(self):
        _,out=self.query('SELECT Code AS X INTO Temporary FROM Catalog.Items; SELECT X FROM Temporary ORDER BY X');self.assertEqual(out,['1','2'])
    def test_batch(self):
        _,out=self.run_body('Q=New Query("SELECT Code FROM Catalog.Items"); Message(Q.ExecuteBatch().Count());');self.assertEqual(out,['1'])
    def test_safe_mode(self):
        with self.assertRaises(BSLError):self.run_body('SetSafeMode(True); Q=New Query("SELECT Code FROM Catalog.Items"); Q.Execute();')
    def test_result_frozen_after_write(self):
        _,out=self.run_body('Q=New Query("SELECT Description AS D, Ref AS R FROM Catalog.Items ORDER BY Code"); S=Q.Execute().Select(); S.Next(); O=S.R.GetObject(); O.Description="Changed"; O.Write(); Message(S.D);');self.assertEqual(out,['Alpha'])
    def test_ref_report_requery(self):
        _,out=self.run_body('Q=New Query("SELECT Ref AS R FROM Catalog.Items"); T=Q.Execute().Unload(); Q=New Query("SELECT R FROM &Input"); Q.SetParameter("Input",T); Message(Q.Execute().Unload().Count());')
        self.assertEqual(out,['2'])
    def test_constants_catalog_join(self):
        _,out=self.query('SELECT A.Description AS X FROM Catalog.Items AS A INNER JOIN Constants AS C ON C.Flag=TRUE ORDER BY A.Code',constants=True);self.assertEqual(out,['Alpha','Beta'])
    def test_combined_transaction_snapshot(self):
        _,out=self.run_body('BeginTransaction(); Constants.Flag.Set(False); O=Catalogs.Items.CreateItem(); O.Code="3"; O.Write(); Q=New Query("SELECT COUNT(*) AS X FROM Catalog.Items AS A INNER JOIN Constants AS C ON C.Flag=FALSE"); S=Q.Execute().Select(); S.Next(); Message(S.X); RollbackTransaction(); S=Q.Execute().Select(); S.Next(); Message(S.X);',constants=True);self.assertEqual(out,['3','0'])
    def test_binding_rejects_foreign_application(self):
        from yadinassi.source_query_references import make_binding
        app,_=self.run_body('');other=SourceApplication(package());self.addCleanup(other.close)
        binding=make_binding(app,app.interpreter._catalogs,'Items')
        with self.assertRaises(TypeError):binding.value(other.references.ref('Catalog','Items',self.ids[0]))
    def test_binding_rejects_forged_callback(self):
        from dataclasses import replace
        from yadinassi.source_query_references import make_binding
        app,_=self.run_body('');binding=make_binding(app,app.interpreter._catalogs,'Items');ref=app.references.ref('Catalog','Items',self.ids[0])
        with self.assertRaises(TypeError):binding.value(replace(ref,read_member=lambda r,n:'fake'))
    def test_binding_closed_owner(self):
        from yadinassi.source_query_references import make_binding
        app,_=self.run_body('');binding=make_binding(app,app.interpreter._catalogs,'Items');ref=app.references.ref('Catalog','Items',self.ids[0]);app.close()
        with self.assertRaises(ValueError):binding.value(ref)
    def test_query_rejects_foreign_caller(self):
        from yadinassi.source_constant_queries import SourceConstantQuery
        app,_=self.run_body('');other=SourceApplication(package());self.addCleanup(other.close);other.start();other.interpreter._context_stack.append('server')
        query=SourceConstantQuery(app.interpreter,app,'SELECT Code FROM Catalog.Items')
        with self.assertRaises(ValueError):query.read(other.interpreter)
