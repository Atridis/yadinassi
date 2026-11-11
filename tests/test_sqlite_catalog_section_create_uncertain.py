"""v3 creation faults with real concurrent backend writes, not native 1C evidence."""
from contextlib import closing, redirect_stderr, redirect_stdout
from dataclasses import replace
from datetime import datetime
from decimal import Decimal
from io import StringIO
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch
from uuid import uuid4

from test_sqlite_catalog_backend import configuration
from test_sqlite_catalog_create_uncertain import CreateConnection, mocked_cli_storage_source
from yadinassi.catalog_backend import (BackendError, CatalogDraft, CatalogKey, FieldSchema,
                                      TabularRow, TabularSectionRows, TabularSectionSchema)
from yadinassi.sqlite_catalog import SQLiteCatalogBackend


class SectionCreateConnection(CreateConnection):
    def __init__(self, wrapped, *, section_error=None, commit_after_error=None,
                 mark_after_commit=False, **fault):
        super().__init__(wrapped, **fault)
        self.section_error = section_error
        self.commit_after_error = commit_after_error
        self.mark_after_commit = mark_after_commit
        self.commit_calls = 0

    def execute(self, sql, *args):
        if (self.section_error is not None and sql.startswith('CREATE TABLE ')
                and 'owner_id TEXT NOT NULL REFERENCES' in sql):
            raise self.section_error
        if sql == 'COMMIT':
            self.commit_calls += 1
            if self.commit_after_error is not None or self.mark_after_commit:
                result = self.wrapped.execute(sql, *args)
                self.mark_once()
                if self.commit_after_error is not None: raise self.commit_after_error
                return result
        return super().execute(sql, *args)


class SQLiteSectionCreateUncertainTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        config = configuration()
        self.category, product = config.catalogs
        self.lines = TabularSectionSchema(uuid4(), 'Lines', product.fields)
        self.notes = TabularSectionSchema(uuid4(), 'Notes', (FieldSchema(uuid4(), 'Text', 'string', (32,)),))
        self.product = replace(product, tabular_sections=(self.lines, self.notes))
        self.config = replace(config, catalogs=(self.category, self.product))
        self.real_connect = sqlite3.connect
        self.handles = []
        self.addCleanup(self.close_handles)
        self.reset_path('owned')

    def reset_path(self, name):
        self.path = Path(self.temp.name) / (name + '.sqlite')
        self.saved_card = None
        self.saved_receipt = None
        self.after_write = None
        self.writer_calls = 0

    def close_handles(self):
        for handle in self.handles:
            try: handle.wrapped.close()
            except sqlite3.Error: pass

    def injected(self, **fault):
        calls = [0]
        def connect(*args, **kwargs):
            calls[0] += 1
            connection = self.real_connect(*args, **kwargs)
            if calls[0] != 1: return connection
            proxy = SectionCreateConnection(connection, **fault)
            self.handles.append(proxy)
            return proxy
        return patch('yadinassi.sqlite_catalog.sqlite3.connect', side_effect=connect)

    def write_concurrently(self):
        # Runs only after the creator's real COMMIT (or physical close). A
        # separate backend writes valid owners, typed rows and its own receipt.
        self.writer_calls += 1
        backend = SQLiteCatalogBackend(self.path)
        try:
            self.assertEqual(backend.storage_version, 3)
            category_key = CatalogKey(backend.database_id, self.category.identity, uuid4())
            self.product_key = CatalogKey(backend.database_id, self.product.identity, uuid4())
            stamp = datetime(2024, 2, 29, 12, 34, 56)
            owner_values = ('owner', Decimal('1.25'), True, stamp, category_key)
            first, second, note = uuid4(), uuid4(), uuid4()
            submitted = (TabularSectionRows(self.lines.identity, (
                TabularRow(first, ('x' * 32, Decimal('12.35'), True, stamp, category_key)),
                TabularRow(second, ('second', Decimal('-2.26'), False, datetime(1, 1, 1), category_key)))),
                TabularSectionRows(self.notes.identity, (TabularRow(note, ('note',)),)))
            self.expected_sections = (TabularSectionRows(self.lines.identity, (
                TabularRow(first, ('x' * 32, Decimal('12.35'), True, stamp, category_key)),
                TabularRow(second, ('second', Decimal('-2.26'), False, datetime(1, 1, 1), category_key)))),
                TabularSectionRows(self.notes.identity, (TabularRow(note, ('note',)),)))
            self.operation = uuid4()
            tx = backend.begin_write(self.operation)
            try:
                tx.create(CatalogDraft(category_key, 'C', 'category', False, ()))
                tx.create(CatalogDraft(self.product_key, 'P', 'product', False, owner_values, submitted))
                tx.commit()
            finally: tx.close()
            view = backend.begin_read()
            try:
                self.saved_card = view.read_catalog(self.product_key)
                self.saved_category = view.read_catalog(category_key)
                self.assertEqual(self.saved_card.tabular_sections, self.expected_sections)
            finally: view.close()
            self.saved_receipt = backend.committed_operation(self.operation)
            self.assertEqual(len(self.saved_receipt[1]), 2)
        finally: backend.close()
        self.after_write = self.path.read_bytes()
        self.created_inode = self.path.stat().st_ino

    def assert_complete_v3(self):
        backend = SQLiteCatalogBackend(self.path)
        try:
            self.assertEqual(backend.storage_version, 3)
            self.assertTrue(backend.capabilities().catalog_tabular_sections)
            self.assertEqual(backend.export_configuration(), {f.path: f.content for f in self.config.files})
            mappings = backend.inspect_section_storage_mapping()
            self.assertEqual({entry[2] for entry in mappings}, {self.lines.identity, self.notes.identity})
            if self.saved_card is not None:
                view = backend.begin_read()
                try:
                    self.assertEqual(view.read_catalog(self.product_key), self.saved_card)
                    self.assertEqual(view.read_catalog(self.product_key).tabular_sections, self.expected_sections)
                    self.assertEqual(view.read_catalog(self.saved_category.key), self.saved_category)
                finally: view.close()
                self.assertEqual(backend.committed_operation(self.operation), self.saved_receipt)
        finally: backend.close()
        if self.after_write is not None:
            self.assertEqual(self.path.read_bytes(), self.after_write)
            self.assertEqual(self.path.stat().st_ino, self.created_inode)
        with closing(self.real_connect(self.path.as_uri() + '?mode=ro', uri=True)) as db:
            self.assertEqual(db.execute('PRAGMA user_version').fetchone(), (3,))
            self.assertEqual(db.execute('PRAGMA foreign_key_check').fetchall(), [])
            self.assertEqual(db.execute('SELECT COUNT(*) FROM catalog_section_storage_map').fetchone(), (2,))

    def assert_reserved_without_schema(self):
        self.assertTrue(self.path.exists())
        with closing(self.real_connect(self.path.as_uri() + '?mode=ro', uri=True)) as db:
            self.assertEqual(db.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall(), [])
            self.assertEqual(db.execute('PRAGMA user_version').fetchone(), (0,))

    def test_v3_postcommit_concurrent_owner_and_rows_survive_errors_and_interruptions(self):
        for index, error in enumerate((sqlite3.OperationalError('lost response'), MemoryError('memory'), KeyboardInterrupt('interrupt'))):
            with self.subTest(error=type(error)):
                self.reset_path('commit-' + str(index))
                expected = BackendError if isinstance(error, sqlite3.Error) else type(error)
                with self.injected(commit_after_error=error, marker=self.write_concurrently):
                    with self.assertRaises(expected) as caught: SQLiteCatalogBackend.create(self.path, self.config)
                if expected is BackendError: self.assertEqual(caught.exception.code, 'uncertain_commit')
                else: self.assertIs(caught.exception, error)
                self.assertEqual(self.writer_calls, 1)
                self.assertEqual(self.handles[-1].commit_calls, 1)
                self.assert_complete_v3()

    def test_v3_postcommit_concurrent_rows_survive_close_before_or_after_release(self):
        for fault in ('before', 'after'):
            with self.subTest(close=fault):
                self.reset_path('close-' + fault)
                with self.injected(mark_after_commit=True, close=fault, marker=self.write_concurrently):
                    with self.assertRaisesRegex(BackendError, 'uncertain_commit'):
                        SQLiteCatalogBackend.create(self.path, self.config)
                self.assertEqual(self.writer_calls, 1)
                self.assert_complete_v3()

    def test_v3_failed_reopen_keeps_concurrent_owner_sections_and_receipt(self):
        real_init = SQLiteCatalogBackend.__init__
        def initialize(backend, *args, **kwargs):
            if self.saved_card is not None: raise BackendError('integrity')
            return real_init(backend, *args, **kwargs)
        with self.injected(mark_after_commit=True, marker=self.write_concurrently), \
                patch.object(SQLiteCatalogBackend, '__init__', initialize):
            with self.assertRaisesRegex(BackendError, 'uncertain_commit'):
                SQLiteCatalogBackend.create(self.path, self.config)
        self.assertEqual(self.writer_calls, 1)
        self.assert_complete_v3()

    def test_v3_precommit_section_ddl_failure_keeps_reserved_file_and_original_error(self):
        for index, error in enumerate((sqlite3.OperationalError('section DDL'), MemoryError('section memory'))):
            with self.subTest(error=type(error)):
                self.reset_path('ddl-' + str(index))
                expected = BackendError if isinstance(error, sqlite3.Error) else type(error)
                with self.injected(section_error=error):
                    with self.assertRaises(expected) as caught: SQLiteCatalogBackend.create(self.path, self.config)
                if expected is BackendError: self.assertEqual(caught.exception.code, 'storage_error')
                else: self.assertIs(caught.exception, error)
                self.assertEqual(self.handles[-1].commit_calls, 0)
                self.assert_reserved_without_schema()

    def test_v3_commit_failure_before_dispatch_keeps_reserved_file(self):
        with self.injected(commit='before'):
            with self.assertRaisesRegex(BackendError, 'uncertain_commit'):
                SQLiteCatalogBackend.create(self.path, self.config)
        self.assertEqual(self.handles[-1].commit_calls, 1)
        self.assert_reserved_without_schema()

    def test_v3_cli_uncertain_warning_preserves_actual_concurrent_owner_and_rows(self):
        from yadinassi import cli
        errors, output = StringIO(), StringIO()
        with mocked_cli_storage_source(self.config), \
                self.injected(commit_after_error=sqlite3.OperationalError('private diagnostic'), marker=self.write_concurrently), \
                redirect_stderr(errors), redirect_stdout(output):
            status = cli.main(['--create-db', str(self.path), '--import-xml', '/private/source'])
        self.assertEqual(status, 1)
        self.assertEqual(output.getvalue(), '')
        self.assertIn('outcome uncertain', errors.getvalue())
        self.assertIn('preserve the destination and SQLite journal', errors.getvalue())
        self.assertNotIn('configuration import refused', errors.getvalue())
        for private in ('/private', str(self.path), 'private diagnostic'):
            self.assertNotIn(private, errors.getvalue())
        self.assertEqual(self.writer_calls, 1)
        self.assert_complete_v3()

    def test_v3_cli_precommit_warning_preserves_actual_reserved_destination(self):
        from yadinassi import cli
        errors, output = StringIO(), StringIO()
        with mocked_cli_storage_source(self.config), \
                self.injected(section_error=sqlite3.OperationalError('private section SQL')), \
                redirect_stderr(errors), redirect_stdout(output):
            status = cli.main(['--create-db', str(self.path), '--import-xml', '/private/source'])
        self.assertEqual(status, 1)
        self.assertEqual(output.getvalue(), '')
        self.assertIn('database creation failed', errors.getvalue())
        self.assertIn('preserve and inspect', errors.getvalue())
        for absent in ('outcome uncertain', 'configuration import refused', '/private', str(self.path), 'private section SQL'):
            self.assertNotIn(absent, errors.getvalue())
        self.assertEqual(self.handles[-1].commit_calls, 0)
        self.assert_reserved_without_schema()

    def test_v3_cli_success_retains_version_section_layout_and_sources(self):
        from yadinassi import cli
        errors, output = StringIO(), StringIO()
        with mocked_cli_storage_source(self.config), \
                redirect_stderr(errors), redirect_stdout(output):
            status = cli.main(['--create-db', str(self.path), '--import-xml', '/private/source'])
        self.assertEqual(status, 0)
        self.assertEqual(errors.getvalue(), '')
        self.assertEqual(output.getvalue(), 'Created SQLite database.\n')
        self.assert_complete_v3()
