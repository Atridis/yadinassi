"""Owned SQLite section fixtures only; no XML, BSL or native 1C support implied."""
from contextlib import closing
from dataclasses import replace
import datetime
import decimal
import hashlib
from pathlib import Path
import sqlite3
import tempfile
import unittest
from uuid import UUID, uuid4

from test_sqlite_catalog_backend import configuration
from yadinassi.catalog_backend import (
    BackendError, CatalogDraft, CatalogKey, CatalogSchema, FieldSchema,
    TabularRow, TabularSectionRows, TabularSectionSchema,
)
from yadinassi.sqlite_catalog import SQLiteCatalogBackend, _json, _schema_data
from yadinassi.sqlite_catalog_layout import quote_identifier


class ConnectionFault:
    """Delegate all SQLite behavior except a precisely selected execute call."""
    def __init__(self, connection, fail):
        self.connection, self.fail = connection, fail

    def __getattr__(self, name):
        return getattr(self.connection, name)

    def execute(self, sql, parameters=()):
        return self.fail(self.connection, sql, parameters)


class CatalogSectionTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / 'sections.sqlite'
        config = configuration()
        self.category, product = config.catalogs
        self.lines = TabularSectionSchema(uuid4(), 'Lines', product.fields)
        self.notes = TabularSectionSchema(uuid4(), 'Notes', (
            FieldSchema(uuid4(), 'Text', 'string', (65536,)),))
        self.product = replace(product, tabular_sections=(self.lines, self.notes))
        self.config = replace(config, catalogs=(self.category, self.product))
        self.backend = SQLiteCatalogBackend.create(self.path, self.config)
        self.addCleanup(lambda: self.backend.close())

    def values(self, text='текст', amount='12.30', active=True):
        return (text, decimal.Decimal(amount), active,
                datetime.datetime(1, 1, 1),
                CatalogKey(self.backend.database_id, self.category.identity, UUID(int=0)))

    def section(self, *rows):
        return TabularSectionRows(self.lines.identity, tuple(rows))

    def row(self, text='строка', amount='12.30'):
        return TabularRow(uuid4(), self.values(text, amount))

    def draft(self, sections=None, code='10'):
        return CatalogDraft(
            CatalogKey(self.backend.database_id, self.product.identity, uuid4()),
            code, 'Owner', False, self.values(), sections)

    def create(self, draft, operation=None):
        tx = self.backend.begin_write(operation or uuid4())
        try:
            tx.create(draft)
            return tx.commit()[0]
        finally:
            tx.close()

    def update(self, draft, revision, operation=None):
        tx = self.backend.begin_write(operation or uuid4())
        try:
            tx.update(draft, revision)
            return tx.commit()[0]
        finally:
            tx.close()

    def read(self, key, backend=None):
        view = (backend or self.backend).begin_read()
        try:
            return view.read_catalog(key)
        finally:
            view.close()

    def reopen(self):
        self.backend.close()
        self.backend = SQLiteCatalogBackend(self.path)

    def sql(self, sql, args=()):
        with closing(sqlite3.connect(self.path)) as connection, connection:
            return connection.execute(sql, args).fetchall()

    def table(self, section=None):
        return quote_identifier(self.backend._section_layout.table_name(
            self.product.identity, (section or self.lines).identity))

    def expected(self, *rows, notes=()):
        return (self.section(*rows), TabularSectionRows(self.notes.identity, notes))

    def test_create_reopen_preserves_exact_types_uuid_and_row_order(self):
        # Deliberately oppose UUID sort order to require persisted row position.
        first = TabularRow(UUID(int=99), self.values('первый', '0.10', False))
        second = TabularRow(UUID(int=1), self.values('второй', '-12.30'))
        note = TabularRow(uuid4(), ('заметка',))
        draft = self.draft(self.expected(first, second, notes=(note,)))
        revision = self.create(draft)
        self.reopen()
        card = self.read(draft.key)
        self.assertEqual(card.revision, revision)
        self.assertEqual(card.values, draft.values)
        self.assertEqual(card.tabular_sections, draft.tabular_sections)
        values = card.tabular_sections[0].rows[0].values
        for actual, kind in zip(values, (str, decimal.Decimal, bool, datetime.datetime, CatalogKey)):
            self.assertIs(type(actual), kind)
        self.assertIs(type(card.tabular_sections[0].rows[0].identity), UUID)

    def test_create_none_exposes_every_section_as_empty(self):
        draft = self.draft()
        self.create(draft)
        self.assertEqual(self.read(draft.key).tabular_sections, self.expected())

    def test_update_none_preserves_rows_and_explicit_omission_clears_section(self):
        first, second = self.row(), self.row('second')
        note = TabularRow(uuid4(), ('keep until replacement',))
        draft = self.draft(self.expected(first, second, notes=(note,)))
        revision = self.create(draft)
        unchanged = replace(draft, description='Edited', tabular_sections=None)
        revision = self.update(unchanged, revision)
        self.assertEqual(self.read(draft.key).tabular_sections, draft.tabular_sections)
        reordered = replace(draft, tabular_sections=(self.section(second, first),))
        revision = self.update(reordered, revision)
        card = self.read(draft.key)
        self.assertEqual(card.tabular_sections, self.expected(second, first))
        self.assertEqual(card.revision, revision)

    def test_explicit_empty_clears_all_rows_but_keeps_owner(self):
        draft = self.draft((self.section(self.row()),))
        revision = self.create(draft)
        revision = self.update(replace(draft, tabular_sections=()), revision)
        card = self.read(draft.key)
        self.assertEqual(card.tabular_sections, self.expected())
        self.assertEqual(card.key, draft.key)
        self.assertEqual(card.revision, revision)

    def test_deletion_mark_preserves_section_rows(self):
        draft = self.draft((self.section(self.row()),))
        revision = self.create(draft)
        self.update(replace(draft, deletion_mark=True, tabular_sections=None), revision)
        card = self.read(draft.key)
        self.assertTrue(card.deletion_mark)
        self.assertEqual(card.tabular_sections, self.expected(*draft.tabular_sections[0].rows))

    def test_stale_update_cannot_change_owner_or_sections(self):
        draft = self.draft((self.section(self.row()),))
        revision = self.create(draft)
        self.update(replace(draft, description='Current', tabular_sections=None), revision)
        before = self.read(draft.key)
        tx = self.backend.begin_write(uuid4())
        try:
            with self.assertRaisesRegex(BackendError, 'conflict'):
                tx.update(replace(draft, description='Stale', tabular_sections=()), revision)
            tx.commit()
        finally:
            tx.close()
        self.assertEqual(self.read(draft.key), before)

    def test_explicit_rollback_restores_owner_and_sections(self):
        draft = self.draft((self.section(self.row()),))
        revision = self.create(draft)
        before = self.read(draft.key)
        tx = self.backend.begin_write(uuid4())
        tx.update(replace(draft, description='Rollback', tabular_sections=()), revision)
        tx.rollback()
        self.assertEqual(self.read(draft.key), before)
        new = self.draft((self.section(self.row()),), code='20')
        tx = self.backend.begin_write(uuid4())
        tx.create(new)
        tx.rollback()
        self.assertIsNone(self.read(new.key))

    def install_second_insert_fault(self, tx):
        original = tx._connection
        table = self.table()
        seen = []
        def fail(connection, sql, args):
            if sql.lstrip().upper().startswith('INSERT') and table in sql:
                seen.append(sql)
                if len(seen) == 2:
                    raise sqlite3.OperationalError('injected section insertion failure')
            return connection.execute(sql, args)
        tx._connection = ConnectionFault(original, fail)
        return seen

    def test_midway_update_failure_is_atomic_and_transaction_can_continue(self):
        draft = self.draft((self.section(self.row()),))
        revision = self.create(draft)
        before = self.read(draft.key)
        tx = self.backend.begin_write(uuid4())
        seen = self.install_second_insert_fault(tx)
        try:
            with self.assertRaisesRegex(BackendError, 'storage_error'):
                tx.update(replace(draft, description='Must roll back',
                    tabular_sections=(self.section(self.row(), self.row()),)), revision)
            self.assertEqual(len(seen), 2)
            self.assertEqual(tx.read_catalog(draft.key), before)
            survivor = self.draft(code='20')
            tx.create(survivor)
            revisions = tx.commit()
            self.assertEqual(len(revisions), 1)
            self.assertEqual(revisions[0].record_id, survivor.key.record_id)
        finally:
            tx.close()
        self.assertEqual(self.read(draft.key), before)

    def test_midway_create_failure_leaves_no_owner_or_rows(self):
        draft = self.draft((self.section(self.row(), self.row()),))
        tx = self.backend.begin_write(uuid4())
        seen = self.install_second_insert_fault(tx)
        try:
            with self.assertRaisesRegex(BackendError, 'storage_error'):
                tx.create(draft)
            self.assertEqual(len(seen), 2)
            self.assertIsNone(tx.read_catalog(draft.key))
            self.assertEqual(tx.commit(), ())
        finally:
            tx.close()
        self.assertEqual(self.sql('SELECT COUNT(*) FROM ' + self.table()), [(0,)])
        self.assertIsNone(self.read(draft.key))

    def test_replacement_never_deletes_owner(self):
        draft = self.draft((self.section(self.row()),))
        revision = self.create(draft)
        owner = quote_identifier(self.backend._layout.table_name(self.product.identity))
        tx = self.backend.begin_write(uuid4())
        statements = []
        tx._connection.set_trace_callback(statements.append)
        try:
            tx.update(replace(draft, tabular_sections=()), revision)
            tx.commit()
        finally:
            tx.close()
        self.assertFalse(any(sql.lstrip().upper().startswith('DELETE FROM ' + owner.upper())
                             for sql in statements))
        self.assertIsNotNone(self.read(draft.key))

    def test_receipt_binds_row_identity_values_order_and_section_identity(self):
        first, second = self.row(), self.row('second')
        draft = self.draft((self.section(first, second),))
        operation = uuid4()
        revision = self.create(draft, operation)
        self.assertEqual(self.backend.resolve_write(operation, draft), revision)
        alternatives = (
            (self.section(second, first),),
            (self.section(replace(first, identity=uuid4()), second),),
            (self.section(replace(first, values=self.values('changed')), second),),
            (TabularSectionRows(self.notes.identity, ()),),
            (), None,
        )
        for sections in alternatives:
            with self.subTest(sections=sections):
                with self.assertRaises(BackendError):
                    self.backend.resolve_write(operation, replace(draft, tabular_sections=sections))

    def test_receipt_distinguishes_none_from_explicit_empty(self):
        for sections in (None, ()):
            with self.subTest(sections=sections):
                draft = self.draft(sections, code='none' if sections is None else 'empty')
                operation = uuid4()
                revision = self.create(draft, operation)
                self.assertEqual(self.backend.resolve_write(operation, draft), revision)
                with self.assertRaisesRegex(BackendError, 'conflict'):
                    self.backend.resolve_write(operation,
                        replace(draft, tabular_sections=() if sections is None else None))

    def test_uncertain_commit_after_actual_commit_resolves_on_reopen(self):
        draft = self.draft((self.section(self.row()),))
        operation = uuid4()
        tx = self.backend.begin_write(operation)
        tx.create(draft)
        def fail_after_commit(connection, sql, args):
            result = connection.execute(sql, args)
            if sql.strip().upper() == 'COMMIT':
                raise sqlite3.OperationalError('lost commit acknowledgement')
            return result
        tx._connection = ConnectionFault(tx._connection, fail_after_commit)
        with self.assertRaisesRegex(BackendError, 'uncertain_commit'):
            tx.commit()
        self.reopen()
        revision = self.backend.resolve_write(operation, draft)
        self.assertIsNotNone(revision)
        card = self.read(draft.key)
        self.assertEqual(card.revision, revision)
        self.assertEqual(card.tabular_sections, self.expected(*draft.tabular_sections[0].rows))
        self.assertEqual(self.sql('SELECT COUNT(*) FROM ' + self.table()), [(1,)])

    def test_readonly_reopen_reads_sections_and_refuses_writes(self):
        draft = self.draft((self.section(self.row()),))
        self.create(draft)
        self.backend.close()
        before = self.path.read_bytes()
        readonly = SQLiteCatalogBackend(self.path, read_only=True)
        try:
            self.assertEqual(self.read(draft.key, readonly).tabular_sections,
                             self.expected(*draft.tabular_sections[0].rows))
            with self.assertRaisesRegex(BackendError, 'unsupported'):
                readonly.begin_write(uuid4())
        finally:
            readonly.close()
        self.assertEqual(self.path.read_bytes(), before)

    def test_v3_physical_layout_owner_fk_and_row_constraints(self):
        self.assertEqual(self.backend.storage_version, 3)
        self.assertEqual(self.sql('PRAGMA user_version'), [(3,)])
        table = self.table()
        columns = self.sql('PRAGMA table_info(' + table + ')')
        expected = {'owner_id', 'row_id', 'row_number'} | {
            self.backend._section_layout.field_name(self.product.identity, self.lines.identity, f.identity)
            for f in self.lines.fields}
        self.assertEqual({row[1] for row in columns}, expected)
        self.assertEqual([row[1] for row in sorted(columns, key=lambda row: row[5]) if row[5]],
                         ['owner_id', 'row_id'])
        owner_table = self.backend._layout.table_name(self.product.identity)
        foreign = self.sql('PRAGMA foreign_key_list(' + table + ')')
        self.assertTrue(any(row[2] == owner_table and row[3:5] == ('owner_id', 'record_id') for row in foreign))
        unique_columns = []
        for index in self.sql('PRAGMA index_list(' + table + ')'):
            if index[2]:
                unique_columns.append(tuple(row[2] for row in self.sql(
                    'PRAGMA index_info(' + quote_identifier(index[1]) + ')')))
        self.assertIn(('owner_id', 'row_number'), unique_columns)

    def test_duplicate_row_ids_and_unknown_sections_are_rejected_atomically(self):
        row = self.row()
        malformed = ((self.section(row, row),),
                     (self.section(row), self.section()),
                     (TabularSectionRows(uuid4(), ()),),
                     (self.section(replace(row, identity=UUID(int=0))),))
        for sections in malformed:
            with self.subTest(sections=sections):
                draft = self.draft(sections)
                tx = self.backend.begin_write(uuid4())
                try:
                    with self.assertRaises(BackendError):
                        tx.create(draft)
                    self.assertIsNone(tx.read_catalog(draft.key))
                finally:
                    tx.rollback()

    def test_row_identity_is_scoped_to_owner_and_section(self):
        row = self.row()
        first = self.draft((self.section(row),))
        second = self.draft((self.section(row),), code='20')
        self.create(first)
        self.create(second)
        self.assertEqual(self.read(first.key).tabular_sections[0].rows, (row,))
        self.assertEqual(self.read(second.key).tabular_sections[0].rows, (row,))

    def test_section_values_enforce_exact_types_and_reference_ownership(self):
        valid = self.values()
        bad_values = (valid[:1] + (1.25,) + valid[2:],
                      valid[:2] + (1,) + valid[3:],
                      valid[:1] + (decimal.Decimal('NaN'),) + valid[2:],
                      valid[:1] + (decimal.Decimal('Infinity'),) + valid[2:],
                      valid[:-1] + (CatalogKey(uuid4(), self.category.identity, UUID(int=0)),),
                      valid[:-1] + (CatalogKey(self.backend.database_id, self.category.identity, uuid4()),),
                      valid[:-1])
        for values in bad_values:
            with self.subTest(values=values):
                tx = self.backend.begin_write(uuid4())
                try:
                    with self.assertRaises(BackendError):
                        tx.create(self.draft((self.section(TabularRow(uuid4(), values)),)))
                finally:
                    tx.rollback()

    def test_row_limit_counts_all_sections_for_one_owner(self):
        lines = tuple(self.row() for _ in range(600))
        notes = tuple(TabularRow(uuid4(), ('note',)) for _ in range(400))
        draft = self.draft(self.expected(*lines, notes=notes))
        revision = self.create(draft)
        self.assertEqual(sum(len(s.rows) for s in self.read(draft.key).tabular_sections), 1000)
        too_many = replace(draft, tabular_sections=self.expected(
            *lines, notes=notes + (TabularRow(uuid4(), ('one too many',)),)))
        with self.assertRaises(BackendError):
            self.update(too_many, revision)
        self.assertEqual(self.read(draft.key).revision, revision)
        self.assertEqual(sum(len(s.rows) for s in self.read(draft.key).tabular_sections), 1000)

    def test_section_payload_limit_is_aggregate_not_per_row(self):
        notes = tuple(TabularRow(uuid4(), ('x' * 65536,)) for _ in range(17))
        draft = self.draft((TabularSectionRows(self.notes.identity, notes),))
        with self.assertRaises(BackendError):
            self.create(draft)
        self.assertIsNone(self.read(draft.key))

    def test_section_count_limits_reject_before_creating_file(self):
        too_many = tuple(TabularSectionSchema(uuid4(), 'Section%d' % i) for i in range(17))
        configs = (replace(self.config, catalogs=(self.category, replace(self.product, tabular_sections=too_many))),
                   replace(self.config, catalogs=tuple(CatalogSchema(
                       uuid4(), 'Catalog%d' % i, 8, 64,
                       tabular_sections=tuple(TabularSectionSchema(uuid4(), 'Section%d' % j)
                                              for j in range(16))) for i in range(33))))
        for index, config in enumerate(configs):
            path = Path(self.directory.name) / ('limit%d.sqlite' % index)
            with self.assertRaises(BackendError):
                SQLiteCatalogBackend.create(path, config)
            self.assertFalse(path.exists())

    def test_corrupt_persisted_row_identity_is_not_returned(self):
        draft = self.draft((self.section(self.row()),))
        self.create(draft)
        self.sql('UPDATE ' + self.table() + ' SET row_id=?', ('not-a-uuid',))
        with self.assertRaises(BackendError):
            self.read(draft.key)

    def test_corrupt_persisted_typed_value_is_not_coerced(self):
        draft = self.draft((self.section(self.row()),))
        self.create(draft)
        field = self.lines.fields[1]
        column = quote_identifier(self.backend._section_layout.field_name(
            self.product.identity, self.lines.identity, field.identity))
        self.sql('UPDATE ' + self.table() + ' SET ' + column + '=?', ('NaN',))
        with self.assertRaises(BackendError):
            self.read(draft.key)

    def test_corrupt_row_order_gap_is_not_silently_renumbered(self):
        draft = self.draft((self.section(self.row(), self.row()),))
        self.create(draft)
        self.sql('UPDATE ' + self.table() + ' SET row_number=9 WHERE row_number=2')
        with self.assertRaises(BackendError):
            self.read(draft.key)

    def test_persisted_aggregate_payload_overflow_is_rejected_on_read(self):
        notes = tuple(TabularRow(uuid4(), ('small',)) for _ in range(17))
        draft = self.draft((TabularSectionRows(self.notes.identity, notes),))
        self.create(draft)
        column = quote_identifier(self.backend._section_layout.field_name(
            self.product.identity, self.notes.identity, self.notes.fields[0].identity))
        self.sql('UPDATE ' + self.table(self.notes) + ' SET ' + column + '=?', ('x' * 65536,))
        with self.assertRaises(BackendError):
            self.read(draft.key)

    def test_mapping_tamper_is_rejected_on_reopen(self):
        from copy import deepcopy
        # Malformed new section metadata must stay inside BackendError, never
        # leak UUID constructor AttributeError from untrusted JSON values.
        definition = _schema_data(self.product)
        for malformed in (123, {}, None):
            changed = deepcopy(definition)
            changed[5][0][0] = malformed
            self.sql('UPDATE catalog_schema SET definition=? WHERE identity=?',
                     (_json(changed), str(self.product.identity)))
            with self.assertRaises(BackendError):
                SQLiteCatalogBackend(self.path)
        self.sql('UPDATE catalog_schema SET definition=? WHERE identity=?',
                 (_json(definition), str(self.product.identity)))
        self.backend.close()
        self.sql('UPDATE catalog_section_storage_map SET physical_name=? WHERE section_id=?',
                 ('catalog_section_missing', str(self.lines.identity)))
        with self.assertRaises(BackendError):
            SQLiteCatalogBackend(self.path)

    def test_nonempty_reference_in_section_roundtrips(self):
        key = CatalogKey(self.backend.database_id, self.category.identity, uuid4())
        category = CatalogDraft(key, 'C1', 'Category', False, ())
        self.create(category)
        row = TabularRow(uuid4(), self.values()[:-1] + (key,))
        draft = self.draft((self.section(row),))
        self.create(draft)
        self.reopen()
        self.assertEqual(self.read(draft.key).tabular_sections[0].rows, (row,))

    def test_external_section_ddl_after_open_is_rejected(self):
        self.sql('ALTER TABLE ' + self.table() + ' ADD COLUMN unexpected TEXT')
        with self.assertRaises(BackendError):
            self.backend.begin_read()

    def test_hostile_names_are_quoted_and_mapping_survives_reopen(self):
        self.backend.close()
        lines = replace(self.lines, name='Строки"; DROP TABLE catalog_schema;--',
                        fields=(replace(self.lines.fields[0], name='Поле";--'),) + self.lines.fields[1:])
        product = replace(self.product, name='Товары";--', tabular_sections=(lines, self.notes))
        path = Path(self.directory.name) / 'hostile.sqlite'
        backend = SQLiteCatalogBackend.create(path, replace(self.config, catalogs=(self.category, product)))
        try:
            mapping = backend.inspect_section_storage_mapping()
            row = next(row for row in mapping if row[2] == lines.identity)
            self.assertEqual(row[:4], (product.identity, product.name, lines.identity, lines.name))
            self.assertEqual(row[5][0][:2], (lines.fields[0].identity, lines.fields[0].name))
            backend.close()
            backend = SQLiteCatalogBackend(path)
            self.assertEqual(backend.inspect_section_storage_mapping(), mapping)
        finally:
            backend.close()

    def test_renamed_and_reused_names_keep_uuid_storage_mapping(self):
        draft = self.draft((self.section(self.row()),))
        self.create(draft)
        before_card = self.read(draft.key)
        before_map = self.backend.inspect_section_storage_mapping()
        # Fixture-only metadata rename. Never recompute or rewrite the registry.
        fields = self.lines.fields
        renamed_lines = replace(self.lines, name=self.notes.name, fields=(
            replace(fields[0], name=fields[1].name), replace(fields[1], name=fields[0].name)) + fields[2:])
        renamed_notes = replace(self.notes, name=self.lines.name)
        renamed_product = replace(self.product, name=self.category.name,
                                  tabular_sections=(renamed_lines, renamed_notes))
        renamed_category = replace(self.category, name=self.product.name)
        self.backend.close()
        with closing(sqlite3.connect(self.path)) as connection, connection:
            connection.execute('UPDATE catalog_schema SET name=? WHERE identity=?',
                               ('temporary_fixture_name', str(self.product.identity)))
            for schema in (renamed_category, renamed_product):
                connection.execute('UPDATE catalog_schema SET name=?, definition=? WHERE identity=?',
                                   (schema.name, _json(_schema_data(schema)), str(schema.identity)))
        self.reopen()
        after_map = self.backend.inspect_section_storage_mapping()
        storage = lambda mapping: {(r[0], r[2]): (r[4], {f[0]: f[2] for f in r[5]}) for r in mapping}
        self.assertEqual(storage(before_map), storage(after_map))
        row = next(r for r in after_map if r[2] == self.lines.identity)
        self.assertEqual(row[1], renamed_product.name)
        self.assertEqual(row[3], renamed_lines.name)
        self.assertEqual(row[5][0][1], renamed_lines.fields[0].name)
        self.assertEqual(self.read(draft.key), before_card)

    def test_v3_capability_and_runtime_activation_are_explicit(self):
        from yadinassi.database_context import SQLiteDBContext
        self.assertTrue(self.backend.capabilities().catalog_tabular_sections)
        self.backend.close()
        before = self.path.read_bytes()
        context = SQLiteDBContext(self.path)
        try:
            with self.assertRaisesRegex(BackendError, 'unsupported'):
                context.require_active()
        finally:
            context.close()
        self.assertEqual(before, self.path.read_bytes())
        self.reopen()

    def test_selection_and_scan_share_nested_row_budget(self):
        from unittest.mock import patch
        from yadinassi.catalog_backend import CatalogSelection, CatalogScanRequest
        for code in ('10', '20'):
            self.create(self.draft((self.section(self.row(), self.row()),), code=code))
        with patch('yadinassi.sqlite_catalog._MAX_ROWS', 3):
            view = self.backend.begin_read()
            try:
                with self.assertRaisesRegex(BackendError, 'unsupported'):
                    view.select_catalog(self.product.identity, CatalogSelection(2))
                with self.assertRaisesRegex(BackendError, 'unsupported'):
                    view.scan_catalog(self.product.identity, CatalogScanRequest(page_size=1))
            finally:
                view.close()

    def test_schema_reuse_preserves_full_section_cards(self):
        from yadinassi.catalog_backend import CatalogScanRequest, CatalogOrder
        expected = []
        for code in ('10', '20'):
            draft = self.draft((self.section(self.row(text=code)),), code=code)
            self.create(draft)
            expected.append(self.read(draft.key))
        view = self.backend.begin_read()
        self.addCleanup(view.close)
        queries = []
        view._connection.set_trace_callback(queries.append)
        for read in (lambda: view.select_catalog(self.product.identity),
                     lambda: view.scan_catalog(self.product.identity, CatalogScanRequest(
                         order=(CatalogOrder('code'),))).cards):
            queries.clear()
            self.assertEqual(read(), tuple(expected))
            self.assertEqual(sum(query.startswith('SELECT definition FROM catalog_schema')
                                 for query in queries), 1)

    def test_commit_failure_before_actual_commit_has_no_receipt_or_rows(self):
        operation = uuid4()
        draft = self.draft((self.section(self.row()),))
        tx = self.backend.begin_write(operation)
        tx.create(draft)
        def fail_before_commit(connection, sql, args):
            if sql.strip().upper() == 'COMMIT':
                raise sqlite3.OperationalError('commit refused before execution')
            return connection.execute(sql, args)
        tx._connection = ConnectionFault(tx._connection, fail_before_commit)
        with self.assertRaisesRegex(BackendError, 'uncertain_commit'):
            tx.commit()
        self.reopen()
        self.assertIsNone(self.backend.resolve_write(operation, draft))
        self.assertIsNone(self.read(draft.key))
        self.assertEqual(self.sql('SELECT COUNT(*) FROM ' + self.table()), [(0,)])

    def test_legacy_none_hash_is_unchanged_in_v3(self):
        draft = self.draft()
        operation = uuid4()
        revision = self.create(draft, operation)
        view = self.backend.begin_read()
        try:
            normalized, encoded_values = view._draft(draft)
            self.assertEqual(normalized, draft)
        finally:
            view.close()
        old_intent = [[str(draft.key.catalog_id), str(draft.key.record_id),
                       draft.code, draft.description, draft.deletion_mark, encoded_values, 1]]
        old_hash = hashlib.sha256(_json(old_intent).encode('utf-8')).hexdigest()
        self.assertEqual(self.backend.committed_operation(operation)[0], old_hash)
        self.assertEqual(self.backend.resolve_write(operation, draft), revision)

    def test_owner_registry_names_are_reserved_for_v3_creation(self):
        path = Path(self.directory.name) / 'reserved.sqlite'
        category = replace(self.category, name='section_storage_map')
        config = replace(self.config, catalogs=(category, self.product))
        backend = SQLiteCatalogBackend.create(path, config)
        try:
            self.assertNotEqual(backend._layout.table_name(category.identity), 'catalog_section_storage_map')
        finally:
            backend.close()

    def test_section_order_is_canonical_but_row_order_is_not(self):
        row = self.row()
        note = TabularRow(uuid4(), ('note',))
        draft = self.draft(self.expected(row, notes=(note,)))
        operation = uuid4()
        revision = self.create(draft, operation)
        self.assertEqual(self.backend.resolve_write(operation,
            replace(draft, tabular_sections=tuple(reversed(draft.tabular_sections)))), revision)



    def test_rollback_to_failure_closes_and_rolls_back_entire_transaction(self):
        draft = self.draft((self.section(self.row()),))
        revision = self.create(draft)
        before = self.read(draft.key)
        operation = uuid4()
        staged = self.draft(code='20')
        tx = self.backend.begin_write(operation)
        tx.create(staged)
        table = self.table()
        inserts = []
        statements = []
        def fail(connection, sql, args):
            statements.append(sql)
            if sql.startswith('ROLLBACK TO '):
                raise sqlite3.OperationalError('savepoint rollback refused')
            if sql.startswith('INSERT INTO ') and table in sql:
                inserts.append(sql)
                if len(inserts) == 2:
                    raise sqlite3.OperationalError('section insertion refused')
            return connection.execute(sql, args)
        tx._connection = ConnectionFault(tx._connection, fail)
        with self.assertRaisesRegex(BackendError, 'storage_error'):
            tx.update(replace(draft, description='Uncommitted',
                tabular_sections=(self.section(self.row(), self.row()),)), revision)
        self.assertEqual(len(inserts), 2)
        self.assertIn('ROLLBACK', statements)
        self.assertTrue(tx._closed)
        self.assertIsNone(self.backend._active)
        with self.assertRaisesRegex(BackendError, 'closed'):
            tx.commit()
        self.assertEqual(self.read(draft.key), before)
        self.assertIsNone(self.read(staged.key))
        self.assertIsNone(self.backend.committed_operation(operation))

    def test_repeated_release_failure_closes_and_rolls_back_transaction(self):
        draft = self.draft((self.section(self.row()),))
        revision = self.create(draft)
        before = self.read(draft.key)
        operation = uuid4()
        staged = self.draft(code='20')
        tx = self.backend.begin_write(operation)
        tx.create(staged)
        statements = []
        def fail(connection, sql, args):
            statements.append(sql)
            if sql.startswith('RELEASE '):
                raise sqlite3.OperationalError('release refused')
            return connection.execute(sql, args)
        tx._connection = ConnectionFault(tx._connection, fail)
        with self.assertRaisesRegex(BackendError, 'storage_error'):
            tx.update(replace(draft, description='Uncommitted', tabular_sections=()), revision)
        self.assertEqual(sum(sql.startswith('RELEASE ') for sql in statements), 2)
        self.assertIn('ROLLBACK TO catalog_record_write', statements)
        self.assertIn('ROLLBACK', statements)
        self.assertTrue(tx._closed)
        self.assertIsNone(self.backend._active)
        self.assertEqual(self.read(draft.key), before)
        self.assertIsNone(self.read(staged.key))
        self.assertIsNone(self.backend.committed_operation(operation))

    def test_one_release_failure_preserves_prior_writes_after_savepoint_rollback(self):
        draft = self.draft((self.section(self.row()),))
        revision = self.create(draft)
        before = self.read(draft.key)
        staged = self.draft((self.section(self.row()),), code='20')
        tx = self.backend.begin_write(uuid4())
        tx.create(staged)
        releases = []
        def fail_once(connection, sql, args):
            if sql.startswith('RELEASE '):
                releases.append(sql)
                if len(releases) == 1:
                    raise sqlite3.OperationalError('first release refused')
            return connection.execute(sql, args)
        tx._connection = ConnectionFault(tx._connection, fail_once)
        try:
            with self.assertRaisesRegex(BackendError, 'storage_error'):
                tx.update(replace(draft, description='Uncommitted', tabular_sections=()), revision)
            self.assertEqual(len(releases), 2)
            self.assertFalse(tx._closed)
            self.assertEqual(tx.read_catalog(draft.key), before)
            revisions = tx.commit()
            self.assertEqual(tuple(r.record_id for r in revisions), (staged.key.record_id,))
        finally:
            tx.close()
        self.assertEqual(self.read(draft.key), before)
        self.assertIsNotNone(self.read(staged.key))

    def test_lost_release_ack_closes_and_rolls_back_entire_transaction(self):
        draft = self.draft((self.section(self.row()),))
        revision = self.create(draft)
        before = self.read(draft.key)
        operation = uuid4()
        staged = self.draft(code='20')
        tx = self.backend.begin_write(operation)
        tx.create(staged)
        statements = []
        def fail_after_release(connection, sql, args):
            statements.append(sql)
            result = connection.execute(sql, args)
            if sql.startswith('RELEASE '):
                raise sqlite3.OperationalError('release acknowledgement lost')
            return result
        tx._connection = ConnectionFault(tx._connection, fail_after_release)
        with self.assertRaisesRegex(BackendError, 'storage_error'):
            tx.update(replace(draft, description='Uncommitted', tabular_sections=()), revision)
        self.assertIn('ROLLBACK TO catalog_record_write', statements)
        self.assertIn('ROLLBACK', statements)
        self.assertTrue(tx._closed)
        self.assertIsNone(self.backend._active)
        self.assertEqual(self.read(draft.key), before)
        self.assertIsNone(self.read(staged.key))
        self.assertIsNone(self.backend.committed_operation(operation))

    def test_transaction_row_budget_is_shared_between_owners(self):
        from unittest.mock import patch
        first = self.draft((self.section(self.row(), self.row()),), code='10')
        excess = self.draft((self.section(self.row(), self.row()),), code='20')
        last = self.draft((self.section(self.row()),), code='30')
        with patch('yadinassi.sqlite_catalog._MAX_ROWS', 3):
            tx = self.backend.begin_write(uuid4())
            try:
                tx.create(first)
                with self.assertRaisesRegex(BackendError, 'unsupported'):
                    tx.create(excess)
                self.assertIsNone(tx.read_catalog(excess.key))
                tx.create(last)
                revisions = tx.commit()
                self.assertEqual(tuple(r.record_id for r in revisions),
                                 (first.key.record_id, last.key.record_id))
            finally:
                tx.close()
        self.assertEqual(len(self.read(first.key).tabular_sections[0].rows), 2)
        self.assertEqual(len(self.read(last.key).tabular_sections[0].rows), 1)
        self.assertIsNone(self.read(excess.key))

    def test_transaction_byte_budget_is_shared_between_owners(self):
        from unittest.mock import patch
        first = self.draft((TabularSectionRows(self.notes.identity,
            (TabularRow(uuid4(), ('first' * 100,)),)),), code='10')
        excess = self.draft((TabularSectionRows(self.notes.identity,
            (TabularRow(uuid4(), ('other' * 100,)),)),), code='20')
        legacy = self.draft(code='30')
        view = self.backend.begin_read()
        try:
            first_size = len(_json(view._draft_sections(first)))
            second_size = len(_json(view._draft_sections(excess)))
        finally:
            view.close()
        with patch('yadinassi.sqlite_catalog._MAX_CONFIG_BYTES', first_size + second_size - 1):
            tx = self.backend.begin_write(uuid4())
            try:
                tx.create(first)
                with self.assertRaisesRegex(BackendError, 'unsupported'):
                    tx.create(excess)
                self.assertIsNone(tx.read_catalog(excess.key))
                tx.create(legacy)
                revisions = tx.commit()
                self.assertEqual(tuple(r.record_id for r in revisions),
                                 (first.key.record_id, legacy.key.record_id))
            finally:
                tx.close()
        self.assertIsNone(self.read(excess.key))
        self.assertIsNotNone(self.read(first.key))
        self.assertIsNotNone(self.read(legacy.key))

    def self_reference_schema(self):
        self.backend.close()
        section = TabularSectionSchema(uuid4(), 'Peers', (
            FieldSchema(uuid4(), 'Peer', 'catalog_ref', (), self.product.identity),))
        self.product = replace(self.product, tabular_sections=(section,))
        self.config = replace(self.config, catalogs=(self.category, self.product))
        self.path = Path(self.directory.name) / 'self-reference.sqlite'
        self.backend = SQLiteCatalogBackend.create(self.path, self.config)
        return section

    def test_staged_cyclic_section_references_commit_in_one_transaction(self):
        section = self.self_reference_schema()
        first, second = self.draft(code='10'), self.draft(code='20')
        first_row = TabularRow(uuid4(), (second.key,))
        second_row = TabularRow(uuid4(), (first.key,))
        tx = self.backend.begin_write(uuid4())
        try:
            tx.create(first)
            tx.create(second)
            first_revision = tx.read_catalog(first.key).revision
            second_revision = tx.read_catalog(second.key).revision
            tx.update(replace(first, tabular_sections=(TabularSectionRows(section.identity, (first_row,)),)), first_revision)
            tx.update(replace(second, tabular_sections=(TabularSectionRows(section.identity, (second_row,)),)), second_revision)
            self.assertEqual(len(tx.commit()), 4)
        finally:
            tx.close()
        self.reopen()
        self.assertEqual(self.read(first.key).tabular_sections,
                         (TabularSectionRows(section.identity, (first_row,)),))
        self.assertEqual(self.read(second.key).tabular_sections,
                         (TabularSectionRows(section.identity, (second_row,)),))
        self.assertEqual(self.read(first.key).revision.token, '2')
        self.assertEqual(self.sql('PRAGMA foreign_key_check'), [])

    def test_create_self_and_forward_section_references_refuse_without_mutation(self):
        section = self.self_reference_schema()
        for target_kind in ('self', 'forward'):
            with self.subTest(target_kind=target_kind):
                draft = self.draft()
                target = draft.key if target_kind == 'self' else replace(draft.key, record_id=uuid4())
                draft = replace(draft, tabular_sections=(TabularSectionRows(
                    section.identity, (TabularRow(uuid4(), (target,)),)),))
                tx = self.backend.begin_write(uuid4())
                try:
                    with self.assertRaisesRegex(BackendError, 'not_found'):
                        tx.create(draft)
                    self.assertIsNone(tx.read_catalog(draft.key))
                    self.assertEqual(tx._changes, [])
                finally:
                    tx.rollback()

    def test_interpreter_opts_into_v3_without_enabling_ui(self):
        from yadinassi import Interpreter
        from yadinassi.database_context import SQLiteDBContext
        before = self.path.read_bytes()
        output = []
        with SQLiteDBContext(self.path) as context:
            interpreter = Interpreter(output=output.append, database_context=context)
            interpreter.execute('O=Catalogs.Products.CreateItem(); Message(O.Lines.Count());')
            self.assertEqual(output, ['0'])
            with self.assertRaisesRegex(BackendError, 'unsupported'):
                context.require_active()
            self.assertIsNone(context.backend._active)
        self.assertEqual(self.path.read_bytes(), before)

    def test_ui_application_refuses_v3_before_creating_partial_editor(self):
        from yadinassi.database_context import SQLiteDBContext
        from yadinassi.ui.catalog_editor import CatalogEditorApplication
        before = self.path.read_bytes()
        with SQLiteDBContext(self.path) as context:
            with self.assertRaisesRegex(BackendError, 'unsupported'):
                CatalogEditorApplication(context)
            self.assertIsNone(context.backend._active)
        self.assertEqual(self.path.read_bytes(), before)


