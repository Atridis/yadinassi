"""Real section records flatten inside one authorized source snapshot."""
import unittest
from unittest.mock import patch
import test_source_document_sections as support
from yadinassi.configuration_source_runtime import SourceApplication
from yadinassi.source_document_section_store import SourceDocumentSectionStore
from yadinassi.errors import BSLError
SEED=support.CREATE+'R=D.Lines.Add(); R.Flag=True; R=D.Lines.Add(); R.Flag=False; D.Write(); '
class SourceDocumentSectionQueryTests(unittest.TestCase):
    setUp=support.SourceDocumentSectionTests.setUp
    def run_body(self,body,children=support.SECTION):
        out=[];app=SourceApplication(support.package(SEED+body,children=children),scratch_database=self.path,source_document_sections=True,output=out.append);self.addCleanup(app.close);app.start();return app,out
    def test_rows(self):
        _,out=self.run_body('Q=New Query("SELECT LineNumber AS N, Flag FROM Document.Invoice.Lines ORDER BY LineNumber"); S=Q.Execute().Select(); While S.Next() Do Message(S.N); Message(S.Flag); EndDo;');self.assertEqual(out,['1','Да','2','Нет'])
    def test_owner_join(self):
        _,out=self.run_body('Q=New Query("SELECT D.Number AS N, L.Flag FROM Document.Invoice.Lines AS L INNER JOIN Document.Invoice AS D ON L.Ref=D.Ref ORDER BY L.LineNumber"); S=Q.Execute().Select(); S.Next(); Message(S.N);');self.assertEqual(out,['A'])
    def test_typed_owner(self):
        _,out=self.run_body('Q=New Query("SELECT Ref AS R FROM Document.Invoice.Lines"); S=Q.Execute().Select(); S.Next(); Message(S.R.Number);');self.assertEqual(out,['A'])
    def test_unload_requery(self):
        _,out=self.run_body('Q=New Query("SELECT Ref AS R, LineNumber AS N FROM Document.Invoice.Lines"); T=Q.Execute().Unload(); Q.Text="SELECT R FROM &Input ORDER BY N"; Q.SetParameter("Input",T); S=Q.Execute().Select(); S.Next(); Message(S.R.Number);');self.assertEqual(out,['A'])
    def test_packages(self):
        _,out=self.run_body('Q=New Query("SELECT Ref AS R, LineNumber AS N INTO T FROM Document.Invoice.Lines; SELECT R FROM T ORDER BY N"); Message(Q.Execute().Unload().Count());');self.assertEqual(out,['2'])
    def test_temp_reuse(self):
        _,out=self.run_body('M=New TempTablesManager; Q=New Query("SELECT Ref AS R INTO T FROM Document.Invoice.Lines"); Q.TempTablesManager=M; Q.Execute(); Q.Text="SELECT R FROM T"; Message(Q.Execute().Unload().Count());');self.assertEqual(out,['2'])
    def test_union(self):
        _,out=self.run_body('Q=New Query("SELECT LineNumber AS N FROM Document.Invoice.Lines UNION ALL SELECT LineNumber AS N FROM Document.Invoice.Lines"); Message(Q.Execute().Unload().Count());');self.assertEqual(out,['4'])
    def test_derived(self):
        _,out=self.run_body('Q=New Query("SELECT T.N FROM (SELECT LineNumber AS N FROM Document.Invoice.Lines) AS T"); Message(Q.Execute().Unload().Count());');self.assertEqual(out,['2'])
    def test_same_record_read_once(self):
        original=SourceDocumentSectionStore.read_documents;calls=[]
        def read(store,name,identity=None):calls.append((name,store.transaction_active));return original(store,name,identity)
        with patch.object(SourceDocumentSectionStore,'read_documents',read):self.run_body('Q=New Query("SELECT Ref FROM Document.Invoice; SELECT Ref FROM Document.Invoice.Lines"); Q.ExecuteBatch();')
        self.assertEqual(calls,[('Invoice',True)])
    def test_unknown_section(self):
        with self.assertRaises(BSLError):self.run_body('Q=New Query("SELECT Ref FROM Document.Invoice.Missing"); Q.Execute();')
    def test_catalog_section_unsupported(self):
        with self.assertRaises(BSLError):self.run_body('Q=New Query("SELECT Ref FROM Catalog.Items.Lines"); Q.Execute();')
    def test_safe(self):
        with self.assertRaises(BSLError):self.run_body('Q=New Query("SELECT Ref FROM Document.Invoice.Lines"); SetSafeMode(True); Q.Execute();')
    def test_empty_section(self):
        _,out=self.run_body('D.Lines.Clear(); D.Write(); Q=New Query("SELECT Ref FROM Document.Invoice.Lines"); Message(Q.Execute().Unload().Count());');self.assertEqual(out,['0'])
    def test_russian(self):
        _,out=self.run_body('Q=New Query("ВЫБРАТЬ НомерСтроки КАК N ИЗ Документ.Invoice.Lines УПОРЯДОЧИТЬ ПО НомерСтроки"); S=Q.Execute().Select(); S.Next(); Message(S.N);');self.assertEqual(out,['1'])
    def test_transaction_not_committed(self):
        _,out=self.run_body('BeginTransaction(); D.Lines.Clear(); D.Write(); Q=New Query("SELECT COUNT(*) AS N FROM Document.Invoice.Lines"); S=Q.Execute().Select(); S.Next(); Message(S.N); RollbackTransaction(); S=Q.Execute().Select(); S.Next(); Message(S.N);');self.assertEqual(out,['0','2'])
    def test_failed_package_keeps_temp(self):
        _,out=self.run_body('M=New TempTablesManager; Q=New Query("SELECT Ref AS R INTO T FROM Document.Invoice.Lines"); Q.TempTablesManager=M; Q.Execute(); Q.Text="DESTROY T; SELECT Missing FROM Document.Invoice.Lines"; Try Q.Execute(); Except EndTry; Q.Text="SELECT R FROM T"; Message(Q.Execute().Unload().Count());');self.assertEqual(out,['2'])
    def test_low_row_budget_rolls_back_snapshot(self):
        from yadinassi.source_constant_queries import SourceConstantQuery
        app,_=self.run_body('');query=SourceConstantQuery(app.interpreter,app,'SELECT Ref FROM Document.Invoice.Lines')
        app.interpreter._context_stack.append('server');self.addCleanup(app.interpreter._context_stack.pop)
        with patch('yadinassi.source_catalog_queries.MAX_ROWS',1):
            with self.assertRaisesRegex(ValueError,'resource limit'):query.read(app.interpreter)
        self.assertFalse(app.constant_store.transaction_active)
        self.assertEqual(len(app.constant_store.read_document_bundle('Invoice',app.constant_store.read_documents('Invoice')[0][0])[3]['lines']),2)
    def test_low_cell_budget_rolls_back_snapshot(self):
        from yadinassi.source_constant_queries import SourceConstantQuery
        app,_=self.run_body('');query=SourceConstantQuery(app.interpreter,app,'SELECT Ref FROM Document.Invoice.Lines')
        app.interpreter._context_stack.append('server');self.addCleanup(app.interpreter._context_stack.pop)
        with patch('yadinassi.source_catalog_queries.MAX_CELLS',1):
            with self.assertRaisesRegex(ValueError,'resource limit'):query.read(app.interpreter)
        self.assertFalse(app.constant_store.transaction_active)
