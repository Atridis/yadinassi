"""Shared inventory scenarios on the canonical demo, not another configuration."""
from datetime import datetime
from yadinassi.inventory_application_reports import InventoryReports, UNAVAILABLE
import test_main_demo_runtime as runtime_fixture
SEED = runtime_fixture.SEED

POST = '''D=Documents.Receipt.CreateDocument();D.Number="r1";D.Date=Date(2024,1,1);
D.Warehouse=Склад.Ссылка;D.State=Enums.States.Approved;L=D.Lines.Add();
L.Product=Карточка.Ссылка;L.Quantity=5;L.Amount=10;L.Unit=Enums.Units.Piece;'''

# Reuse setup without inheriting the other class's test methods.
import unittest
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

    def test_undo_posting_reopen_and_repost_preserves_enum_values(self):
        self.vm.execute(SEED + POST + 'D.Write(DocumentWriteMode.Posting);D.Write(DocumentWriteMode.UndoPosting);')
        self.assertEqual(self.reports().read('StockMovements').rows, ())
        self.vm.execute('D=D.Ref.GetObject();D.Write(DocumentWriteMode.Posting);')
        rows = self.reports().read('StockMovements')
        values = dict(zip((c.name for c in rows.columns), rows.rows[0]))
        self.assertEqual((values['Unit'], values['State']), ('Piece', 'Approved'))
        from yadinassi.database_context import SQLiteDBContext
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
