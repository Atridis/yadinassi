"""Offline integration of qualifier normalization with bounded catalog scans."""
from contextlib import closing
from dataclasses import replace
from decimal import Decimal
from unittest import TestCase
from unittest.mock import patch
from uuid import uuid4

import test_sqlite_catalog_sections as fixtures
from yadinassi.catalog_backend import BackendError, CatalogComparison, CatalogScanRequest
from yadinassi.sqlite_catalog_layout import quote_identifier


class QualifierScanIntegrationTests(TestCase):
    setUp = fixtures.CatalogSectionTests.setUp
    values = fixtures.CatalogSectionTests.values
    section = fixtures.CatalogSectionTests.section
    row = fixtures.CatalogSectionTests.row
    draft = fixtures.CatalogSectionTests.draft
    create = fixtures.CatalogSectionTests.create
    expected = fixtures.CatalogSectionTests.expected
    sql = fixtures.CatalogSectionTests.sql

    def test_normalized_owner_and_section_values_survive_batched_scan_and_projection(self):
        row = self.row('x' * 33, '12.345')
        draft = replace(self.draft(self.expected(row), code='ABCDEFGHtail'),
                        values=self.values('y' * 33, '1.245'))
        self.create(draft)
        request = CatalogScanRequest(CatalogComparison('code', 'eq', 'ABCDEFGH'))
        with closing(self.backend.begin_read()) as view:
            statements = []
            view._connection.set_trace_callback(statements.append)
            fields = ('code', self.product.fields[0].identity, self.product.fields[1].identity)
            with patch.object(view, '_card', side_effect=AssertionError('projection materialized a card')):
                result = view.scan_catalog_values(self.product.identity, request, fields)
            self.assertEqual(result.rows[0].values, ('ABCDEFGH', 'y' * 32, Decimal('1.25')))
            for section in self.product.tabular_sections:
                table = self.backend._section_layout.table_name(self.product.identity, section.identity)
                self.assertFalse(any(table in sql for sql in statements))
            card = view.scan_catalog(self.product.identity, request).cards[0]
            self.assertEqual(card.values[:2], ('y' * 32, Decimal('1.25')))
            self.assertEqual(card.tabular_sections[0].rows[0].values[:2], ('x' * 32, Decimal('12.35')))
            self.assertEqual(card.tabular_sections[0].rows[0].identity, row.identity)
        self.assertEqual(draft.values[:2], ('y' * 33, Decimal('1.245')))

    def test_normalized_duplicate_code_does_not_change_existing_scan_result(self):
        first = self.draft(self.expected(self.row()), code='ABCDEFGHfirst')
        self.create(first)
        second = self.draft(self.expected(self.row()), code='ABCDEFGHsecond')
        with closing(self.backend.begin_write(uuid4())) as tx:
            with self.assertRaisesRegex(BackendError, 'duplicate_code'):
                tx.create(second)
            tx.commit()
        with closing(self.backend.begin_read()) as view:
            page = view.scan_catalog(self.product.identity,
                CatalogScanRequest(CatalogComparison('code', 'eq', 'ABCDEFGH')))
            self.assertEqual(len(page.cards), 1)
            self.assertEqual(page.cards[0].key, first.key)
            self.assertEqual(page.cards[0].tabular_sections, first.tabular_sections)

    def test_overlong_persisted_utf16_is_rejected_even_when_filter_excludes_owner(self):
        draft = self.draft(self.expected(), code='safe')
        self.create(draft)
        table = quote_identifier(self.backend._layout.table_name(self.product.identity))
        self.sql('UPDATE %s SET code=? WHERE record_id=?' % table, ('😀' * 5, str(draft.key.record_id)))
        with closing(self.backend.begin_read()) as view:
            request = CatalogScanRequest(CatalogComparison('code', 'eq', 'absent'))
            with self.assertRaisesRegex(BackendError, 'integrity'):
                view.scan_catalog_values(self.product.identity, request, ('code',))
            with self.assertRaisesRegex(BackendError, 'integrity'):
                view.scan_catalog(self.product.identity, request)
