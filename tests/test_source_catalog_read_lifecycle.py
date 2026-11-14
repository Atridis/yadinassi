"""Source catalog OnRead with shared record lifecycle poison frontier."""
import unittest
import test_source_catalog_object_modules as fixture
from yadinassi.errors import BSLError

CREATE=fixture.CREATE+'O.Description="saved";O.Write();'
class SourceCatalogReadLifecycleTests(unittest.TestCase):
    setUp=fixture.SourceCatalogModuleTests.setUp
    run_body=fixture.SourceCatalogModuleTests.run_body
    def test_loaded_fields_and_no_auto_save(self):
        app,out=self.run_body('Procedure OnRead() Message(Description);Description="memory";EndProcedure',CREATE+'R=O.Ref.GetObject();Message(R.Description);')
        self.assertEqual(out,['saved','memory']);self.assertEqual(app.constant_store.read_records('Items')[0][2]['description'],'saved')
    def test_russian_event_instance_reuse(self):
        module='Перем Счетчик Экспорт;Счетчик=0;Процедура ПриЧтении() Счетчик=Счетчик+1;КонецПроцедуры'
        _,out=self.run_body(module,CREATE+'O.Read();O.Read();Message(O.Счетчик);R=O.Ref.GetObject();Message(R.Счетчик);')
        self.assertEqual(out,['2','1'])
    def test_create_lookup_query_do_not_fire(self):
        module='Procedure OnRead() Raise "unexpected";EndProcedure'
        _,out=self.run_body(module,CREATE+'Message(Catalogs.Items.FindByCode("A")=O.Ref);Q=New Query("SELECT Code FROM Catalog.Items");Message(Q.Execute().Select().Next());')
        self.assertEqual(out,['Да','Да'])
    def test_selection_getobject(self):
        _,out=self.run_body('Procedure OnRead() Message("read");EndProcedure',CREATE+'S=Catalogs.Items.Select();S.Next();R=S.GetObject();')
        self.assertEqual(out,['read'])
    def test_recursive_read_invalidates_existing_object(self):
        app,out=self.run_body('Procedure OnRead() Read();EndProcedure',CREATE+'Try O.Read();Except Message("failed");EndTry;Try Message(O.Code);Except Message("closed");EndTry;')
        self.assertEqual(out,['failed','closed']);self.assertFalse(app.constant_store.transaction_active)
    def test_recursive_getobject(self):
        _,out=self.run_body('Procedure OnRead() R=Ref.GetObject();EndProcedure',CREATE+'Try R=O.Ref.GetObject();Except Message("failed");EndTry;')
        self.assertEqual(out,['failed'])
    def test_no_write_during_read(self):
        app,out=self.run_body('Procedure OnRead() Description="leak";Write();EndProcedure',CREATE+'Try R=O.Ref.GetObject();Except Message("failed");EndTry;')
        self.assertEqual(out,['failed']);self.assertEqual(app.constant_store.read_records('Items')[0][2]['description'],'saved')
    def test_owner_transaction_success_not_committed(self):
        app,out=self.run_body('Procedure OnRead() EndProcedure','BeginTransaction();'+CREATE+'R=O.Ref.GetObject();Message(TransactionActive());RollbackTransaction();')
        self.assertEqual(out,['Да']);self.assertEqual(app.constant_store.read_records('Items'),[])
    def test_owner_transaction_failure_rolls_back(self):
        app,out=self.run_body('Procedure OnRead() Raise "fail";EndProcedure','BeginTransaction();'+CREATE+'Try R=O.Ref.GetObject();Except Message("failed");EndTry;Message(TransactionActive());')
        self.assertEqual(out,['failed','Нет']);self.assertEqual(app.constant_store.read_records('Items'),[])
    def test_initialization_precedes_loaded_fields(self):
        _,out=self.run_body('Description="init";Procedure OnRead() Message(Description);EndProcedure',CREATE+'R=O.Ref.GetObject();')
        self.assertEqual(out,['saved'])
    def test_invalid_signatures_and_ambiguous_aliases(self):
        for i,module in enumerate(('Procedure OnRead(P) EndProcedure','Function OnRead() Return 1;EndFunction','Procedure OnRead() EndProcedure Procedure ПриЧтении() EndProcedure')):
            self.path=self.path.with_name(str(i)+'.sqlite')
            with self.assertRaises(BSLError):self.run_body(module,fixture.CREATE)
    def test_distinct_nested_catalogs(self):
        module='Procedure OnRead() Message(Code);If Code="A" Then R=Catalogs.Items.FindByCode("B").GetObject();EndIf;EndProcedure'
        _,out=self.run_body(module,CREATE+'B=Catalogs.Items.CreateItem();B.Code="B";B.Write();R=O.Ref.GetObject();')
        self.assertEqual(out,['A','B'])
    def test_swallowed_missing_nested_read_cannot_restart_transaction(self):
        module='Procedure OnRead() Try R=Catalogs.Items.EmptyRef().GetObject();Except EndTry;BeginTransaction();EndProcedure'
        app,out=self.run_body(module,CREATE+'Try R=O.Ref.GetObject();Except Message("failed");EndTry;')
        self.assertEqual(out,['failed']);self.assertFalse(app.constant_store.transaction_active)
    def test_swallowed_missing_read_cannot_continue_query(self):
        module='Procedure OnRead() Try R=Catalogs.Items.EmptyRef().GetObject();Except EndTry;Q=New Query("SELECT Code FROM Catalog.Items");Q.Execute();EndProcedure'
        app,out=self.run_body(module,CREATE+'Try R=O.Ref.GetObject();Except Message("failed");EndTry;')
        self.assertEqual(out,['failed']);self.assertFalse(app.constant_store.transaction_active)
    def test_cross_document_catalog_cycle_refused(self):
        import test_source_document_records as doc
        from yadinassi.configuration_source_runtime import SourceApplication
        catalog='Procedure OnRead() R=Documents.Invoice.FindByNumber("D").GetObject();EndProcedure'
        document='Procedure OnRead() R=Catalogs.Items.FindByCode("A").GetObject();EndProcedure'
        body=CREATE+'D=Documents.Invoice.CreateDocument();D.Number="D";D.Date=Date(2026,1,1);D.Write();Try R=D.Ref.GetObject();Except Message("cycle");EndTry;'
        source=doc.package(body,extra={'Catalogs/Items/Ext/ObjectModule.bsl':catalog.encode(),'Documents/Invoice/Ext/ObjectModule.bsl':document.encode()})
        out=[];app=SourceApplication(source,scratch_database=self.path,source_document_records=True,output=out.append);self.addCleanup(app.close);app.start()
        self.assertEqual(out,['cycle']);self.assertFalse(app.constant_store.transaction_active)
    def test_same_source_reopen(self):
        from yadinassi.configuration_source_runtime import SourceApplication
        module='Procedure OnRead() Message("read");EndProcedure'
        body='If Catalogs.Items.FindByCode("A").IsEmpty() Then '+CREATE+' EndIf;R=Catalogs.Items.FindByCode("A").GetObject();'
        app,_=self.run_body(module,body);app.close();out=[]
        app=SourceApplication(fixture.source(module,body),existing_scratch_database=self.path,source_catalog_records=True,output=out.append);self.addCleanup(app.close);app.start();self.assertEqual(out,['read'])
    def test_constant_side_effect_rollback(self):
        from test_source_constant_store import configuration
        from yadinassi.configuration_source import import_source
        from yadinassi.configuration_source_runtime import SourceApplication
        module='Procedure OnRead() Constants.Flag.Set(True);Raise "failed";EndProcedure'
        body='Constants.Flag.Set(False);'+CREATE+'Try R=O.Ref.GetObject();Except Message("failed");EndTry;'
        files={f.path:f.content for f in fixture.source(module,body).files}
        files.update({f.path:f.content for f in configuration().files if f.path=='Constants/Flag.xml'})
        files['Configuration.xml']=files['Configuration.xml'].replace(b'</Configuration>',b'<ChildObjects><Catalog>Items</Catalog><Constant>Flag</Constant></ChildObjects></Configuration>')
        out=[];app=SourceApplication(import_source(files),scratch_database=self.path,source_catalog_records=True,output=out.append);self.addCleanup(app.close);app.start()
        self.assertEqual(out,['failed']);self.assertIs(app.constant_store.get('Flag'),False)
    def test_previously_rejected_definition_not_silently_added_on_reopen(self):
        from unittest.mock import patch
        from yadinassi.source_catalog_store import SourceCatalogStore
        source=fixture.source('Procedure OnRead() EndProcedure')
        with patch('yadinassi.source_catalog_definitions.catalog_module_program',side_effect=ValueError('old OnRead unsupported')):
            store=SourceCatalogStore.create(self.path,source);store.close()
        before=self.path.read_bytes()
        with self.assertRaises(ValueError):SourceCatalogStore.reopen(self.path,source)
        self.assertEqual(self.path.read_bytes(),before)
