"""Atomic original demo object checks over real references and section rows."""
from contextlib import closing
from dataclasses import replace
from pathlib import Path
import sqlite3
import unittest
from unittest.mock import patch
from uuid import uuid4

import test_catalog_object_preparation as fixture
from test_catalog_commit_cleanup_recovery import FaultConnection
from test_sqlite_catalog_backend import configuration
from yadinassi import BSLError, Interpreter
from yadinassi.db.catalog.catalog_backend import BackendError, CatalogKey
from yadinassi.db.catalog.catalog_object_preparation import (
    CatalogWriteRefused, write_prepared_catalog_object)
from yadinassi.db.database_context import SQLiteDBContext
from yadinassi.db.sqlite.sqlite_catalog import SQLiteCatalogBackend, _View
from yadinassi.types.unique_identifiers import BSLUUID


class CatalogObjectWriteTests(unittest.TestCase):
    def setUp(self):
        fixture.CatalogObjectPreparationTests.setUp(self)

    def write(self, source=fixture.SOURCE, **kwargs):
        return write_prepared_catalog_object(source, self.card, **kwargs)

    def pending(self, fault='after'):
        original = self.context.backend.begin_write
        def begin(operation):
            view = original(operation)
            view._connection = FaultConnection(view._connection, commit_fault=fault)
            return view
        with patch.object(self.context.backend, 'begin_write', begin):
            with self.assertRaisesRegex(BackendError, 'uncertain_commit'):
                self.write()
        self.assertTrue(self.card._uncertain_write)
        self.assertIsNone(self.card._pending_write)

    def test_original_checks_and_real_save_reopen_with_references_and_rows(self):
        self.assertEqual(self.write(), ())
        self.assertFalse(self.card.is_new())
        self.assertEqual(self.card.get_member('Description'), 'Кабель USB-C')
        context = SQLiteDBContext(self.context.path)
        self.addCleanup(context.close)
        vm = Interpreter(database_context=context)
        self.addCleanup(vm.close)
        vm.execute('Карточка=Справочники.Номенклатура.НайтиПоКоду("1").ПолучитьОбъект();')
        self.assertEqual(vm.execute('Карточка.Наименование'), 'Кабель USB-C')
        self.assertEqual(vm.execute('Карточка.ВидНоменклатуры.Наименование'), 'Товары')
        self.assertEqual(vm.execute('Карточка.Склады.Получить(0).Склад.Наименование'), 'Основной')

    def reference_read_probes(self, observe):
        read_catalog = _View.read_catalog
        read_marks = _View._read_catalog_reference_marks
        def read(view, key):
            result = read_catalog(view, key)
            observe(view, key)
            return result
        def marks(view, schema, identities):
            result = read_marks(view, schema, identities)
            for identity in identities:
                observe(view, CatalogKey(view.database_id, schema.identity, identity))
            return result
        return patch.object(_View, 'read_catalog', read), patch.object(_View, '_read_catalog_reference_marks', marks)

    def test_reference_reads_use_writer_view_not_separate_backend_reads(self):
        seen = []
        def observe(view, key):
            seen.append((key, view, self.context.backend._active, view._connection.in_transaction))
        read, marks = self.reference_read_probes(observe)
        with patch.object(self.context.backend, 'begin_read', side_effect=AssertionError('outside read')), \
             read, marks:
            self.write()
        self.assertCountEqual([key for key, *_ in seen],
                              [self.vm.variables[name]._key for name in ('вид', 'склад')])
        for _, view, active_view, in_transaction in seen:
            self.assertIs(view, seen[0][1])
            self.assertIs(view, active_view)
            self.assertTrue(in_transaction)

    def test_missing_kind_and_empty_sections_refuse_without_write(self):
        self.vm.execute('Карточка.ВидНоменклатуры=Справочники.ВидыНоменклатуры.ПустаяСсылка(); Карточка.Склады.Очистить();')
        with patch.object(_View, 'create', side_effect=AssertionError('write')):
            with self.assertRaises(CatalogWriteRefused) as error:
                self.write()
        self.assertEqual([m.field for m in error.exception.messages], ['ВидНоменклатуры', 'Склады'])
        self.assertTrue(self.card.is_new())
        self.assertIsNone(self.card._pending_write)
        self.assertIsNone(self.context.backend._active)

    def test_marked_reference_rejected_before_record_changes(self):
        self.vm.execute('Вид.ПометкаУдаления=Истина; Вид.Записать();')
        with patch.object(_View, 'create', side_effect=AssertionError('write')):
            with self.assertRaises(CatalogWriteRefused) as error:
                self.write()
        self.assertEqual([m.field for m in error.exception.messages], ['ВидНоменклатуры'])
        self.assertIn('помечен', error.exception.messages[0].text)

    def test_missing_reference_has_original_message_before_storage_error(self):
        target = self.vm.variables['вид']._manager
        self.card.set_member('ВидНоменклатуры', target.get_ref(BSLUUID(str(uuid4()))))
        with self.assertRaises(CatalogWriteRefused) as error:
            self.write()
        self.assertIn('не существует', error.exception.messages[0].text)
        self.assertIsNone(self.card._pending_write)

    def test_duplicate_and_empty_unsaved_rows_refuse(self):
        self.vm.execute('Карточка.Склады.Добавить(); Строка=Карточка.Склады.Добавить(); Строка.Склад=Склад.Ссылка;')
        with self.assertRaises(CatalogWriteRefused) as error:
            self.write()
        self.assertEqual([m.field for m in error.exception.messages],
                         ['Склады[1].Склад', 'Склады[2].Склад'])
        self.assertTrue(self.card.is_new())

    def test_writer_lock_prevents_reference_mark_between_check_and_save(self):
        attempts = []
        def observe(view, key):
            with closing(sqlite3.connect(self.context.path, timeout=0)) as other:
                table = self.context.backend._layout.table_name(key.catalog_id)
                with self.assertRaisesRegex(sqlite3.OperationalError, 'locked'):
                    other.execute('UPDATE "' + table + '" SET deletion_mark=1 WHERE record_id=?',
                                  (str(key.record_id),))
            attempts.append(key)
        read, marks = self.reference_read_probes(observe)
        with read, marks:
            self.write()
        self.assertCountEqual(attempts, [self.vm.variables[name]._key for name in ('вид', 'склад')])
        self.assertFalse(self.card.is_new())

    def test_target_changed_before_begin_is_observed_in_writer_snapshot(self):
        original = self.context.backend.begin_write
        def begin(operation):
            other = SQLiteDBContext(self.context.path)
            try:
                vm = Interpreter(database_context=other)
                try:
                    vm.execute('O=Catalogs.Склады.FindByCode("1").GetObject(); O.DeletionMark=True; O.Write();')
                finally:
                    vm.close()
            finally:
                other.close()
            return original(operation)
        with patch.object(self.context.backend, 'begin_write', begin):
            with self.assertRaises(CatalogWriteRefused) as error:
                self.write()
        self.assertIn('Склад помечен', error.exception.messages[0].text)

    def test_existing_cancellation_and_delete_mark_branch(self):
        with self.assertRaises(CatalogWriteRefused):
            self.write(cancel=True)
        self.vm.execute('Карточка.ПометкаУдаления=Истина; Карточка.Наименование=" x "; Карточка.Склады.Очистить();')
        self.assertEqual(self.write(), ())
        self.assertEqual(self.card.get_member('Description'), ' x ')
        self.vm.execute('Карточка.ПометкаУдаления=Ложь;')
        with self.assertRaises(CatalogWriteRefused):
            self.write()

    def test_original_revision_conflict_is_not_overwritten(self):
        self.write()
        self.vm.execute('Другой=Карточка.Ссылка.ПолучитьОбъект(); Другой.Наименование="Другой"; Другой.Записать();')
        self.card.set_member('Description', 'Изменено')
        with self.assertRaisesRegex(BackendError, 'conflict'):
            self.write()
        self.assertEqual(self.vm.execute('Карточка.Ссылка.ПолучитьОбъект().Наименование'), 'Другой')

    def test_error_after_buffer_change_rolls_back_transaction_not_candidate(self):
        source = ('Процедура ПередЗаписью(Отказ) '
                  'Наименование="Changed"; Ноль=0; Результат=1/Ноль; КонецПроцедуры')
        with patch.object(_View, 'create', side_effect=AssertionError('write')):
            with self.assertRaises(BSLError):
                self.write(source)
        self.assertEqual(self.card.get_member('Description'), 'Changed')
        self.assertTrue(self.card.is_new())
        self.assertIsNone(self.context.backend._active)

    def test_uncertain_after_commit_never_reexecutes_preparation_or_commits_again(self):
        self.pending()
        with patch('yadinassi.db.catalog.catalog_object_preparation._prepare_catalog_object', side_effect=AssertionError('BSL replay')), \
             patch.object(_View, 'commit', side_effect=AssertionError('second commit')):
            for write in (self.write, self.card.write):
                with self.assertRaisesRegex(BackendError, 'uncertain_commit'):
                    write()
        self.assertTrue(self.card.is_new())
        fresh = self.vm.execute('Справочники.Номенклатура.НайтиПоКоду("1").ПолучитьОбъект()')
        self.assertEqual(fresh.get_member('Description'), 'Кабель USB-C')
        self.assertEqual(len(fresh._sections['склады']._rows), 1)

    def test_uncertain_before_commit_rolls_back_and_fresh_request_revalidates(self):
        self.pending('before')
        self.assertTrue(self.vm.execute('Справочники.Номенклатура.НайтиПоКоду("1").Пустая()'))
        self.vm.execute('Вид.ПометкаУдаления=Истина; Вид.Записать();')
        with self.assertRaisesRegex(BackendError, 'uncertain_commit'):
            self.card.write()
        self.assertTrue(self.card.is_new())
        fresh = self.vm.execute('''Новая=Справочники.Номенклатура.СоздатьЭлемент();
            Новая.Код="1"; Новая.Наименование="Кабель USB-C"; Новая.ВидНоменклатуры=Вид.Ссылка;
            Строка=Новая.Склады.Добавить(); Строка.Склад=Склад.Ссылка;
            Новая''')
        with self.assertRaises(CatalogWriteRefused):
            write_prepared_catalog_object(fixture.SOURCE, fresh)
        self.assertTrue(fresh.is_new())

    def test_uncertain_cannot_be_cleared_by_source_or_backend_replacement(self):
        self.pending()
        with self.assertRaisesRegex(BackendError, 'uncertain_commit'):
            self.write(fixture.SOURCE + '\n')
        backend = self.context.backend
        replacement = SQLiteCatalogBackend(self.context.path)
        self.addCleanup(replacement.close)
        self.context._backend = replacement
        try:
            with self.assertRaisesRegex(BackendError, 'uncertain_commit'):
                self.write()
        finally:
            self.context._backend = backend
        self.assertTrue(self.card._uncertain_write)

    def test_preparation_cannot_relabel_an_ordinary_uncertain_write(self):
        original = _View.commit
        def uncertain(view, **kwargs):
            original(view, **kwargs)
            raise BackendError('uncertain_commit')
        with patch.object(_View, 'commit', uncertain), self.assertRaises(BackendError):
            self.card.write()
        for write in (self.write, self.card.write):
            with self.assertRaisesRegex(BackendError, 'uncertain_commit'):
                write()

    def test_nonidempotent_preparation_is_not_replayed_on_uncertain_write(self):
        source = 'Процедура ПередЗаписью(Отказ) Наименование=Наименование+"!"; КонецПроцедуры'
        original = self.context.backend.begin_write
        def begin(operation):
            view = original(operation)
            view._connection = FaultConnection(view._connection, commit_fault='before')
            return view
        with patch.object(self.context.backend, 'begin_write', begin), self.assertRaises(BackendError):
            self.write(source)
        frozen = self.card.get_member('Description')
        with self.assertRaisesRegex(BackendError, 'uncertain_commit'):
            self.write(source)
        self.assertEqual(self.card.get_member('Description'), frozen)
        self.assertIsNone(self.card._pending_write)

    def test_guarded_auto_numbering_refusal_and_uncertain_commit(self):
        schemas = tuple(replace(s, numbering='decimal_v1') if s.name == 'Номенклатура'
                        else s for s in self.context.backend._schemas)
        context = SQLiteDBContext.create(Path(self.temp.name) / 'numbered.sqlite',
                                         replace(configuration(), catalogs=schemas))
        self.addCleanup(context.close)
        vm = Interpreter(database_context=context)
        self.addCleanup(vm.close)
        vm.execute('''
            K=Catalogs.ВидыНоменклатуры.CreateItem(); K.Code="1"; K.Description="Товары"; K.Write();
            W=Catalogs.Склады.CreateItem(); W.Code="1"; W.Description="Основной"; W.Write();
            P=Catalogs.Номенклатура.CreateItem(); P.Description="x"; P.ВидНоменклатуры=K.Ref;
            R=P.Склады.Add(); R.Склад=W.Ref;
        ''')
        obj = vm.variables['p']
        with self.assertRaises(CatalogWriteRefused):
            write_prepared_catalog_object(fixture.SOURCE, obj)
        self.assertEqual(obj.get_member('Code'), '')
        obj.set_member('Description', ' Кабель ')
        original = context.backend.begin_write
        def begin(operation):
            view = original(operation)
            view._connection = FaultConnection(view._connection, commit_fault='after')
            return view
        with patch.object(context.backend, 'begin_write', begin), self.assertRaises(BackendError):
            write_prepared_catalog_object(fixture.SOURCE, obj)
        self.assertTrue(obj._uncertain_write)
        self.assertEqual(obj.get_member('Code'), '')
        with patch('yadinassi.db.catalog.catalog_object_preparation._prepare_catalog_object', side_effect=AssertionError('BSL replay')):
            with self.assertRaisesRegex(BackendError, 'uncertain_commit'):
                write_prepared_catalog_object(fixture.SOURCE, obj)
        fresh = vm.execute('Справочники.Номенклатура.НайтиПоКоду("00000001").ПолучитьОбъект()')
        self.assertEqual(fresh.get_member('Code'), '00000001')
        self.assertEqual(fresh.get_member('Description'), 'Кабель')

    def test_existing_update_after_uncertain_rollback_reloads_unchanged_sections(self):
        self.write()
        section = self.card.get_member('Склады')
        self.assertFalse(section._dirty)
        self.card.set_member('Description', ' Новый кабель ')
        self.pending('before')
        with self.assertRaisesRegex(BackendError, 'uncertain_commit'):
            self.write()
        fresh = self.vm.execute('Карточка.Ссылка.ПолучитьОбъект()')
        self.assertEqual(len(fresh._sections['склады']._rows), 1)
        fresh.set_member('Description', ' Новый кабель ')
        write_prepared_catalog_object(fixture.SOURCE, fresh)
        self.assertEqual(self.vm.execute('Карточка.Ссылка.ПолучитьОбъект().Наименование'), 'Новый кабель')
        self.assertEqual(self.vm.execute('Карточка.Ссылка.ПолучитьОбъект().Склады.Количество()'), 1)

    def test_uncertain_commit_locks_scalar_and_row_edits(self):
        self.pending()
        section = self.card.get_member('Склады')
        for action in (lambda: self.card.set_member('Description', 'replacement'),
                       section.add,
                       lambda: section._rows[0].set_member('Склад', self.vm.variables['склад'].get_member('Ref'))):
            with self.subTest(action=action), self.assertRaisesRegex(BackendError, 'uncertain_commit'):
                action()
        with self.assertRaisesRegex(BackendError, 'uncertain_commit'):
            self.write()

    def test_direct_reference_attributes_and_presentation_fail_closed(self):
        for expression in ('ВидНоменклатуры.Наименование', 'Строка(ВидНоменклатуры)'):
            source = 'Процедура ПередЗаписью(Отказ) X=' + expression + '; КонецПроцедуры'
            with self.subTest(expression=expression), \
                 patch.object(_View, 'create', side_effect=AssertionError('write')):
                with self.assertRaises((BSLError, BackendError)):
                    self.write(source)
            self.assertTrue(self.card.is_new())
            self.assertIsNone(self.context.backend._active)
