"""Owned row ordering remains atomic and explicit-write only."""
import unittest
from unittest.mock import patch
import test_source_document_sections as fixture
from yadinassi.errors import BSLError

ROWS='R=D.Lines.Add();R.Flag=True;S=D.Lines.Add();S.Flag=False;'
class SourceSectionRowOrderTests(unittest.TestCase):
    setUp=fixture.SourceDocumentSectionTests.setUp
    run_body=fixture.SourceDocumentSectionTests.run_body
    def test_insert_front_and_end(self):
        _,out=self.run_body(ROWS+'T=D.Lines.Insert(0);T.Flag=False;U=D.Lines.Вставить(3);U.Flag=True;Message(R.LineNumber);Message(U.НомерСтроки);Message(D.Lines.Count());')
        self.assertEqual(out,['2','4','4'])
    def test_move_row_preserves_identity(self):
        _,out=self.run_body(ROWS+'D.Lines.Move(S,-1);Message(D.Lines.Get(0)=S);Message(R.Flag);Message(R.LineNumber);Message(D.Lines.IndexOf(R));')
        self.assertEqual(out,['Да','Да','2','1'])
    def test_move_index_and_russian(self):
        _,out=self.run_body(ROWS+'D.Lines.Сдвинуть(0,1);Message(D.Lines.Индекс(R));Message(S.НомерСтроки);')
        self.assertEqual(out,['1','1'])
    def test_zero_move_keeps_iterator(self):
        _,out=self.run_body(ROWS+'For Each X In D.Lines Do D.Lines.Move(X,0);EndDo;Message(R.LineNumber);')
        self.assertEqual(out,['1'])
    def test_reorder_invalidates_iterator(self):
        with self.assertRaises(BSLError):self.run_body(ROWS+'For Each X In D.Lines Do D.Lines.Move(R,1);EndDo;')
    def test_invalid_moves_atomic(self):
        _,out=self.run_body(ROWS+'Try D.Lines.Move(R,-1);Except EndTry;Try D.Lines.Move(S,1);Except EndTry;Try D.Lines.Move(R,0.5);Except EndTry;Message(R.LineNumber);Message(S.LineNumber);')
        self.assertEqual(out,['1','2'])
    def test_insert_invalid_atomic(self):
        _,out=self.run_body(ROWS+'Try D.Lines.Insert(3);Except EndTry;Try D.Lines.Insert(-1);Except EndTry;Try D.Lines.Insert("0");Except EndTry;Message(D.Lines.Count());Message(R.LineNumber);')
        self.assertEqual(out,['2','1'])
    def test_budget_insert_atomic(self):
        with patch('yadinassi.source_document_sections._MAX_ROWS',2):
            _,out=self.run_body(ROWS+'Try D.Lines.Insert(0);Except Message("bound");EndTry;Message(R.LineNumber);Message(D.Lines.Count());')
        self.assertEqual(out,['bound','1','2'])
    def test_deleted_row_refused(self):
        _,out=self.run_body(ROWS+'D.Lines.Delete(R);Try D.Lines.IndexOf(R);Except Message("deleted");EndTry;Try D.Lines.Move(R,0);Except Message("deleted");EndTry;')
        self.assertEqual(out,['deleted','deleted'])
    def test_foreign_owner_row_refused(self):
        _,out=self.run_body(ROWS+'E=Documents.Invoice.CreateDocument();T=E.Lines.Add();T.Flag=True;Try D.Lines.IndexOf(T);Except Message("foreign");EndTry;Try D.Lines.Move(T,0);Except Message("foreign");EndTry;Message(R.LineNumber);')
        self.assertEqual(out,['foreign','foreign','1'])
    def test_detached_section_refused(self):
        _,out=self.run_body(ROWS+'D.Write();Old=D.Lines;D.Read();Try Old.Insert(0);Except Message("old");EndTry;')
        self.assertEqual(out,['old'])
    def test_no_implicit_persistence(self):
        app,_=self.run_body(ROWS+'D.Write();D.Lines.Move(R,1);')
        store=app.constant_store;rid=store.read_documents('Invoice')[0][0]
        self.assertTrue(store.read_document_bundle('Invoice',rid)[3]['lines'][0]['flag'])
    def test_write_persists_order(self):
        app,_=self.run_body(ROWS+'D.Lines.Move(R,1);D.Write();')
        store=app.constant_store;rid=store.read_documents('Invoice')[0][0]
        self.assertFalse(store.read_document_bundle('Invoice',rid)[3]['lines'][0]['flag'])
    def test_unassigned_insert_not_defaulted(self):
        with self.assertRaises(BSLError):self.run_body('R=D.Lines.Insert(0);Message(R.Flag);')
    def test_exact_indexof_row_required(self):
        with self.assertRaises(BSLError):self.run_body(ROWS+'D.Lines.IndexOf(0);')
    def test_failed_insert_does_not_invalidate_iteration(self):
        _,out=self.run_body(ROWS+'For Each X In D.Lines Do Try D.Lines.Insert(-1);Except EndTry;Message(X.Flag);EndDo;')
        self.assertEqual(out,['Да','Нет'])
    def test_noop_move_still_checks_owned_receiver(self):
        _,out=self.run_body(ROWS+'E=Documents.Invoice.CreateDocument();T=E.Lines.Add();Try D.Lines.Move(T,0);Except Message("foreign");EndTry;Message(D.Lines.Count());')
        self.assertEqual(out,['foreign','2'])
