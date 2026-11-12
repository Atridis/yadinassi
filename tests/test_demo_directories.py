"""Original warehouses and kinds in one durable, bounded local application."""
from contextlib import closing
from dataclasses import replace
from hashlib import sha256
from legacy_demo_fixture import legacy_demo_files
from pathlib import Path
import json
import sqlite3
import tempfile
import unittest
from unittest.mock import patch
from uuid import uuid4

from yadinassi import Interpreter
from yadinassi.catalog_backend import BackendError, CatalogDraft, CatalogKey
from yadinassi.configuration_xml import (import_demo_directories_configuration,
    DEMO_KINDS_SOURCE_ISSUE, DEMO_DIRECTORIES_SOURCE_ISSUE)
from yadinassi.database_context import SQLiteDBContext
from yadinassi.sqlite_catalog import SQLiteCatalogBackend, _View
from yadinassi.ui.catalog_editor import CatalogEditorApplication
from test_catalog_commit_cleanup_recovery import FaultConnection


class DemoDirectoriesTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / 'demo.sqlite'
        self.files = legacy_demo_files()
        self.backend = SQLiteCatalogBackend.create_demo_directories(self.path, self.files)
        self.addCleanup(lambda: self.backend.close())
        self.schemas = {s.name: s for s in self.backend._schemas}
        self.warehouse = self.schemas['Склады']
        self.kind = self.schemas['ВидыНоменклатуры']

    def app(self, name='Склады'):
        app = CatalogEditorApplication(SQLiteDBContext(self.path))
        self.addCleanup(app.close)
        app.select(str(self.schemas[name].identity))
        app.open()
        return app

    def draft(self, name='Основной склад'):
        return CatalogDraft(CatalogKey(self.backend.database_id, self.warehouse.identity,
            uuid4()), '', name, False, (), auto_number=True)

    def save(self, draft, operation=None):
        tx = self.backend.begin_write(operation or uuid4())
        try:
            tx.create(draft)
            return tx.commit_outcomes()[0]
        finally:
            tx.close()

    def mutate_source(self):
        path = 'Catalogs/Номенклатура/Ext/ObjectModule.bsl'
        raw = self.files[path] + b'\n'
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute('UPDATE configuration_file SET content=?,sha256=? WHERE path=?',
                       (raw, sha256(raw).hexdigest(), path))

    def test_full_archive_two_catalogs_only_one_original_form(self):
        self.assertEqual(self.backend.storage_version, 6)
        self.assertEqual(set(self.schemas), {'ВидыНоменклатуры', 'Склады'})
        self.assertEqual(self.backend.export_configuration(), self.files)
        self.assertEqual(self.backend.active_form_catalogs(), (self.kind.identity,))
        self.assertEqual(self.backend.read_form_source(self.kind.identity).catalog_name,
                         'ВидыНоменклатуры')
        with self.assertRaisesRegex(BackendError, 'not_found'):
            self.backend.read_form_source(self.warehouse.identity)
        imported = import_demo_directories_configuration(self.files)
        self.assertEqual(imported.modules, ())
        self.assertFalse(self.backend.capabilities().catalog_tabular_sections)

    def test_ordinary_create_and_wrong_profile_cannot_activate(self):
        imported = import_demo_directories_configuration(self.files)
        for activate in (False, True):
            with self.subTest(activate=activate), self.assertRaisesRegex(BackendError, 'unsupported'):
                SQLiteCatalogBackend.create(Path(self.temp.name) / 'wrong.sqlite',
                                            imported, activate=activate)
        with self.assertRaisesRegex(BackendError, 'unsupported'):
            SQLiteCatalogBackend.create(Path(self.temp.name) / 'wrong.sqlite',
                imported, _source_profile='demo_kinds_v1')
        forged = replace(imported, catalogs=(self.kind,))
        with self.assertRaisesRegex(BackendError, 'unsupported'):
            SQLiteCatalogBackend.create(Path(self.temp.name) / 'wrong.sqlite',
                forged, _source_profile='demo_directories_v1')

    def test_all_source_bytes_remain_closed(self):
        variants = [dict(self.files), dict(self.files), dict(self.files)]
        variants[0]['Catalogs/Склады.xml'] += b'\n'
        variants[1].pop('Catalogs/Номенклатура/Ext/ObjectModule.bsl')
        variants[2]['Catalogs/Склады/Ext/ObjectModule.bsl'] = b'Procedure BeforeWrite(Cancel) EndProcedure'
        for files in variants:
            with self.subTest(paths=len(files)), self.assertRaises(ValueError):
                import_demo_directories_configuration(files)

    def test_old_kinds_and_inert_profiles_are_not_upgraded(self):
        old = SQLiteCatalogBackend.create_demo_kinds(Path(self.temp.name) / 'kinds.sqlite', self.files)
        self.addCleanup(old.close)
        self.assertEqual([s.name for s in old._schemas], ['ВидыНоменклатуры'])
        old.close()
        reopened = SQLiteCatalogBackend(Path(self.temp.name) / 'kinds.sqlite')
        self.addCleanup(reopened.close)
        self.assertEqual([s.name for s in reopened._schemas], ['ВидыНоменклатуры'])
        inert = SQLiteCatalogBackend.create_inert(Path(self.temp.name) / 'inert.sqlite', self.files)
        self.addCleanup(inert.close)
        self.assertEqual(inert.active_form_catalogs(), ())
        with self.assertRaisesRegex(BackendError, 'unsupported'):
            inert.begin_write(uuid4())
        inert.close()
        reopened_inert = SQLiteCatalogBackend(Path(self.temp.name) / 'inert.sqlite')
        self.addCleanup(reopened_inert.close)
        self.assertEqual(reopened_inert.storage_version, 5)
        self.assertFalse(reopened_inert.capabilities().catalog_create)

    def test_profile_marker_cannot_be_swapped_to_kinds_only(self):
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute('UPDATE database_info SET activation_issues=?',
                       (json.dumps([DEMO_KINDS_SOURCE_ISSUE]),))
        with self.assertRaises(BackendError):
            self.backend.begin_write(uuid4())
        with self.assertRaises(BackendError):
            SQLiteCatalogBackend(self.path)
        old_path = Path(self.temp.name) / 'kinds.sqlite'
        old = SQLiteCatalogBackend.create_demo_kinds(old_path, self.files)
        old.close()
        with closing(sqlite3.connect(old_path)) as db, db:
            db.execute('UPDATE database_info SET activation_issues=?',
                       (json.dumps([DEMO_DIRECTORIES_SOURCE_ISSUE]),))
        with self.assertRaises(BackendError):
            SQLiteCatalogBackend(old_path)

    def test_independent_numbering_and_products_stay_inert(self):
        context = SQLiteDBContext(self.path)
        self.addCleanup(context.close)
        vm = Interpreter(database_context=context)
        vm.execute('W=Catalogs.Склады.CreateItem(); W.Description="Основной"; W.Write();'
                   'K=Catalogs.ВидыНоменклатуры.CreateItem(); K.Description="Товары"; K.Write();')
        self.assertEqual(vm.execute('W.Code'), '000000001')
        self.assertEqual(vm.execute('K.Code'), '000000001')
        with self.assertRaises(Exception):
            vm.execute('Catalogs.Номенклатура.CreateItem()')
        self.assertEqual(self.save(self.draft()).code, '000000002')

    def test_warehouse_create_save_close_and_database_reopen(self):
        app = self.app()
        editor = app.editor
        self.assertFalse(editor.snapshot()['originalForm'])
        editor.change('InputData1', 'Основной склад')
        editor.command('SaveButton')
        self.assertEqual(editor.save_state, 'saved')
        self.assertEqual(editor.snapshot()['fields'][0]['inputText'], '000000001')
        reference = editor._saved_reference()
        app.event('closeCard')
        app.close()
        app = CatalogEditorApplication(SQLiteDBContext(self.path))
        self.addCleanup(app.close)
        app.select(str(self.warehouse.identity))
        app.open(reference)
        self.assertEqual(app.editor.snapshot()['fields'][1]['inputText'], 'Основной склад')
        self.assertFalse(app.editor.snapshot()['dirty'])

    def test_warehouse_edit_and_unchanged_save_do_not_duplicate(self):
        app = self.app()
        editor = app.editor
        editor.change('InputData1', 'Склад')
        editor.command('SaveButton')
        editor.change('InputData1', 'Главный склад')
        editor.command('SaveButton')
        self.assertEqual(editor.save_state, 'saved')
        with patch.object(editor.object, 'write', side_effect=AssertionError('duplicate write')):
            editor.command('SaveButton')
        self.assertEqual(editor.save_state, 'unchanged')
        reference = editor._saved_reference()
        app.event('closeCard')
        app.open(reference)
        self.assertEqual(app.editor.snapshot()['fields'][1]['inputText'], 'Главный склад')

    def test_warehouse_dirty_close_and_discard_do_not_write(self):
        app = self.app()
        app.editor.change('InputData1', 'Не сохранять')
        app.event('closeCard')
        self.assertIsNotNone(app.editor)
        with patch.object(app.editor.object, 'write', side_effect=AssertionError('discard write')):
            app.event('command', control='CancelButton')
        self.assertIsNone(app.editor)
        self.assertEqual(self.save(self.draft()).code, '000000001')

    def test_original_kind_handlers_remain_active_beside_warehouse(self):
        app = self.app('ВидыНоменклатуры')
        self.assertTrue(app.editor.snapshot()['originalForm'])
        app.editor.change('InputData1', ' x ')
        app.editor.command('SaveButton')
        self.assertEqual(app.editor.save_state, 'rejected')
        app.editor.change('InputData1', ' Товары ')
        app.editor.command('SaveButton')
        self.assertEqual(app.editor.save_state, 'saved')
        self.assertEqual(app.editor.snapshot()['fields'][1]['inputText'], 'Товары')

    def test_archived_product_drift_blocks_warehouse_write_but_not_receipt(self):
        draft = self.draft()
        operation = uuid4()
        self.save(draft, operation)
        self.mutate_source()
        with self.assertRaises(BackendError):
            self.save(self.draft())
        with self.assertRaises(BackendError):
            self.backend.active_form_catalogs()
        with patch.object(_View, 'create', side_effect=AssertionError('replay')):
            self.assertEqual(self.backend.resolve_write_outcome(operation, draft).code, '000000001')

    def test_ui_source_drift_retains_unsaved_warehouse_buffer(self):
        app = self.app()
        app.editor.change('InputData1', 'Не потерять')
        self.mutate_source()
        app.editor.command('SaveButton')
        self.assertEqual(app.editor.save_state, 'rejected')
        self.assertTrue(app.editor.snapshot()['dirty'])
        self.assertEqual(app.editor.snapshot()['fields'][1]['inputText'], 'Не потерять')
        with closing(sqlite3.connect(self.path)) as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM commit_receipt').fetchone()[0], 0)

    def test_uncertain_warehouse_commit_resolves_once(self):
        draft = self.draft()
        operation = uuid4()
        tx = self.backend.begin_write(operation)
        tx.create(draft)
        tx._connection = FaultConnection(tx._connection, commit_fault='after')
        with self.assertRaisesRegex(BackendError, 'uncertain_commit'):
            tx.commit_outcomes()
        self.backend.close()
        self.backend = SQLiteCatalogBackend(self.path)
        with patch.object(_View, 'create', side_effect=AssertionError('replay')):
            self.assertEqual(self.backend.resolve_write_outcome(operation, draft).code, '000000001')
        self.assertEqual(self.save(self.draft()).code, '000000002')

    def test_ui_pending_refresh_never_writes_twice(self):
        app = self.app()
        app.editor.change('InputData1', 'Склад')
        with patch.object(app.editor, '_refresh', side_effect=BackendError('storage_error')):
            app.editor.command('SaveButton')
        self.assertTrue(app.editor.pending_refresh)
        with patch.object(_View, 'commit', side_effect=AssertionError('recommit')):
            app.editor.command('SaveButton')
        self.assertEqual(app.editor.save_state, 'saved')

    def test_read_only_profile_has_no_write_authority(self):
        backend = SQLiteCatalogBackend(self.path, read_only=True)
        self.addCleanup(backend.close)
        self.assertEqual(backend.active_form_catalogs(), (self.kind.identity,))
        self.assertEqual(backend.export_configuration(), self.files)
        with self.assertRaisesRegex(BackendError, 'unsupported'):
            backend.begin_write(uuid4())

    def test_generation_change_blocks_new_write_and_historical_receipt(self):
        draft = self.draft()
        operation = uuid4()
        self.save(draft, operation)
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute('UPDATE database_info SET generation=generation+1')
        with self.assertRaisesRegex(BackendError, 'schema_changed'):
            self.backend.begin_write(uuid4())
        with self.assertRaisesRegex(BackendError, 'schema_changed'):
            self.backend.resolve_write_outcome(operation, draft)

    def test_warehouse_mark_unmark_preserves_code_and_reopens(self):
        app = self.app()
        editor = app.editor
        editor.change('InputData1', 'Основной склад'); editor.command('SaveButton')
        reference = editor._saved_reference(); code = editor.object.get_member('Code')
        control = next(f['control'] for f in editor.snapshot()['fields'] if f['name'] == 'DeletionMark')
        for value in (True, False):
            editor.change(control, value)
            self.assertNotEqual(editor.object.get_member('DeletionMark'), value)
            editor.command('SaveButton')
            self.assertEqual(editor.object.get_member('DeletionMark'), value)
            self.assertEqual(editor.object.get_member('Code'), code)
            app.event('closeCard')
            self.assertEqual(app.snapshot()['state']['list']['rows'][0]['deletionMark']['value'], value)
            app.open(reference); editor = app.editor
            field = next(f for f in editor.snapshot()['fields'] if f['name'] == 'DeletionMark')
            self.assertEqual(field['inputText'], value)
            self.assertFalse(editor.snapshot()['originalForm'])
