"""Original demo source to real temporary v6 SQLite UI edit/save/reopen.

Local host adapter evidence, not native 1C managed-form parity.
"""
from pathlib import Path
import tempfile
import sqlite3
from contextlib import closing
from unittest import mock
import unittest

from yadinassi.catalog_backend import BackendError
from yadinassi.database_context import SQLiteDBContext
from yadinassi.sqlite_catalog import SQLiteCatalogBackend, _View
from yadinassi.ui.catalog_editor import CatalogEditorApplication
from yadinassi.ui.protocol import UIError


class ImportedKindEditorTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / 'demo.sqlite'
        root = Path(__file__).parent / 'fixtures/demo_cf/source'
        files = {path.relative_to(root).as_posix(): path.read_bytes()
                 for path in root.rglob('*') if path.is_file()}
        backend = SQLiteCatalogBackend.create_demo_kinds(self.path, files)
        backend.close()
        self.context = SQLiteDBContext(self.path)
        self.app = CatalogEditorApplication(self.context)
        self.addCleanup(self.app.close)
        inventory = self.app.snapshot()['state']['catalogs']
        self.assertEqual(len(inventory), 1)
        self.assertEqual(inventory[0]['name'], 'ВидыНоменклатуры')
        self.catalog_id = inventory[0]['id']
        self.app.select(self.catalog_id)
        self.app.open()
        self.editor = self.app.editor

    def change(self, value):
        return self.editor.change('InputData1', value)

    def test_original_change_normalizes_and_displays_field_message(self):
        self.change(' x ')
        state = self.editor.snapshot()
        self.assertEqual(state['fields'][1]['inputText'], 'x')
        self.assertEqual(state['fieldMessages'], [{'text': 'Название вида должно содержать не менее трех символов, например: Товары или Материалы.', 'field': 'Объект.Наименование'}])
        self.assertTrue(state['originalForm'])
        self.change(' good ')
        self.assertEqual(self.editor.snapshot()['fieldMessages'], [])

    def test_code_read_only_and_host_rejects_forged_input(self):
        self.assertTrue(self.editor.snapshot()['fields'][0]['readOnly'])
        with self.assertRaises(UIError): self.editor.change('InputData0', '77')
        self.assertEqual(self.editor.snapshot()['fields'][0]['inputText'], '')

    def test_server_refusal_retains_buffer_and_never_calls_write(self):
        self.change(' x ')
        with mock.patch.object(self.editor.object, 'write', side_effect=AssertionError('write')):
            self.editor.command('SaveButton')
        state = self.editor.snapshot()
        self.assertEqual(state['saveState'], 'rejected')
        self.assertEqual(state['fields'][1]['inputText'], 'x')
        self.assertTrue(state['dirty'])
        self.assertEqual(state['fieldMessages'][0]['text'], 'Укажите название вида номенклатуры длиной не менее трех символов.')

    def test_success_refreshes_persisted_normalized_buffer(self):
        self.change(' valid name ')
        self.editor.command('SaveButton')
        state = self.editor.snapshot()
        self.assertEqual(state['saveState'], 'saved')
        self.assertEqual(state['fields'][1]['inputText'], 'valid name')
        self.assertFalse(state['dirty'])
        self.assertEqual(self.editor.object.get_member('Description'), 'valid name')

    def test_dirty_close_and_cancel_do_not_write(self):
        self.change(' changed ')
        with mock.patch.object(self.editor.object, 'write', side_effect=AssertionError('write')):
            self.editor.close()
            self.assertFalse(self.editor.form.closed)
            self.editor.command('CancelButton')
        self.assertTrue(self.editor.form.closed)

    def test_source_drift_preserves_buffer_and_stays_stale(self):
        self.change(' valid ')
        before = self.editor.snapshot()['fields']
        backend = self.context.backend
        with mock.patch.object(backend, 'read_form_source', side_effect=BackendError('schema_changed')):
            with self.assertRaises(BackendError): self.change('other')
        with self.assertRaises(BackendError): self.change('another')
        self.assertEqual(self.editor.snapshot()['fields'], before)
        self.assertTrue(self.editor.snapshot()['sourceStale'])

    def test_pending_refresh_never_runs_original_bsl(self):
        self.change('Valid category')
        with mock.patch.object(self.editor, '_refresh', side_effect=BackendError('storage_error')):
            self.editor.command('SaveButton')
        self.assertTrue(self.editor.pending_refresh)
        with mock.patch.object(self.editor, '_source_draft', side_effect=AssertionError('BSL replay')), \
             mock.patch.object(_View, 'commit', side_effect=AssertionError('second commit')):
            self.editor.command('SaveButton')
        self.assertEqual(self.editor.save_state, 'saved')

    def test_pending_commit_never_prepares_or_replaces_intent(self):
        self.change('Valid category')
        original = _View.commit
        def uncertain(view):
            original(view)
            raise BackendError('uncertain_commit')
        with mock.patch.object(_View, 'commit', uncertain):
            self.editor.command('SaveButton')
        self.assertTrue(self.editor.pending_commit)
        with closing(sqlite3.connect(self.path)) as db, db:
            source = db.execute("SELECT content FROM configuration_file WHERE path='Configuration.xml'").fetchone()[0]
            db.execute("UPDATE configuration_file SET content=? WHERE path='Configuration.xml'", (b'<changed/>',))
        with mock.patch.object(self.editor, '_source_draft', side_effect=AssertionError('BSL replay')), \
             mock.patch.object(_View, 'commit', side_effect=AssertionError('second commit')):
            self.editor.command('SaveButton')
        self.assertEqual(self.editor.save_state, 'committed')
        self.assertFalse(self.editor.pending_commit)
        self.assertTrue(self.editor.pending_refresh)
        self.assertTrue(self.editor.snapshot()['sourceStale'])
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute("UPDATE configuration_file SET content=? WHERE path='Configuration.xml'", (source,))
        with mock.patch.object(self.editor, '_source_draft', side_effect=AssertionError('BSL replay')), \
             mock.patch.object(_View, 'commit', side_effect=AssertionError('second commit')):
            self.editor.command('SaveButton')
        self.assertEqual(self.editor.save_state, 'saved')
        self.assertFalse(self.editor.pending_refresh)
        self.assertTrue(self.editor.snapshot()['sourceStale'])
        self.assertEqual(self.editor.object.get_member('Description'), 'Valid category')

    def test_create_save_close_database_reopen_persisted_original_form(self):
        self.change('  Товары  ')
        self.editor.command('SaveButton')
        before = self.editor.snapshot()
        self.assertEqual(before['saveState'], 'saved')
        code = before['fields'][0]['inputText']
        self.assertTrue(code and code.isdecimal())
        reference = self.editor._saved_reference()
        self.editor.close()
        self.app.close()
        app = CatalogEditorApplication(SQLiteDBContext(self.path))
        self.addCleanup(app.close)
        app.select(self.catalog_id)
        app.open(reference)
        after = app.editor.snapshot()
        self.assertTrue(after['originalForm'])
        self.assertEqual(after['fields'][0]['inputText'], code)
        self.assertEqual(after['fields'][1]['inputText'], 'Товары')
        self.assertFalse(after['dirty'])

    def test_source_change_between_preparation_and_write_is_rejected(self):
        self.change('Valid category')
        original = self.context.backend.begin_write
        with closing(sqlite3.connect(self.path)) as db:
            source = db.execute("SELECT content FROM configuration_file WHERE path='Configuration.xml'").fetchone()[0]
        def drift(operation):
            with closing(sqlite3.connect(self.path)) as db, db:
                db.execute("UPDATE configuration_file SET content=? WHERE path='Configuration.xml'", (b'<changed/>',))
            return original(operation)
        with mock.patch.object(self.context.backend, 'begin_write', side_effect=drift):
            self.editor.command('SaveButton')
        state = self.editor.snapshot()
        self.assertEqual(state['saveState'], 'rejected')
        self.assertTrue(state['dirty'])
        self.assertTrue(state['isNew'])
        self.assertEqual(state['fields'][1]['inputText'], 'Valid category')
        self.assertTrue(state['sourceStale'])
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute("UPDATE configuration_file SET content=? WHERE path='Configuration.xml'", (source,))
        with mock.patch.object(self.editor.object, 'write', side_effect=AssertionError('revived')):
            self.editor.command('SaveButton')
        self.assertTrue(self.editor.snapshot()['sourceStale'])
        self.assertEqual(self.editor.save_state, 'rejected')

    def test_repeated_save_does_not_allocate_another_number(self):
        self.change('Valid category')
        self.editor.command('SaveButton')
        first = self.editor.snapshot()
        with mock.patch.object(self.editor.object, 'write', side_effect=AssertionError('unchanged write')):
            self.editor.command('SaveButton')
        second = self.editor.snapshot()
        self.assertEqual(first['reference'], second['reference'])
        self.assertEqual(first['fields'][0]['inputText'], second['fields'][0]['inputText'])
        self.app.event('closeCard')
        self.assertEqual(self.app.view.page(0, 8)['total'], 1)

    def test_backend_replacement_cannot_resolve_pending_commit(self):
        self.change('Valid category')
        commit = _View.commit
        def uncertain(view):
            commit(view)
            raise BackendError('uncertain_commit')
        with mock.patch.object(_View, 'commit', uncertain):
            self.editor.command('SaveButton')
        pending = self.editor.object._pending_write
        replacement = SQLiteCatalogBackend(self.path)
        self.addCleanup(replacement.close)
        with mock.patch.object(self.context, '_backend', replacement), \
             mock.patch.object(self.editor.object, 'write', side_effect=AssertionError('replaced backend')):
            self.editor.command('SaveButton')
        self.assertIs(self.editor.object._pending_write, pending)
        self.assertTrue(self.editor.pending_commit)
        self.assertTrue(self.editor.snapshot()['sourceStale'])

    def test_backend_replacement_cannot_adopt_pending_refresh(self):
        self.change('Valid category')
        with mock.patch.object(self.editor, '_refresh', side_effect=BackendError('storage_error')):
            self.editor.command('SaveButton')
        original = self.editor.object
        replacement = SQLiteCatalogBackend(self.path)
        self.addCleanup(replacement.close)
        with mock.patch.object(self.context, '_backend', replacement), \
             mock.patch.object(self.editor, '_refresh', side_effect=AssertionError('replaced backend')):
            self.editor.command('SaveButton')
        self.assertIs(self.editor.object, original)
        self.assertTrue(self.editor.pending_refresh)
        self.assertTrue(self.editor.snapshot()['sourceStale'])

    def test_stale_discard_returns_closed_protocol_snapshot_without_reread(self):
        import json
        from yadinassi.ui.editor_protocol import CatalogEditorSession
        from yadinassi.ui.protocol import encode_line
        session = CatalogEditorSession(self.app)
        hello = {'jsonrpc': '2.0', 'id': 1, 'method': 'editor.hello',
                 'params': {'protocol': 'yadinassi-editor/0'}}
        session.exchange(encode_line(hello))
        self.change('Valid category')
        self.editor._source_stale = True
        request = {'jsonrpc': '2.0', 'id': 2, 'method': 'editor.event',
                   'params': {'event': 'command', 'control': 'CancelButton', 'baseRevision': 0}}
        with mock.patch.object(self.context.backend, 'begin_read', side_effect=AssertionError('stale read')):
            result = json.loads(session.exchange(encode_line(request)))
        self.assertNotIn('error', result)
        self.assertEqual(result['result']['state']['kind'], 'closed')
        self.assertIsNone(result['result']['state']['editor'])

    def mark(self, value):
        control = next(f['control'] for f in self.editor.snapshot()['fields'] if f['name'] == 'DeletionMark')
        return self.editor.change(control, value)

    def test_kind_deletion_mark_uses_current_draft_in_original_save(self):
        self.change('x'); self.mark(True); self.editor.command('SaveButton')
        self.assertEqual(self.editor.save_state, 'saved')
        self.assertTrue(self.editor.object.get_member('DeletionMark'))
        self.assertEqual(self.editor.object.get_member('Description'), 'x')
        reference = self.editor._saved_reference()
        self.app.event('closeCard'); self.app.open(reference); self.editor = self.app.editor
        self.mark(False); self.editor.command('SaveButton')
        self.assertEqual(self.editor.error, 'form_validation')
        self.assertTrue(self.editor.object.get_member('Ref').get_member('DeletionMark'))
        self.assertFalse(next(f for f in self.editor.snapshot()['fields'] if f['name'] == 'DeletionMark')['inputText'])
        self.change('Valid kind'); self.editor.command('SaveButton')
        self.assertEqual(self.editor.save_state, 'saved')
        self.assertFalse(self.editor.object.get_member('DeletionMark'))

    def test_kind_checkbox_does_not_invent_original_change_handler(self):
        with mock.patch.object(self.editor, '_source_draft', side_effect=AssertionError('invented handler')):
            self.mark(True)
        self.assertTrue(self.editor.snapshot()['dirty'])
        self.assertFalse(self.editor.object.get_member('DeletionMark'))
        self.assertEqual(self.editor.snapshot()['fieldMessages'], [])

    def test_kind_mark_change_does_not_skip_original_description_handler(self):
        self.mark(True); self.change(' x ')
        self.assertEqual(self.editor.snapshot()['fields'][1]['inputText'], 'x')
        self.assertTrue(self.editor.snapshot()['fieldMessages'])
        self.editor.command('SaveButton')
        self.assertEqual(self.editor.save_state, 'saved')
        self.assertTrue(self.editor.object.get_member('DeletionMark'))

    def test_kind_mark_is_not_lost_as_unchanged_save(self):
        self.change('Valid kind'); self.editor.command('SaveButton')
        self.mark(True); self.editor.command('SaveButton')
        self.assertTrue(self.editor.object.get_member('DeletionMark'))
        with mock.patch.object(self.editor.object, 'write', side_effect=AssertionError('duplicate write')):
            self.editor.command('SaveButton')
        self.assertEqual(self.editor.save_state, 'unchanged')
        self.mark(False); self.editor.command('SaveButton')
        self.assertFalse(self.editor.object.get_member('DeletionMark'))

    def test_kind_mark_uncertain_commit_preserves_exact_value(self):
        self.change('x'); self.mark(True)
        original = _View.commit
        def uncertain(view): original(view); raise BackendError('uncertain_commit')
        with mock.patch.object(_View, 'commit', uncertain): self.editor.command('SaveButton')
        self.assertTrue(self.editor.pending_commit)
        with self.assertRaises(UIError): self.mark(False)
        with mock.patch.object(self.editor, '_source_draft', side_effect=AssertionError('form replay')), \
             mock.patch.object(_View, 'commit', side_effect=AssertionError('second commit')):
            self.editor.command('SaveButton')
        self.assertEqual(self.editor.save_state, 'saved')
        self.assertTrue(self.editor.object.get_member('DeletionMark'))
