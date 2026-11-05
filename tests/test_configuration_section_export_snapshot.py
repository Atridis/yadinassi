"""Export snapshots with real v3 catalog data and independently owned views."""
from contextlib import closing
from dataclasses import replace
from datetime import datetime
from decimal import Decimal
import hashlib
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch
from uuid import uuid4

from test_configuration_export_snapshot import InterleavingConnection
from test_sqlite_catalog_backend import configuration
from yadinassi.catalog_backend import (BackendError, CatalogDraft, CatalogKey, FieldSchema,
                                      TabularRow, TabularSectionRows, TabularSectionSchema)
from yadinassi.configuration_xml import ConfigurationFile
import yadinassi.sqlite_catalog as storage
from yadinassi.sqlite_catalog import SQLiteCatalogBackend
from yadinassi.sqlite_catalog_layout import quote_identifier


class ConfigurationSectionExportSnapshotTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / 'v3.sqlite'
        config = configuration()
        self.category, product = config.catalogs
        self.lines = TabularSectionSchema(uuid4(), 'Lines', product.fields)
        self.notes = TabularSectionSchema(uuid4(), 'Notes', (FieldSchema(uuid4(), 'Text', 'string', (32,)),))
        self.product = replace(product, tabular_sections=(self.lines, self.notes))
        files = config.files + (ConfigurationFile('Ext/Тест.bsl', b'', 'module'),
                                ConfigurationFile('Extra.xml', b'\xef\xbb\xbf<x>\r\n</x>', 'xml'))
        config = replace(config, catalogs=(self.category, self.product), files=files)
        self.expected_files = {file.path: file.content for file in files}
        self.backend = SQLiteCatalogBackend.create(self.path, config)
        self.addCleanup(self.backend.close)
        self.assertEqual(self.backend.storage_version, 3)
        category_key = CatalogKey(self.backend.database_id, self.category.identity, uuid4())
        self.key = CatalogKey(self.backend.database_id, self.product.identity, uuid4())
        values = ('owner', Decimal('1.25'), True, datetime(2024, 2, 29), category_key)
        self.sections = (TabularSectionRows(self.lines.identity, (
            TabularRow(uuid4(), values), TabularRow(uuid4(), ('second',) + values[1:]))),
            TabularSectionRows(self.notes.identity, (TabularRow(uuid4(), ('note',)),)))
        self.operation = uuid4()
        tx = self.backend.begin_write(self.operation)
        try:
            tx.create(CatalogDraft(category_key, 'C', 'category', False, ()))
            tx.create(CatalogDraft(self.key, 'P', 'product', False, values, self.sections))
            tx.commit()
        finally: tx.close()
        self.original = self.read()
        self.receipt = self.backend.committed_operation(self.operation)

    def read(self):
        view = self.backend.begin_read()
        try: return view.read_catalog(self.key)
        finally: view.close()

    def changed_draft(self):
        first = self.sections[0].rows[0]
        changed = replace(first, values=('pending row',) + first.values[1:])
        sections = (replace(self.sections[0], rows=(changed,) + self.sections[0].rows[1:]), self.sections[1])
        return CatalogDraft(self.key, self.original.code, 'pending owner', False, self.original.values, sections)

    def test_export_preserves_active_v3_read_or_pending_write_view(self):
        for writing in (False, True):
            with self.subTest(writing=writing):
                operation = uuid4()
                view = self.backend.begin_write(operation) if writing else self.backend.begin_read()
                try:
                    if writing: view.update(self.changed_draft(), self.original.revision)
                    expected = view.read_catalog(self.key)
                    changes, intents = view._changes, view._intents
                    budget = (view._section_write_bytes, view._section_write_rows)
                    before = self.path.read_bytes()
                    self.assertEqual(self.backend.export_configuration(), self.expected_files)
                    self.assertIs(self.backend._active, view)
                    self.assertFalse(view._closed)
                    self.assertIs(view._changes, changes)
                    self.assertIs(view._intents, intents)
                    self.assertEqual((view._section_write_bytes, view._section_write_rows), budget)
                    self.assertEqual(view.read_catalog(self.key), expected)
                    self.assertEqual(self.path.read_bytes(), before)
                    if writing:
                        revisions = view.commit()
                        self.assertEqual(revisions, (expected.revision,))
                        self.assertEqual(self.backend.committed_operation(operation)[1], revisions)
                finally: view.close()
                self.assertEqual(self.read(), expected)
        self.assertEqual(self.backend.committed_operation(self.operation), self.receipt)
        self.assertEqual(self.backend.export_configuration(), self.expected_files)

    def test_v3_interleave_source_owner_and_rows_cannot_bypass_export_preflight(self):
        owner_table = quote_identifier(self.backend._layout.table_name(self.product.identity))
        section_table = quote_identifier(self.backend._section_layout.table_name(self.product.identity, self.lines.identity))
        text_column = quote_identifier(self.backend._section_layout.field_name(
            self.product.identity, self.lines.identity, self.product.fields[0].identity))
        row_id = str(self.sections[0].rows[0].identity)
        for limit_kind in ('files', 'bytes'):
            with self.subTest(limit=limit_kind):
                payload = b'additional'; path = 'Concurrent-' + limit_kind + '.xml'
                args = (path, 'xml', payload, hashlib.sha256(payload).hexdigest())
                expected = self.backend.export_configuration()
                before_card = self.read()
                before_bytes = self.path.read_bytes()
                outcomes = []
                def writer_attempt():
                    with closing(sqlite3.connect(self.path, isolation_level=None, timeout=0)) as db:
                        db.execute('BEGIN IMMEDIATE')
                        db.execute('INSERT INTO configuration_file VALUES(?,?,?,?)', args)
                        db.execute('UPDATE ' + owner_table + ' SET description=?,revision=revision+1 WHERE record_id=?',
                                   ('interleaved owner', str(self.key.record_id)))
                        db.execute('UPDATE ' + section_table + ' SET ' + text_column + '=? WHERE owner_id=? AND row_id=?',
                                   ('interleaved row', str(self.key.record_id), row_id))
                        try:
                            db.execute('COMMIT')
                            outcomes.append('committed')
                        except sqlite3.OperationalError:
                            outcomes.append('locked')
                            db.execute('ROLLBACK')
                original_connect = self.backend._connect
                def connect(): return InterleavingConnection(original_connect(), writer_attempt)
                limit_name = '_MAX_FILES' if limit_kind == 'files' else '_MAX_CONFIG_BYTES'
                limit = len(expected) if limit_kind == 'files' else sum(map(len, expected.values()))
                with patch.object(storage, limit_name, limit), patch.object(self.backend, '_connect', side_effect=connect):
                    exported = self.backend.export_configuration()
                self.assertEqual(outcomes, ['locked'])
                self.assertEqual(exported, expected)
                self.assertEqual(self.read(), before_card)
                self.assertEqual(self.path.read_bytes(), before_bytes)
                self.assertIsNone(self.backend._active)
                # Once export releases its snapshot, this same transaction can
                # commit. Its added source then fails the original resource cap.
                writer_attempt()
                self.assertEqual(outcomes, ['locked', 'committed'])
                with patch.object(storage, limit_name, limit):
                    with self.assertRaisesRegex(BackendError, 'integrity'): self.backend.export_configuration()
                self.assertEqual(self.backend.export_configuration(), dict(expected, **{path: payload}))
                changed = self.read()
                self.assertEqual(changed.description, 'interleaved owner')
                self.assertEqual(int(changed.revision.token), int(before_card.revision.token) + 1)
                first = before_card.tabular_sections[0].rows[0]
                expected_rows = (replace(first, values=('interleaved row',) + first.values[1:]),) + before_card.tabular_sections[0].rows[1:]
                self.assertEqual(changed.tabular_sections, (
                    replace(before_card.tabular_sections[0], rows=expected_rows), before_card.tabular_sections[1]))
        self.assertEqual(self.backend.committed_operation(self.operation), self.receipt)

    def test_v3_failed_export_releases_only_export_connection_and_not_pending_view(self):
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute("UPDATE configuration_file SET sha256='invalid' WHERE path='Configuration.xml'")
        view = self.backend.begin_write(uuid4())
        try:
            view.update(self.changed_draft(), self.original.revision)
            expected = view.read_catalog(self.key)
            changes, intents = view._changes, view._intents
            with self.assertRaisesRegex(BackendError, 'integrity'): self.backend.export_configuration()
            self.assertIs(self.backend._active, view)
            self.assertFalse(view._closed)
            self.assertIs(view._changes, changes)
            self.assertIs(view._intents, intents)
            self.assertEqual(view.read_catalog(self.key), expected)
        finally: view.rollback()
        with closing(sqlite3.connect(self.path, isolation_level=None, timeout=0)) as db:
            db.execute('BEGIN IMMEDIATE')
            db.execute('UPDATE configuration_file SET sha256=? WHERE path=?',
                       (hashlib.sha256(self.expected_files['Configuration.xml']).hexdigest(), 'Configuration.xml'))
            db.execute('COMMIT')
        self.assertIsNone(self.backend._active)
        self.assertEqual(self.read(), self.original)
        self.assertEqual(self.backend.export_configuration(), self.expected_files)
        self.assertEqual(self.backend.committed_operation(self.operation), self.receipt)
