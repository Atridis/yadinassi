"""Original demo BSL over real catalog buffers; no native or import parity."""
from dataclasses import replace
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from uuid import uuid4

from yadinassi import Interpreter, BSLError
from yadinassi.catalog_backend import CatalogSchema, FieldSchema, TabularSectionSchema, BackendError
from yadinassi.database_context import SQLiteDBContext
from yadinassi.catalog_object_preparation import prepare_catalog_object
from test_sqlite_catalog_backend import configuration

SOURCE = (Path(__file__).parent / 'fixtures/demo_cf/source/Catalogs/Номенклатура/Ext/ObjectModule.bsl').read_text(encoding='utf-8-sig')


class CatalogObjectPreparationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        kind, warehouse, product = uuid4(), uuid4(), uuid4()
        # Explicit logical schema, not silently activating imported demo modules.
        schemas = (CatalogSchema(kind, 'ВидыНоменклатуры', 8, 100),
                   CatalogSchema(warehouse, 'Склады', 8, 100),
                   CatalogSchema(product, 'Номенклатура', 8, 100,
                       (FieldSchema(uuid4(), 'ВидНоменклатуры', 'catalog_ref', (), kind),),
                       (TabularSectionSchema(uuid4(), 'Склады', (
                           FieldSchema(uuid4(), 'Склад', 'catalog_ref', (), warehouse),)),)))
        self.context = SQLiteDBContext.create(Path(self.temp.name) / 'db.sqlite',
                                             replace(configuration(), catalogs=schemas))
        self.addCleanup(self.context.close)
        self.vm = Interpreter(database_context=self.context)
        self.addCleanup(self.vm.close)
        self.vm.execute('''
            Вид = Справочники.ВидыНоменклатуры.СоздатьЭлемент();
            Вид.Код = "1"; Вид.Наименование = "Товары"; Вид.Записать();
            Склад = Справочники.Склады.СоздатьЭлемент();
            Склад.Код = "1"; Склад.Наименование = "Основной"; Склад.Записать();
            Карточка = Справочники.Номенклатура.СоздатьЭлемент();
            Карточка.Код = "1"; Карточка.Наименование = "  Кабель USB-C  ";
            Карточка.ВидНоменклатуры = Вид.Ссылка;
            Строка = Карточка.Склады.Добавить(); Строка.Склад = Склад.Ссылка;
        ''')
        self.card = self.vm.variables['карточка']

    def prepare(self, source=SOURCE, **kwargs):
        return prepare_catalog_object(source, self.card, **kwargs)

    def test_original_bsl_accepts_and_trims_same_candidate_without_write(self):
        with patch.object(self.context.backend, 'begin_write', side_effect=AssertionError('write')):
            self.assertEqual(self.prepare(), (False, ()))
        self.assertEqual(self.card.get_member('Наименование'), 'Кабель USB-C')
        self.assertTrue(self.card.is_new())
        # The host separately commits precisely this candidate after preparation.
        self.card.write()
        self.assertEqual(self.vm.execute('Карточка.Ссылка.ПолучитьОбъект().Наименование'), 'Кабель USB-C')

    def test_original_bsl_missing_kind_and_rows_cancels(self):
        self.vm.execute('Карточка.ВидНоменклатуры=Справочники.ВидыНоменклатуры.ПустаяСсылка(); Карточка.Склады.Очистить();')
        cancel, records = self.prepare()
        self.assertTrue(cancel)
        self.assertEqual([r.field for r in records], ['ВидНоменклатуры', 'Склады'])
        self.assertTrue(self.card.is_new())

    def test_original_empty_and_duplicate_rows_have_exact_fields(self):
        self.vm.execute('Карточка.Склады.Добавить(); Строка=Карточка.Склады.Добавить(); Строка.Склад=Склад.Ссылка;')
        cancel, records = self.prepare()
        self.assertTrue(cancel)
        self.assertEqual([r.field for r in records], ['Склады[1].Склад', 'Склады[2].Склад'])
        self.assertIn('строке 1', records[1].text)

    def test_original_marked_references_cancel(self):
        self.vm.execute('Вид.ПометкаУдаления=Истина; Вид.Записать(); Склад.ПометкаУдаления=Истина; Склад.Записать();')
        cancel, records = self.prepare()
        self.assertTrue(cancel)
        self.assertEqual([r.field for r in records], ['ВидНоменклатуры', 'Склады[].Склад'])
        self.assertTrue(all('помечен' in r.text for r in records))

    def test_original_delete_skips_but_unmark_validates(self):
        self.vm.execute('Карточка.ПометкаУдаления=Истина; Карточка.Наименование=" x ";')
        self.assertEqual(self.prepare(), (False, ()))
        self.assertEqual(self.card.get_member('Наименование'), ' x ')
        self.vm.execute('Карточка.ПометкаУдаления=Ложь;')
        self.assertTrue(self.prepare()[0])
        self.assertEqual(self.card.get_member('Наименование'), 'x')

    def test_existing_cancellation_is_preserved(self):
        self.assertEqual(self.prepare(cancel=True), (True, ()))

    def test_direct_field_arguments_are_live_references(self):
        source = '''Процедура ПередЗаписью(Отказ) Изменить(Наименование); КонецПроцедуры
                    Процедура Изменить(Значение) Значение="Changed"; КонецПроцедуры'''
        self.assertEqual(self.prepare(source), (False, ()))
        self.assertEqual(self.card.get_member('Description'), 'Changed')

    def test_local_parameter_shadows_field(self):
        source = '''Процедура ПередЗаписью(Отказ) Локально("old"); КонецПроцедуры
                    Процедура Локально(Знач Наименование) Наименование="Changed"; КонецПроцедуры'''
        self.assertEqual(self.prepare(source), (False, ()))
        self.assertEqual(self.card.get_member('Description'), '  Кабель USB-C  ')

        schema = self.card._manager._schema
        self.card._manager._schema = replace(schema, fields=schema.fields + (
            FieldSchema(uuid4(), 'Отказ', 'boolean'),))
        with self.assertRaises(ValueError): self.prepare()

    def test_denies_write_io_globals_and_dynamic_execution(self):
        for body in ('ЭтотОбъект.Записать();', 'ЭтотОбъект.Write();',
                     'x=Справочники.Номенклатура;', 'x=Новый ЗаписьТекста;',
                     'Выполнить "ЭтотОбъект.Записать();";', 'x=ЭтотОбъект._manager;'):
            with self.subTest(body=body), patch.object(self.context.backend, 'begin_write', side_effect=AssertionError('write')):
                with self.assertRaises((ValueError, BSLError)):
                    self.prepare('Процедура ПередЗаписью(Отказ) '+body+' КонецПроцедуры')

        # A schema may legitimately contain a row field named like an object method.
        # It must not turn property reads into captured callable capabilities.
        schema = self.card._manager._schema
        section = schema.tabular_sections[0]
        self.card._manager._schema = replace(schema, tabular_sections=(replace(
            section, fields=section.fields + (FieldSchema(uuid4(), 'Write', 'string', (32,)),)),))
        with patch.object(self.context.backend, 'begin_write', side_effect=AssertionError('write')):
            with self.assertRaises((ValueError, BSLError)):
                self.prepare('Процедура ПередЗаписью(Отказ) f=ЭтотОбъект.Write; f(); КонецПроцедуры')

    def test_no_top_level_execution_or_context_crossing(self):
        for source in ('x=1;\n'+SOURCE,
                       '&НаСервере\nПроцедура ПередЗаписью(Отказ) КонецПроцедуры',
                       'Процедура ПередЗаписью(Знач Отказ) Отказ=Истина; КонецПроцедуры',
                       'Процедура ПередЗаписью() КонецПроцедуры'):
            with self.assertRaises(ValueError): self.prepare(source)

    def test_uncertain_commit_rejected_before_parsing_or_preparation(self):
        self.card._pending_write = ('pending',)
        with self.assertRaises(BackendError) as error: self.prepare('invalid source')
        self.assertEqual(error.exception.code, 'uncertain_commit')
        self.assertEqual(self.card.get_member('Description'), '  Кабель USB-C  ')

    def test_partial_mutation_on_error_is_not_rollback_or_success(self):
        source = '''Процедура ПередЗаписью(Отказ)
                     Наименование="Changed"; ЭтотОбъект.Записать(); КонецПроцедуры'''
        with self.assertRaises(BSLError): self.prepare(source)
        self.assertEqual(self.card.get_member('Description'), 'Changed')
        self.assertTrue(self.card.is_new())

    def test_row_numbers_are_read_only_current_positions_not_uuid(self):
        self.vm.execute('Вторая=Карточка.Склады.Добавить();')
        self.assertEqual(self.vm.execute('Вторая.НомерСтроки'), 2)
        self.assertEqual(self.vm.execute('Вторая.LineNumber'), 2)
        with self.assertRaises(BSLError): self.vm.execute('Вторая.НомерСтроки=9;')
        self.vm.execute('Карточка.Склады.Удалить(0);')
        self.assertEqual(self.vm.execute('Вторая.НомерСтроки'), 1)
        self.vm.execute('Карточка.Склады.Очистить();')
        with self.assertRaises(BSLError): self.vm.execute('Вторая.LineNumber')

    def test_bounded_text_expansion(self):
        body = 'x="' + 'x'*1024 + '";' + 'x=x+x;'*8
        with self.assertRaises((ValueError, BSLError)):
            self.prepare('Процедура ПередЗаписью(Отказ) '+body+' КонецПроцедуры')

    def test_message_limit_cannot_be_reported_as_success(self):
        body = 'm=Новый СообщениеПользователю; m.Текст="error";' + 'm.Сообщить();'*129
        with self.assertRaises((ValueError, BSLError)):
            self.prepare('Процедура ПередЗаписью(Отказ) '+body+' КонецПроцедуры')
