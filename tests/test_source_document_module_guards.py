"""Independent lifecycle transaction and direct-host bypass guards."""
import unittest
from uuid import uuid4, uuid5, NAMESPACE_URL
import re
import test_source_document_sections as fixture
import test_source_document_records as records
from test_source_constant_store import configuration
from yadinassi.configuration_source import import_source
from yadinassi.configuration_source_runtime import SourceApplication
from yadinassi.source_document_section_store import SourceDocumentSectionStore
from yadinassi.errors import BSLError

def package(module,body='',sections=True):
    source=fixture.package(body,children=fixture.SECTION if sections else '')
    files={f.path:f.content for f in source.files}
    files['Documents/Invoice/Ext/ObjectModule.bsl']=module.encode()
    for f in configuration().files:
        if f.path=='Configuration.xml':files[f.path]=f.content
        elif f.path.startswith('Constants/'):
            identity=str(uuid5(NAMESPACE_URL,'document-guard:'+f.path)).encode()
            files[f.path]=re.sub(br'uuid="[^"]+"',b'uuid="'+identity+b'"',f.content,count=1)
    return import_source(files)

class SourceDocumentModuleGuardTests(unittest.TestCase):
    setUp=records.SourceDocumentRecordTests.setUp
    def app(self,module,body='',sections=True):
        app=SourceApplication(package(module,body,sections),scratch_database=self.path,source_document_sections=True);self.addCleanup(app.close);return app
    def persisted(self,app):
        store=SourceDocumentSectionStore.reopen(self.path,app.source);self.addCleanup(store.close);return store
    def test_host_scalar_write_cannot_skip_object_events(self):
        source=package('Procedure OnWrite(Cancel) Cancel=True; EndProcedure',sections=False)
        store=SourceDocumentSectionStore.create(self.path,source);self.addCleanup(store.close)
        with self.assertRaises(ValueError):store.write_document('Invoice',uuid4(),0,records.SourceDocumentRecordTests.values(self))
        self.assertEqual(store.read_documents('Invoice'),[])
    def test_host_bundle_write_cannot_skip_object_events(self):
        source=package('Procedure OnWrite(Cancel) Cancel=True; EndProcedure')
        store=SourceDocumentSectionStore.create(self.path,source);self.addCleanup(store.close)
        with self.assertRaises(ValueError):store.write_document_bundle('Invoice',uuid4(),0,records.SourceDocumentRecordTests.values(self),{'lines':()})
        self.assertEqual(store.read_documents('Invoice'),[])
    def test_caught_constant_failure_cannot_restart_through_catalog(self):
        module='Procedure OnWrite(Cancel) Try Constants.Flag.Set("bad"); Except EndTry; Try C=Catalogs.Items.CreateItem(); C.Code="L"; C.Write(); Except EndTry; EndProcedure'
        app=self.app(module,fixture.CREATE+'D.Write();')
        with self.assertRaises(BSLError):app.start()
        self.assertFalse(app.constant_store.transaction_active)
        store=self.persisted(app);self.assertEqual(store.read_records('Items'),[]);self.assertEqual(store.read_documents('Invoice'),[])
    def test_caught_initializer_abort_cannot_leak_catalog_write(self):
        module='Try Constants.Flag.Set("bad"); Except EndTry; Try C=Catalogs.Items.CreateItem(); C.Code="L"; C.Write(); Except EndTry;'
        app=self.app(module,'D=Documents.Invoice.CreateDocument();')
        with self.assertRaises(BSLError):app.start()
        self.assertFalse(app.constant_store.transaction_active)
        self.assertEqual(self.persisted(app).read_records('Items'),[])
    def test_beforewrite_is_not_silently_skipped(self):
        module='Procedure BeforeWrite(Cancel,WriteMode,PostingMode) Constants.Flag.Set(True); EndProcedure Function Ping() Export Return 7; EndFunction'
        app=self.app(module,'Constants.Flag.Set(False); '+fixture.CREATE+'If D.Ping()<>7 Then Raise "exports broken"; EndIf; D.Write();')
        with self.assertRaises(BSLError):app.start()
        store=self.persisted(app);self.assertEqual(store.read_documents('Invoice'),[])
        self.assertFalse(store.get('Flag'))
    def test_date_field_does_not_shadow_date_constructor_call(self):
        module='Procedure SetDate() Export Date=Date(2026,1,1); EndProcedure'
        out=[];source=package(module,'D=Documents.Invoice.CreateDocument(); D.Number="A"; D.SetDate(); D.Write(); Message(D.Ref.Date=Date(2026,1,1));')
        app=SourceApplication(source,scratch_database=self.path,source_document_sections=True,output=out.append);self.addCleanup(app.close);app.start();self.assertEqual(out,['Да'])
