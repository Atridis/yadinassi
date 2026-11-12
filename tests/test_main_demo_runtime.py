"""One database end-to-end: original policy, inventory and explicit CLI grant."""
from pathlib import Path
from contextlib import redirect_stdout, redirect_stderr
from io import StringIO
import tempfile
import unittest
from yadinassi import Interpreter, cli
from yadinassi.database_context import SQLiteDBContext
from yadinassi.configuration_main_demo import PROFILE, import_main_demo_configuration
from yadinassi.catalog_object_preparation import CatalogWriteRefused, write_prepared_catalog_object
from yadinassi.catalog_backend import BackendError
from yadinassi.sqlite_launch import launch_snapshot
from test_main_demo_configuration import source, ROOT

SEED='''Вид=Справочники.ВидыНоменклатуры.СоздатьЭлемент(); Вид.Наименование="Товары"; Вид.Записать();
Склад=Справочники.Склады.СоздатьЭлемент(); Склад.Наименование="Основной"; Склад.Записать();
Карточка=Справочники.Номенклатура.СоздатьЭлемент(); Карточка.Наименование="  Кабель  ";
Карточка.ВидНоменклатуры=Вид.Ссылка; Строка=Карточка.Склады.Добавить(); Строка.Склад=Склад.Ссылка;
Карточка.Записать();'''

class MainDemoRuntimeTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup)
        self.path=Path(temp.name)/'main.sqlite'
        self.context=SQLiteDBContext.create_main_demo(self.path,
            import_main_demo_configuration(source(),profile=PROFILE));self.addCleanup(self.context.close)
        self.output=[];self.vm=Interpreter(database_context=self.context,output=self.output.append)
        self.addCleanup(self.vm.close)

    def test_fresh_empty_database_reopens_with_full_source(self):
        with SQLiteDBContext(self.path) as reopened:
            self.assertEqual(reopened.backend.accumulation_configuration.profile,PROFILE)
            self.assertEqual(len(reopened.backend.accumulation_configuration.catalogs),3)
        self.vm.execute('Q=New Query("SELECT COUNT(*) AS N FROM Catalog.Номенклатура");S=Q.Execute().Select();S.Next();Message(S.N);')
        self.assertEqual(self.output,['0'])

    def test_programmatic_write_cannot_skip_original_object_validation(self):
        self.vm.execute('Карточка=Справочники.Номенклатура.СоздатьЭлемент();Карточка.Наименование=" x ";')
        card=self.vm.variables['карточка']
        with self.assertRaises(CatalogWriteRefused) as refused:card.write()
        self.assertEqual(len(refused.exception.messages),3);self.assertTrue(card.is_new())

    def test_original_reference_section_trim_and_reopen(self):
        self.vm.execute(SEED+'Прочитано=Карточка.Ссылка.ПолучитьОбъект();')
        card=self.vm.variables['прочитано']
        self.assertEqual(card.get_member('наименование'),'Кабель')
        self.assertEqual(card.get_member('код'),'000000001')
        self.vm.execute('Message(Прочитано.Склады.Количество());')
        self.assertEqual(self.output,['1'])

    def test_posted_inventory_uses_same_russian_catalogs(self):
        self.vm.execute(SEED+'''D=Documents.Receipt.CreateDocument();D.Number="r1";D.Date=Date(2024,1,1);
D.Warehouse=Склад.Ссылка;L=D.Lines.Add();L.Product=Карточка.Ссылка;L.Quantity=5;L.Amount=10;
L.Unit=Enums.Units.Piece;D.Write(DocumentWriteMode.Posting);
Q=New Query("SELECT SUM(Quantity) AS N FROM AccumulationRegister.Stock");S=Q.Execute().Select();S.Next();Message(S.N);''')
        self.assertEqual(self.output,['5'])

    def test_foreign_preparation_cannot_replace_original_handler(self):
        self.vm.execute('Карточка=Справочники.Номенклатура.СоздатьЭлемент();')
        with self.assertRaises(BackendError):write_prepared_catalog_object(
            'Процедура ПередЗаписью(Отказ) КонецПроцедуры',self.vm.variables['карточка'])

    def test_launch_snapshot_preserves_main_demo_route(self):
        snapshot=launch_snapshot(self.context.backend)
        self.assertEqual((snapshot.profile,snapshot.route),(PROFILE,'main-demo'))
        self.assertEqual(len(snapshot.files),33)

    def test_cli_creates_one_main_demo_from_canonical_xml(self):
        path=self.path.with_name('cli.sqlite');out=StringIO();err=StringIO()
        with redirect_stdout(out),redirect_stderr(err):
            code=cli.main(['--create-demo-db',str(path),'--import-xml',str(ROOT/'examples/demo')])
        self.assertEqual(code,0,err.getvalue())
        with SQLiteDBContext(path) as reopened:self.assertEqual(reopened.backend.accumulation_configuration.profile,PROFILE)