class LegacySectionCompatibilityTests(unittest.TestCase):
    def test_v2_without_sections_keeps_format_and_legacy_receipt_hash(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'legacy.sqlite'
            config = configuration()
            backend = SQLiteCatalogBackend.create(path, config)
            try:
                schema = config.catalogs[0]
                draft = CatalogDraft(CatalogKey(backend.database_id, schema.identity, uuid4()), '1', 'Legacy', False, ())
                operation = uuid4()
                tx = backend.begin_write(operation)
                tx.create(draft)
                revision = tx.commit()[0]
                expected = hashlib.sha256(_json([[str(schema.identity), str(draft.key.record_id),
                    draft.code, draft.description, False, _json([]), 1]]).encode('utf-8')).hexdigest()
                with closing(sqlite3.connect(path)) as connection:
                    self.assertEqual(connection.execute('PRAGMA user_version').fetchone()[0], 2)
                    self.assertEqual(connection.execute('SELECT request_hash FROM commit_receipt WHERE operation_id=?',
                                                       (str(operation),)).fetchone()[0], expected)
                self.assertEqual(backend.resolve_write(operation, draft), revision)
                self.assertFalse(backend.capabilities().catalog_tabular_sections)
                self.assertEqual(backend.inspect_section_storage_mapping(), ())
                tx = backend.begin_write(uuid4())
                try:
                    with self.assertRaisesRegex(BackendError, 'unsupported'):
                        tx.update(replace(draft, tabular_sections=(TabularSectionRows(uuid4(), ()),)), revision)
                finally:
                    tx.rollback()
            finally:
                backend.close()

    def test_v1_rejects_nonempty_section_intent_without_upgrade(self):
        from yadinassi.sqlite_catalog import _APPLICATION_ID
        from yadinassi.sqlite_catalog_migration import _V1_DDL
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'legacy-v1.sqlite'
            database_id, config_id = uuid4(), uuid4()
            schema = CatalogSchema(uuid4(), 'Legacy', 8, 64)
            with closing(sqlite3.connect(path)) as connection, connection:
                for ddl in _V1_DDL:
                    connection.execute(ddl)
                connection.execute('PRAGMA application_id=%d' % _APPLICATION_ID)
                connection.execute('PRAGMA user_version=1')
                connection.execute('INSERT INTO database_info VALUES(1,?,1,?,?,1,?)',
                                   (str(database_id), str(config_id), 'Fixture', '[]'))
                content = b'<fixture/>'
                connection.execute('INSERT INTO configuration_file VALUES(?,?,?,?)',
                    ('Configuration.xml', 'xml', content, hashlib.sha256(content).hexdigest()))
                connection.execute('INSERT INTO catalog_schema VALUES(?,?,?)',
                    (str(schema.identity), schema.name, _json(_schema_data(schema))))
            backend = SQLiteCatalogBackend(path)
            try:
                draft = CatalogDraft(CatalogKey(database_id, schema.identity, uuid4()), '1', 'Owner', False, (),
                                     (TabularSectionRows(uuid4(), ()),))
                tx = backend.begin_write(uuid4())
                try:
                    with self.assertRaisesRegex(BackendError, 'unsupported'):
                        tx.create(draft)
                finally:
                    tx.rollback()
                self.assertEqual(backend.storage_version, 1)
                self.assertEqual(backend.inspect_section_storage_mapping(), ())
            finally:
                backend.close()

    def test_non_ascii_legacy_schema_read_limit_remains_compatible(self):
        import json
        from yadinassi.sqlite_catalog import _APPLICATION_ID
        from yadinassi.sqlite_catalog_migration import _V1_DDL
        names = tuple(FieldSchema(uuid4(), 'f%d' % n + '😀'*120, 'string', (8,)) for n in range(64))
        legacy = CatalogSchema(uuid4(), 'Legacy', 8, 64, names)
        data = _schema_data(legacy, enforce_serialized_limit=False)
        raw = json.dumps(data, ensure_ascii=False, separators=(',', ':'))
        self.assertLess(len(raw), 65536)
        self.assertGreater(len(_json(data)), 65536)
        with tempfile.TemporaryDirectory() as directory:
            for version in (1, 2):
                path = Path(directory)/('legacy%d.sqlite' % version)
                if version == 1:
                    with closing(sqlite3.connect(path)) as db, db:
                        for ddl in _V1_DDL: db.execute(ddl)
                        db.execute('PRAGMA application_id=%d' % _APPLICATION_ID)
                        db.execute('PRAGMA user_version=1')
                        db.execute('INSERT INTO database_info VALUES(1,?,1,?,?,1,?)', (str(uuid4()),str(uuid4()),'Fixture','[]'))
                        db.execute('INSERT INTO catalog_schema VALUES(?,?,?)', (str(legacy.identity),legacy.name,raw))
                else:
                    short = replace(legacy, fields=tuple(replace(f,name='f%d' % n) for n,f in enumerate(names)))
                    config = replace(configuration(), catalogs=(short,))
                    db = SQLiteCatalogBackend.create(path, config); db.close()
                    with closing(sqlite3.connect(path)) as db, db:
                        db.execute('UPDATE catalog_schema SET definition=? WHERE identity=?', (raw,str(legacy.identity)))
                backend = SQLiteCatalogBackend(path)
                try:
                    view = backend.begin_read()
                    try: self.assertEqual(view.catalog_schema(legacy.identity), legacy)
                    finally: view.close()
                finally: backend.close()
