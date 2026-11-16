import unittest
from decimal import localcontext
import test_source_document_sections as fixture
import test_source_catalog_definitions as catalog
from yadinassi.configuration_source_runtime import SourceApplication
from yadinassi.errors import BSLError
ROWS='R=D.Lines.Add();R.Flag=True;S=D.Lines.Add();S.Flag=False;'
class SourceSectionOrderTotalTests(unittest.TestCase):
    setUp=fixture.SourceDocumentSectionTests.setUp
    run_body=fixture.SourceDocumentSectionTests.run_body
    def test_sort_preserves_handle_and_updates_line(self):
        _,out=self.run_body(ROWS+'D.Lines.Sort("Flag ASC");Message(D.Lines.Get(0)=S);Message(R.LineNumber);Message(R.Flag);')
        self.assertEqual(out,['Да','2','Да'])
    def test_sort_russian_desc(self):
        _,out=self.run_body(ROWS+'D.Lines.Сортировать("Flag Убыв");Message(D.Lines.Get(0)=R);')
        self.assertEqual(out,['Да'])
    def test_bad_direction_atomic(self):
        _,out=self.run_body(ROWS+'Try D.Lines.Sort("Flag unknown");Except Message("bad");EndTry;Message(R.LineNumber);')
        self.assertEqual(out,['bad','1'])
    def test_duplicate_refused(self):
        with self.assertRaises(BSLError):self.run_body(ROWS+'D.Lines.Sort("Flag,Flag");')
    def test_unknown_even_empty(self):
        with self.assertRaises(BSLError):self.run_body('D.Lines.Sort("Unknown");')
    def test_missing_assignment_atomic(self):
        _,out=self.run_body(ROWS+'D.Lines.Add();Try D.Lines.Sort("Flag");Except Message("missing");EndTry;Message(R.LineNumber);')
        self.assertEqual(out,['missing','1'])
    def test_sort_no_implicit_write(self):
        app,_=self.run_body(ROWS+'D.Write();D.Lines.Sort("Flag");')
        store=app.constant_store;rid=store.read_documents('Invoice')[0][0]
        self.assertTrue(store.read_document_bundle('Invoice',rid)[3]['lines'][0]['flag'])
    def test_noop_sort_keeps_iterator(self):
        _,out=self.run_body(ROWS+'For Each X In D.Lines Do D.Lines.Sort("Flag DESC");EndDo;Message(R.LineNumber);')
        self.assertEqual(out,['1'])
    def test_reorder_invalidates_iterator(self):
        with self.assertRaises(BSLError):self.run_body(ROWS+'For Each X In D.Lines Do D.Lines.Sort("Flag");EndDo;')
    def numeric(self,body):
        typ='<v8:Type>xs:decimal</v8:Type><v8:NumberQualifiers><v8:Digits>30</v8:Digits><v8:FractionDigits>6</v8:FractionDigits><v8:AllowedSign>Any</v8:AllowedSign></v8:NumberQualifiers>'
        children=fixture.SECTION.replace(catalog.attribute('Flag'),catalog.attribute('Amount',typ))
        out=[];app=SourceApplication(fixture.package(fixture.CREATE+body,children=children),scratch_database=self.path,source_document_sections=True,output=out.append);self.addCleanup(app.close);app.start();return out
    def test_exact_total(self):
        self.assertEqual(self.numeric('R=D.Lines.Add();R.Amount=0.1;S=D.Lines.Add();S.Amount=0.2;Message(D.Lines.Total("Amount"));'),['0,3'])
    def test_empty_total(self):self.assertEqual(self.numeric('Message(D.Lines.Итог("Amount"));'),['0'])
    def test_boolean_total_not_coerced(self):
        with self.assertRaises(BSLError):self.run_body('D.Lines.Total("Flag");')
    def test_unassigned_total_refused(self):
        with self.assertRaises(BSLError):self.numeric('D.Lines.Add();D.Lines.Total("Amount");')
    def test_total_does_not_invalidate_iterator(self):
        self.assertEqual(self.numeric('R=D.Lines.Add();R.Amount=3;For Each X In D.Lines Do Message(D.Lines.Total("Amount"));EndDo;'),['3'])
    def test_total_ignores_ambient_precision(self):
        with localcontext() as ctx:
            ctx.prec=2
            self.assertEqual(self.numeric('R=D.Lines.Add();R.Amount=9999.01;S=D.Lines.Add();S.Amount=0.02;Message(D.Lines.Total("Amount"));'),['9\u00a0999,03'])
    def test_numeric_sort(self):
        self.assertEqual(self.numeric('R=D.Lines.Add();R.Amount=10;S=D.Lines.Add();S.Amount=-2;D.Lines.Sort("Amount");Message(R.LineNumber);Message(S.LineNumber);'),['2','1'])
    def test_old_section_sort_denied(self):
        _,out=self.run_body(ROWS+'D.Write();Old=D.Lines;D.Read();Try Old.Sort("Flag");Except Message("old");EndTry;')
        self.assertEqual(out,['old'])
    def test_datetime_sort(self):
        typ='<v8:Type>xs:dateTime</v8:Type><v8:DateQualifiers><v8:DateFractions>DateTime</v8:DateFractions></v8:DateQualifiers>'
        children=fixture.SECTION.replace(catalog.attribute('Flag'),catalog.attribute('When',typ))
        body=fixture.CREATE+'R=D.Lines.Add();R.When=Date(2026,1,2);S=D.Lines.Add();S.When=Date(2026,1,1);D.Lines.Sort("When");Message(S.LineNumber);'
        out=[];app=SourceApplication(fixture.package(body,children=children),scratch_database=self.path,source_document_sections=True,output=out.append);self.addCleanup(app.close);app.start();self.assertEqual(out,['1'])
    def test_multifield_sort_and_string_error_atomic(self):
        typ='<v8:Type>xs:string</v8:Type><v8:StringQualifiers><v8:Length>20</v8:Length><v8:AllowedLength>Variable</v8:AllowedLength></v8:StringQualifiers>'
        children=fixture.SECTION.replace('</ChildObjects></TabularSection>',catalog.attribute('Text',typ)+'</ChildObjects></TabularSection>')
        body=fixture.CREATE+'R=D.Lines.Add();R.Flag=True;R.Text="Б";S=D.Lines.Add();S.Flag=True;S.Text="А";D.Lines.Sort("Flag DESC,Text ASC");Message(S.LineNumber);S.Text="漢";Try D.Lines.Sort("Text");Except Message("collation");EndTry;Message(S.LineNumber);'
        out=[];app=SourceApplication(fixture.package(body,children=children),scratch_database=self.path,source_document_sections=True,output=out.append);self.addCleanup(app.close);app.start();self.assertEqual(out,['1','collation','1'])
