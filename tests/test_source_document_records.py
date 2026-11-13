"""Explicit nonposting source documents, storage and language contract."""
import tempfile
import unittest
from pathlib import Path
from uuid import uuid4
import test_source_catalog_definitions as fixture
from yadinassi.configuration_source import import_source
from yadinassi.configuration_source_runtime import SourceApplication
from yadinassi.source_document_definitions import source_document_definitions
from yadinassi.source_document_store import SourceDocumentStore
from yadinassi.source_catalog_store import SourceCatalogStore
from yadinassi.dates import BSLDate
from yadinassi.errors import BSLError

BASE='<Name>Invoice</Name><NumberType>String</NumberType><NumberLength>9</NumberLength><NumberPeriodicity>Nonperiodical</NumberPeriodicity><CheckUnique>true</CheckUnique><Autonumbering>false</Autonumbering><Posting>Deny</Posting>'
def package(body='',props=BASE,children='',extra=None):
    files={f.path:f.content for f in fixture.config().files}
    files['Documents/Invoice.xml']=('<MetaDataObject xmlns="'+fixture.MD+'" xmlns:v8="http://v8.1c.ru/8.1/data/core" xmlns:xs="http://www.w3.org/2001/XMLSchema"><Document uuid="00000000-0000-0000-0000-000000000003"><Properties>'+props+'</Properties><ChildObjects>'+children+'</ChildObjects></Document></MetaDataObject>').encode()
    if body:files['Ext/SessionModule.bsl']=('Procedure SessionParametersSetting(Names) '+body+' EndProcedure').encode()
    files.update(extra or {})
    return import_source(files)

