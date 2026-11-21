"""Shared inventory scenarios on the canonical demo, not another configuration."""
from datetime import datetime
from yadinassi.configuration.demos.inventory_application_reports import InventoryReports, UNAVAILABLE
import test_main_demo_runtime as runtime_fixture
SEED = runtime_fixture.SEED

POST = '''D=Documents.Receipt.CreateDocument();D.Number="r1";D.Date=Date(2024,1,1);
D.Warehouse=Склад.Ссылка;D.State=Enums.States.Approved;L=D.Lines.Add();
L.Product=Карточка.Ссылка;L.Quantity=5;L.Amount=10;L.Unit=Enums.Units.Piece;'''

# Reuse setup without inheriting the other class's test methods.
import unittest
from unittest.mock import patch
class MainDemoInventoryScenarios(unittest.TestCase):
    setUp = runtime_fixture.MainDemoRuntimeTests.setUp

    def reports(self):
        return InventoryReports(self.context, self.context.backend.accumulation_configuration)

    def test_unsaved_and_saved_unposted_documents_do_not_create_movements(self):
        self.vm.execute(SEED + POST)
        self.assertEqual(self.reports().read('StockMovements').rows, ())
        self.vm.execute('D.Write();')
        self.assertEqual(self.reports().read('StockMovements').rows, ())
        self.vm.execute('D.Write(DocumentWriteMode.Posting);')
        self.assertEqual(len(self.reports().read('StockMovements').rows), 1)

    def test_clean_document_update_preserves_blob_and_dirty_clear_rolls_back(self):
        self.vm.execute(SEED + POST + 'D.Write(DocumentWriteMode.Posting);')
        document = self.vm.variables['d']
        original_rows = document.get_member('Lines')._stored_rows()
        original_revision = document._revision
        expected_movements = self.reports().read('StockMovements').rows
        backend = self.context.backend
        connect = backend._connect
        trace = []
        def traced_connect(**kwargs):
            connection = connect(**kwargs)
            connection.set_trace_callback(trace.append)
            return connection
        with patch.object(backend, '_connect', side_effect=traced_connect):
            self.vm.execute('D=D.Ref.GetObject(); D.Number="r2"; D.Write();')
        updates = [sql for sql in trace if sql.startswith('UPDATE document_record SET')]
        self.assertEqual(len(updates), 1)
        self.assertNotIn('sections_json', updates[0])
        self.assertEqual(self.reports().read('StockMovements').rows, expected_movements)
        self.vm.execute('D=D.Ref.GetObject();')
        document = self.vm.variables['d']
        self.assertNotEqual(document._revision, original_revision)
        self.assertTrue(document.get_member('Posted'))
        self.assertEqual(document.get_member('Lines')._stored_rows(), original_rows)
        self.vm.execute('BeginTransaction(); D.Lines.Clear(); D.Write(); RollbackTransaction();')
        self.vm.execute('Saved=D.Ref.GetObject();')
        self.assertEqual(self.vm.variables['saved'].get_member('Lines')._stored_rows(), original_rows)
        self.vm.execute('D.Write(); D=D.Ref.GetObject();')
        self.assertEqual(self.vm.variables['d'].get_member('Lines').count(), 0)
        self.assertTrue(self.vm.variables['d'].get_member('Posted'))

    def test_clean_document_write_charges_full_intent_before_mutation(self):
        from contextlib import closing
        from uuid import uuid4
        from yadinassi.db.catalog.catalog_backend import BackendError
        from yadinassi.db.sqlite.sqlite_documents import DocumentView
        from yadinassi.db.transaction_backend import TransactionRequest

        self.vm.execute(SEED + POST + 'D.Write(); D=D.Ref.GetObject();')
        document = self.vm.variables['d']
        document.set_member('Number', 'r2')
        expected = document._revision
        backend = self.context.backend
        full = document._draft()
        partial = document._draft(changes=True)
        with closing(backend.begin_unit_of_work(uuid4())) as unit:
            view = DocumentView(unit._view)
            full_size = view._intent(full, expected)[2][0]
            self.assertLess(view._intent(partial, expected)[2][0], full_size)
            request = TransactionRequest('document_update', partial, expected)
            with patch('yadinassi.db.sqlite.sqlite_transactions.MAX_BYTES', full_size-1):
                with self.assertRaisesRegex(BackendError, 'unsupported'):
                    unit.stage(request)
            with patch('yadinassi.db.sqlite.sqlite_documents._MAX_ROW', full_size-1):
                with self.assertRaisesRegex(BackendError, 'invalid_input'):
                    unit.stage(request)
            self.assertEqual(unit.read_document(document._key).number, 'r1')
            self.assertEqual(unit.requests, ())
            with patch('yadinassi.db.sqlite.sqlite_transactions.MAX_BYTES', full_size):
                unit.stage(request)
            self.assertEqual(unit._bytes, full_size)
            self.assertEqual(unit.read_document(document._key).number, 'r2')
            unit.rollback()

    def test_undo_posting_reopen_and_repost_preserves_enum_values(self):
        self.vm.execute(SEED + POST + 'D.Write(DocumentWriteMode.Posting);D.Write(DocumentWriteMode.UndoPosting);')
        self.assertEqual(self.reports().read('StockMovements').rows, ())
        self.vm.execute('D=D.Ref.GetObject();D.Write(DocumentWriteMode.Posting);')
        rows = self.reports().read('StockMovements')
        values = dict(zip((c.name for c in rows.columns), rows.rows[0]))
        self.assertEqual((values['Unit'], values['State']), ('Piece', 'Approved'))
        from yadinassi.db.database_context import SQLiteDBContext
        with SQLiteDBContext(self.path) as reopened:
            reports=InventoryReports(reopened,reopened.backend.accumulation_configuration)
            self.assertEqual(reports.read('StockMovements').rows, rows.rows)

    def test_deleted_historical_catalog_label_does_not_erase_movements(self):
        self.vm.execute(SEED + POST + 'D.Write(DocumentWriteMode.Posting);')
        before=self.reports().read('StockMovements')
        self.vm.execute('Карточка.ПометкаУдаления=Истина;Карточка.Записать();')
        after=self.reports().read('StockMovements')
        self.assertEqual(after.rows,before.rows)
        self.assertIn(UNAVAILABLE,dict(after.labels).values())

    def test_shortage_refuses_without_persisting_document_or_movements(self):
        from yadinassi import BSLRuntimeError
        self.vm.execute(SEED + POST + 'D.Write(DocumentWriteMode.Posting);')
        before=self.reports().read('StockMovements')
        self.vm.execute('''I=Documents.Issue.CreateDocument();I.Number="i1";I.Date=Date(2024,1,2);
I.Warehouse=Склад.Ссылка;I.State=Enums.States.Approved;R=I.Lines.Add();
R.Product=Карточка.Ссылка;R.Unit=Enums.Units.Piece;R.Quantity=6;R.Amount=12;''')
        with self.assertRaises(BSLRuntimeError) as refused:
            self.vm.execute('I.Write(DocumentWriteMode.Posting);')
        self.assertIn('document write cancelled',str(refused.exception))
        self.assertEqual(self.reports().read('StockMovements').rows,before.rows)
        self.vm.execute('Q=New Query("SELECT COUNT(*) AS N FROM Document.Issue");S=Q.Execute().Select();S.Next();Message(S.N);')
        self.assertEqual(self.output,['0'])
        self.vm.execute('R.Quantity=5;I.Write(DocumentWriteMode.Posting);')
        self.assertEqual(len(self.reports().read('StockMovements').rows),2)

    def test_existing_cancel_and_exception_modes_remain_atomic(self):
        from yadinassi import BSLRuntimeError
        self.vm.execute(SEED + POST + 'D.Write(DocumentWriteMode.Posting);')
        before=self.reports().read('StockMovements')
        for mode in (1,2):
            with self.subTest(mode=mode):
                self.vm.execute('I=Documents.Issue.CreateDocument();I.Number="cancel";I.Date=Date(2024,1,2);'
                    'I.Warehouse=Склад.Ссылка;R=I.Lines.Add();R.Product=Карточка.Ссылка;'
                    'R.Unit=Enums.Units.Piece;R.Quantity=1;R.Amount=2;'
                    f'I.AdditionalProperties.Insert("Mode",{mode});')
                with self.assertRaises(BSLRuntimeError):
                    self.vm.execute('I.Write(DocumentWriteMode.Posting);')
                self.assertEqual(self.reports().read('StockMovements').rows,before.rows)
