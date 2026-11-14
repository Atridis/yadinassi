import unittest
import test_source_document_sections as fixture
from yadinassi.errors import BSLError

ROWS='R=D.Lines.Add();R.Flag=True;S=D.Lines.Add();S.Flag=False;T=D.Lines.Add();T.Flag=True;'
class SourceSectionSearchTests(unittest.TestCase):
    setUp=fixture.SourceDocumentSectionTests.setUp
    run_body=fixture.SourceDocumentSectionTests.run_body
    def test_find_first_live_handle(self):
        _,out=self.run_body(ROWS+'X=D.Lines.Find(True,"Flag");Message(X=R);X.Flag=False;Message(R.Flag);')
        self.assertEqual(out,['Да','Нет'])
    def test_russian_and_case(self):
        _,out=self.run_body(ROWS+'Message(D.Lines.Найти(False,"fLaG")=S);')
        self.assertEqual(out,['Да'])
    def test_empty_find_returns_undefined(self):
        _,out=self.run_body('Message(D.Lines.Find(True,"Flag")=Undefined);')
        self.assertEqual(out,['Да'])
    def test_findrows_order_and_live_identity(self):
        _,out=self.run_body(ROWS+'A=D.Lines.НайтиСтроки(New Structure("Flag",True));Message(A.Count());Message(A.Get(0)=R);Message(A.Get(1)=T);A.Get(0).Flag=False;Message(R.Flag);')
        self.assertEqual(out,['2','Да','Да','Нет'])
    def test_result_membership_snapshot(self):
        _,out=self.run_body(ROWS+'A=D.Lines.FindRows(New Structure("Flag",True));R.Flag=False;Message(A.Count());Message(A.Get(0)=R);')
        self.assertEqual(out,['2','Да'])
    def test_empty_structure_empty_result(self):
        _,out=self.run_body(ROWS+'Message(D.Lines.FindRows(New Structure).Count());')
        self.assertEqual(out,['0'])
    def test_wrong_type_rejected_even_empty(self):
        with self.assertRaises(BSLError):self.run_body('D.Lines.Find("true","Flag");')
    def test_unknown_field_rejected_even_empty(self):
        with self.assertRaises(BSLError):self.run_body('D.Lines.FindRows(New Structure("Other",True));')
    def test_missing_assignment_not_defaulted(self):
        with self.assertRaises(BSLError):self.run_body('D.Lines.Add();D.Lines.Find(False,"Flag");')
    def test_find_requires_explicit_field(self):
        with self.assertRaises(BSLError):self.run_body(ROWS+'D.Lines.Find(True);')
    def test_filters_exact_structure(self):
        with self.assertRaises(BSLError):self.run_body(ROWS+'D.Lines.FindRows(New Map);')
    def test_deleted_result_handle_denied(self):
        _,out=self.run_body(ROWS+'A=D.Lines.FindRows(New Structure("Flag",True));D.Lines.Delete(R);Try Message(A.Get(0).Flag);Except Message("deleted");EndTry;')
        self.assertEqual(out,['deleted'])
    def test_search_does_not_invalidate_iterator(self):
        _,out=self.run_body(ROWS+'For Each X In D.Lines Do D.Lines.Find(X.Flag,"Flag");EndDo;Message(D.Lines.Count());')
        self.assertEqual(out,['3'])
    def test_enum_search_and_wrong_domain(self):
        import test_source_record_enums as enums
        from yadinassi.configuration_source_runtime import SourceApplication
        body=fixture.CREATE+'R=D.Lines.Add();R.Choice=Enums.State.Active;Message(D.Lines.Find(Enums.State.Active,"Choice")=R);Try D.Lines.Find(Enums.Mode.Auto,"Choice");Except Message("domain");EndTry;'
        out=[];app=SourceApplication(enums.package(body,'section'),scratch_database=self.path,source_document_sections=True,output=out.append);self.addCleanup(app.close);app.start()
        self.assertEqual(out,['Да','domain'])
    def test_search_uses_current_row_order(self):
        _,out=self.run_body(ROWS+'D.Lines.Move(T,-2);Message(D.Lines.Find(True,"Flag")=T);')
        self.assertEqual(out,['Да'])
    def test_old_section_denied(self):
        _,out=self.run_body(ROWS+'D.Write();Old=D.Lines;D.Read();Try Old.Find(True,"Flag");Except Message("old");EndTry;')
        self.assertEqual(out,['old'])
    def test_multifield_and_case_insensitive_filter(self):
        import test_source_catalog_definitions as catalog
        from yadinassi.configuration_source_runtime import SourceApplication
        typ='<v8:Type>xs:string</v8:Type><v8:StringQualifiers><v8:Length>8</v8:Length><v8:AllowedLength>Variable</v8:AllowedLength></v8:StringQualifiers>'
        children=fixture.SECTION.replace('</ChildObjects></TabularSection>',catalog.attribute('Text',typ)+'</ChildObjects></TabularSection>')
        body=fixture.CREATE+'R=D.Lines.Add();R.Flag=True;R.Text="A";S=D.Lines.Add();S.Flag=True;S.Text="B";A=D.Lines.FindRows(New Structure("fLaG,tExT",True,"B"));Message(A.Count());Message(A.Get(0)=S);'
        out=[];app=SourceApplication(fixture.package(body,children=children),scratch_database=self.path,source_document_sections=True,output=out.append);self.addCleanup(app.close);app.start()
        self.assertEqual(out,['1','Да'])
    def test_no_match_returns_undefined(self):
        _,out=self.run_body('R=D.Lines.Add();R.Flag=True;Message(D.Lines.Find(False,"Flag")=Undefined);')
        self.assertEqual(out,['Да'])
