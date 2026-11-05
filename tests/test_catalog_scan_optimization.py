"""Independent regression coverage for bounded full-card and scalar scans."""
from contextlib import closing
from dataclasses import replace
from decimal import Decimal
import unittest
from unittest.mock import patch
from uuid import UUID, uuid4

import test_sqlite_catalog_sections as section_fixtures
import test_sqlite_catalog_migration as migration_fixtures
from yadinassi.catalog_backend import (
    BackendError, CatalogCard, CatalogComparison, CatalogDraft, CatalogKey,
    CatalogOrder, CatalogPredicate, CatalogScanRequest, CatalogValueRow,
)
from yadinassi.sqlite_catalog import SQLiteCatalogBackend
from yadinassi.sqlite_catalog_layout import quote_identifier


class ScanOptimizationTests(unittest.TestCase):
    setUp = section_fixtures.CatalogSectionTests.setUp
    values = section_fixtures.CatalogSectionTests.values
    section = section_fixtures.CatalogSectionTests.section
    row = section_fixtures.CatalogSectionTests.row
    draft = section_fixtures.CatalogSectionTests.draft
    create = section_fixtures.CatalogSectionTests.create
    sql = section_fixtures.CatalogSectionTests.sql
    table = section_fixtures.CatalogSectionTests.table
    expected = section_fixtures.CatalogSectionTests.expected

    def seed(self, count=3):
        drafts = tuple(self.draft(code=str(i).zfill(4)) for i in range(count))
        with closing(self.backend.begin_write(uuid4())) as tx:
            for draft in drafts:
                tx.create(draft)
            tx.commit()
        return drafts

    def view(self):
        view = self.backend.begin_read()
        self.addCleanup(view.close)
        return view

    def owner_table(self):
        return quote_identifier(self.backend._layout.table_name(self.product.identity))

    def test_thousand_owners_hit_and_miss_do_not_materialize_unselected_cards(self):
        self.seed(1000)
        view = self.view()
        sql = []
        view._connection.set_trace_callback(sql.append)
        for code, expected in (('0999', 1), ('missing', 0)):
            with self.subTest(code=code), patch.object(view, '_card', wraps=view._card) as card:
                sql.clear()
                page = view.scan_catalog(self.product.identity, CatalogScanRequest(
                    CatalogComparison('code', 'eq', code), page_size=1))
                self.assertEqual(len(page.cards), expected)
                self.assertEqual(card.call_count, expected)
                self.assertLess(len(sql), 100, sql)
                self.assertIsNone(page.continuation)
                if expected:
                    self.assertIs(type(page.cards[0]), CatalogCard)
                    self.assertEqual(page.cards[0].tabular_sections, self.expected())

    def test_projection_has_values_not_partial_cards_and_never_reads_sections(self):
        drafts = self.seed()
        view = self.view()
        sql = []
        view._connection.set_trace_callback(sql.append)
        fields = ('description', self.product.fields[1].identity, 'code', 'ref')
        with patch.object(view, '_card', side_effect=AssertionError('partial card')):
            page = view.scan_catalog_values(self.product.identity, CatalogScanRequest(
                CatalogComparison('code', 'eq', '0001')), fields)
        self.assertEqual(len(page.rows), 1)
        row = page.rows[0]
        self.assertIs(type(row), CatalogValueRow)
        self.assertEqual(row.key, drafts[1].key)
        self.assertEqual(row.values, ('Owner', Decimal('12.30'), '0001', drafts[1].key))
        self.assertFalse(hasattr(row, 'tabular_sections'))
        for section in self.product.tabular_sections:
            table = self.backend._section_layout.table_name(self.product.identity, section.identity)
            self.assertFalse(any(table in query for query in sql), sql)

    def test_projection_continuations_are_consumed_and_bound_to_field_order_and_mode(self):
        self.seed()
        view = self.view()
        request = CatalogScanRequest(order=(CatalogOrder('code'),), page_size=1)
        fields = ('code', 'description')
        first = view.scan_catalog_values(self.product.identity, request, fields)
        next_request = replace(request, continuation=first.continuation)
        with self.assertRaises(BackendError):
            view.scan_catalog_values(self.product.identity, next_request, fields[::-1])
        with self.assertRaises(BackendError):
            view.scan_catalog(self.product.identity, next_request)
        second = view.scan_catalog_values(self.product.identity, next_request, fields)
        self.assertEqual(second.rows[0].values[0], '0001')
        with self.assertRaises(BackendError):
            view.scan_catalog_values(self.product.identity, next_request, fields)
        full = view.scan_catalog(self.product.identity, request)
        with self.assertRaises(BackendError):
            view.scan_catalog_values(self.product.identity,
                replace(request, continuation=full.continuation), fields)

    def test_projection_continuation_cannot_cross_views_or_change_request(self):
        self.seed()
        view = self.view()
        request = CatalogScanRequest(page_size=1)
        fields = ('code',)
        token = view.scan_catalog_values(self.product.identity, request, fields).continuation
        with self.assertRaises(BackendError):
            view.scan_catalog_values(self.product.identity,
                replace(request, page_size=2, continuation=token), fields)
        view.close()
        other = self.view()
        with self.assertRaises(BackendError):
            other.scan_catalog_values(self.product.identity,
                replace(request, continuation=token), fields)

    def test_large_unrelated_sections_do_not_consume_filtered_result_budget(self):
        drafts = []
        for i in range(11):
            draft = self.draft(self.expected(*(self.row() for _ in range(1000))), code=str(i))
            self.create(draft)
            drafts.append(draft)
        view = self.view()
        missing = view.scan_catalog(self.product.identity, CatalogScanRequest(
            CatalogComparison('code', 'eq', 'absent'), page_size=1))
        self.assertEqual(missing.cards, ())
        selected = view.scan_catalog(self.product.identity, CatalogScanRequest(
            CatalogComparison('code', 'eq', '10'), page_size=1))
        self.assertEqual(selected.cards[0].tabular_sections, drafts[-1].tabular_sections)
        with self.assertRaisesRegex(BackendError, 'unsupported'):
            view.scan_catalog(self.product.identity, CatalogScanRequest(page_size=1))
        scalar = view.scan_catalog_values(self.product.identity,
            CatalogScanRequest(page_size=1), ('code',))
        self.assertEqual(len(scalar.rows), 1)

    def test_full_page_materializes_only_returned_cards_with_all_sections(self):
        drafts = []
        for i in range(3):
            draft = self.draft(self.expected(self.row(str(i))), code=str(i))
            self.create(draft)
            drafts.append(draft)
        view = self.view()
        with patch.object(view, '_card', wraps=view._card) as card:
            page = view.scan_catalog(self.product.identity, CatalogScanRequest(
                order=(CatalogOrder('code'),), page_size=1))
        self.assertEqual(card.call_count, 1)
        self.assertEqual(page.cards[0].tabular_sections, drafts[0].tabular_sections)
        self.assertIsNotNone(page.continuation)

    def test_decimal_exact_order_and_signed_zero_comparison(self):
        amounts = ('9999999999.98', '9999999999.99', '-0.00', '0.00', '-0.01')
        for i, amount in enumerate(amounts):
            self.create(replace(self.draft(code=str(i)), values=self.values(amount=amount)))
        view = self.view()
        field = self.product.fields[1].identity
        page = view.scan_catalog_values(self.product.identity, CatalogScanRequest(
            order=(CatalogOrder(field), CatalogOrder('code'))), ('code', field))
        self.assertEqual([row.values[0] for row in page.rows], ['4', '2', '3', '0', '1'])
        for operator, expected in (('eq', ['2', '3']), ('ne', ['0', '1', '4'])):
            page = view.scan_catalog_values(self.product.identity, CatalogScanRequest(
                CatalogComparison(field, operator, Decimal('-0.00')),
                (CatalogOrder('code'),)), ('code',))
            self.assertEqual([row.values[0] for row in page.rows], expected)
        page = view.scan_catalog_values(self.product.identity, CatalogScanRequest(
            CatalogComparison(field, 'gt', Decimal(amounts[0]))), ('code',))
        self.assertEqual([row.values[0] for row in page.rows], ['1'])

    def test_casefold_expansions_use_python_semantics_for_filter_and_order(self):
        for i, text in enumerate(('Straße', 'STRASSE', 'Σ', 'ς', 'İ', 'i\u0307')):
            self.create(replace(self.draft(code=str(i)), description=text))
        view = self.view()
        for term, expected in (('strasse', ['0', '1']), ('σ', ['2', '3']), ('i\u0307', ['4', '5'])):
            page = view.scan_catalog_values(self.product.identity, CatalogScanRequest(
                CatalogComparison('description', 'eq', term), (CatalogOrder('code'),),
                string_comparison='casefold_v1'), ('code',))
            self.assertEqual([row.values[0] for row in page.rows], expected)
        page = view.scan_catalog_values(self.product.identity, CatalogScanRequest(
            order=(CatalogOrder('description'), CatalogOrder('code')),
            string_comparison='casefold_v1'), ('code',))
        self.assertEqual([row.values[0] for row in page.rows], ['4', '5', '0', '1', '2', '3'])

    def test_empty_reference_eq_ne_and_mixed_boolean_predicates(self):
        key = CatalogKey(self.backend.database_id, self.category.identity, uuid4())
        with closing(self.backend.begin_write(uuid4())) as tx:
            tx.create(CatalogDraft(key, 'cat', 'Category', False, ()))
            tx.commit()
        self.create(self.draft(code='empty'))
        self.create(replace(self.draft(code='linked'), values=self.values()[:-1] + (key,)))
        field = self.product.fields[-1].identity
        empty = CatalogKey(self.backend.database_id, self.category.identity, UUID(int=0))
        view = self.view()
        for op, expected in (('eq', ['empty']), ('ne', ['linked'])):
            page = view.scan_catalog_values(self.product.identity, CatalogScanRequest(
                CatalogComparison(field, op, empty)), ('code',))
            self.assertEqual([row.values[0] for row in page.rows], expected)
        pred = CatalogPredicate('or', (CatalogComparison(field, 'ne', empty),
            CatalogComparison(self.product.fields[1].identity, 'eq', Decimal('12.30'))))
        page = view.scan_catalog_values(self.product.identity, CatalogScanRequest(
            pred, (CatalogOrder('code'),)), ('code',))
        self.assertEqual([row.values[0] for row in page.rows], ['empty', 'linked'])

    def test_parseable_noncanonical_record_uuid_keeps_numeric_order_and_equality(self):
        drafts = []
        for i, identity in enumerate((UUID(int=10), UUID(int=2))):
            draft = replace(self.draft(code=str(i)), key=CatalogKey(
                self.backend.database_id, self.product.identity, identity))
            self.create(draft)
            drafts.append(draft)
        self.sql('UPDATE ' + self.owner_table() + ' SET record_id=? WHERE record_id=?',
                 (drafts[0].key.record_id.hex.upper(), str(drafts[0].key.record_id)))
        view = self.view()
        page = view.scan_catalog_values(self.product.identity, CatalogScanRequest(), ('ref',))
        self.assertEqual([row.key.record_id.int for row in page.rows], [2, 10])
        page = view.scan_catalog_values(self.product.identity, CatalogScanRequest(
            CatalogComparison('ref', 'eq', drafts[0].key)), ('code',))
        self.assertEqual([row.values[0] for row in page.rows], ['0'])

    def test_filtered_out_corrupt_scalar_is_refused_in_both_modes(self):
        self.seed(2)
        column = quote_identifier(self.backend._layout.field_name(
            self.product.identity, self.product.fields[1].identity))
        self.sql('UPDATE ' + self.owner_table() + ' SET ' + column + "='NaN' WHERE code='0001'")
        view = self.view()
        request = CatalogScanRequest(CatalogComparison('code', 'eq', '0000'))
        with self.assertRaises(BackendError):
            view.scan_catalog(self.product.identity, request)
        with self.assertRaises(BackendError):
            view.scan_catalog_values(self.product.identity, request, ('code',))

    def test_unrelated_corrupt_section_refused_by_full_scan_but_scalar_is_allowed(self):
        self.create(self.draft(code='good'))
        self.create(self.draft(self.expected(self.row()), code='bad'))
        self.sql('UPDATE ' + self.table() + " SET row_id='bad-uuid'")
        view = self.view()
        request = CatalogScanRequest(CatalogComparison('code', 'eq', 'good'))
        with self.assertRaises(BackendError):
            view.scan_catalog(self.product.identity, request)
        page = view.scan_catalog_values(self.product.identity, request, ('code',))
        self.assertEqual(page.rows[0].values, ('good',))

    def test_legacy_custom_field_fallback_keeps_typed_projection(self):
        fixture = migration_fixtures.MigrationTests()
        fixture.setUp()
        try:
            with closing(SQLiteCatalogBackend(fixture.path)) as backend, closing(backend.begin_read()) as view:
                field = fixture.sa.fields[1].identity
                request = CatalogScanRequest(CatalogComparison(field, 'eq', Decimal('123.4')),
                                             (CatalogOrder(field),))
                with patch.object(view, '_card', side_effect=AssertionError('partial card')):
                    page = view.scan_catalog_values(fixture.a, request, (field, 'code'))
                self.assertEqual(page.rows[0].values, (Decimal('123.40'), '1'))
        finally:
            fixture.tearDown()

    def test_continuation_uses_pinned_snapshot_during_external_writer_attempt(self):
        import sqlite3
        self.seed()
        view = self.view()
        request = CatalogScanRequest(order=(CatalogOrder('code'),), page_size=1)
        first = view.scan_catalog_values(self.product.identity, request, ('code',))
        self.assertEqual(first.rows[0].values, ('0000',))
        with closing(sqlite3.connect(self.path, timeout=0.05)) as writer:
            try:
                writer.execute('UPDATE ' + self.owner_table() + " SET code='changed' WHERE code='0001'")
                writer.commit()
            except sqlite3.OperationalError as error:
                self.assertIn('locked', str(error).lower())
                writer.rollback()
        sql = []
        view._connection.set_trace_callback(sql.append)
        second = view.scan_catalog_values(self.product.identity,
            replace(request, continuation=first.continuation), ('code',))
        self.assertEqual(second.rows[0].values, ('0001',))
        self.assertTrue(any('LIMIT 2 OFFSET 1' in query for query in sql), sql)
        last = view.scan_catalog_values(self.product.identity,
            replace(request, continuation=second.continuation), ('code',))
        self.assertEqual(last.rows[0].values, ('0002',))
        self.assertIsNone(last.continuation)


    def test_full_selection_batches_all_owners_without_partial_cards(self):
        from yadinassi.catalog_backend import CatalogSelection
        drafts = self.seed(1000)
        view = self.view(); statements = []
        view._connection.set_trace_callback(statements.append)
        with patch.object(view, '_card', wraps=view._card) as materialize:
            cards = view.select_catalog(self.product.identity, CatalogSelection(1000))
        self.assertEqual(len(cards), 1000)
        self.assertEqual(materialize.call_count, 1000)
        self.assertEqual(tuple(card.key for card in cards), tuple(draft.key for draft in drafts))
        self.assertTrue(all(type(card) is CatalogCard and card.tabular_sections == self.expected()
                            for card in cards))
        self.assertLessEqual(len(statements), 52, statements)
        self.assertEqual(sum(sql.startswith('SELECT definition FROM catalog_schema')
                             for sql in statements), 1)

    def test_selection_corruption_refuses_before_constructing_cards(self):
        from yadinassi.catalog_backend import CatalogSelection
        for code in ('10', '20'):
            draft = self.draft(self.expected(self.row(text=code)), code=code)
            self.create(draft)
        self.sql('UPDATE ' + self.table() + ' SET row_number=2 WHERE owner_id=?',
                 (str(draft.key.record_id),))
        view = self.view()
        with patch.object(view, '_card', wraps=view._card) as materialize:
            with self.assertRaisesRegex(BackendError, 'integrity'):
                view.select_catalog(self.product.identity, CatalogSelection(2))
        self.assertEqual(materialize.call_count, 0)


