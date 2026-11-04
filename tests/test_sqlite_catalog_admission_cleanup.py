"""Admission faults use disposable SQLite files, never a user's database."""
from contextlib import contextmanager
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch
from uuid import uuid4

from test_sqlite_catalog_backend import configuration
from yadinassi.catalog_backend import BackendError
from yadinassi.sqlite_catalog import SQLiteCatalogBackend, _View


class AdmissionFaultConnection:
    def __init__(self, wrapped, *, statement=None, primary=None, after=False,
                 rollback_error=None, close_error=None, close_after=False,
                 transaction_error=None):
        self.wrapped = wrapped
        self.statement, self.primary, self.after = statement, primary, after
        self.rollback_error, self.close_error = rollback_error, close_error
        self.close_after, self.transaction_error = close_after, transaction_error
        self.close_calls = 0
        self.statements = []

    def __getattr__(self, name):
        return getattr(self.wrapped, name)

    @property
    def in_transaction(self):
        if self.transaction_error is not None: raise self.transaction_error
        return self.wrapped.in_transaction

    def execute(self, sql, *args):
        self.statements.append(sql)
        if sql == 'ROLLBACK' and self.rollback_error is not None:
            raise self.rollback_error
        if sql == self.statement and self.primary is not None:
            if self.after: self.wrapped.execute(sql, *args)
            raise self.primary
        return self.wrapped.execute(sql, *args)

    def close(self):
        self.close_calls += 1
        if self.close_error is not None:
            if self.close_after: self.wrapped.close()
            raise self.close_error
        self.wrapped.close()

    def disable_faults(self):
        self.primary = self.rollback_error = self.close_error = self.transaction_error = None


class SQLiteCatalogAdmissionCleanupTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / 'admission.sqlite'
        self.backend = SQLiteCatalogBackend.create(self.path, configuration())
        self.real_connect = sqlite3.connect
        self.connections = []

    def tearDown(self):
        for connection in self.connections: connection.disable_faults()
        try:
            try: self.backend.close()
            except BackendError: pass  # A proxy may already have physically closed.
        finally:
            for connection in self.connections: connection.wrapped.close()
            self.temp.cleanup()

    @contextmanager
    def connection_fault(self, **faults):
        def connect(*args, **kwargs):
            connection = AdmissionFaultConnection(self.real_connect(*args, **kwargs), **faults)
            self.connections.append(connection)
            return connection
        with patch('yadinassi.sqlite_catalog.sqlite3.connect', side_effect=connect):
            yield

    def assert_owned_and_blocked(self, connection):
        owner = self.backend._active
        self.assertIsNotNone(owner)
        self.assertNotIsInstance(owner, _View)
        self.assertIs(owner._connection, connection)
        self.assertTrue(owner._closed)
        self.assertFalse(hasattr(owner, 'commit'))
        with patch('yadinassi.sqlite_catalog.sqlite3.connect', side_effect=AssertionError('must not open')):
            with self.assertRaisesRegex(BackendError, 'busy'): self.backend.begin_read()
            with self.assertRaisesRegex(BackendError, 'busy'): self.backend.begin_write(uuid4())
        return owner

    def assert_reusable(self):
        view = self.backend.begin_read()
        try:
            self.assertIs(self.backend._active, view)
            self.assertEqual(len(view.catalogs()), 2)
        finally: view.close()
        self.assertIsNone(self.backend._active)

    def test_begin_failure_before_or_after_sql_retains_live_handle(self):
        for statement in ('BEGIN', 'BEGIN IMMEDIATE'):
            for after in (False, True):
                with self.subTest(statement=statement, after=after):
                    with self.connection_fault(statement=statement,
                            primary=sqlite3.OperationalError('begin failed'), after=after,
                            rollback_error=sqlite3.OperationalError('rollback failed'),
                            close_error=sqlite3.OperationalError('close failed')):
                        with self.assertRaisesRegex(BackendError, 'busy'):
                            if statement == 'BEGIN': self.backend.begin_read()
                            else: self.backend.begin_write(uuid4())
                    connection = self.connections[-1]
                    owner = self.assert_owned_and_blocked(connection)
                    self.assertEqual(connection.wrapped.in_transaction, after)
                    self.assertEqual(connection.close_calls, 1)
                    connection.disable_faults()
                    owner.close()
                    self.assertIsNone(owner._connection)
                    self.assert_reusable()

    def test_schema_error_survives_failed_rollback_and_close(self):
        primary = BackendError('schema_changed')
        with self.connection_fault(statement='PRAGMA user_version', primary=primary,
                rollback_error=sqlite3.OperationalError('rollback failed'),
                close_error=sqlite3.OperationalError('close failed')):
            with self.assertRaises(BackendError) as caught: self.backend.begin_write(uuid4())
        self.assertIs(caught.exception, primary)
        connection = self.connections[-1]
        owner = self.assert_owned_and_blocked(connection)
        self.assertTrue(connection.wrapped.in_transaction)
        other = self.real_connect(self.path, isolation_level=None, timeout=0)
        try:
            with self.assertRaises(sqlite3.OperationalError): other.execute('BEGIN IMMEDIATE')
            self.assertEqual(other.execute('SELECT COUNT(*) FROM commit_receipt').fetchone(), (0,))
        finally: other.close()
        connection.disable_faults()
        owner.close()
        self.assert_reusable()

    def test_view_initialization_failure_has_provisional_owner(self):
        primary = BackendError('schema_changed')
        statement = 'SELECT database_uuid,generation FROM database_info WHERE singleton=1'
        with self.connection_fault(statement=statement, primary=primary,
                close_error=sqlite3.OperationalError('close failed')):
            with self.assertRaises(BackendError) as caught: self.backend.begin_write(uuid4())
        self.assertIs(caught.exception, primary)
        connection = self.connections[-1]
        owner = self.assert_owned_and_blocked(connection)
        self.assertFalse(connection.wrapped.in_transaction)  # ROLLBACK succeeded.
        connection.disable_faults()
        owner.close()
        self.assert_reusable()

    def test_view_allocation_failure_retains_owner_and_original_interruption(self):
        primary = MemoryError('view allocation')
        with self.connection_fault(close_error=KeyboardInterrupt('cleanup')):
            with patch('yadinassi.sqlite_catalog._View', side_effect=primary):
                with self.assertRaises(MemoryError) as caught: self.backend.begin_write(uuid4())
        self.assertIs(caught.exception, primary)
        connection = self.connections[-1]
        owner = self.assert_owned_and_blocked(connection)
        connection.disable_faults()
        owner.close()
        self.assert_reusable()

    def test_first_admission_interruption_survives_cleanup_interruption(self):
        for primary in (KeyboardInterrupt('primary'), SystemExit('primary'), MemoryError('primary')):
            with self.subTest(error=type(primary).__name__):
                with self.connection_fault(statement='PRAGMA user_version', primary=primary,
                        rollback_error=KeyboardInterrupt('rollback'), close_error=SystemExit('close')):
                    with self.assertRaises(type(primary)) as caught: self.backend.begin_write(uuid4())
                self.assertIs(caught.exception, primary)
                connection = self.connections[-1]
                owner = self.assert_owned_and_blocked(connection)
                connection.disable_faults()
                owner.close()
                self.assert_reusable()

    def test_new_cleanup_interruption_is_not_hidden_by_ordinary_admission_error(self):
        cleanup = KeyboardInterrupt('cleanup')
        with self.connection_fault(statement='PRAGMA user_version', primary=BackendError('schema_changed'),
                close_error=cleanup):
            with self.assertRaises(KeyboardInterrupt) as caught: self.backend.begin_write(uuid4())
        self.assertIs(caught.exception, cleanup)
        connection = self.connections[-1]
        owner = self.assert_owned_and_blocked(connection)
        connection.disable_faults()
        owner.close()
        self.assert_reusable()

    def test_rollback_interruption_still_closes_and_remains_visible(self):
        cleanup = KeyboardInterrupt('rollback')
        with self.connection_fault(statement='PRAGMA user_version', primary=BackendError('schema_changed'),
                rollback_error=cleanup):
            with self.assertRaises(KeyboardInterrupt) as caught: self.backend.begin_write(uuid4())
        self.assertIs(caught.exception, cleanup)
        self.assertEqual(self.connections[-1].close_calls, 1)
        self.assertIsNone(self.backend._active)
        self.assert_reusable()

    def test_connect_admission_failure_retains_handle_without_changing_error_category(self):
        with self.connection_fault(statement='PRAGMA foreign_keys=ON',
                primary=sqlite3.OperationalError('connect admission failed'),
                close_error=sqlite3.OperationalError('close failed')):
            with self.assertRaisesRegex(BackendError, 'storage_error'): self.backend.begin_write(uuid4())
        connection = self.connections[-1]
        owner = self.assert_owned_and_blocked(connection)
        self.assertFalse(connection.wrapped.in_transaction)
        self.assertNotIn('BEGIN IMMEDIATE', connection.statements)
        connection.disable_faults()
        owner.close()
        self.assert_reusable()

    def test_connect_admission_interruption_survives_close_error(self):
        primary = KeyboardInterrupt('connect admission')
        with self.connection_fault(statement='PRAGMA trusted_schema=OFF', primary=primary,
                close_error=sqlite3.OperationalError('close failed')):
            with self.assertRaises(KeyboardInterrupt) as caught: self.backend.begin_read()
        self.assertIs(caught.exception, primary)
        connection = self.connections[-1]
        owner = self.assert_owned_and_blocked(connection)
        connection.disable_faults()
        owner.close()
        self.assert_reusable()

    def test_readonly_connect_admission_retains_owner_without_admitting_writes(self):
        self.backend.close()
        self.backend = SQLiteCatalogBackend(self.path, read_only=True)
        primary = BackendError('unsupported')
        with self.connection_fault(statement='PRAGMA query_only=ON', primary=primary,
                close_error=sqlite3.OperationalError('close failed')):
            with self.assertRaises(BackendError) as caught: self.backend.begin_read()
        self.assertIs(caught.exception, primary)
        connection = self.connections[-1]
        owner = self.backend._active
        self.assertIsNotNone(owner)
        self.assertIs(owner._connection, connection)
        self.assertFalse(connection.wrapped.in_transaction)
        with patch('yadinassi.sqlite_catalog.sqlite3.connect', side_effect=AssertionError('must not open')):
            with self.assertRaisesRegex(BackendError, 'busy'): self.backend.begin_read()
            with self.assertRaisesRegex(BackendError, 'unsupported'): self.backend.begin_write(uuid4())
        connection.disable_faults()
        owner.close()
        self.assert_reusable()

    def test_connect_factory_failure_clears_empty_owner(self):
        for primary in (sqlite3.OperationalError('open failed'), KeyboardInterrupt('open interrupted')):
            with self.subTest(error=type(primary).__name__):
                with patch('yadinassi.sqlite_catalog.sqlite3.connect', side_effect=primary):
                    if isinstance(primary, sqlite3.Error):
                        with self.assertRaisesRegex(BackendError, 'storage_error'): self.backend.begin_read()
                    else:
                        with self.assertRaises(KeyboardInterrupt) as caught: self.backend.begin_read()
                        self.assertIs(caught.exception, primary)
                self.assertIsNone(self.backend._active)
                self.assert_reusable()

    def test_file_admission_failure_clears_empty_owner(self):
        primary = BackendError('invalid_input')
        with patch.object(self.backend, '_check_file', side_effect=primary), \
                patch('yadinassi.sqlite_catalog.sqlite3.connect', side_effect=AssertionError('must not open')):
            with self.assertRaises(BackendError) as caught: self.backend.begin_read()
        self.assertIs(caught.exception, primary)
        self.assertIsNone(self.backend._active)
        self.assert_reusable()

    def test_failed_transaction_probe_still_closes_and_preserves_primary(self):
        primary = BackendError('schema_changed')
        with self.connection_fault(statement='PRAGMA user_version', primary=primary,
                transaction_error=sqlite3.OperationalError('probe failed')):
            with self.assertRaises(BackendError) as caught: self.backend.begin_write(uuid4())
        self.assertIs(caught.exception, primary)
        self.assertEqual(self.connections[-1].close_calls, 1)
        self.assertIsNone(self.backend._active)
        self.assert_reusable()

    def test_error_after_physical_close_requires_confirmed_retry(self):
        primary = BackendError('schema_changed')
        with self.connection_fault(statement='PRAGMA user_version', primary=primary,
                close_error=sqlite3.OperationalError('close response lost'), close_after=True):
            with self.assertRaises(BackendError) as caught: self.backend.begin_write(uuid4())
        self.assertIs(caught.exception, primary)
        connection = self.connections[-1]
        owner = self.assert_owned_and_blocked(connection)
        with self.assertRaises(sqlite3.ProgrammingError): connection.wrapped.execute('SELECT 1')
        connection.disable_faults()
        # The old handle rejects the transaction probe, but idempotent close
        # still confirms release. The first probe error remains observable.
        with self.assertRaisesRegex(BackendError, 'storage_error'): owner.close()
        self.assertIsNone(owner._connection)
        self.assertIsNone(self.backend._active)
        owner.close()
        self.assert_reusable()

    def test_backend_close_retries_failed_admission_handle(self):
        with self.connection_fault(statement='PRAGMA user_version', primary=BackendError('schema_changed'),
                close_error=sqlite3.OperationalError('close failed')):
            with self.assertRaisesRegex(BackendError, 'schema_changed'): self.backend.begin_read()
        connection = self.connections[-1]
        owner = self.assert_owned_and_blocked(connection)
        with self.assertRaisesRegex(BackendError, 'storage_error'): self.backend.close()
        self.assertIs(self.backend._active, owner)
        connection.disable_faults()
        self.backend.close()
        self.assertIsNone(self.backend._active)
        with self.assertRaisesRegex(BackendError, 'closed'): self.backend.begin_read()

    def test_successful_admission_transfers_handle_without_closing_it(self):
        with self.connection_fault():
            view = self.backend.begin_write(uuid4())
        self.assertIsInstance(view, _View)
        self.assertIs(self.backend._active, view)
        self.assertIs(view._connection, self.connections[-1])
        self.assertEqual(self.connections[-1].close_calls, 0)
        self.assertEqual(len(view.catalogs()), 2)
        with patch('yadinassi.sqlite_catalog.sqlite3.connect', side_effect=AssertionError('must not open')):
            with self.assertRaisesRegex(BackendError, 'busy'): self.backend.begin_read()
        self.assertIs(self.backend._active, view)
        view.close()
        self.assertEqual(self.connections[-1].close_calls, 1)
        self.assert_reusable()

    def test_interrupted_empty_reservation_is_removed_without_opening(self):
        primary = KeyboardInterrupt('reservation')
        def assign(instance, name, value):
            object.__setattr__(instance, name, value)
            if instance is self.backend and name == '_active' and value is not None:
                raise primary
        with patch.object(SQLiteCatalogBackend, '__setattr__', assign), \
                patch('yadinassi.sqlite_catalog.sqlite3.connect', side_effect=AssertionError('must not open')):
            with self.assertRaises(KeyboardInterrupt) as caught: self.backend.begin_read()
        self.assertIs(caught.exception, primary)
        self.assertIsNone(self.backend._active)
        self.assert_reusable()

    def test_interrupted_view_transfer_closes_the_current_owner(self):
        primary = KeyboardInterrupt('transfer')
        def assign(instance, name, value):
            object.__setattr__(instance, name, value)
            if instance is self.backend and name == '_active' and isinstance(value, _View):
                raise primary
        with self.connection_fault(close_error=sqlite3.OperationalError('close failed')), \
                patch.object(SQLiteCatalogBackend, '__setattr__', assign):
            with self.assertRaises(KeyboardInterrupt) as caught: self.backend.begin_write(uuid4())
        self.assertIs(caught.exception, primary)
        view = self.backend._active
        self.assertIsInstance(view, _View)
        self.assertTrue(view._closed)
        self.assertIs(view._connection, self.connections[-1])
        with self.assertRaisesRegex(BackendError, 'closed'): view.commit()
        with self.assertRaisesRegex(BackendError, 'busy'): self.backend.begin_read()
        self.connections[-1].disable_faults()
        view.close()
        self.assert_reusable()


if __name__ == '__main__': unittest.main()
