"""Fault injection over real disposable SQLite transactions, not native 1C."""
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch
from uuid import uuid4

from sqlite_catalog_fixture import configuration_files
from yadinassi import Interpreter
from yadinassi.catalog_backend import BackendError, CatalogDraft, CatalogKey
from yadinassi.configuration_xml import import_configuration
from yadinassi.database_context import SQLiteDBContext
from yadinassi.sqlite_catalog import _View


class FaultConnection:
    def __init__(self, wrapped, *, commit_fault=None, close_fault=None, close_count=0, rollback_fault=False):
        self.wrapped = wrapped
        self.commit_fault = commit_fault
        self.close_fault = close_fault
        self.close_count = close_count
        self.rollback_fault = rollback_fault
        self.commit_calls = 0

    def __getattr__(self, name): return getattr(self.wrapped, name)

    def execute(self, sql, *args):
        if sql == 'ROLLBACK' and self.rollback_fault:
            raise sqlite3.OperationalError('injected rollback')
        if sql == 'COMMIT':
            self.commit_calls += 1
            if self.commit_fault == 'before': raise sqlite3.OperationalError('injected')
            if self.commit_fault == 'after':
                self.wrapped.execute(sql, *args)
                raise sqlite3.OperationalError('injected')
            if self.commit_fault == 'interrupt':
                self.wrapped.execute(sql, *args)
                raise KeyboardInterrupt()
            if self.commit_fault == 'memory':
                self.wrapped.execute(sql, *args)
                raise MemoryError()
        return self.wrapped.execute(sql, *args)

    def close(self):
        if self.close_count:
            self.close_count -= 1
            if self.close_fault == 'after': self.wrapped.close()
            raise sqlite3.OperationalError('injected')
        self.wrapped.close()


class CatalogCommitCleanupRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name)/'owned.sqlite'
        self.context = SQLiteDBContext.create(self.path, import_configuration(configuration_files()))
        self.vm = Interpreter(database_context=self.context)
        self.vm.execute('P=Catalogs.Products.CreateItem();P.Code="30";P.Text="original";')
        self.obj = self.vm.execute('P')

    def tearDown(self):
        self.context.close()
        self.temp.cleanup()

    def injected_write(self, **fault):
        backend = self.context.backend
        original = backend.begin_write
        captured = []
        def begin(operation):
            view = original(operation)
            view._connection = FaultConnection(view._connection, **fault)
            captured.append(view)
            return view
        return patch.object(backend, 'begin_write', side_effect=begin), captured

    def assert_retained_and_resolve_without_recommit(self):
        self.assertIsNotNone(self.obj._pending_write)
        with self.assertRaisesRegex(BackendError, 'uncertain_commit'):
            self.obj.set_member('Text', 'changed')
        with patch.object(_View, 'commit', side_effect=AssertionError('must resolve receipt')):
            self.obj.write()
        self.assertFalse(self.obj.is_new())
        self.assertEqual(self.vm.execute('Catalogs.Products.FindByCode("30").Text'), 'original')

    def test_close_raises_after_physical_close_and_real_commit(self):
        instrument, views = self.injected_write(close_fault='after', close_count=1)
        with instrument, self.assertRaisesRegex(BackendError, 'uncertain_commit'):
            self.obj.write()
        self.assertTrue(self.obj.is_new())
        self.assertIsNone(self.context.backend._active)
        self.assertEqual(views[0]._connection, None)
        self.assert_retained_and_resolve_without_recommit()

    def test_persistent_close_failure_keeps_view_closed_and_owned(self):
        instrument, views = self.injected_write(close_fault='before', close_count=100)
        with instrument, self.assertRaisesRegex(BackendError, 'uncertain_commit'):
            self.obj.write()
        view = views[0]
        self.assertIs(self.context.backend._active, view)
        with self.assertRaisesRegex(BackendError, 'closed'): view.catalogs()
        with self.assertRaisesRegex(BackendError, 'closed'): view.commit()
        with self.assertRaisesRegex(BackendError, 'busy'): self.context.backend.begin_read()
        self.assertIsNotNone(self.obj._pending_write)
        view._connection.close_count = 0
        view.close()
        self.assertIsNone(self.context.backend._active)
        self.assert_retained_and_resolve_without_recommit()

    def test_commit_error_after_sql_commit_resolves_without_second_write(self):
        instrument, views = self.injected_write(commit_fault='after')
        with instrument, self.assertRaisesRegex(BackendError, 'uncertain_commit'):
            self.obj.write()
        self.assertEqual(views[0]._closed, True)
        self.assert_retained_and_resolve_without_recommit()

    def test_commit_error_before_sql_commit_retries_original_intent(self):
        instrument, views = self.injected_write(commit_fault='before')
        with instrument, self.assertRaisesRegex(BackendError, 'uncertain_commit'):
            self.obj.write()
        operation = self.obj._pending_write[2]
        self.assertIsNone(self.context.backend.committed_operation(operation))
        self.assertTrue(self.vm.execute('Catalogs.Products.FindByCode("30").IsEmpty()'))
        self.obj.write()
        self.assertFalse(self.obj.is_new())
        self.assertEqual(self.vm.execute('Catalogs.Products.FindByCode("30").Text'), 'original')
        self.assertIsNotNone(self.context.backend.committed_operation(operation))

    def test_original_operation_id_survives_interrupted_acceptance(self):
        instrument, _ = self.injected_write(commit_fault='after')
        with instrument, self.assertRaisesRegex(BackendError, 'uncertain_commit'):
            self.obj.write()
        operation = self.obj._pending_write[2]
        self.obj._operation_id = uuid4()  # State after an interrupted acceptance.
        self.assertNotEqual(operation, self.obj._operation_id)
        self.assert_retained_and_resolve_without_recommit()

    def test_interrupt_after_commit_propagates_and_keeps_pending(self):
        instrument, _ = self.injected_write(commit_fault='interrupt')
        with instrument, self.assertRaises(KeyboardInterrupt): self.obj.write()
        self.assert_retained_and_resolve_without_recommit()

    def test_cleanup_interrupt_is_not_hidden_by_duplicate_code(self):
        self.obj.write()
        self.vm.execute('Q=Catalogs.Products.CreateItem();Q.Code="30";')
        other = self.vm.execute('Q')
        with patch.object(_View, 'rollback', side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt): other.write()
        self.assertIsNone(other._pending_write)
        self.assertIsNone(self.context.backend._active)

    def test_duplicate_error_survives_ordinary_close_failure(self):
        self.obj.write()
        self.vm.execute('Q=Catalogs.Products.CreateItem();Q.Code="30";')
        other = self.vm.execute('Q')
        instrument, views = self.injected_write(close_fault='before', close_count=1)
        with instrument, self.assertRaisesRegex(BackendError, 'duplicate_code'):
            other.write()
        self.assertIsNone(other._pending_write)
        self.assertTrue(views[0]._closed)
        self.assertIsNone(self.context.backend._active)

    def test_failed_rollback_still_closes_connection_and_releases_ownership(self):
        backend = self.context.backend
        view = backend.begin_write(uuid4())
        schema = next(item for item in backend._schemas if item.name == 'Categories')
        draft = CatalogDraft(CatalogKey(backend.database_id, schema.identity, uuid4()),
                             '1', 'category', False, ())
        view.create(draft)
        view._connection = FaultConnection(view._connection, rollback_fault=True)
        with self.assertRaisesRegex(BackendError, 'storage_error'): view.close()
        self.assertIsNone(backend._active)
        with self.assertRaisesRegex(BackendError, 'closed'): view.catalogs()
        read = backend.begin_read()
        try: self.assertIsNone(read.read_catalog(draft.key))
        finally: read.close()

    def test_first_interruption_survives_second_cleanup_interruption(self):
        primary = KeyboardInterrupt('primary')
        commit = _View.commit
        def committed_then_interrupt(view):
            commit(view)
            raise primary
        with patch.object(_View, 'commit', committed_then_interrupt), \
                patch.object(_View, 'rollback', side_effect=KeyboardInterrupt('cleanup')):
            with self.assertRaises(KeyboardInterrupt) as caught: self.obj.write()
        self.assertIs(caught.exception, primary)
        self.assert_retained_and_resolve_without_recommit()

    def test_outer_close_failure_after_commit_keeps_pending(self):
        real_close = _View.close
        count = [0]
        def close(view):
            count[0] += 1
            real_close(view)
            if count[0] == 2: raise BackendError('storage_error')
        with patch.object(_View, 'close', close):
            with self.assertRaisesRegex(BackendError, 'uncertain_commit'): self.obj.write()
        self.assert_retained_and_resolve_without_recommit()

    def test_existing_record_update_resolves_original_revision_once(self):
        self.obj.write()
        self.obj.set_member('Text', 'updated')
        original_revision = self.obj._revision
        instrument, _ = self.injected_write(close_fault='after', close_count=1)
        with instrument, self.assertRaisesRegex(BackendError, 'uncertain_commit'):
            self.obj.write()
        self.assertEqual(self.obj._pending_write[1], original_revision)
        with patch.object(_View, 'commit', side_effect=AssertionError('must resolve')):
            self.obj.write()
        self.assertEqual(int(self.obj._revision.token), int(original_revision.token)+1)
        self.assertEqual(self.vm.execute('Catalogs.Products.FindByCode("30").Text'), 'updated')

    def test_multi_record_commit_and_receipt_remain_atomic_on_close_failure(self):
        backend = self.context.backend
        schema = next(item for item in backend._schemas if item.name == 'Categories')
        operation = uuid4()
        view = backend.begin_write(operation)
        drafts = [CatalogDraft(CatalogKey(backend.database_id, schema.identity, uuid4()),
                               str(i), 'category', False, ()) for i in (1, 2)]
        for draft in drafts: view.create(draft)
        view._connection = FaultConnection(view._connection, close_fault='after', close_count=1)
        with self.assertRaisesRegex(BackendError, 'uncertain_commit'): view.commit()
        receipt = backend.committed_operation(operation)
        self.assertEqual(len(receipt[1]), 2)
        read = backend.begin_read()
        try:
            self.assertEqual([read.read_catalog(d.key).code for d in drafts], ['1', '2'])
        finally: read.close()