class SourceDocumentRecordTests(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory();self.addCleanup(tmp.cleanup);self.path=Path(tmp.name)/'doc.sqlite'
    def store(self,source=None):
        result=SourceDocumentStore.create(self.path,source or package());self.addCleanup(result.close);return result
    def values(self,number='A',**kwargs):return dict(number=number,date=BSLDate(0),deletionmark=False,posted=False,**kwargs)
    def run_app(self,body,**kw):
        out=[];app=SourceApplication(package(body,**kw),scratch_database=self.path,source_document_records=True,output=out.append)
        self.addCleanup(app.close);app.start();return app,out
    def test_parser(self):
        defs,errors=source_document_definitions(package(children=fixture.attribute()));self.assertFalse(errors);self.assertEqual(len(defs['invoice'].fields),5)
    def test_posting_refused(self):
        defs,errors=source_document_definitions(package(props=BASE.replace('Deny','Allow')));self.assertFalse(defs);self.assertIn('invoice',errors)
    def test_auto_refused(self):
        defs,errors=source_document_definitions(package(props=BASE.replace('<Autonumbering>false','<Autonumbering>true')));self.assertFalse(defs)
    def test_module_refused(self):
        defs,errors=source_document_definitions(package(extra={'Documents/Invoice/Ext/ObjectModule.bsl':b'Message("bad");'}));self.assertFalse(defs)
    def test_tabular_refused(self):
        defs,errors=source_document_definitions(package(children='<TabularSection/>'));self.assertFalse(defs)
    def test_write_reopen(self):
        source=package();store=self.store(source);identity=uuid4();values=self.values();store.write_document('Invoice',identity,0,values);store.close()
        reopened=SourceDocumentStore.reopen(self.path,source);self.addCleanup(reopened.close);self.assertEqual(reopened.read_documents('Invoice')[0][2],values)
    def test_number_unique(self):
        store=self.store();store.write_document('Invoice',uuid4(),0,self.values())
        with self.assertRaises(ValueError):store.write_document('Invoice',uuid4(),0,self.values())
        self.assertEqual(len(store.read_documents('Invoice')),1)
    def test_posted_payload_refused(self):
        store=self.store();values=self.values();values['posted']=True
        with self.assertRaises(ValueError):store.write_document('Invoice',uuid4(),0,values)
    def test_date_required(self):
        store=self.store();values=self.values();del values['date']
        with self.assertRaises(ValueError):store.write_document('Invoice',uuid4(),0,values)
    def test_stale_revision(self):
        store=self.store();identity=uuid4();store.write_document('Invoice',identity,0,self.values());store.write_document('Invoice',identity,1,self.values())
        with self.assertRaisesRegex(ValueError,'stale'):store.write_document('Invoice',identity,1,self.values())
    def test_shared_rollback(self):
        store=self.store();store.begin_transaction();store.write_record('Items',uuid4(),0,dict(code='C',description='',deletionmark=False));store.write_document('Invoice',uuid4(),0,self.values());store.rollback_transaction();self.assertFalse(store.read_records('Items'));self.assertFalse(store.read_documents('Invoice'))
    def test_failed_write_rolls_all(self):
        store=self.store();store.begin_transaction();store.write_document('Invoice',uuid4(),0,self.values())
        with self.assertRaises(ValueError):store.write_document('Invoice',uuid4(),0,self.values())
        self.assertFalse(store.transaction_active);self.assertFalse(store.read_documents('Invoice'))
    def test_v4_refuses_v5(self):
        store=self.store();store.close()
        with self.assertRaises(ValueError):SourceCatalogStore.reopen(self.path,package())
    def test_upgrade(self):
        original=self.path.with_name('v4.sqlite');store=SourceCatalogStore.create(original,package());store.write_record('Items',uuid4(),0,dict(code='C',description='',deletionmark=False));store.close();before=original.read_bytes()
        SourceDocumentStore.upgrade_copy(original,self.path);self.assertEqual(before,original.read_bytes());new=SourceDocumentStore.reopen(self.path,package());self.addCleanup(new.close);self.assertEqual(len(new.read_records('Items')),1);self.assertFalse(new.read_documents('Invoice'))
    def test_upgrade_existing_destination_refused(self):
        old=self.path.with_name('v4.sqlite');s=SourceCatalogStore.create(old,package());s.close();self.path.write_bytes(b'keep')
        with self.assertRaises(FileExistsError):SourceDocumentStore.upgrade_copy(old,self.path)
        self.assertEqual(self.path.read_bytes(),b'keep')
    def test_bsl_cycle(self):
        _,out=self.run_app('O=Documents.Invoice.CreateDocument(); Message(O.IsNew()); O.Number="A"; O.Date=Date(2026,1,1); O.Write(); Message(O.IsNew()); P=O.Ref.GetObject(); Message(P.Number); Message(P.Posted); S=Documents.Invoice.Select(); Message(S.Next()); Message(S.Number);')
        self.assertEqual(out,['Да','Нет','A','Нет','Да','A'])
    def test_bsl_direct_fields(self):
        _,out=self.run_app('O=Documents.Invoice.CreateDocument(); O.Number="A"; O.Date=Date(2026,1,1); O.Write(); Message(O.Ref.Number);')
        self.assertEqual(out,['A'])
    def test_bsl_posted_readonly(self):
        with self.assertRaises(BSLError):self.run_app('O=Documents.Invoice.CreateDocument(); O.Posted=True;')
    def test_bsl_safe_mode(self):
        with self.assertRaises(BSLError):self.run_app('SetSafeMode(True); O=Documents.Invoice.CreateDocument();')
    def test_bsl_ref_readonly(self):
        with self.assertRaises(BSLError):self.run_app('R=Documents.Invoice.EmptyRef(); R.Number="A";')
    def test_bsl_missing_date(self):
        with self.assertRaises(BSLError):self.run_app('O=Documents.Invoice.CreateDocument(); O.Number="A"; O.Write();')
    def test_bsl_write_mode_refused(self):
        with self.assertRaises(BSLError):self.run_app('O=Documents.Invoice.CreateDocument(); O.Write(True);')