class ProjectionBoundaryTests(unittest.TestCase):
    def setUp(self):
        import test_catalog_queries as query_fixtures
        query_fixtures.CatalogQueryTests.setUp(self)
        self.addCleanup(self.temp.cleanup)
        self.addCleanup(self.context.close)

    def test_projected_ref_cannot_substitute_another_row_identity(self):
        from yadinassi.catalog_backend import CatalogValuePage
        from yadinassi.queries import BSLQuery
        from yadinassi.sqlite_catalog import _View
        manager = self.vm._catalogs.get_index('Products')
        with closing(manager._view()) as view:
            key = view.scan_catalog_values(manager._schema.identity,
                CatalogScanRequest(page_size=1), ('ref',)).rows[0].key
        other = replace(key, record_id=uuid4())
        page = CatalogValuePage((CatalogValueRow(key, (other,)),), None)
        with patch.object(_View, 'scan_catalog_values', return_value=page):
            with self.assertRaisesRegex(BackendError, 'integrity'):
                BSLQuery(self.vm._catalogs, 'SELECT Ref FROM Catalog.Products').execute()
        with closing(self.context.backend.begin_read()):
            pass

    def test_hostile_key_components_are_rejected_before_equality_and_release_view(self):
        from yadinassi.catalog_backend import CatalogValuePage
        from yadinassi.queries import BSLQuery
        from yadinassi.sqlite_catalog import _View
        class Hostile:
            def __eq__(self, other):
                raise AssertionError('hostile equality executed')
            def __ne__(self, other):
                raise AssertionError('hostile inequality executed')
        manager = self.vm._catalogs.get_index('Products')
        with closing(manager._view()) as view:
            key = view.scan_catalog_values(manager._schema.identity,
                CatalogScanRequest(page_size=1), ('ref',)).rows[0].key
        for component in ('database_id', 'catalog_id', 'record_id'):
            invalid = replace(key, **{component: Hostile()})
            for bad_key, bad_value in ((invalid, key), (key, invalid)):
                for mode in ('query', 'find'):
                    with self.subTest(component=component, row_key=bad_key is invalid, mode=mode):
                        page = CatalogValuePage((CatalogValueRow(bad_key, (bad_value,)),), None)
                        with patch.object(_View, 'scan_catalog_values', return_value=page):
                            with self.assertRaisesRegex(BackendError, 'integrity'):
                                if mode == 'query':
                                    BSLQuery(self.vm._catalogs, 'SELECT Ref FROM Catalog.Products').execute()
                                else:
                                    manager.find_by_code('1')
                        with closing(self.context.backend.begin_read()):
                            pass
