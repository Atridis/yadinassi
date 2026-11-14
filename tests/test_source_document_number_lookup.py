"""Nonperiodical source document lookup, never posting or inferred numbering."""
import unittest
from unittest.mock import patch
from uuid import uuid4
import test_source_document_records as fixture
from yadinassi.configuration_source_runtime import SourceApplication
from yadinassi.source_document_runtime import SourceDocumentCall
from yadinassi.source_references import SourceReferenceManager
from yadinassi.errors import BSLError

DOC='D=Documents.Invoice.CreateDocument();D.Number="A";D.Date=Date(2026,1,1);D.Write();'
class SourceDocumentNumberLookupTests(unittest.TestCase):
    setUp=fixture.SourceDocumentRecordTests.setUp
    run_app=fixture.SourceDocumentRecordTests.run_app
    def test_found_canonical_ref(self):
        _,out=self.run_app(DOC+'Message(Documents.Invoice.FindByNumber("A")=D.Ref);')
        self.assertEqual(out,['Да'])
    def test_russian_alias(self):
        _,out=self.run_app(DOC+'Сообщить(Документы.Invoice.НайтиПоНомеру("A")=D.Ссылка);')
        self.assertEqual(out,['Да'])
    def test_missing_empty_and_case_sensitive(self):
        _,out=self.run_app(DOC+'Message(Documents.Invoice.FindByNumber("a").IsEmpty());Message(Documents.Invoice.FindByNumber("").IsEmpty());')
        self.assertEqual(out,['Да','Да'])
    def test_own_transaction_and_rollback(self):
        _,out=self.run_app('BeginTransaction();'+DOC+'Message(Documents.Invoice.FindByNumber("A")=D.Ref);RollbackTransaction();Message(Documents.Invoice.FindByNumber("A").IsEmpty());')
        self.assertEqual(out,['Да','Да'])
    def test_deletion_mark_does_not_hide(self):
        _,out=self.run_app(DOC+'D.DeletionMark=True;D.Write();Message(Documents.Invoice.FindByNumber("A")=D.Ref);')
        self.assertEqual(out,['Да'])
    def test_number_change(self):
        _,out=self.run_app(DOC+'D.Number="B";D.Write();Message(Documents.Invoice.FindByNumber("A").IsEmpty());Message(Documents.Invoice.FindByNumber("B")=D.Ref);')
        self.assertEqual(out,['Да','Да'])
    def test_type_arity_and_length(self):
        for value in ('1','True','Undefined','"1234567890"','"A",Date(2026,1,1)',''):
            with self.subTest(value=value):
                self.path=self.path.with_name('bad'+str(len(value))+value[:1].replace('"','x')+'.sqlite')
                with self.assertRaises(BSLError):self.run_app('Documents.Invoice.FindByNumber('+value+');')
    def test_reopen(self):
        body='If Documents.Invoice.FindByNumber("A").IsEmpty() Then '+DOC+' EndIf;Message(Documents.Invoice.FindByNumber("A").IsEmpty());'
        app,_=self.run_app(body);app.close()
        out=[];app=SourceApplication(fixture.package(body),existing_scratch_database=self.path,source_document_records=True,output=out.append)
        self.addCleanup(app.close);app.start();self.assertEqual(out,['Нет'])
    def test_closed_and_foreign_caller(self):
        app,_=self.run_app('');call=SourceDocumentCall(SourceReferenceManager(app,'Document','Invoice'),'findnumber')
        foreign=SourceApplication(fixture.package());self.addCleanup(foreign.close);foreign.start()
        with self.assertRaises(ValueError):list(call.invoke(foreign.interpreter,['A']))
        app.close()
        with self.assertRaises(ValueError):list(call.invoke(app.interpreter,['A']))
    def test_direct_call_and_reader_failure(self):
        app=SourceApplication(fixture.package('Documents.Invoice.FindByNumber("A");'),scratch_database=self.path,source_document_records=True);self.addCleanup(app.close)
        call=SourceDocumentCall(SourceReferenceManager(app,'Document','Invoice'),'findnumber')
        with self.assertRaises(ValueError):call('A')
        with patch.object(app.constant_store,'read_documents',side_effect=ValueError('integrity sentinel')):
            with self.assertRaisesRegex(BSLError,'integrity sentinel'):app.start()
    def test_ambiguous_data_not_arbitrary_first(self):
        app=SourceApplication(fixture.package('Documents.Invoice.FindByNumber("A");'),scratch_database=self.path,source_document_records=True);self.addCleanup(app.close)
        with patch.object(app.constant_store,'read_documents',return_value=[(uuid4(),1,{'number':'A'}),(uuid4(),1,{'number':'A'})]):
            with self.assertRaisesRegex(BSLError,'ambiguous'):app.start()
    def test_lookup_never_initializes_object(self):
        app=SourceApplication(fixture.package('Message(Documents.Invoice.FindByNumber("A").IsEmpty());'),scratch_database=self.path,source_document_records=True);self.addCleanup(app.close)
        with patch('yadinassi.source_document_runtime.create_object',side_effect=AssertionError('object initialization')):
            app.start()
    def test_invalid_type_before_record_read(self):
        app=SourceApplication(fixture.package('Documents.Invoice.FindByNumber(1);'),scratch_database=self.path,source_document_records=True);self.addCleanup(app.close)
        with patch.object(app.constant_store,'read_documents',side_effect=AssertionError('read')):
            with self.assertRaises(BSLError):app.start()
    def test_without_scratch_capability_refused(self):
        app=SourceApplication(fixture.package('Documents.Invoice.FindByNumber("A");'));self.addCleanup(app.close)
        with self.assertRaises(BSLError):app.start()
