"""One exact main-demo database serves original catalogs and inventory reports."""
from datetime import datetime
from pathlib import Path
import tempfile
import unittest
from test_main_demo_configuration import source
from test_main_demo_runtime import SEED
from yadinassi.configuration_main_demo import PROFILE, import_main_demo_configuration
from yadinassi.database_context import SQLiteDBContext
from yadinassi.inventory_application_reports import InventoryReports
from yadinassi.inventory_host_operations import _source_configuration
from yadinassi.catalog_backend import BackendError
from yadinassi.runtime import Interpreter

class MainDemoUIReportsTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(); self.addCleanup(temporary.cleanup)
        self.config = import_main_demo_configuration(source(), profile=PROFILE)
        self.context = SQLiteDBContext.create_main_demo(Path(temporary.name)/'demo.sqlite', self.config)
        self.addCleanup(self.context.close)
        self.vm = Interpreter(database_context=self.context)
        self.addCleanup(self.vm.close)
        self.reports = InventoryReports(self.context, self.config)

    def test_posted_document_and_reports_use_original_catalog_records(self):
        self.vm.execute(SEED + '''D=Documents.Receipt.CreateDocument();D.Number="r1";D.Date=Date(2024,1,1);
D.Warehouse=Склад.Ссылка;D.State=Enums.States.Approved;L=D.Lines.Add();L.Product=Карточка.Ссылка;
L.Quantity=5;L.Amount=10;L.Unit=Enums.Units.Piece;D.Write(DocumentWriteMode.Posting);''')
        result = self.reports.read('StockMovements')
        columns = {c.name:i for i,c in enumerate(result.columns)}
        self.assertEqual(result.rows[0][columns['Unit']], 'Piece')
        self.assertEqual(result.rows[0][columns['State']], 'Approved')
        self.assertTrue(any('Кабель' in text for key,text in result.labels))
        for name, options in (
            ('StockBalance', {'at':datetime(2024,1,2)}),
            ('StockTurnovers', {'start':datetime(2024,1,1),'end':datetime(2024,2,1)}),
            ('StockStatement', {'start':datetime(2024,1,1),'end':datetime(2024,2,1),'periodicity':'None'})):
            self.assertEqual(len(self.reports.read(name, **options).rows), 1)
        self.assertIsNone(self.context.backend._active)

    def test_report_choices_are_original_product_catalog(self):
        self.vm.execute(SEED)
        choices = self.reports.choices('StockStatement', 'Product')
        self.assertEqual([row.description for row in choices.rows], ['Кабель'])
        product = next(c for c in self.config.catalogs if c.name == 'Номенклатура')
        self.assertEqual(choices.catalog_id, product.identity)
        self.assertIsNone(self.context.backend._active)

    def test_foreign_owner_profile_hook_never_runs(self):
        class Foreign:
            @property
            def profile(self): raise AssertionError('untrusted hook')
        backend = self.context.backend; original = backend.accumulation_configuration
        try:
            backend.accumulation_configuration = Foreign()
            with self.assertRaises(BackendError): _source_configuration(backend)
            with self.assertRaises(BackendError): self.reports._admit()
        finally:
            backend.accumulation_configuration = original
