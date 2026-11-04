"""v3 admission/ownership faults on disposable SQLite with real section rows."""
from contextlib import contextmanager
from dataclasses import replace
from pathlib import Path
import sqlite3
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from uuid import uuid4

from test_sqlite_catalog_admission_cleanup import AdmissionFaultConnection
from test_sqlite_catalog_backend import configuration
from yadinassi.catalog_backend import (BackendError, CatalogDraft, CatalogKey, FieldSchema,
                                      TabularRow, TabularSectionRows, TabularSectionSchema)
from yadinassi.sqlite_catalog import SQLiteCatalogBackend, _View


class SQLiteCatalogSectionAdmissionCleanupTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / 'admission-v3.sqlite'
        config = configuration()
        field = FieldSchema(uuid4(), 'Text', 'string', (32,))
        section = TabularSectionSchema(uuid4(), 'Rows', (field,))
        self.schema = replace(config.catalogs[0], tabular_sections=(section,))
        config = replace(config, catalogs=(self.schema,) + config.catalogs[1:])
        self.backend = SQLiteCatalogBackend.create(self.path, config)
        self.assertEqual(self.backend.storage_version, 3)
        self.key = CatalogKey(self.backend.database_id, self.schema.identity, uuid4())
        self.sections = (TabularSectionRows(section.identity, (
            TabularRow(uuid4(), ('first',)), TabularRow(uuid4(), ('second',)))),)
        tx = self.backend.begin_write(uuid4())
        try:
            tx.create(CatalogDraft(self.key, '10', 'owner', False, (), self.sections))
            tx.commit()
        finally: tx.close()
        view = self.backend.begin_read()
        try: self.card = view.read_catalog(self.key)
        finally: view.close()
        self.before = self.path.read_bytes()
        self.real_connect = sqlite3.connect
        self.connections = []

    def tearDown(self):
        for connection in self.connections: connection.disable_faults()
        try:
            try: self.backend.close()
            except BackendError: pass
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

    def begin(self, writing):
        return self.backend.begin_write(uuid4()) if writing else self.backend.begin_read()

    def assert_owned_and_blocked(self, connection, *, transferred=False):
        owner = self.backend._active
        self.assertIsNotNone(owner)
        self.assertIs(owner._connection, connection)
        self.assertTrue(owner._closed)
        if transferred:
            self.assertIsInstance(owner, _View)
            with self.assertRaisesRegex(BackendError, 'closed'): owner.commit()
            with self.assertRaisesRegex(BackendError, 'closed'): owner.read_catalog(self.key)
        else:
            self.assertNotIsInstance(owner, _View)
            self.assertFalse(hasattr(owner, 'commit'))
        with patch('yadinassi.sqlite_catalog.sqlite3.connect', side_effect=AssertionError('must not reopen')):
            with self.assertRaisesRegex(BackendError, 'busy'): self.backend.begin_read()
            with self.assertRaisesRegex(BackendError, 'busy'): self.backend.begin_write(uuid4())
        return owner

    def assert_persisted_unchanged(self):
        self.assertIsNone(self.backend._active)
        view = self.backend.begin_read()
        try:
            self.assertEqual(view.read_catalog(self.key), self.card)
            self.assertEqual(view.read_catalog(self.key).tabular_sections, self.sections)
        finally: view.close()
        self.assertEqual(self.path.read_bytes(), self.before)

    def test_section_registry_admission_fault_keeps_owner_and_original_error(self):
        statements = ('SELECT COUNT(*) FROM catalog_section_storage_map',
                      'SELECT catalog_id,section_id,physical_name FROM catalog_section_storage_map')
        for writing in (False, True):
            for statement in statements:
                for error_type in (sqlite3.OperationalError, MemoryError, KeyboardInterrupt, SystemExit):
                    with self.subTest(writing=writing, statement=statement, error=error_type):
                        primary = error_type('schema_changed')
                        expected_type = BackendError if isinstance(primary, sqlite3.Error) else error_type
                        with self.connection_fault(statement=statement, primary=primary,
                                rollback_error=sqlite3.OperationalError('rollback failed'),
                                close_error=sqlite3.OperationalError('close failed')):
                            with self.assertRaises(expected_type) as caught: self.begin(writing)
                        if isinstance(primary, sqlite3.Error):
                            self.assertEqual(caught.exception.code, 'busy')
                        else:
                            self.assertIs(caught.exception, primary)
                        connection = self.connections[-1]
                        owner = self.assert_owned_and_blocked(connection)
                        self.assertIn(statement, connection.statements)
                        self.assertTrue(connection.wrapped.in_transaction)
                        self.assertEqual(connection.close_calls, 1)
                        connection.disable_faults()
                        owner.close()
                        self.assert_persisted_unchanged()

    def test_changed_v3_table_or_field_mapping_is_rejected_before_view_admission(self):
        for writing in (False, True):
            for mapping in ('_tables', '_fields'):
                with self.subTest(writing=writing, mapping=mapping):
                    changed = SimpleNamespace(_tables=dict(self.backend._section_layout._tables),
                                              _fields=dict(self.backend._section_layout._fields))
                    getattr(changed, mapping).pop(next(iter(getattr(changed, mapping))))
                    with self.connection_fault(close_error=sqlite3.OperationalError('close failed')), \
                            patch('yadinassi.sqlite_catalog.load_section_layout', return_value=changed):
                        with self.assertRaisesRegex(BackendError, 'schema_changed'): self.begin(writing)
                    connection = self.connections[-1]
                    owner = self.assert_owned_and_blocked(connection)
                    self.assertFalse(connection.wrapped.in_transaction)  # Rollback succeeded.
                    connection.disable_faults()
                    owner.close()
                    self.assert_persisted_unchanged()

    def test_v3_interrupted_owner_transfer_retains_handle_and_never_admits_mutations(self):
        for writing in (False, True):
            for after in (False, True):
                with self.subTest(writing=writing, after=after):
                    primary = KeyboardInterrupt('v3 owner transfer')
                    def assign(instance, name, value):
                        transfer = instance is self.backend and name == '_active' and isinstance(value, _View)
                        if transfer and not after: raise primary
                        object.__setattr__(instance, name, value)
                        if transfer: raise primary
                    with self.connection_fault(close_error=sqlite3.OperationalError('close failed')), \
                            patch.object(SQLiteCatalogBackend, '__setattr__', assign):
                        with self.assertRaises(KeyboardInterrupt) as caught: self.begin(writing)
                    self.assertIs(caught.exception, primary)
                    connection = self.connections[-1]
                    owner = self.assert_owned_and_blocked(connection, transferred=after)
                    self.assertFalse(connection.wrapped.in_transaction)
                    connection.disable_faults()
                    owner.close()
                    self.assert_persisted_unchanged()

    def test_successful_v3_admission_transfers_live_handle_and_preserves_exact_rows(self):
        for writing in (False, True):
            with self.subTest(writing=writing):
                with self.connection_fault(): view = self.begin(writing)
                connection = self.connections[-1]
                try:
                    self.assertIs(self.backend._active, view)
                    self.assertIsInstance(view, _View)
                    self.assertIs(view._connection, connection)
                    self.assertFalse(view._closed)
                    self.assertEqual(connection.close_calls, 0)
                    self.assertIn('SELECT COUNT(*) FROM catalog_section_storage_map', connection.statements)
                    self.assertEqual(view.read_catalog(self.key), self.card)
                    with self.assertRaisesRegex(BackendError, 'busy'): self.backend.begin_read()
                    with self.assertRaisesRegex(BackendError, 'busy'): self.backend.begin_write(uuid4())
                finally: view.close()
                self.assertEqual(connection.close_calls, 1)
                self.assertIsNone(view._connection)
                self.assert_persisted_unchanged()
