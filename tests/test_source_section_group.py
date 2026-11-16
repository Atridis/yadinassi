"""Complete-schema bounded source grouping, not native section parity."""
import unittest
from unittest.mock import patch
import test_source_document_sections as fixture
import test_source_catalog_definitions as catalog
from yadinassi.configuration_source_runtime import SourceApplication
from yadinassi.errors import BSLError

ROWS='R=D.Lines.Add();R.Flag=True;S=D.Lines.Add();S.Flag=False;T=D.Lines.Add();T.Flag=True;'
class SourceSectionGroupTests(unittest.TestCase):
    setUp=fixture.SourceDocumentSectionTests.setUp
    run_body=fixture.SourceDocumentSectionTests.run_body
    def test_deduplicate(self):
        _,out=self.run_body(ROWS+'D.Lines.GroupBy("Flag");Message(D.Lines.Count());Message(D.Lines.Get(0).Flag);Message(D.Lines.Get(1).Flag);')
        self.assertEqual(out,['2','Да','Нет'])
    def test_russian_and_case(self):
        _,out=self.run_body(ROWS+'D.Lines.Свернуть("fLaG","");Message(D.Lines.Count());');self.assertEqual(out,['2'])
    def test_empty(self):
        _,out=self.run_body('D.Lines.GroupBy("Flag");Message(D.Lines.Count());');self.assertEqual(out,['0'])
    def test_old_handles_invalidated(self):
        _,out=self.run_body(ROWS+'D.Lines.GroupBy("Flag");Try Message(R.Flag);Except Message("old");EndTry;');self.assertEqual(out,['old'])
    def test_iteration_invalidated(self):
        with self.assertRaises(BSLError):self.run_body(ROWS+'For Each X In D.Lines Do D.Lines.GroupBy("Flag");EndDo;')
    def test_unassigned_atomic(self):
        _,out=self.run_body(ROWS+'D.Lines.Add();Try D.Lines.GroupBy("Flag");Except Message("bad");EndTry;Message(R.Flag);Message(D.Lines.Count());');self.assertEqual(out,['bad','Да','4'])
    def test_rejected_schema_atomic(self):
        for i,args in enumerate(('""','"Flag","Flag"','"Missing"','"Flag,Flag"','" Flag"','1','"Flag",1','"Flag","",""')):
            self.path=self.path.with_name(str(i)+'.sqlite')
            _,out=self.run_body(ROWS+'Try D.Lines.GroupBy('+args+');Except Message("bad");EndTry;Message(R.Flag);');self.assertEqual(out,['bad','Да'])
    def test_boolean_not_total(self):
        with self.assertRaises(BSLError):self.run_body(ROWS+'D.Lines.GroupBy("","Flag");')
    def test_no_persistence(self):
        app,_=self.run_body(ROWS+'D.Write();D.Lines.GroupBy("Flag");')
        rid=app.constant_store.read_documents('Invoice')[0][0]
        self.assertEqual(len(app.constant_store.read_document_bundle('Invoice',rid)[3]['lines']),3)
    def test_persistence_explicit(self):
        _,out=self.run_body(ROWS+'D.Lines.GroupBy("Flag");D.Write();D.Read();Message(D.Lines.Count());');self.assertEqual(out,['2'])
    def test_safe_mode(self):
        with self.assertRaises(BSLError):self.run_body(ROWS+'SetSafeMode(True);D.Lines.GroupBy("Flag");')
    def test_detached_section(self):
        _,out=self.run_body(ROWS+'D.Write();Old=D.Lines;D.Read();Try Old.GroupBy("Flag");Except Message("old");EndTry;');self.assertEqual(out,['old'])
    def numeric(self,body,digits=20):
        typ=f'<v8:Type>xs:decimal</v8:Type><v8:NumberQualifiers><v8:Digits>{digits}</v8:Digits><v8:FractionDigits>2</v8:FractionDigits><v8:AllowedSign>Any</v8:AllowedSign></v8:NumberQualifiers>'
        children=fixture.SECTION.replace('</ChildObjects></TabularSection>',catalog.attribute('Amount',typ)+'</ChildObjects></TabularSection>')
        out=[];app=SourceApplication(fixture.package(fixture.CREATE+body,children=children),scratch_database=self.path,source_document_sections=True,output=out.append);self.addCleanup(app.close);app.start();return out
    def test_numeric_total(self):
        self.assertEqual(self.numeric('R=D.Lines.Add();R.Flag=True;R.Amount=0.1;S=D.Lines.Add();S.Flag=True;S.Amount=0.2;D.Lines.GroupBy("Flag","Amount");Message(D.Lines.Count());Message(D.Lines.Get(0).Amount);'),['1','0,3'])
    def test_missing_column_rejected(self):
        with self.assertRaises(BSLError):self.numeric('D.Lines.GroupBy("Flag");')
    def test_load_failure_atomic(self):
        with patch('yadinassi.source_section_tables.load',side_effect=ValueError('budget')):
            _,out=self.run_body(ROWS+'Try D.Lines.GroupBy("Flag");Except Message("bad");EndTry;Message(R.Flag);Message(D.Lines.Count());')
        self.assertEqual(out,['bad','Да','3'])