class CatalogEditorCommitCleanupTests(unittest.TestCase):
    def test_editor_locks_unresolved_write_after_error_or_interruption(self):
        from ui_catalog_fixture import repository
        from yadinassi.ui.catalog_editor import CatalogEditorApplication
        from yadinassi.ui.protocol import UIError
        for fault in ('after', 'memory'):
            with self.subTest(fault=fault):
                previous, path, _, ids = repository(self)
                previous.close()
                context = SQLiteDBContext(path)
                app = CatalogEditorApplication(context)
                try:
                    app.event('selectCatalog', catalog=ids['category'])
                    app.event('create')
                    field = next(f for f in app.editor.snapshot()['fields'] if f['name'] == 'Code')
                    app.event('change', control=field['control'], value='20')
                    original = context.backend.begin_write
                    def begin(operation):
                        view = original(operation)
                        view._connection = FaultConnection(view._connection, commit_fault=fault)
                        return view
                    with patch.object(context.backend, 'begin_write', side_effect=begin):
                        if fault == 'memory':
                            with self.assertRaises(MemoryError):
                                app.event('command', control='SaveButton')
                        else:
                            app.event('command', control='SaveButton')
                    self.assertTrue(app.editor.snapshot()['editingLocked'])
                    self.assertEqual(app.editor.snapshot()['saveState'], 'uncertain')
                    with self.assertRaises(UIError): app.event('command', control='CancelButton')
                    with patch.object(_View, 'commit', side_effect=AssertionError('must resolve')):
                        app.event('command', control='SaveButton')
                    self.assertEqual(app.editor.snapshot()['saveState'], 'saved')
                finally:
                    app.close()
