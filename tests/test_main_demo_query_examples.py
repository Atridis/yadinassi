"""Public query examples use the canonical database, not per-feature schemas."""
from pathlib import Path
import unittest
from yadinassi import Interpreter
from yadinassi.database_context import SQLiteDBContext
import test_main_demo_runtime as runtime

ROOT = Path(__file__).resolve().parents[1]
REPORTS = ('derived-document-report', 'document-query-report', 'query-membership-report')

class MainDemoQueryExampleTests(unittest.TestCase):
    setUp = runtime.MainDemoRuntimeTests.setUp

    def report(self, name, vm=None):
        self.output.clear()
        (vm or self.vm).execute((ROOT / 'examples' / (name + '.bsl')).read_text())
        return list(self.output)

    def seed(self):
        self.vm.execute(runtime.SEED + '''
For N=1 To 2 Do
 D=Documents.Receipt.CreateDocument();D.Number=String(N);D.Date=Date(2024,1,N);
 D.Warehouse=Склад.Ссылка;D.State=Enums.States.Draft;
 L=D.Lines.Add();L.Product=Карточка.Ссылка;L.Unit=Enums.Units.Piece;L.Quantity=1;L.Amount=N*10;
 D.Write();
EndDo;
''')

    def test_all_reports_accept_empty_main_database(self):
        for name in REPORTS:
            with self.subTest(name=name): self.assertEqual(self.report(name), [])

    def test_all_reports_run_after_reopen_without_changing_database(self):
        self.seed()
        expected = (['1','10','2','20'], ['Основной','2','30'], ['1','10','2','20'])
        self.vm.close(); self.context.close()
        before = self.path.read_bytes()
        with SQLiteDBContext(self.path) as reopened:
            vm=Interpreter(database_context=reopened, output=self.output.append)
            try:
                for name, values in zip(REPORTS, expected):
                    with self.subTest(name=name): self.assertEqual(self.report(name, vm), values)
            finally: vm.close()
        self.assertEqual(self.path.read_bytes(), before)

    def test_membership_report_filters_deleted_products(self):
        self.seed()
        self.vm.execute('Карточка.ПометкаУдаления=Истина;Карточка.Записать();')
        self.assertEqual(self.report('query-membership-report'), [])
        self.assertEqual(self.report('document-query-report'), ['Основной','2','30'])

    def test_derived_report_keeps_empty_receipt_with_zero_total(self):
        self.seed()
        self.vm.execute('D=Documents.Receipt.CreateDocument();D.Number="3";D.Date=Date(2024,1,3);D.Warehouse=Склад.Ссылка;D.State=Enums.States.Draft;D.Write();')
        self.assertEqual(self.report('derived-document-report'), ['1','10','2','20','3','0'])
        self.assertEqual(self.report('document-query-report'), ['Основной','2','30'])
