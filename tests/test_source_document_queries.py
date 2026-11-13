"""Real v5 Document query snapshots and typed detached reports."""
import unittest
from unittest.mock import patch
import test_source_document_records as support
from yadinassi.errors import BSLError
from yadinassi.source_document_store import SourceDocumentStore

SEED='O=Catalogs.Items.CreateItem(); O.Code="C"; O.Description="catalog"; O.Write(); D=Documents.Invoice.CreateDocument(); D.Number="A"; D.Date=Date(2026,1,1); D.Write(); D=Documents.Invoice.CreateDocument(); D.Number="B"; D.Date=Date(2026,1,2); D.Write(); '
class SourceDocumentQueryTests(unittest.TestCase):
    setUp=support.SourceDocumentRecordTests.setUp
    def run_body(self,body):return support.SourceDocumentRecordTests.run_app(self,SEED+body)
    def test_real_fields(self):
        _,out=self.run_body('Q=New Query("SELECT Number, Posted FROM Document.Invoice ORDER BY Number"); S=Q.Execute().Select(); While S.Next() Do Message(S.Number); Message(S.Posted); EndDo;');self.assertEqual(out,['A','Нет','B','Нет'])
    def test_russian(self):
        _,out=self.run_body('Q=New Query("ВЫБРАТЬ Номер КАК N ИЗ Документ.Invoice УПОРЯДОЧИТЬ ПО Номер"); S=Q.Execute().Select(); S.Next(); Message(S.N);');self.assertEqual(out,['A'])
    def test_ref_live(self):
        _,out=self.run_body('Q=New Query("SELECT Ref AS R FROM Document.Invoice ORDER BY Number"); S=Q.Execute().Select(); S.Next(); Message(S.R.Number);');self.assertEqual(out,['A'])
    def test_unload_requery(self):
        _,out=self.run_body('Q=New Query("SELECT Ref AS R FROM Document.Invoice"); T=Q.Execute().Unload(); Q.Text="SELECT R FROM &Input"; Q.SetParameter("Input",T); S=Q.Execute().Select(); S.Next(); Message(S.R.IsEmpty());');self.assertEqual(out,['Нет'])
    def test_temp_requery(self):
        _,out=self.run_body('M=New TempTablesManager; Q=New Query("SELECT Ref AS R INTO T FROM Document.Invoice"); Q.TempTablesManager=M; Q.Execute(); Q.Text="SELECT R FROM T"; Message(Q.Execute().Unload().Count());');self.assertEqual(out,['2'])
    def test_package_join(self):
        _,out=self.run_body('Q=New Query("SELECT Ref AS R INTO T FROM Document.Invoice; SELECT D.Number AS N FROM T INNER JOIN Document.Invoice AS D ON T.R=D.Ref ORDER BY D.Number"); S=Q.Execute().Select(); While S.Next() Do Message(S.N); EndDo;');self.assertEqual(out,['A','B'])
    def test_union(self):
        _,out=self.run_body('Q=New Query("SELECT Number AS N FROM Document.Invoice UNION ALL SELECT Number AS N FROM Document.Invoice"); Message(Q.Execute().Unload().Count());');self.assertEqual(out,['4'])
    def test_derived(self):
        _,out=self.run_body('Q=New Query("SELECT T.N FROM (SELECT Number AS N FROM Document.Invoice) AS T"); Message(Q.Execute().Unload().Count());');self.assertEqual(out,['2'])
    def test_mixed_catalog_document(self):
        _,out=self.run_body('Q=New Query("SELECT D.Number AS N, C.Code AS C FROM Document.Invoice AS D INNER JOIN Catalog.Items AS C ON D.DeletionMark=C.DeletionMark"); Message(Q.Execute().Unload().Count());');self.assertEqual(out,['2'])
    def test_batch_snapshot_once(self):
        calls=[];original=SourceDocumentStore.read_documents
        def read(store,name,identity=None):calls.append(name);return original(store,name,identity)
        with patch.object(SourceDocumentStore,'read_documents',read):self.run_body('Q=New Query("SELECT Ref FROM Document.Invoice; SELECT Ref FROM Document.Invoice"); Q.ExecuteBatch();')
        self.assertEqual(calls,['Invoice'])
    def test_package_failure_atomic(self):
        _,out=self.run_body('M=New TempTablesManager; Q=New Query("SELECT Ref AS R INTO T FROM Document.Invoice"); Q.TempTablesManager=M; Q.Execute(); Q.Text="DESTROY T; SELECT Missing FROM Document.Invoice"; Try Q.Execute(); Except EndTry; Q.Text="SELECT R FROM T"; Message(Q.Execute().Unload().Count());');self.assertEqual(out,['2'])
    def test_no_posting_source(self):
        with self.assertRaises(BSLError):self.run_body('Q=New Query("SELECT Ref FROM Document.Invoice.Lines"); Q.Execute();')
    def test_safe(self):
        with self.assertRaises(BSLError):self.run_body('Q=New Query("SELECT Ref FROM Document.Invoice"); SetSafeMode(True); Q.Execute();')
    def test_no_document_v4(self):
        from yadinassi.configuration_source_runtime import SourceApplication
        app=SourceApplication(support.package('Q=New Query("SELECT Ref FROM Document.Invoice"); Q.Execute();'),scratch_database=self.path,source_catalog_records=True);self.addCleanup(app.close)
        with self.assertRaises(BSLError):app.start()
    def test_explicit_transaction(self):
        _,out=self.run_body('BeginTransaction(); D=Documents.Invoice.CreateDocument(); D.Number="C"; D.Date=Date(2026,1,3); D.Write(); Q=New Query("SELECT COUNT(*) AS N FROM Document.Invoice"); S=Q.Execute().Select(); S.Next(); Message(S.N); RollbackTransaction(); S=Q.Execute().Select(); S.Next(); Message(S.N);');self.assertEqual(out,['3','2'])
    def test_empty_typed_report(self):
        _,out=self.run_body('Q=New Query("SELECT Ref AS R FROM Document.Invoice WHERE Number=""absent"""); T=Q.Execute().Unload(); Q.Text="SELECT R FROM &Input"; Q.SetParameter("Input",T); Message(Q.Execute().Unload().Count());');self.assertEqual(out,['0'])
    def test_destroy(self):
        _,out=self.run_body('Q=New Query("SELECT Ref INTO T FROM Document.Invoice; DESTROY T; SELECT Number FROM Document.Invoice"); Message(Q.ExecuteBatch().Count());');self.assertEqual(out,['3'])
    def test_ref_getobject(self):
        _,out=self.run_body('Q=New Query("SELECT Ref AS R FROM Document.Invoice ORDER BY Number"); S=Q.Execute().Select(); S.Next(); O=S.R.GetObject(); Message(O.Number);');self.assertEqual(out,['A'])
    def test_same_name_catalog_document_do_not_collide(self):
        from yadinassi.configuration_source import import_source
        from yadinassi.configuration_source_runtime import SourceApplication
        source=support.package();files={f.path:f.content for f in source.files}
        files['Catalogs/Invoice.xml']=files.pop('Catalogs/Items.xml').replace(b'<Name>Items</Name>',b'<Name>Invoice</Name>')
        body='O=Catalogs.Invoice.CreateItem(); O.Code="C"; O.Write(); D=Documents.Invoice.CreateDocument(); D.Number="D"; D.Date=Date(2026,1,1); D.Write(); Q=New Query("SELECT C.Code AS C, D.Number AS N FROM Catalog.Invoice AS C INNER JOIN Document.Invoice AS D ON C.DeletionMark=D.DeletionMark"); S=Q.Execute().Select(); S.Next(); Message(S.C); Message(S.N);'
        files['Ext/SessionModule.bsl']=('Procedure SessionParametersSetting(Names) '+body+' EndProcedure').encode()
        out=[];app=SourceApplication(import_source(files),scratch_database=self.path,source_document_records=True,output=out.append);self.addCleanup(app.close);app.start();self.assertEqual(out,['C','D'])
    def test_binding_exact_owner_and_callbacks(self):
        from dataclasses import replace
        from uuid import uuid4
        from yadinassi.source_query_references import make_binding
        from yadinassi.configuration_source_runtime import SourceApplication
        app,_=self.run_body(''); other=SourceApplication(support.package()); self.addCleanup(other.close)
        binding=make_binding(app,app.interpreter._catalogs,'Invoice','Document')
        ref=app.references.ref('Document','Invoice',uuid4())
        self.assertIs(binding.value(ref),ref)
        with self.assertRaises(TypeError):binding.value(other.references.ref('Document','Invoice',ref.reference_uuid))
        with self.assertRaises(TypeError):binding.value(replace(ref,read_member=lambda *a:'fake'))
        with self.assertRaises(TypeError):binding.require_context(other.interpreter._catalogs,None)
        app.close()
        with self.assertRaises(ValueError):binding.value(ref)
    def test_final_owner_failure_leaves_temp_tables_unpublished(self):
        from yadinassi.source_query_references import SourcePackageScope
        from yadinassi.source_constant_queries import SourceConstantQuery
        from yadinassi.query_packages import BSLTempTablesManager
        app,_=self.run_body(''); query=SourceConstantQuery(app.interpreter,app,'SELECT Ref INTO T FROM Document.Invoice')
        manager=BSLTempTablesManager(); query._temp_tables_manager=manager
        app.interpreter._context_stack.append('server');self.addCleanup(app.interpreter._context_stack.pop)
        original=SourcePackageScope.require_context;calls=[]
        def guard(scope,statements,catalogs):
            calls.append(1)
            if len(calls)==3:raise ValueError('final ownership failure')
            return original(scope,statements,catalogs)
        with patch.object(SourcePackageScope,'require_context',guard):
            with self.assertRaisesRegex(ValueError,'final ownership'):query.read(app.interpreter)
        self.assertEqual(manager._tables,{})
        self.assertFalse(app.constant_store.transaction_active)
