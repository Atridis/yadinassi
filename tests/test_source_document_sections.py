"""v6 section aggregate persistence and owned row lifecycle."""
import unittest
from uuid import uuid4
import test_source_document_records as base
import test_source_catalog_definitions as catalog
from yadinassi.source_document_section_store import SourceDocumentSectionStore
from yadinassi.source_document_store import SourceDocumentStore
from yadinassi.source_document_definitions import source_document_definitions
from yadinassi.configuration_source_runtime import SourceApplication
from yadinassi.errors import BSLError

SECTION='<TabularSection uuid="00000000-0000-0000-0000-000000000099"><Properties><Name>Lines</Name></Properties><ChildObjects>'+catalog.attribute('Flag')+'</ChildObjects></TabularSection>'
def package(body='',children=SECTION,**kwargs):return base.package(body,children=children,**kwargs)
CREATE='D=Documents.Invoice.CreateDocument(); D.Number="A"; D.Date=Date(2026,1,1); '
class SourceDocumentSectionTests(unittest.TestCase):
    setUp=base.SourceDocumentRecordTests.setUp
    values=base.SourceDocumentRecordTests.values
    def store(self,source=None):
        store=SourceDocumentSectionStore.create(self.path,source or package());self.addCleanup(store.close);return store
    def run_body(self,body):
        out=[];app=SourceApplication(package(CREATE+body),scratch_database=self.path,source_document_sections=True,output=out.append);self.addCleanup(app.close);app.start();return app,out
    def test_parser_v5_unchanged(self):
        definitions,errors=source_document_definitions(package());self.assertFalse(definitions);self.assertIn('invoice',errors)
    def test_parser_v6(self):
        definitions,errors=source_document_definitions(package(),allow_sections=True);self.assertFalse(errors);self.assertEqual(definitions['invoice'].sections[0].name,'Lines')
    def test_bundle_reopen(self):
        source=package();s=self.store(source);rid=uuid4();s.write_document_bundle('Invoice',rid,0,self.values(),{'lines':({'flag':True},)});s.close()
        other=SourceDocumentSectionStore.reopen(self.path,source);self.addCleanup(other.close);self.assertEqual(other.read_document_bundle('Invoice',rid)[3],{'lines':({'flag':True},)})
    def test_scalar_write_cannot_drop_sections(self):
        s=self.store()
        with self.assertRaises(ValueError):s.write_document('Invoice',uuid4(),0,self.values())
    def test_missing_field(self):
        s=self.store()
        with self.assertRaises(ValueError):s.write_document_bundle('Invoice',uuid4(),0,self.values(),{'lines':({},)})
        self.assertFalse(s.read_documents('Invoice'))
    def test_failed_bundle_rolls_outer(self):
        s=self.store();s.begin_transaction();s.write_document_bundle('Invoice',uuid4(),0,self.values(),{'lines':()})
        with self.assertRaises(ValueError):s.write_document_bundle('Invoice',uuid4(),0,self.values('B'),{'lines':({},)})
        self.assertFalse(s.transaction_active);self.assertFalse(s.read_documents('Invoice'))
    def test_revision(self):
        s=self.store();rid=uuid4();s.write_document_bundle('Invoice',rid,0,self.values(),{'lines':()});s.write_document_bundle('Invoice',rid,1,self.values(),{'lines':({'flag':False},)})
        with self.assertRaisesRegex(ValueError,'stale'):s.write_document_bundle('Invoice',rid,1,self.values(),{'lines':()})
        self.assertEqual(len(s.read_document_bundle('Invoice',rid)[3]['lines']),1)
    def test_bsl_cycle(self):
        _,out=self.run_body('R=D.Lines.Add(); R.Flag=True; Message(R.LineNumber); D.Write(); O=D.Ref.GetObject(); Message(O.Lines.Count()); Message(O.Lines.Get(0).Flag);');self.assertEqual(out,['1','1','Да'])
    def test_index(self):
        _,out=self.run_body('R=D.Lines.Add(); R.Flag=True; Message(D.Lines[0].Flag);');self.assertEqual(out,['Да'])
    def test_iteration(self):
        _,out=self.run_body('R=D.Lines.Add(); R.Flag=True; For Each L In D.Lines Do Message(L.Flag); EndDo;');self.assertEqual(out,['Да'])
    def test_delete_invalidates(self):
        _,out=self.run_body('R=D.Lines.Add(); R.Flag=True; D.Lines.Delete(R); Try Message(R.Flag); Except Message("detached"); EndTry; Message(D.Lines.Count());');self.assertEqual(out,['detached','0'])
    def test_clear_invalidates(self):
        _,out=self.run_body('R=D.Lines.Add(); R.Flag=True; D.Lines.Clear(); Try Message(R.Flag); Except Message("detached"); EndTry;');self.assertEqual(out,['detached'])
    def test_read_invalidates(self):
        _,out=self.run_body('R=D.Lines.Add(); R.Flag=True; D.Write(); Old=D.Lines; D.Read(); Try Old.Count(); Except Message("detached"); EndTry; Try Message(R.Flag); Except Message("row"); EndTry;');self.assertEqual(out,['detached','row'])
    def test_linenumber_readonly(self):
        with self.assertRaises(BSLError):self.run_body('R=D.Lines.Add(); R.LineNumber=2;')
    def test_missing_explicit(self):
        with self.assertRaises(BSLError):self.run_body('D.Lines.Add(); D.Write();')
    def test_safe_mode(self):
        with self.assertRaises(BSLError):self.run_body('S=D.Lines; SetSafeMode(True); S.Add();')
    def test_reorder_numbers(self):
        _,out=self.run_body('A=D.Lines.Add(); A.Flag=True; B=D.Lines.Add(); B.Flag=False; D.Lines.Delete(0); Message(B.LineNumber);');self.assertEqual(out,['1'])
    def test_iteration_modification(self):
        _,out=self.run_body('A=D.Lines.Add(); A.Flag=True; B=D.Lines.Add(); B.Flag=False; Try For Each R In D.Lines Do D.Lines.Clear(); EndDo; Except Message("changed"); EndTry;');self.assertEqual(out,['changed'])
    def test_empty_bundle(self):
        _,out=self.run_body('D.Write(); O=D.Ref.GetObject(); Message(O.Lines.Count());');self.assertEqual(out,['0'])
    def test_upgrade_copy(self):
        old=self.path.with_name('v5.sqlite');source=package();s=SourceDocumentStore.create(old,source);s.close();before=old.read_bytes()
        SourceDocumentSectionStore.upgrade_copy(old,self.path);self.assertEqual(old.read_bytes(),before)
        s=SourceDocumentSectionStore.reopen(self.path,source);self.addCleanup(s.close);self.assertTrue(s.document('Invoice').sections)
