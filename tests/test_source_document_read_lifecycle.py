"""Bounded source OnRead: loaded state, instance lifetime and atomic failures."""
import unittest
import test_source_document_object_modules as fixture

CREATE=fixture.CREATE+'D.Write();'
class SourceDocumentReadLifecycleTests(unittest.TestCase):
    setUp=fixture.SourceDocumentModuleTests.setUp
    run_body=fixture.SourceDocumentModuleTests.run_body
    def test_loaded_fields_before_event_and_no_automatic_save(self):
        module='Procedure OnRead() Message(Number);Number="MEM";EndProcedure'
        app,out=self.run_body(module,CREATE+'O=D.Ref.GetObject();Message(O.Number);')
        self.assertEqual(out,['A','MEM']);self.assertEqual(app.constant_store.read_documents('Invoice')[0][2]['number'],'A')
    def test_russian_event_and_read_existing_instance(self):
        module='Перем Счетчик Экспорт;Счетчик=0;Процедура ПриЧтении() Счетчик=Счетчик+1;КонецПроцедуры'
        _,out=self.run_body(module,CREATE+'D.Read();D.Read();Message(D.Счетчик);O=D.Ref.GetObject();Message(O.Счетчик);')
        self.assertEqual(out,['2','1'])
    def test_create_and_lookup_do_not_fire(self):
        _,out=self.run_body('Procedure OnRead() Raise "unexpected";EndProcedure',CREATE+'Message(Documents.Invoice.FindByNumber("A")=D.Ref);')
        self.assertEqual(out,['Да'])
    def test_selection_object_fires(self):
        _,out=self.run_body('Procedure OnRead() Message("read");EndProcedure',CREATE+'S=Documents.Invoice.Select();S.Next();O=S.GetObject();')
        self.assertEqual(out,['read'])
    def test_loaded_sections_and_memory_edits(self):
        module='Procedure OnRead() Message(Lines.Count());Lines.Get(0).Flag=False;EndProcedure'
        app,out=self.run_body(module,fixture.CREATE+'R=D.Lines.Add();R.Flag=True;D.Write();O=D.Ref.GetObject();Message(O.Lines.Get(0).Flag);',sections=True)
        self.assertEqual(out,['1','Нет']);store=app.constant_store;rid=store.read_documents('Invoice')[0][0]
        self.assertTrue(store.read_document_bundle('Invoice',rid)[3]['lines'][0]['flag'])
    def test_recursive_read_refused_and_existing_object_closed(self):
        module='Procedure OnRead() Read();EndProcedure'
        app,out=self.run_body(module,CREATE+'Try D.Read();Except Message("recursive");EndTry;Try Message(D.Number);Except Message("closed");EndTry;')
        self.assertEqual(out,['recursive','closed']);self.assertFalse(app.constant_store.transaction_active)
    def test_recursive_getobject_refused(self):
        _,out=self.run_body('Procedure OnRead() O=Ref.GetObject();EndProcedure',CREATE+'Try O=D.Ref.GetObject();Except Message("recursive");EndTry;')
        self.assertEqual(out,['recursive'])
    def test_write_inside_read_refused(self):
        app,out=self.run_body('Procedure OnRead() Number="B";Write();EndProcedure',CREATE+'Try O=D.Ref.GetObject();Except Message("write refused");EndTry;')
        self.assertEqual(out,['write refused']);self.assertEqual(app.constant_store.read_documents('Invoice')[0][2]['number'],'A')
    def test_explicit_transaction_success_remains_open(self):
        _,out=self.run_body('Procedure OnRead() EndProcedure',CREATE+'BeginTransaction();O=D.Ref.GetObject();Message(TransactionActive());RollbackTransaction();')
        self.assertEqual(out,['Да'])
    def test_explicit_transaction_failure_rolls_back(self):
        app,out=self.run_body('Procedure OnRead() Raise "fail";EndProcedure','BeginTransaction();'+CREATE+'Try O=D.Ref.GetObject();Except Message("failed");EndTry;Message(TransactionActive());')
        self.assertEqual(out,['failed','Нет']);self.assertEqual(app.constant_store.read_documents('Invoice'),[])
    def test_handler_cannot_end_owned_transaction(self):
        _,out=self.run_body('Procedure OnRead() RollbackTransaction();EndProcedure',CREATE+'Try O=D.Ref.GetObject();Except Message("denied");EndTry;')
        self.assertEqual(out,['denied'])
    def test_other_write_event_still_blocked(self):
        module='Procedure OnRead() EndProcedure Procedure BeforeWrite(Cancel,Mode,PostingMode) EndProcedure'
        app,out=self.run_body(module,fixture.CREATE+'Try D.Write();Except Message("unsupported");EndTry;')
        self.assertEqual(out,['unsupported']);self.assertEqual(app.constant_store.read_documents('Invoice'),[])
    def test_handler_catalog_side_effect_rolls_back_on_failure(self):
        module='Procedure OnRead() C=Catalogs.Items.CreateItem();C.Code="C";C.Write();Raise "fail";EndProcedure'
        app,out=self.run_body(module,CREATE+'Try O=D.Ref.GetObject();Except Message("failed");EndTry;')
        self.assertEqual(out,['failed']);self.assertEqual(app.constant_store.read_records('Items'),[])
    def test_handler_catalog_write_participates_in_owner_transaction(self):
        module='Procedure OnRead() C=Catalogs.Items.CreateItem();C.Code="C";C.Write();EndProcedure'
        app,_=self.run_body(module,CREATE+'BeginTransaction();O=D.Ref.GetObject();RollbackTransaction();')
        self.assertEqual(app.constant_store.read_records('Items'),[])
    def test_failed_section_read_invalidates_handles(self):
        module='Procedure OnRead() Lines.Get(0).Flag=False;Raise "fail";EndProcedure'
        app,out=self.run_body(module,fixture.CREATE+'R=D.Lines.Add();R.Flag=True;D.Write();Old=D.Lines;Try D.Read();Except EndTry;Try Old.Count();Except Message("detached");EndTry;',sections=True)
        self.assertEqual(out,['detached']);rid=app.constant_store.read_documents('Invoice')[0][0]
        self.assertTrue(app.constant_store.read_document_bundle('Invoice',rid)[3]['lines'][0]['flag'])
    def test_nested_distinct_documents_share_transaction(self):
        module='Procedure OnRead() Message(Number);If Number="A" Then O=Documents.Invoice.FindByNumber("B").GetObject();EndIf;EndProcedure'
        _,out=self.run_body(module,CREATE+'B=Documents.Invoice.CreateDocument();B.Number="B";B.Date=Date(2026,1,1);B.Write();O=D.Ref.GetObject();Message(TransactionActive());')
        self.assertEqual(out,['A','B','Нет'])
    def test_reopen_preserves_event_marker_without_migration(self):
        from yadinassi.configuration_source_runtime import SourceApplication
        module='Procedure OnRead() Message("read");EndProcedure'
        body='If Documents.Invoice.FindByNumber("A").IsEmpty() Then '+CREATE+' EndIf;O=Documents.Invoice.FindByNumber("A").GetObject();'
        app,_=self.run_body(module,body);app.close();out=[]
        reopened=SourceApplication(fixture.package(module,body),existing_scratch_database=self.path,source_document_records=True,output=out.append);self.addCleanup(reopened.close)
        reopened.start();self.assertEqual(out,['read'])
    def test_swallowed_sibling_failure_cannot_restart_transaction(self):
        module='Procedure OnRead() C=Catalogs.Items.CreateItem();C.Code="X";C.Write();Try C=Catalogs.Items.CreateItem();C.Code="X";C.Write();Except EndTry;C=Catalogs.Items.CreateItem();C.Code="LEAK";C.Write();EndProcedure'
        app,out=self.run_body(module,CREATE+'Try O=D.Ref.GetObject();Except Message("failed");EndTry;')
        self.assertEqual(out,['failed']);self.assertEqual(app.constant_store.read_records('Items'),[])
    def test_swallowed_failure_cannot_begin_new_transaction(self):
        module='Procedure OnRead() C=Catalogs.Items.CreateItem();C.Code="X";C.Write();Try C=Catalogs.Items.CreateItem();C.Code="X";C.Write();Except EndTry;BeginTransaction();EndProcedure'
        app,out=self.run_body(module,CREATE+'Try O=D.Ref.GetObject();Except Message("failed");EndTry;')
        self.assertEqual(out,['failed']);self.assertFalse(app.constant_store.transaction_active)
