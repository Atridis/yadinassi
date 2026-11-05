"""Creation failures leave only disposable, authored test files in place."""
from contextlib import closing, redirect_stderr
from io import StringIO
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from test_sqlite_catalog_backend import configuration
from yadinassi.catalog_backend import BackendError
from yadinassi.sqlite_catalog import SQLiteCatalogBackend


class CreateConnection:
    def __init__(self, wrapped, *, commit=None, precommit=False, close=None, marker=None,
                 precommit_error=None, rollback_error=None, close_error=None, probe_error=None):
        self.wrapped = wrapped
        self.commit = commit
        self.precommit = precommit
        self.close_fault = close
        self.marker = marker
        self.precommit_error, self.rollback_error = precommit_error, rollback_error
        self.close_error, self.probe_error = close_error, probe_error
        self.close_called = 0
        self.marker_called = 0

    def __getattr__(self, name): return getattr(self.wrapped, name)

    def mark_once(self):
        if self.marker is not None:
            marker, self.marker = self.marker, None
            self.marker_called += 1
            marker()

    @property
    def in_transaction(self):
        if self.probe_error is not None: raise self.probe_error
        return self.wrapped.in_transaction

    def execute(self, sql, *args):
        if self.precommit_error is not None and sql.startswith('CREATE TABLE database_info'):
            raise self.precommit_error
        if self.precommit and sql.startswith('CREATE TABLE database_info'):
            raise sqlite3.OperationalError('injected')
        if sql == 'ROLLBACK' and self.rollback_error is not None: raise self.rollback_error
        if sql == 'COMMIT':
            if self.commit == 'before': raise sqlite3.OperationalError('injected')
            if self.commit in ('after', 'interrupt', 'memory', 'concurrent'):
                self.wrapped.execute(sql, *args)
                if self.commit == 'concurrent': self.mark_once()
                if self.commit == 'interrupt': raise KeyboardInterrupt()
                if self.commit == 'memory': raise MemoryError()
                raise sqlite3.OperationalError('injected')
        return self.wrapped.execute(sql, *args)

    def close(self):
        self.close_called += 1
        if self.close_error is not None: raise self.close_error
        if self.close_fault == 'before': raise sqlite3.OperationalError('injected')
        self.wrapped.close()
        self.mark_once()
        if self.close_fault == 'after': raise sqlite3.OperationalError('injected')


class SQLiteCreateUncertainTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name)/'owned.sqlite'
        self.config = configuration()
        self.real_connect = sqlite3.connect
        self.handles = []
        self.addCleanup(self.close_test_handles)

    def close_test_handles(self):
        for item in self.handles:
            try: item.wrapped.close()
            except sqlite3.Error: pass

    def injected(self, **fault):
        calls = [0]
        def connect(*args, **kwargs):
            calls[0] += 1
            conn = self.real_connect(*args, **kwargs)
            if calls[0] != 1: return conn
            proxy = CreateConnection(conn, **fault)
            self.handles.append(proxy)
            return proxy
        return patch('yadinassi.sqlite_catalog.sqlite3.connect', side_effect=connect)

    def assert_complete_source(self):
        backend = SQLiteCatalogBackend(self.path)
        try:
            self.assertEqual(backend.export_configuration(),
                             {item.path:item.content for item in self.config.files})
        finally: backend.close()

    def test_commit_lost_response_keeps_complete_created_database(self):
        with self.injected(commit='after'):
            with self.assertRaisesRegex(BackendError, 'uncertain_commit'):
                SQLiteCatalogBackend.create(self.path, self.config)
        self.assertTrue(self.path.exists())
        self.assert_complete_source()

    def test_error_before_commit_dispatch_keeps_reserved_file(self):
        with self.injected(commit='before'):
            with self.assertRaisesRegex(BackendError, 'uncertain_commit'):
                SQLiteCatalogBackend.create(self.path, self.config)
        self.assertTrue(self.path.exists())
        with closing(self.real_connect(self.path)) as db:
            self.assertIsNone(db.execute("SELECT name FROM sqlite_master WHERE name='database_info'").fetchone())

    def test_close_failure_after_commit_keeps_complete_created_database(self):
        with self.injected(close='after'):
            with self.assertRaisesRegex(BackendError, 'uncertain_commit'):
                SQLiteCatalogBackend.create(self.path, self.config)
        self.assertTrue(self.path.exists())
        self.assert_complete_source()

    def test_interrupted_commit_keeps_complete_database_and_interrupt(self):
        with self.injected(commit='interrupt'):
            with self.assertRaises(KeyboardInterrupt):
                SQLiteCatalogBackend.create(self.path, self.config)
        self.assertTrue(self.path.exists())
        self.assert_complete_source()

    def test_memory_error_after_commit_keeps_database_and_error(self):
        with self.injected(commit='memory'):
            with self.assertRaises(MemoryError):
                SQLiteCatalogBackend.create(self.path, self.config)
        self.assertTrue(self.path.exists())
        self.assert_complete_source()

    def test_concurrent_postcommit_write_survives_lost_response(self):
        def concurrent_writer():
            with closing(self.real_connect(self.path)) as db, db:
                db.execute('CREATE TABLE retained_marker(value TEXT)')
                db.execute("INSERT INTO retained_marker VALUES('committed later')")
        with self.injected(commit='concurrent', marker=concurrent_writer):
            with self.assertRaisesRegex(BackendError, 'uncertain_commit'):
                SQLiteCatalogBackend.create(self.path, self.config)
        self.assertEqual(self.handles[0].marker_called, 1)
        with closing(self.real_connect(self.path)) as db:
            self.assertEqual(db.execute('SELECT value FROM retained_marker').fetchone(), ('committed later',))

    def test_unconfirmed_physical_close_does_not_remove_file(self):
        with self.injected(close='before'):
            with self.assertRaisesRegex(BackendError, 'uncertain_commit'):
                SQLiteCatalogBackend.create(self.path, self.config)
        self.assertTrue(self.path.exists())
        self.handles[0].wrapped.close()  # Explicit cleanup of this disposable test connection.
        self.assert_complete_source()

    def test_failed_precommit_never_unlinks_concurrent_same_inode_write(self):
        def concurrent_writer():
            with closing(self.real_connect(self.path)) as db, db:
                db.execute('CREATE TABLE retained_marker(value TEXT)')
                db.execute("INSERT INTO retained_marker VALUES('other process')")
        with self.injected(precommit=True, marker=concurrent_writer):
            with self.assertRaisesRegex(BackendError, 'storage_error'):
                SQLiteCatalogBackend.create(self.path, self.config)
        with closing(self.real_connect(self.path)) as db:
            self.assertEqual(db.execute('SELECT value FROM retained_marker').fetchone(), ('other process',))

    def test_connect_failure_leaves_reserved_path_and_original_error(self):
        with patch('yadinassi.sqlite_catalog.sqlite3.connect', side_effect=sqlite3.OperationalError('injected')):
            with self.assertRaisesRegex(BackendError, 'storage_error'):
                SQLiteCatalogBackend.create(self.path, self.config)
        self.assertTrue(self.path.exists())

    def test_reopen_failure_after_commit_keeps_database_and_is_uncertain(self):
        with patch.object(SQLiteCatalogBackend, '__init__', side_effect=BackendError('integrity')):
            with self.assertRaisesRegex(BackendError, 'uncertain_commit'):
                SQLiteCatalogBackend.create(self.path, self.config)
        self.assertTrue(self.path.exists())
        self.assert_complete_source()

    def test_existing_destination_is_never_modified(self):
        self.path.write_bytes(b'existing data')
        with self.assertRaises(BackendError): SQLiteCatalogBackend.create(self.path, self.config)
        self.assertEqual(self.path.read_bytes(), b'existing data')

    def test_precommit_interruption_survives_ordinary_cleanup_failures(self):
        primary = KeyboardInterrupt('primary')
        with self.injected(precommit_error=primary,
                           rollback_error=sqlite3.OperationalError('rollback'),
                           close_error=sqlite3.OperationalError('close')):
            with self.assertRaises(KeyboardInterrupt) as caught:
                SQLiteCatalogBackend.create(self.path, self.config)
        self.assertIs(caught.exception, primary)
        self.assertTrue(self.path.exists())
        self.assertEqual(self.handles[0].close_called, 1)

    def test_cleanup_interruption_is_not_hidden_by_ordinary_primary(self):
        cleanup = KeyboardInterrupt('cleanup')
        with self.injected(precommit=True, close_error=cleanup):
            with self.assertRaises(KeyboardInterrupt) as caught:
                SQLiteCatalogBackend.create(self.path, self.config)
        self.assertIs(caught.exception, cleanup)
        self.assertTrue(self.path.exists())

    def test_failed_transaction_probe_still_attempts_close(self):
        with self.injected(precommit=True, probe_error=sqlite3.OperationalError('probe')):
            with self.assertRaisesRegex(BackendError, 'storage_error'):
                SQLiteCatalogBackend.create(self.path, self.config)
        self.assertTrue(self.path.exists())
        self.assertEqual(self.handles[0].close_called, 1)

    def test_failed_rollback_still_attempts_close(self):
        with self.injected(precommit=True, rollback_error=sqlite3.OperationalError('rollback')):
            with self.assertRaisesRegex(BackendError, 'storage_error'):
                SQLiteCatalogBackend.create(self.path, self.config)
        self.assertTrue(self.path.exists())
        self.assertEqual(self.handles[0].close_called, 1)

    def test_cli_warns_on_uncertain_creation_without_private_details(self):
        from yadinassi import cli
        output = StringIO()
        with patch('yadinassi.configuration_import.load_configuration_directory', return_value=self.config), \
                patch.object(cli.SQLiteDBContext, 'create', side_effect=BackendError('uncertain_commit')), \
                redirect_stderr(output):
            status = cli.main(['--create-db',str(self.path),'--import-xml','/private/source'])
        self.assertEqual(status, 1)
        self.assertIn('outcome uncertain', output.getvalue())
        self.assertIn('preserve', output.getvalue())
        self.assertNotIn('/private', output.getvalue())
        self.assertNotIn(str(self.path), output.getvalue())

    def test_cli_warns_after_ordinary_create_or_context_close_failure(self):
        from unittest.mock import Mock
        from yadinassi import cli
        for phase in ('create', 'close'):
            with self.subTest(phase=phase):
                output = StringIO()
                context = Mock()
                if phase == 'close': context.close.side_effect = BackendError('storage_error')
                create = Mock(return_value=context) if phase == 'close' else Mock(side_effect=BackendError('storage_error'))
                with patch('yadinassi.configuration_import.load_configuration_directory', return_value=self.config), \
                        patch.object(cli.SQLiteDBContext, 'create', create), redirect_stderr(output):
                    status = cli.main(['--create-db',str(self.path),'--import-xml','/private/source'])
                self.assertEqual(status, 1)
                self.assertIn('preserve and inspect', output.getvalue())
                self.assertNotIn('/private', output.getvalue())
                self.assertNotIn(str(self.path), output.getvalue())
