"""Inclusive date windows retain bounded snapshot validation and ownership."""
import unittest
from unittest.mock import patch
import test_source_document_records as fixture
from yadinassi.errors import BSLError
from yadinassi.source_document_runtime import SourceDocumentCall
from yadinassi.source_references import SourceReferenceManager
from yadinassi.dates import BSLDate
from yadinassi.configuration_source_runtime import SourceApplication

DOCS=''
for n in (1,2,3):DOCS+=f'D=Documents.Invoice.CreateDocument();D.Number="{n}";D.Date=Date(2026,1,{n});D.Write();'
class SourceDocumentDateSelectionTests(unittest.TestCase):
    setUp=fixture.SourceDocumentRecordTests.setUp
    run_app=fixture.SourceDocumentRecordTests.run_app
    def numbers(self,args):
        _,out=self.run_app(DOCS+'S=Documents.Invoice.Select('+args+');While S.Next() Do Message(S.Number);EndDo;');return sorted(out)
    def test_inclusive_range(self):self.assertEqual(self.numbers('Date(2026,1,1),Date(2026,1,2)'),['1','2'])
    def test_single_boundary(self):self.assertEqual(self.numbers('Date(2026,1,2),Date(2026,1,2)'),['2'])
    def test_start_only(self):self.assertEqual(self.numbers('Date(2026,1,2)'),['2','3'])
    def test_end_only(self):self.assertEqual(self.numbers('Undefined,Date(2026,1,2)'),['1','2'])
    def test_unbounded_compatible(self):self.assertEqual(self.numbers('Undefined,Undefined'),['1','2','3'])
    def test_empty_window(self):self.assertEqual(self.numbers('Date(2027,1,1)'),[])
    def test_russian(self):
        _,out=self.run_app(DOCS+'S=Документы.Invoice.Выбрать(Дата(2026,1,2),Дата(2026,1,2));Сообщить(S.Следующий());Сообщить(S.Number);');self.assertEqual(out,['Да','2'])
    def test_reversed_rejected(self):
        with self.assertRaises(BSLError):self.run_app('Documents.Invoice.Select(Date(2026,1,3),Date(2026,1,1));')
    def test_wrong_types_and_arity(self):
        for i,args in enumerate(('1','"20260101"','True','Undefined,Undefined,Undefined')):
            self.path=self.path.with_name(str(i)+'.sqlite')
            with self.assertRaises(BSLError):self.run_app('Documents.Invoice.Select('+args+');')
    def test_predicate_validated_before_reader(self):
        app=SourceApplication(fixture.package('Documents.Invoice.Select("bad");'),scratch_database=self.path,source_document_records=True);self.addCleanup(app.close)
        with patch.object(app.constant_store,'read_documents',side_effect=AssertionError('reader reached')):
            with self.assertRaises(BSLError):app.start()
    def test_reader_integrity_not_hidden_by_empty_range(self):
        app=SourceApplication(fixture.package('Documents.Invoice.Select(Date(2027,1,1));'),scratch_database=self.path,source_document_records=True);self.addCleanup(app.close)
        with patch.object(app.constant_store,'read_documents',side_effect=ValueError('integrity sentinel')):
            with self.assertRaisesRegex(BSLError,'integrity sentinel'):app.start()
    def test_transaction_visibility_and_rollback(self):
        _,out=self.run_app('BeginTransaction();'+DOCS+'S=Documents.Invoice.Select(Date(2026,1,2),Date(2026,1,2));Message(S.Next());RollbackTransaction();S=Documents.Invoice.Select(Date(2026,1,2));Message(S.Next());');self.assertEqual(out,['Да','Нет'])
    def test_snapshot_does_not_recalculate_after_write(self):
        _,out=self.run_app(DOCS+'S=Documents.Invoice.Select(Date(2026,1,3));D.Date=Date(2025,1,1);D.Write();Message(S.Next());Message(S.Number);');self.assertEqual(out,['Да','3'])
    def test_getobject_from_selection(self):
        _,out=self.run_app(DOCS+'S=Documents.Invoice.Select(Date(2026,1,2),Date(2026,1,2));S.Next();O=S.GetObject();Message(O.Number);');self.assertEqual(out,['2'])
    def test_foreign_caller_refused(self):
        app,_=self.run_app('');foreign=SourceApplication(fixture.package());self.addCleanup(foreign.close);foreign.start()
        call=SourceDocumentCall(SourceReferenceManager(app,'Document','Invoice'),'select')
        with self.assertRaises(ValueError):list(call.invoke(foreign.interpreter,[]))
    def test_time_component_not_expanded(self):
        body='D=Documents.Invoice.CreateDocument();D.Number="A";D.Date=Date(2026,1,2,12,0,0);D.Write();S=Documents.Invoice.Select(Undefined,Date(2026,1,2));Message(S.Next());S=Documents.Invoice.Select(Date(2026,1,2,12,0,0),Date(2026,1,2,12,0,0));Message(S.Next());'
        _,out=self.run_app(body);self.assertEqual(out,['Нет','Да'])
    def test_selection_never_initializes_objects(self):
        app=SourceApplication(fixture.package('Documents.Invoice.Select(Date(2026,1,1));'),scratch_database=self.path,source_document_records=True);self.addCleanup(app.close)
        with patch('yadinassi.source_document_runtime.create_object',side_effect=AssertionError('init')):app.start()
    def test_deletion_mark_not_hidden(self):
        _,out=self.run_app(DOCS+'D.DeletionMark=True;D.Write();S=Documents.Invoice.Select(Date(2026,1,3));Message(S.Next());Message(S.DeletionMark);');self.assertEqual(out,['Да','Да'])
