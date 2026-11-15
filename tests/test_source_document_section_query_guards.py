"""Independent real section snapshot and publication boundaries."""
import unittest
from unittest.mock import patch
import test_source_document_sections as fixture
from yadinassi.configuration_source_runtime import SourceApplication
from yadinassi.source_document_section_store import SourceDocumentSectionStore
from yadinassi.source_constant_queries import SourceConstantQuery
from yadinassi.source_query_references import SourcePackageScope
from yadinassi.query_packages import BSLTempTablesManager

CREATE=fixture.CREATE+'R=D.Lines.Add(); R.Flag=True; D.Write(); '
class SourceDocumentSectionQueryGuardTests(unittest.TestCase):
    setUp=fixture.SourceDocumentSectionTests.setUp
    def app(self,body=''):
        out=[];app=SourceApplication(fixture.package(CREATE+body),scratch_database=self.path,source_document_sections=True,output=out.append);self.addCleanup(app.close);app.start();return app,out
    def test_typed_owner_survives_report_and_requery(self):
        _,out=self.app('Q=New Query("SELECT Ref AS Owner FROM Document.Invoice.Lines"); T=Q.Execute().Unload(); Q.Text="SELECT Owner FROM &Rows"; Q.SetParameter("Rows",T); S=Q.Execute().Select(); S.Next(); Message(S.Owner=D.Ref); Message(S.Owner.GetObject().Number);')
        self.assertEqual(out,['Да','A'])
    def test_explicit_transaction_not_committed(self):
        _,out=self.app('BeginTransaction(); R=D.Lines.Add(); R.Flag=False; D.Write(); Q=New Query("SELECT Flag FROM Document.Invoice.Lines"); Message(Q.Execute().Unload().Count()); Message(TransactionActive()); RollbackTransaction(); Message(Q.Execute().Unload().Count());')
        self.assertEqual(out,['2','Да','1'])
    def test_section_snapshot_is_frozen(self):
        _,out=self.app('Q=New Query("SELECT Flag FROM Document.Invoice.Lines"); T=Q.Execute().Unload(); D.Lines.Clear(); D.Write(); Message(T.Count()); Message(Q.Execute().Unload().Count());')
        self.assertEqual(out,['1','0'])
    def test_failed_final_owner_does_not_publish_sections(self):
        app,_=self.app();q=SourceConstantQuery(app.interpreter,app,'SELECT Ref INTO T FROM Document.Invoice.Lines');manager=BSLTempTablesManager();q._temp_tables_manager=manager
        app.interpreter._context_stack.append('server');self.addCleanup(app.interpreter._context_stack.pop)
        original=SourcePackageScope.require_context;calls=[]
        def guard(scope,statements,catalogs):
            calls.append(1)
            if len(calls)==3:raise ValueError('injected owner failure')
            return original(scope,statements,catalogs)
        with patch.object(SourcePackageScope,'require_context',guard):
            with self.assertRaisesRegex(ValueError,'injected'):q.read(app.interpreter)
        self.assertEqual(manager._tables,{})
        self.assertFalse(app.constant_store.transaction_active)
    def test_owner_and_sections_share_active_transaction(self):
        app,_=self.app();query=SourceConstantQuery(app.interpreter,app,'SELECT L.Flag FROM Document.Invoice.Lines AS L INNER JOIN Document.Invoice AS D ON L.Ref=D.Ref')
        app.interpreter._context_stack.append('server');self.addCleanup(app.interpreter._context_stack.pop)
        original=SourceDocumentSectionStore._sections;states=[]
        def read(store,definition,identity):
            states.append(store.transaction_active)
            return original(store,definition,identity)
        with patch.object(SourceDocumentSectionStore,'_sections',read):query.read(app.interpreter)
        self.assertTrue(states);self.assertTrue(all(states));self.assertFalse(app.constant_store.transaction_active)
