"""Complete typed section transfer, not automatic persistence or native parity."""
import unittest
import test_source_document_sections as fixture
import test_source_record_enums as enums
from yadinassi.configuration_source_runtime import SourceApplication
from yadinassi.errors import BSLError

ROW='R=D.Lines.Add();R.Flag=True;'
class SourceSectionTableTests(unittest.TestCase):
    setUp=fixture.SourceDocumentSectionTests.setUp
    run_body=fixture.SourceDocumentSectionTests.run_body
    def test_unload_is_detached_typed_snapshot(self):
        _,out=self.run_body(ROW+'T=D.Lines.Unload();R.Flag=False;Message(T.Get(0).Flag);Message(T.Columns.Flag.ValueType.ContainsType(Type("Boolean")));')
        self.assertEqual(out,['Да','Да'])
    def test_russian_load_unload(self):
        _,out=self.run_body(ROW+'T=D.Lines.Выгрузить();D.Lines.Очистить();D.Lines.Загрузить(T);Message(D.Lines.Get(0).Flag);')
        self.assertEqual(out,['Да'])
    def test_loaded_buffer_does_not_auto_write(self):
        app,out=self.run_body(ROW+'D.Write();T=D.Lines.Unload();T.Get(0).Flag=False;D.Lines.Load(T);Message(D.Lines.Get(0).Flag);')
        self.assertEqual(out,['Нет']);store=app.constant_store;rid=store.read_documents('Invoice')[0][0]
        self.assertTrue(store.read_document_bundle('Invoice',rid)[3]['lines'][0]['flag'])
    def test_explicit_write_persists_loaded_values(self):
        app,_=self.run_body(ROW+'T=D.Lines.Unload();T.Get(0).Flag=False;D.Lines.Load(T);D.Write();')
        store=app.constant_store;rid=store.read_documents('Invoice')[0][0]
        self.assertFalse(store.read_document_bundle('Invoice',rid)[3]['lines'][0]['flag'])
    def test_replacement_invalidates_only_old_rows(self):
        _,out=self.run_body(ROW+'T=D.Lines.Unload();S=D.Lines;D.Lines.Load(T);Message(S.Count());Try Message(R.Flag);Except Message("detached");EndTry;')
        self.assertEqual(out,['1','detached'])
    def test_bad_value_does_not_mutate_buffer(self):
        _,out=self.run_body(ROW+'T=New ValueTable;T.Columns.Add("Flag");T.Add().Flag="wrong";Try D.Lines.Load(T);Except Message("invalid");EndTry;Message(R.Flag);Message(D.Lines.Count());')
        self.assertEqual(out,['invalid','Да','1'])
    def test_missing_extra_columns_refused(self):
        for index,columns in enumerate(('', 'T.Columns.Add("Other");','T.Columns.Add("Flag");T.Columns.Add("Extra");')):
            self.path=self.path.with_name(str(index)+'.sqlite')
            _,out=self.run_body(ROW+'T=New ValueTable;'+columns+'Try D.Lines.Load(T);Except Message("shape");EndTry;Message(R.Flag);')
            self.assertEqual(out,['shape','Да'])
    def test_unassigned_unload_refused(self):
        with self.assertRaises(BSLError):self.run_body('D.Lines.Add();D.Lines.Unload();')
    def test_empty_table_clears(self):
        _,out=self.run_body(ROW+'T=New ValueTable;T.Columns.Add("Flag");D.Lines.Load(T);Message(D.Lines.Count());')
        self.assertEqual(out,['0'])
    def test_iteration_version_changes_only_on_success(self):
        _,out=self.run_body(ROW+'R2=D.Lines.Add();R2.Flag=False;T=D.Lines.Unload();Try For Each X In D.Lines Do D.Lines.Load(T);EndDo;Except Message("changed");EndTry;')
        self.assertEqual(out,['changed'])
    def test_enum_roundtrip_and_query(self):
        body=fixture.CREATE+'R=D.Lines.Add();R.Choice=Enums.State.Active;T=D.Lines.Unload();D.Lines.Clear();D.Lines.Load(T);Message(D.Lines.Get(0).Choice=Enums.State.Active);Q=New Query("SELECT Choice FROM &T");Q.SetParameter("T",T);Message(Q.Execute().Select().Next());'
        out=[];app=SourceApplication(enums.package(body,'section'),scratch_database=self.path,source_document_sections=True,output=out.append);self.addCleanup(app.close);app.start()
        self.assertEqual(out,['Да','Да'])
    def test_closed_section_after_reread_refused(self):
        _,out=self.run_body(ROW+'D.Write();Old=D.Lines;T=Old.Unload();D.Read();Try Old.Load(T);Except Message("closed");EndTry;')
        self.assertEqual(out,['closed'])
    def test_foreign_empty_enum_table_rejected_without_buffer_change(self):
        from unittest.mock import patch
        from yadinassi import source_section_tables as transfer
        captured=[];original_unload=transfer.unload;original_load=transfer.load
        def capture(caller,section):
            result=original_unload(caller,section);captured.append(result);return result
        first=SourceApplication(enums.package(fixture.CREATE+'D.Lines.Unload();','section'),scratch_database=self.path.with_name('first.sqlite'),source_document_sections=True);self.addCleanup(first.close)
        with patch.object(transfer,'unload',capture):first.start()
        body=fixture.CREATE+'R=D.Lines.Add();R.Choice=Enums.State.Active;T=D.Lines.Unload();Try D.Lines.Load(T);Except Message("foreign");EndTry;Message(R.Choice=Enums.State.Active);'
        out=[];second=SourceApplication(enums.package(body,'section'),scratch_database=self.path,source_document_sections=True,output=out.append);self.addCleanup(second.close)
        with patch.object(transfer,'load',lambda caller,section,table:original_load(caller,section,captured[0])):second.start()
        self.assertEqual(out,['foreign','Да'])
    def test_catalog_reference_transfer(self):
        from yadinassi.configuration_source import import_source
        body='C=Catalogs.Items.CreateItem();C.Code="A";C.Write();'+fixture.CREATE+'R=D.Lines.Add();R.Choice=C.Ref;T=D.Lines.Unload();D.Lines.Clear();D.Lines.Load(T);Message(D.Lines.Get(0).Choice=C.Ref);'
        files={f.path:f.content for f in enums.package(body,'section').files}
        files['Documents/Invoice.xml']=files['Documents/Invoice.xml'].replace(b'cfg:EnumRef.State',b'cfg:CatalogRef.Items')
        out=[];app=SourceApplication(import_source(files),scratch_database=self.path,source_document_sections=True,output=out.append);self.addCleanup(app.close);app.start();self.assertEqual(out,['Да'])
    def test_load_bound_failure_keeps_old_row(self):
        from unittest.mock import patch
        with patch('yadinassi.source_section_tables._MAX_ROWS',1):
            _,out=self.run_body(ROW+'T=New ValueTable;T.Columns.Add("Flag");T.Add().Flag=False;T.Add().Flag=True;Try D.Lines.Load(T);Except Message("bound");EndTry;Message(R.Flag);Message(D.Lines.Count());')
        self.assertEqual(out,['bound','Да','1'])
    def test_nullable_report_value_refused(self):
        _,out=self.run_body(ROW+'T=New ValueTable;T.Columns.Add("Flag");T.Add().Flag=NULL;Try D.Lines.Load(T);Except Message("null");EndTry;Message(R.Flag);')
        self.assertEqual(out,['null','Да'])
    def test_query_result_bulk_load(self):
        _,out=self.run_body(ROW+'D.Write();Q=New Query("SELECT Flag FROM Document.Invoice.Lines");T=Q.Execute().Unload();D.Lines.Clear();D.Lines.Load(T);Message(D.Lines.Count());Message(D.Lines.Get(0).Flag);')
        self.assertEqual(out,['1','Да'])
    def test_load_in_read_event_remains_memory_only(self):
        import test_source_document_object_modules as modules
        module='Procedure OnRead() T=Lines.Unload();T.Get(0).Flag=False;Lines.Load(T);EndProcedure'
        body=fixture.CREATE+ROW+'D.Write();O=D.Ref.GetObject();Message(O.Lines.Get(0).Flag);'
        out=[];app=SourceApplication(modules.package(module,body,True),scratch_database=self.path,source_document_sections=True,output=out.append);self.addCleanup(app.close);app.start()
        self.assertEqual(out,['Нет']);rid=app.constant_store.read_documents('Invoice')[0][0]
        self.assertTrue(app.constant_store.read_document_bundle('Invoice',rid)[3]['lines'][0]['flag'])
