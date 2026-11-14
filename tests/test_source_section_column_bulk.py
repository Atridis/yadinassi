"""Atomic typed source column updates preserve row identity and never auto-save."""
import unittest
from unittest.mock import patch
import test_source_document_sections as fixture
import test_source_record_enums as enums
from yadinassi.configuration_source_runtime import SourceApplication
from yadinassi.errors import BSLError

ROWS='R=D.Lines.Add();R.Flag=True;S=D.Lines.Add();S.Flag=False;'
class SourceSectionColumnBulkTests(unittest.TestCase):
    setUp=fixture.SourceDocumentSectionTests.setUp
    run_body=fixture.SourceDocumentSectionTests.run_body
    def test_unload_column_detached_array(self):
        _,out=self.run_body(ROWS+'A=D.Lines.UnloadColumn("Flag");R.Flag=False;Message(A.Get(0));Message(A.Get(1));')
        self.assertEqual(out,['Да','Нет'])
    def test_load_column_preserves_handles(self):
        _,out=self.run_body(ROWS+'A=New Array;A.Add(False);A.Add(True);D.Lines.LoadColumn(A,"flag");Message(R.Flag);Message(S.Flag);Message(R.LineNumber);')
        self.assertEqual(out,['Нет','Да','1'])
    def test_fill_selected_and_russian_aliases(self):
        _,out=self.run_body(ROWS+'D.Lines.ЗаполнитьЗначения(True,"Flag");A=D.Lines.ВыгрузитьКолонку("Flag");D.Lines.ЗагрузитьКолонку(A,"Flag");Message(R.Flag);Message(S.Flag);')
        self.assertEqual(out,['Да','Да'])
    def test_fill_all_columns(self):
        _,out=self.run_body(ROWS+'D.Lines.FillValues(True);Message(S.Flag);')
        self.assertEqual(out,['Да'])
    def test_late_invalid_value_atomic(self):
        _,out=self.run_body(ROWS+'A=New Array;A.Add(False);A.Add("bad");Try D.Lines.LoadColumn(A,"Flag");Except Message("invalid");EndTry;Message(R.Flag);Message(S.Flag);')
        self.assertEqual(out,['invalid','Да','Нет'])
    def test_wrong_length_atomic(self):
        _,out=self.run_body(ROWS+'A=New Array;A.Add(False);Try D.Lines.LoadColumn(A,"Flag");Except Message("count");EndTry;Message(R.Flag);')
        self.assertEqual(out,['count','Да'])
    def test_invalid_fill_before_mutation(self):
        _,out=self.run_body(ROWS+'Try D.Lines.FillValues(1,"Flag");Except Message("invalid");EndTry;Message(R.Flag);Message(S.Flag);')
        self.assertEqual(out,['invalid','Да','Нет'])
    def test_unknown_duplicate_and_whitespace_columns(self):
        for index,names in enumerate(('Other','Flag,Flag',' Flag')):
            self.path=self.path.with_name(str(index)+'.sqlite')
            _,out=self.run_body(ROWS+'Try D.Lines.FillValues(False,"'+names+'");Except Message("columns");EndTry;Message(R.Flag);')
            self.assertEqual(out,['columns','Да'])
    def test_readonly_line_number_refused(self):
        with self.assertRaises(BSLError):self.run_body(ROWS+'D.Lines.FillValues(1,"LineNumber");')
    def test_unassigned_unload_refused(self):
        with self.assertRaises(BSLError):self.run_body('D.Lines.Add();D.Lines.UnloadColumn("Flag");')
    def test_fill_assigns_uninitialized_slot(self):
        _,out=self.run_body('R=D.Lines.Add();D.Lines.FillValues(True,"Flag");Message(R.Flag);')
        self.assertEqual(out,['Да'])
    def test_no_automatic_persistence(self):
        app,_=self.run_body(ROWS+'D.Write();D.Lines.FillValues(False,"Flag");')
        store=app.constant_store;rid=store.read_documents('Invoice')[0][0]
        self.assertTrue(store.read_document_bundle('Invoice',rid)[3]['lines'][0]['flag'])
    def test_explicit_write(self):
        app,_=self.run_body(ROWS+'D.Lines.FillValues(True,"Flag");D.Write();')
        store=app.constant_store;rid=store.read_documents('Invoice')[0][0]
        self.assertTrue(store.read_document_bundle('Invoice',rid)[3]['lines'][1]['flag'])
    def test_buffer_bound_failure_atomic(self):
        with patch('yadinassi.source_section_tables._MAX_DOCUMENT_BYTES',1):
            _,out=self.run_body(ROWS+'Try D.Lines.FillValues(False,"Flag");Except Message("bound");EndTry;Message(R.Flag);')
        self.assertEqual(out,['bound','Да'])
    def test_mutating_values_does_not_invalidate_iteration(self):
        _,out=self.run_body(ROWS+'For Each X In D.Lines Do D.Lines.FillValues(True,"Flag");EndDo;Message(S.Flag);')
        self.assertEqual(out,['Да'])
    def test_enum_bulk(self):
        body=fixture.CREATE+'R=D.Lines.Add();R.Choice=Enums.State.Active;A=D.Lines.UnloadColumn("Choice");D.Lines.FillValues(Enums.State.Inactive,"Choice");D.Lines.LoadColumn(A,"Choice");Message(R.Choice=Enums.State.Active);'
        out=[];app=SourceApplication(enums.package(body,'section'),scratch_database=self.path,source_document_sections=True,output=out.append);self.addCleanup(app.close);app.start();self.assertEqual(out,['Да'])
    def test_wrong_enum_fill_rejected_preserving_handle(self):
        body=fixture.CREATE+'R=D.Lines.Add();R.Choice=Enums.State.Active;Try D.Lines.FillValues(Enums.Mode.Auto,"Choice");Except Message("wrong enum");EndTry;Message(R.Choice=Enums.State.Active);'
        out=[];app=SourceApplication(enums.package(body,'section'),scratch_database=self.path,source_document_sections=True,output=out.append);self.addCleanup(app.close);app.start();self.assertEqual(out,['wrong enum','Да'])
    def test_zero_rows_still_validates_fill_type(self):
        with self.assertRaises(BSLError):self.run_body('D.Lines.FillValues("wrong","Flag");')
    def test_empty_exact_column_load(self):
        _,out=self.run_body('A=New Array;D.Lines.LoadColumn(A,"Flag");Message(D.Lines.Count());')
        self.assertEqual(out,['0'])
    def test_detached_section_refused(self):
        _,out=self.run_body(ROWS+'D.Write();Old=D.Lines;D.Read();Try Old.FillValues(False,"Flag");Except Message("detached");EndTry;')
        self.assertEqual(out,['detached'])
    def test_mixed_field_fill_is_atomic_before_first_assignment(self):
        import test_source_catalog_definitions as catalog
        typ='<v8:Type>xs:string</v8:Type><v8:StringQualifiers><v8:Length>8</v8:Length><v8:AllowedLength>Variable</v8:AllowedLength></v8:StringQualifiers>'
        children=fixture.SECTION.replace('</ChildObjects></TabularSection>',catalog.attribute('Text',typ)+'</ChildObjects></TabularSection>')
        body=fixture.CREATE+'R=D.Lines.Add();R.Flag=True;R.Text="old";Try D.Lines.FillValues(False);Except Message("mixed");EndTry;Message(R.Flag);Message(R.Text);'
        out=[];app=SourceApplication(fixture.package(body,children=children),scratch_database=self.path,source_document_sections=True,output=out.append);self.addCleanup(app.close);app.start()
        self.assertEqual(out,['mixed','Да','old'])
    def test_aggregate_other_section_budget_is_checked(self):
        # Distinct field identity, not an alias of Lines.Flag.
        import test_source_catalog_definitions as catalog
        children=fixture.SECTION+fixture.SECTION.replace('000000000099','000000000098').replace('<Name>Lines</Name>','<Name>Other</Name>').replace(catalog.attribute('Flag'),catalog.attribute('OtherFlag'))
        body=fixture.CREATE+'R=D.Lines.Add();R.Flag=True;S=D.Other.Add();S.OtherFlag=True;Try D.Lines.FillValues(False);Except Message("aggregate");EndTry;Message(R.Flag);'
        out=[];app=SourceApplication(fixture.package(body,children=children),scratch_database=self.path,source_document_sections=True,output=out.append);self.addCleanup(app.close)
        with patch('yadinassi.source_section_tables._MAX_ROWS',1):app.start()
        self.assertEqual(out,['aggregate','Да'])
