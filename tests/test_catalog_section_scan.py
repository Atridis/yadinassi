"""Bounded read-only section scan contract on owned SQLite, not native proof."""
from dataclasses import replace
from decimal import Decimal
from uuid import UUID, uuid4
import unittest
from unittest.mock import patch

import test_sqlite_catalog_sections as fixtures
from test_sqlite_catalog_sections import ConnectionFault
from yadinassi.catalog_backend import (
    BackendError, CatalogComparison, CatalogOrder, CatalogPredicate,
    CatalogScanRequest, CatalogSectionPage, CatalogSectionRecord, CatalogKey,
    CatalogDraft, TabularRow, TabularSectionRows,
)
from yadinassi.sqlite_catalog_layout import quote_identifier


class CatalogSectionScanTests(unittest.TestCase):
    setUp = fixtures.CatalogSectionTests.setUp
    values = fixtures.CatalogSectionTests.values
    section = fixtures.CatalogSectionTests.section
    row = fixtures.CatalogSectionTests.row
    draft = fixtures.CatalogSectionTests.draft
    create = fixtures.CatalogSectionTests.create
    sql = fixtures.CatalogSectionTests.sql
    table = fixtures.CatalogSectionTests.table

    def scan(self, view, request=None, section=None):
        return view.scan_catalog_section(self.product.identity,
            (section or self.lines).identity, request or CatalogScanRequest())

    def seed(self, count=3, code='10'):
        rows = tuple(self.row('row'+str(i), str(i)) for i in range(count))
        owner = self.draft((self.section(*rows),), code=code)
        self.create(owner)
        return owner, rows

    def field(self, index, section=None):
        section = section or self.lines
        return quote_identifier(self.backend._section_layout.field_name(
            self.product.identity, section.identity, section.fields[index].identity))

    def view(self):
        view = self.backend.begin_read()
        self.addCleanup(view.close)
        return view

    def test_exact_record_shape_owner_ref_order_and_layout_v3(self):
        owner, rows = self.seed()
        view = self.view()
        request = CatalogScanRequest(CatalogComparison('ref', 'eq', owner.key),
                                     (CatalogOrder(self.lines.fields[1].identity, True),))
        page = self.scan(view, request)
        self.assertIs(type(page), CatalogSectionPage)
        self.assertEqual(page.rows, tuple(CatalogSectionRecord(owner.key, self.lines.identity, r)
                                         for r in reversed(rows)))
        self.assertIsNone(page.continuation)
        self.assertEqual(self.backend.storage_version, 3)
        self.assertEqual(self.sql('PRAGMA user_version'), [(3,)])

    def test_same_row_uuid_is_valid_across_owners(self):
        row = self.row()
        owners = [self.draft((self.section(row),), code=str(i)) for i in (1, 2)]
        for owner in owners: self.create(owner)
        page = self.scan(self.view())
        self.assertEqual({record.owner for record in page.rows}, {owner.key for owner in owners})
        self.assertEqual([record.row.identity for record in page.rows], [row.identity]*2)

    def test_pagination_crosses_1000_rows_without_per_owner_overflow(self):
        self.seed(600, '10'); self.seed(600, '20')
        view = self.view(); request = CatalogScanRequest(page_size=1000)
        first = self.scan(view, request)
        self.assertEqual(len(first.rows), 1000); self.assertIsNotNone(first.continuation)
        second = self.scan(view, replace(request, continuation=first.continuation))
        self.assertEqual(len(second.rows), 200); self.assertIsNone(second.continuation)
        identities = [(r.owner, r.row.identity) for r in first.rows + second.rows]
        self.assertEqual(len(set(identities)), 1200)
        with self.assertRaises(BackendError):
            self.scan(view, replace(request, continuation=first.continuation))

    def test_token_binds_section_predicate_order_page_size_and_string_policy(self):
        owner, unused_rows = self.seed()
        view = self.view(); request = CatalogScanRequest(page_size=1)
        mutations = (
            {'page_size': 2}, {'predicate': CatalogComparison('ref', 'eq', owner.key)},
            {'order': (CatalogOrder(self.lines.fields[1].identity),)},
            {'string_comparison': 'casefold_v1'},
        )
        for change in mutations:
            token = self.scan(view, request).continuation
            with self.subTest(change=change), self.assertRaises(BackendError):
                self.scan(view, replace(request, continuation=token, **change))
        token = self.scan(view, request).continuation
        with self.assertRaises(BackendError):
            self.scan(view, replace(request, continuation=token), section=self.notes)
        view.close()
        newer = self.view()
        with self.assertRaises(BackendError):
            self.scan(newer, replace(request, continuation=token))

    def test_catalog_and_section_share_one_cursor_and_cannot_exchange_tokens(self):
        self.seed(2, '10'); self.seed(2, '20')
        view = self.view(); request = CatalogScanRequest(page_size=1)
        token = self.scan(view, request).continuation
        with self.assertRaises(BackendError):
            view.scan_catalog(self.product.identity, replace(request, continuation=token))
        token = view.scan_catalog(self.product.identity, request).continuation
        with self.assertRaises(BackendError):
            self.scan(view, replace(request, continuation=token))
        token = self.scan(view, request).continuation
        view.scan_catalog(self.product.identity, request)
        with self.assertRaises(BackendError): self.scan(view, replace(request, continuation=token))
        token = view.scan_catalog(self.product.identity, request).continuation
        self.scan(view, request)
        with self.assertRaises(BackendError):
            view.scan_catalog(self.product.identity, replace(request, continuation=token))

    def test_exact_decimal_and_casefold_policy(self):
        rows = (self.row('alpha', '0.10'), self.row('Alpha', '0.20'), self.row('other', '0.30'))
        self.create(self.draft((self.section(*rows),)))
        view = self.view(); text, amount = (f.identity for f in self.lines.fields[:2])
        request = CatalogScanRequest(CatalogComparison(text, 'eq', 'alpha'), (CatalogOrder(amount),))
        self.assertEqual(tuple(r.row for r in self.scan(view, request).rows), rows[:1])
        self.assertEqual(tuple(r.row for r in self.scan(view, replace(request, string_comparison='casefold_v1')).rows), rows[:2])
        request = CatalogScanRequest(CatalogComparison(amount, 'ge', Decimal('0.20')),
                                     (CatalogOrder(amount, True),))
        self.assertEqual([r.row.values[1] for r in self.scan(view, request).rows], [Decimal('0.30'), Decimal('0.20')])
        for bad in (True, 1, 0.1, Decimal('NaN')):
            with self.subTest(bad=bad), self.assertRaises(BackendError):
                self.scan(view, CatalogScanRequest(CatalogComparison(amount, 'eq', bad)))

    def test_empty_section_validates_owner_scope_field_ids_and_order(self):
        view = self.view()
        for request in (
            CatalogScanRequest(CatalogComparison('code', 'eq', '10')),
            CatalogScanRequest(CatalogComparison('description', 'eq', 'Owner')),
            CatalogScanRequest(CatalogComparison('row_id', 'eq', uuid4())),
            CatalogScanRequest(CatalogComparison('row_number', 'eq', Decimal(1))),
            CatalogScanRequest(CatalogComparison(self.notes.fields[0].identity, 'eq', 'x')),
            CatalogScanRequest(CatalogComparison('ref', 'eq', CatalogKey(uuid4(), self.product.identity, uuid4()))),
            CatalogScanRequest(CatalogComparison('ref', 'eq', CatalogKey(self.backend.database_id, self.category.identity, uuid4()))),
            CatalogScanRequest(page_size=True),
            CatalogScanRequest(CatalogPredicate('and', ())),
        ):
            with self.subTest(request=request), self.assertRaises(BackendError): self.scan(view, request)
        with self.assertRaises(BackendError):
            view.scan_catalog_section(self.product.identity, uuid4(), CatalogScanRequest())

    def test_write_view_and_closed_read_view_refuse_scan(self):
        tx = self.backend.begin_write(uuid4())
        try:
            with self.assertRaises(BackendError): self.scan(tx)
        finally: tx.rollback()
        view = self.view(); view.close()
        with self.assertRaises(BackendError): self.scan(view)

    def test_preflight_does_not_read_unrelated_section_or_flatten_catalog(self):
        self.seed()
        # Corruption in Notes must not make a valid Lines-only scan fail.
        note = self.draft((TabularSectionRows(self.notes.identity,
                           (TabularRow(uuid4(), ('note',)),)),), code='20')
        self.create(note)
        self.sql('UPDATE '+self.table(self.notes)+' SET row_id=?', ('bad',))
        view = self.view(); original = view._connection
        def guard(connection, sql, parameters):
            if self.table(self.notes) in sql:
                raise AssertionError('unrelated section read')
            return connection.execute(sql, parameters)
        view._connection = ConnectionFault(original, guard)
        with patch.object(type(view), 'scan_catalog', side_effect=AssertionError('catalog flattening')):
            self.assertEqual(len(self.scan(view).rows), 3)

    def test_filtered_out_corrupt_rows_are_never_hidden_by_owner_filter(self):
        good, unused = self.seed(1, '10')
        bad, unused = self.seed(2, '20')
        # Repair each mutation before trying another, without reopening schema.
        assignments = (
            ('row_id', 'not-a-uuid'), ('row_id', str(uuid4()).upper()),
            ('row_id', str(UUID(int=0))), ('row_number', 9),
            (self.field(1), 'NaN'), (self.field(1), '1.001'),
            (self.field(3), 'not-a-date'), (self.field(4), str(uuid4())),
        )
        for column, value in assignments:
            previous = self.sql('SELECT '+column+' FROM '+self.table()+' WHERE owner_id=? AND row_number=2',
                                (str(bad.key.record_id),))[0][0]
            self.sql('UPDATE '+self.table()+' SET '+column+'=? WHERE owner_id=? AND row_number=2',
                     (value, str(bad.key.record_id)))
            view = self.backend.begin_read()
            try:
                with self.subTest(column=column, value=value), self.assertRaises(BackendError):
                    self.scan(view, CatalogScanRequest(CatalogComparison('ref', 'eq', good.key), page_size=1))
            finally: view.close()
            where_number = 9 if column == 'row_number' else 2
            self.sql('UPDATE '+self.table()+' SET '+column+'=? WHERE owner_id=? AND row_number=?',
                     (previous, str(bad.key.record_id), where_number))

    def test_orphan_owner_is_refused_even_when_filter_matches_nothing(self):
        self.seed(1)
        self.sql('UPDATE '+self.table()+' SET owner_id=?', (str(uuid4()),))
        view = self.view()
        with self.assertRaises(BackendError):
            self.scan(view, CatalogScanRequest(CatalogComparison(self.lines.fields[0].identity, 'eq', 'absent'), page_size=1))

    def assert_preflight_refusal(self, limit, value, section=None):
        view = self.backend.begin_read(); section = section or self.lines
        table = self.table(section)
        # Aggregate/shape checks may touch fields, but payload rows must not be fetched.
        def guard(connection, sql, parameters):
            normalized = sql.upper().replace(' ', '')
            if table in sql and normalized.startswith(('SELECTOWNER_ID,ROW_ID', 'SELECTROW_ID,ROW_NUMBER')):
                raise AssertionError('section payload read before budget refusal')
            return connection.execute(sql, parameters)
        view._connection = ConnectionFault(view._connection, guard)
        try:
            with patch('yadinassi.sqlite_catalog.'+limit, value):
                with self.assertRaises(BackendError):
                    self.scan(view, CatalogScanRequest(page_size=1), section)
        finally: view.close()

    def test_source_row_and_byte_budgets_refuse_before_payload(self):
        self.seed(2, '10'); self.seed(2, '20')
        self.assert_preflight_refusal('_MAX_ROWS', 3)
        self.assert_preflight_refusal('_MAX_CONFIG_BYTES', 1)

    def test_per_owner_row_and_byte_budgets_refuse_before_payload(self):
        self.seed(3)
        self.assert_preflight_refusal('_MAX_SECTION_ROWS', 2)
        self.assert_preflight_refusal('_MAX_ROW_BYTES', 1)

    def test_persisted_actual_owner_payload_above_one_mib_is_refused(self):
        notes = tuple(TabularRow(uuid4(), ('small',)) for unused in range(17))
        self.create(self.draft((TabularSectionRows(self.notes.identity, notes),)))
        self.sql('UPDATE '+self.table(self.notes)+' SET '+self.field(0, self.notes)+'=?', ('x'*65536,))
        with self.assertRaises(BackendError): self.scan(self.view(), section=self.notes)

    def test_owner_and_reference_order_are_deterministic(self):
        owners = [self.seed(2, code)[0] for code in ('10', '20')]
        view = self.view()
        page = self.scan(view, CatalogScanRequest(order=(CatalogOrder('ref'),)))
        self.assertEqual([r.owner.record_id.int for r in page.rows],
                         sorted(owner.key.record_id.int for owner in owners for unused in range(2)))
        first = tuple((r.owner, r.row.identity) for r in self.scan(view).rows)
        second = tuple((r.owner, r.row.identity) for r in self.scan(view).rows)
        self.assertEqual(first, second)

    def test_hostile_request_never_invokes_arbitrary_equality_or_hash(self):
        class Hostile:
            def __eq__(self, other): raise AssertionError('hostile equality')
            def __hash__(self): raise AssertionError('hostile hash')
        view = self.view()
        for request in (
            CatalogScanRequest(CatalogComparison(Hostile(), 'eq', 'x')),
            CatalogScanRequest(CatalogComparison('ref', 'eq', CatalogKey(Hostile(), self.product.identity, uuid4()))),
            CatalogScanRequest(order=(CatalogOrder(Hostile()),)),
            CatalogScanRequest(string_comparison=Hostile()),
            CatalogScanRequest(continuation=Hostile()),
        ):
            with self.assertRaises(BackendError): self.scan(view, request)

    def test_custom_reference_comparisons_require_database_and_target_catalog(self):
        self.seed(1)
        view = self.view(); reference = self.lines.fields[4].identity
        for key in (
            CatalogKey(uuid4(), self.category.identity, UUID(int=0)),
            CatalogKey(self.backend.database_id, self.product.identity, UUID(int=0)),
        ):
            with self.assertRaises(BackendError):
                self.scan(view, CatalogScanRequest(CatalogComparison(reference, 'eq', key)))
        empty = CatalogKey(self.backend.database_id, self.category.identity, UUID(int=0))
        self.assertEqual(len(self.scan(view, CatalogScanRequest(CatalogComparison(reference, 'eq', empty))).rows), 1)

    def test_readonly_v3_scans_persisted_section_but_refuses_writes(self):
        owner, rows = self.seed(1)
        readonly = fixtures.SQLiteCatalogBackend(self.path, read_only=True)
        try:
            view = readonly.begin_read()
            try:
                page = self.scan(view)
                self.assertEqual(page.rows, (CatalogSectionRecord(owner.key, self.lines.identity, rows[0]),))
            finally: view.close()
            with self.assertRaises(BackendError): readonly.begin_write(uuid4())
        finally: readonly.close()

    def test_legacy_v2_section_scan_is_explicitly_unsupported(self):
        legacy = fixtures.SQLiteCatalogBackend.create(self.path.parent/'legacy.sqlite', fixtures.configuration())
        try:
            self.assertEqual(legacy.storage_version, 2)
            view = legacy.begin_read()
            try:
                catalog_id = legacy._schemas[-1].identity
                with self.assertRaisesRegex(BackendError, 'unsupported'):
                    view.scan_catalog_section(catalog_id, uuid4(), CatalogScanRequest())
            finally: view.close()
        finally: legacy.close()

    def test_multipage_snapshot_survives_pending_writer_on_second_backend(self):
        owner, old_rows = self.seed(3)
        other = fixtures.SQLiteCatalogBackend(self.path)
        reader = self.backend.begin_read()
        writer = None
        try:
            request = CatalogScanRequest(order=(CatalogOrder(self.lines.fields[1].identity),),
                                         page_size=1)
            first = self.scan(reader, request)
            self.assertEqual(first.rows[0].row, old_rows[0])
            self.assertIsNotNone(first.continuation)
            writer = other.begin_write(uuid4())
            previous = writer.read_catalog(owner.key)
            changed = tuple(replace(row, values=(row.values[0], Decimal(100 + i)) + row.values[2:])
                            for i, row in enumerate(old_rows))
            writer.update(replace(owner, tabular_sections=(self.section(*changed),)),
                          previous.revision)
            # DELETE journal permits a pending writer while readers are active,
            # but not its commit. Do not pretend concurrent commit can succeed.
            second = self.scan(reader, replace(request, continuation=first.continuation))
            third = self.scan(reader, replace(request, continuation=second.continuation))
            self.assertEqual(tuple(record.row for page in (first, second, third)
                                   for record in page.rows), old_rows)
            self.assertIsNone(third.continuation)
            # This starts a fresh SQL traversal inside the original pinned view,
            # not merely a read from the previous traversal's detached pages.
            again = self.scan(reader, replace(request, page_size=1000))
            self.assertEqual(tuple(record.row for record in again.rows), old_rows)
            reader.close()
            writer.commit()
            fresh = self.backend.begin_read()
            try:
                page = self.scan(fresh, replace(request, page_size=1000))
                self.assertEqual(tuple(record.row for record in page.rows), changed)
            finally:
                fresh.close()
        finally:
            reader.close()
            if writer is not None: writer.close()
            other.close()

    def test_same_section_uuid_in_distinct_catalogs_never_rebinds_rows_or_tokens(self):
        # The authored backend schema scopes section identity by catalog. The XML
        # importer has a stricter global metadata UUID rule; it is not relaxed.
        second_catalog = replace(self.product, identity=uuid4(), name='OtherProducts')
        config = replace(self.config, catalogs=(self.category, self.product, second_catalog))
        backend = fixtures.SQLiteCatalogBackend.create(self.path.parent/'scoped.sqlite', config)
        try:
            owner_id = uuid4()
            row_ids = (uuid4(), uuid4())
            defaults = self.values()[:-1] + (
                CatalogKey(backend.database_id, self.category.identity, UUID(int=0)),)
            owners = []
            expected = []
            tx = backend.begin_write(uuid4())
            try:
                for index, catalog in enumerate((self.product, second_catalog)):
                    rows = tuple(TabularRow(identity,
                        ('catalog'+str(index), Decimal(index * 10 + offset)) + defaults[2:])
                        for offset, identity in enumerate(row_ids))
                    draft = CatalogDraft(CatalogKey(backend.database_id, catalog.identity, owner_id),
                        '10', 'Scoped owner', False, defaults, (self.section(*rows),))
                    tx.create(draft)
                    owners.append(draft.key); expected.append(rows)
                tx.commit()
            finally:
                tx.close()
            self.assertNotEqual(
                backend._section_layout.table_name(self.product.identity, self.lines.identity),
                backend._section_layout.table_name(second_catalog.identity, self.lines.identity))
            view = backend.begin_read()
            try:
                request = CatalogScanRequest(order=(CatalogOrder(self.lines.fields[1].identity),),
                                             page_size=1)
                first = view.scan_catalog_section(self.product.identity, self.lines.identity, request)
                self.assertEqual(first.rows, (CatalogSectionRecord(owners[0], self.lines.identity,
                                                                    expected[0][0]),))
                with self.assertRaisesRegex(BackendError, 'invalid_input'):
                    view.scan_catalog_section(second_catalog.identity, self.lines.identity,
                                              replace(request, continuation=first.continuation))
                other = view.scan_catalog_section(second_catalog.identity, self.lines.identity, request)
                self.assertEqual(other.rows, (CatalogSectionRecord(owners[1], self.lines.identity,
                                                                    expected[1][0]),))
                with self.assertRaisesRegex(BackendError, 'invalid_input'):
                    view.scan_catalog_section(self.product.identity, self.lines.identity,
                                              replace(request, continuation=first.continuation))
                last = view.scan_catalog_section(second_catalog.identity, self.lines.identity,
                                                 replace(request, continuation=other.continuation))
                self.assertEqual(last.rows, (CatalogSectionRecord(owners[1], self.lines.identity,
                                                                   expected[1][1]),))
                self.assertIsNone(last.continuation)
            finally:
                view.close()
        finally:
            backend.close()

    def test_all_scan_modes_reject_foreign_tokens_and_invalidate_previous_traversal(self):
        self.seed(2, '10'); self.seed(2, '20')
        view = self.view(); request = CatalogScanRequest(page_size=1)
        modes = {
            'section': lambda req: self.scan(view, req),
            'cards': lambda req: view.scan_catalog(self.product.identity, req),
            'values': lambda req: view.scan_catalog_values(self.product.identity, req, ('code',)),
        }
        for first_name, first in modes.items():
            for next_name, next_scan in modes.items():
                if first_name == next_name: continue
                with self.subTest(first=first_name, next=next_name):
                    token = first(request).continuation
                    self.assertIsNotNone(token)
                    with self.assertRaisesRegex(BackendError, 'invalid_input'):
                        next_scan(replace(request, continuation=token))
                    next_scan(request)
                    with self.assertRaisesRegex(BackendError, 'invalid_input'):
                        first(replace(request, continuation=token))
