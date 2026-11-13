"""Fresh original product admission and mandatory bounded object policy."""
from contextlib import closing
from dataclasses import replace
from hashlib import sha256
from legacy_demo_fixture import legacy_demo_files
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch
from uuid import uuid4

from yadinassi import Interpreter
from yadinassi.catalog_backend import BackendError
from yadinassi.catalog_object_preparation import CatalogWriteRefused, write_prepared_catalog_object
from yadinassi.configuration_xml import import_demo_products_configuration
from yadinassi.database_context import SQLiteDBContext
from yadinassi.sqlite_catalog import SQLiteCatalogBackend


class DemoProductsProfileTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / 'products.sqlite'
        self.files = legacy_demo_files()
        self.backend = SQLiteCatalogBackend.create_demo_products(self.path, self.files)
        self.addCleanup(self.backend.close)
        self.schemas = {s.name: s for s in self.backend._schemas}
        self.product = self.schemas['Номенклатура']

    def vm(self):
        context = SQLiteDBContext(self.path)
        self.addCleanup(context.close)
        vm = Interpreter(database_context=context)
        self.addCleanup(vm.close)
        return vm

    def test_original_inventory_sections_and_source_binding(self):
        self.assertEqual(set(self.schemas), {'ВидыНоменклатуры', 'Склады', 'Номенклатура'})
        self.assertEqual(self.backend.storage_version, 6)
        self.assertEqual(self.backend.export_configuration(), self.files)
        self.assertTrue(self.backend.capabilities().catalog_tabular_sections)
        self.assertEqual(self.product.description_length, 150)
        self.assertEqual(self.product.fields[0].target_catalog_id,
                         self.schemas['ВидыНоменклатуры'].identity)
        self.assertEqual(self.product.tabular_sections[0].fields[0].target_catalog_id,
                         self.schemas['Склады'].identity)
        self.assertEqual(set(self.backend.active_form_catalogs()),
                         {self.product.identity, self.schemas['ВидыНоменклатуры'].identity})
        record = self.backend.read_form_source(self.product.identity)
        source = self.backend.catalog_write_preparation(self.product.identity,
                                                        expected=record.identity)
        self.assertEqual(source, self.files['Catalogs/Номенклатура/Ext/ObjectModule.bsl'].decode('utf-8-sig'))
        with self.assertRaisesRegex(BackendError, 'schema_changed'):
            self.backend.catalog_write_preparation(self.product.identity,
                expected=replace(record.identity, database_id=uuid4()))
        self.assertIsNone(self.backend.catalog_write_preparation(self.schemas['Склады'].identity))
        self.backend.close()
        with closing(SQLiteCatalogBackend(self.path)) as reopened:
            self.assertEqual(reopened.catalog_write_preparation(self.product.identity), source)

    def test_ordinary_create_cannot_activate_and_archive_mutations_refuse(self):
        imported = import_demo_products_configuration(self.files)
        for active in (True, False):
            with self.assertRaisesRegex(BackendError, 'unsupported'):
                SQLiteCatalogBackend.create(Path(self.temp.name) / 'wrong.sqlite', imported, activate=active)
        altered = dict(self.files)
        altered['Catalogs/Номенклатура/Ext/ObjectModule.bsl'] += b'\n'
        with self.assertRaises(ValueError): import_demo_products_configuration(altered)

    def test_programmatic_write_cannot_skip_original_validation(self):
        vm = self.vm()
        vm.execute('Карточка=Справочники.Номенклатура.СоздатьЭлемент(); Карточка.Наименование=" x ";')
        card = vm.variables['карточка']
        with self.assertRaises(CatalogWriteRefused) as refused: card.write()
        self.assertEqual(len(refused.exception.messages), 3)
        self.assertTrue(card.is_new())
        with self.assertRaisesRegex(BackendError, 'schema_changed'):
            write_prepared_catalog_object('Процедура ПередЗаписью(Отказ) КонецПроцедуры', card)

    def test_programmatic_valid_write_reopen_and_deletion_bypass(self):
        vm = self.vm()
        vm.execute('''
            Вид=Справочники.ВидыНоменклатуры.СоздатьЭлемент();
            Вид.Наименование="Товары"; Вид.Записать();
            Склад=Справочники.Склады.СоздатьЭлемент();
            Склад.Наименование="Основной"; Склад.Записать();
            Карточка=Справочники.Номенклатура.СоздатьЭлемент();
            Карточка.Наименование="  Кабель  ";
            Карточка.ВидНоменклатуры=Вид.Ссылка;
            Строка=Карточка.Склады.Добавить(); Строка.Склад=Склад.Ссылка;
            Карточка.Записать();
            Прочитано=Карточка.Ссылка.ПолучитьОбъект();
        ''')
        card = vm.variables['прочитано']
        self.assertEqual(card.get_member('наименование'), 'Кабель')
        self.assertEqual(card.get_member('код'), '000000001')
        vm.execute('''
            Пустая=Справочники.Номенклатура.СоздатьЭлемент();
            Пустая.ПометкаУдаления=Истина; Пустая.Записать();
        ''')
        self.assertFalse(vm.variables['пустая'].is_new())

    def test_source_drift_refuses_policy_and_programmatic_write(self):
        vm = self.vm()
        vm.execute('Карточка=Справочники.Номенклатура.СоздатьЭлемент();')
        path = 'Catalogs/Номенклатура/Forms/ФормаСписка/Ext/Form/Module.bsl'
        raw = self.files[path] + b'\n'
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute('UPDATE configuration_file SET content=?,sha256=? WHERE path=?',
                       (raw, sha256(raw).hexdigest(), path))
        with self.assertRaisesRegex(BackendError, 'schema_changed'):
            self.backend.catalog_write_preparation(self.product.identity)
        with self.assertRaisesRegex(BackendError, 'schema_changed'):
            vm.variables['карточка'].write()
