"""Local source Catalog ObjectModule lifecycle, not native parity evidence."""
import tempfile
import unittest
from pathlib import Path
from uuid import uuid4
from test_source_catalog_records import package
from yadinassi.configuration_source import import_source
from yadinassi.configuration_source_runtime import SourceApplication
from yadinassi.source_catalog_store import SourceCatalogStore
from yadinassi.errors import BSLError

CREATE='O=Catalogs.Items.CreateItem(); O.Code="A"; '

def source(module,body=''):
    return package(body,extra={'Catalogs/Items/Ext/ObjectModule.bsl':module.encode()})

class SourceCatalogModuleTests(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory();self.addCleanup(tmp.cleanup);self.path=Path(tmp.name)/'objects.sqlite'
    def run_body(self,module,body):
        out=[];app=SourceApplication(source(module,body),scratch_database=self.path,source_catalog_records=True,output=out.append);self.addCleanup(app.close);app.start();return app,out
    def test_beforewrite_persists_fields(self):
        _,out=self.run_body('Procedure BeforeWrite(Cancel) Description="before"; EndProcedure',CREATE+'O.Write(); Message(O.Ref.GetObject().Description);')
        self.assertEqual(out,['before'])
    def test_onwrite_after_record(self):
        _,out=self.run_body('Procedure OnWrite(Cancel) Message(ThisObject.Ref.GetObject().Code); EndProcedure',CREATE+'O.Write();')
        self.assertEqual(out,['A'])
    def test_onwrite_buffer_changes_not_persisted(self):
        _,out=self.run_body('Procedure OnWrite(Cancel) Description="buffer"; EndProcedure',CREATE+'O.Description="persisted"; O.Write(); Message(O.Description); Message(O.Ref.GetObject().Description);')
        self.assertEqual(out,['buffer','persisted'])
    def test_before_cancel_restores_new(self):
        app,out=self.run_body('Procedure BeforeWrite(Cancel) Cancel=True; EndProcedure',CREATE+'Try O.Write(); Except Message(O.IsNew()); EndTry;')
        self.assertEqual(out,['Да']);self.assertEqual(app.constant_store.read_records('Items'),[])
    def test_onwrite_cancel_rolls_record(self):
        app,out=self.run_body('Procedure OnWrite(Cancel) Cancel=True; EndProcedure',CREATE+'Try O.Write(); Except Message(O.IsNew()); EndTry;')
        self.assertEqual(out,['Да']);self.assertEqual(app.constant_store.read_records('Items'),[])
    def test_onwrite_exception_rolls_record(self):
        app,_=self.run_body('Procedure OnWrite(Cancel) Raise "fail"; EndProcedure',CREATE+'Try O.Write(); Except EndTry;')
        self.assertEqual(app.constant_store.read_records('Items'),[])
    def test_cancel_exact_boolean(self):
        app,_=self.run_body('Procedure BeforeWrite(Cancel) Cancel=1; EndProcedure',CREATE+'Try O.Write(); Except EndTry;')
        self.assertEqual(app.constant_store.read_records('Items'),[])
    def test_initializer_fields(self):
        _,out=self.run_body('Description="initialized";',CREATE+'Message(O.Description); O.Write();')
        self.assertEqual(out,['initialized'])
    def test_initializer_loaded_values_win(self):
        _,out=self.run_body('Description="initialized";',CREATE+'O.Description="saved"; O.Write(); Message(O.Ref.GetObject().Description);')
        self.assertEqual(out,['saved'])
    def test_exported_routine_and_modulevar(self):
        _,out=self.run_body('Var Counter Export; Procedure Change() Export Counter=Counter+1; Description="changed"; EndProcedure Counter=0;',CREATE+'O.Change(); Message(O.Counter); O.Counter=5; Message(O.Counter); O.Write();')
        self.assertEqual(out,['1','5'])
    def test_export_calls_write_with_cancel(self):
        app,out=self.run_body('Procedure Save() Export ThisObject.Write(); EndProcedure Procedure BeforeWrite(Cancel) Cancel=True; EndProcedure',CREATE+'Try O.Save(); Except Message(O.IsNew()); EndTry;')
        self.assertEqual(out,['Да']);self.assertEqual(app.constant_store.read_records('Items'),[])
    def test_private_export_unavailable(self):
        with self.assertRaises(BSLError):self.run_body('Procedure Secret() EndProcedure',CREATE+'O.Secret();')
    def test_handler_field_byref(self):
        _,out=self.run_body('Procedure Change(V) V="helper"; EndProcedure Procedure BeforeWrite(Cancel) Change(Description); EndProcedure',CREATE+'O.Write(); Message(O.Ref.GetObject().Description);')
        self.assertEqual(out,['helper'])
    def test_recursive_write_rejected(self):
        app,_=self.run_body('Procedure BeforeWrite(Cancel) ThisObject.Write(); EndProcedure',CREATE+'Try O.Write(); Except EndTry;')
        self.assertEqual(app.constant_store.read_records('Items'),[])
    def test_transaction_takeover_rejected(self):
        app,_=self.run_body('Procedure BeforeWrite(Cancel) CommitTransaction(); EndProcedure',CREATE+'Try O.Write(); Except EndTry;')
        self.assertEqual(app.constant_store.read_records('Items'),[])
    def test_invalid_signature_before_initializer(self):
        with self.assertRaises(BSLError):self.run_body('Procedure OnWrite() EndProcedure Message("should not run");',CREATE)
    def test_unsupported_onread(self):
        with self.assertRaises(BSLError):self.run_body('Procedure OnRead() EndProcedure',CREATE)
    def test_async_module_refused(self):
        with self.assertRaises(BSLError):self.run_body('Async Procedure Later() Export EndProcedure',CREATE)
    def test_field_declaration_conflict(self):
        with self.assertRaises(BSLError):self.run_body('Var Description;',CREATE)
    def test_recursive_initializer(self):
        with self.assertRaises(BSLError):self.run_body('Other=Catalogs.Items.CreateItem();',CREATE)
    def test_direct_store_does_not_bypass_module(self):
        store=SourceCatalogStore.create(self.path,source('Procedure BeforeWrite(Cancel) Cancel=True; EndProcedure'));self.addCleanup(store.close)
        with self.assertRaisesRegex(ValueError,'handler'):
            store.write_record('Items',uuid4(),0,{'code':'A','description':'','deletionmark':False},_handled=True)
        self.assertEqual(store.read_records('Items'),[])
    def test_external_transaction_not_committed(self):
        app,out=self.run_body('Procedure BeforeWrite(Cancel) Description="before"; EndProcedure','BeginTransaction(); '+CREATE+'O.Write(); Message(TransactionActive()); RollbackTransaction();')
        self.assertEqual(out,['Да']);self.assertEqual(app.constant_store.read_records('Items'),[])
    def test_russian_event_fields(self):
        _,out=self.run_body('Процедура ПередЗаписью(Отказ) Наименование="готово"; КонецПроцедуры',CREATE+'O.Write(); Message(O.Description);')
        self.assertEqual(out,['готово'])
    def test_object_module_update_preserves_existing(self):
        package=source('Procedure BeforeWrite(Cancel) Description="first"; EndProcedure',CREATE+'O.Write();');out=[]
        app=SourceApplication(package,scratch_database=self.path,source_catalog_records=True,output=out.append);app.start();app.close()
        changed=source('Procedure BeforeWrite(Cancel) Description="second"; EndProcedure')
        SourceCatalogStore.update_source(self.path,changed)
        store=SourceCatalogStore.reopen(self.path,changed);self.addCleanup(store.close)
        self.assertEqual(store.read_records('Items')[0][2]['description'],'first')
    def test_unqualified_standard_methods(self):
        _,out=self.run_body('Procedure BeforeWrite(Cancel) Message(IsNew()); Message(Metadata().Name); EndProcedure',CREATE+'O.Write();')
        self.assertEqual(out,['Да','Items'])
    def test_caught_rollback_cannot_commit_later_constant(self):
        from test_source_constant_store import configuration
        files={e.path:e.content for e in configuration().files}
        files.update({e.path:e.content for e in source('Procedure BeforeWrite(Cancel) Try Constants.Flag.Set("wrong"); Except EndTry; Try Constants.Flag.Set(True); Except EndTry; EndProcedure',
            'Constants.Flag.Set(False); '+CREATE+'Try O.Write(); Except EndTry; Message(Constants.Flag.Get());').files if e.path!='Configuration.xml'})
        out=[];app=SourceApplication(import_source(files),scratch_database=self.path,source_catalog_records=True,output=out.append);self.addCleanup(app.close)
        app.start();self.assertEqual(out,['Нет']);self.assertEqual(app.constant_store.read_records('Items'),[])
    def test_constant_handler_abort_cannot_commit_catalog_write(self):
        from test_source_constant_store import configuration
        files={e.path:e.content for e in configuration().files}
        files.update({e.path:e.content for e in package().files if e.path!='Configuration.xml'})
        files['Constants/Text/Ext/ValueManagerModule.bsl']=b'Procedure BeforeWrite(Cancel) Try Constants.Date.Get(); Except EndTry; Try O=Catalogs.Items.CreateItem(); O.Code="escape"; O.Write(); Except EndTry; EndProcedure'
        files['Ext/SessionModule.bsl']=b'Procedure SessionParametersSetting(Names) Try Constants.Text.Set("candidate"); Except Message("aborted"); EndTry; EndProcedure'
        out=[];app=SourceApplication(import_source(files),scratch_database=self.path,source_catalog_records=True,output=out.append);self.addCleanup(app.close)
        app.start();self.assertEqual(out,['aborted']);self.assertEqual(app.constant_store.read_records('Items'),[])
        with self.assertRaisesRegex(ValueError,'uninitialized'):app.constant_store.get('Text')
