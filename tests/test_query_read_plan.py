"""Snapshot integrity reuse and stable keyed read-plan contract."""
from dataclasses import replace
import unittest
from unittest.mock import patch

import test_catalog_scan_optimization as scans
import test_document_query_port as documents
import test_catalog_queries as queries
from yadinassi.catalog_backend import CatalogScanRequest, CatalogOrder, BackendError
from yadinassi.document_backend import DocumentScanRequest
from yadinassi.queries import BSLQuery


class CatalogReadPlanTests(unittest.TestCase):
    setUp = scans.ScanOptimizationTests.setUp
    values = scans.ScanOptimizationTests.values
    section = scans.ScanOptimizationTests.section
    row = scans.ScanOptimizationTests.row
    draft = scans.ScanOptimizationTests.draft
    create = scans.ScanOptimizationTests.create
    sql = scans.ScanOptimizationTests.sql
    table = scans.ScanOptimizationTests.table
    expected = scans.ScanOptimizationTests.expected
    seed = scans.ScanOptimizationTests.seed
    view = scans.ScanOptimizationTests.view

    def test_keyset_multiple_orders_has_no_offset(self):
        self.seed(7)
        view = self.view(); trace = []
        view._connection.set_trace_callback(trace.append)
        request = CatalogScanRequest(order=(CatalogOrder('description'), CatalogOrder('code', True)), page_size=2)
        rows = []
        while True:
            page = view.scan_catalog_values(self.product.identity, request, ('code',))
            rows.extend(r.values[0] for r in page.rows)
            if page.continuation is None: break
            request = replace(request, continuation=page.continuation)
        self.assertEqual(rows, [str(i).zfill(4) for i in reversed(range(7))])
        self.assertFalse(any(' OFFSET ' in q.upper() for q in trace))

    def test_two_scans_validate_once_per_snapshot(self):
        self.seed(3); view = self.view()
        with patch.object(view, '_preflight_v2', wraps=view._preflight_v2) as validate:
            for _ in range(2):
                view.scan_catalog_values(self.product.identity, CatalogScanRequest(), ('code',))
            self.assertEqual(validate.call_count, 1)

    def test_new_snapshot_validates_again(self):
        self.seed(3)
        first = self.view()
        first.scan_catalog_values(self.product.identity, CatalogScanRequest(), ('code',)); first.close()
        second = self.view()
        with patch.object(second, '_preflight_v2', wraps=second._preflight_v2) as validate:
            second.scan_catalog_values(self.product.identity, CatalogScanRequest(), ('code',))
            self.assertEqual(validate.call_count, 1)

    def test_failed_validation_not_cached(self):
        self.seed(3); view = self.view()
        with patch.object(view, '_preflight_v2', side_effect=BackendError('integrity')):
            with self.assertRaises(BackendError):
                view.scan_catalog_values(self.product.identity, CatalogScanRequest(), ('code',))
        self.assertFalse(view._validated_sources)


class DocumentReadPlanTests(unittest.TestCase):
    setUp = documents.DocumentQueryPortTests.setUp
    tearDown = documents.DocumentQueryPortTests.tearDown
    object = documents.DocumentQueryPortTests.object
    sql = documents.DocumentQueryPortTests.sql
    seed = documents.DocumentQueryPortTests.seed
    view = documents.DocumentQueryPortTests.view

    def test_full_validation_reused_but_cards_remain_detached(self):
        self.seed(3); view = self.view()
        with patch.object(view, '_preflight', wraps=view._preflight) as validate:
            a = view.scan_documents(self.schema.identity, DocumentScanRequest())
            b = view.scan_documents(self.schema.identity, DocumentScanRequest())
            self.assertEqual(a.rows, b.rows)
            self.assertIsNot(a.rows[0], b.rows[0])
            self.assertEqual(validate.call_count, 1)


class BindingReadPlanTests(unittest.TestCase):
    setUp = queries.CatalogQueryTests.setUp
    tearDown = queries.CatalogQueryTests.tearDown

    def test_simple_and_package_same_rows(self):
        text = 'SELECT Code,Amount FROM Catalog.Products WHERE Amount>=20 ORDER BY Code'
        simple = BSLQuery(self.vm._catalogs, text).execute()
        package = BSLQuery(self.vm._catalogs, text).execute_batch().items[0]
        self.assertEqual(simple._rows, package._rows)
        self.assertEqual(simple._columns, package._columns)

    def test_relational_scan_receives_safe_filter(self):
        from yadinassi.sqlite_catalog import _View
        original = _View.scan_catalog_values; predicates = []
        def scan(view, identity, request, fields):
            predicates.append(request.predicate)
            return original(view, identity, request, fields)
        with patch.object(_View, 'scan_catalog_values', scan):
            BSLQuery(self.vm._catalogs, 'SELECT SUM(Amount) AS Total FROM Catalog.Products WHERE Amount>=20').execute()
        self.assertTrue(predicates)
        self.assertTrue(all(p is not None for p in predicates))

class DocumentProjectionTests(DocumentReadPlanTests):
    def test_header_projection_does_not_decode_sections_twice(self):
        self.seed(3); view = self.view()
        view._validate_query_source(self.schema)
        with patch.object(view, '_card', side_effect=AssertionError('full card')), patch.object(view, '_sections', side_effect=AssertionError('sections')):
            page = view.scan_document_values(self.schema.identity, DocumentScanRequest(), ('number',))
        self.assertEqual(len(page.rows), 3)
        self.assertTrue(all(type(r.values[0]) is str for r in page.rows))

    def test_projection_validation_costs_include_hidden_lines(self):
        self.seed(3); view = self.view()
        count, cells, text = view._validate_query_source(self.schema)
        self.assertEqual(count, 3)
        self.assertGreater(cells, count * 5)
        self.assertGreaterEqual(text, count * 9)

    def test_hidden_corruption_prevents_first_projected_page(self):
        self.seed(3)
        self.sql('UPDATE document_record SET sections_json=? WHERE number=?', ('[]', '000000003'))
        view = self.view()
        with self.assertRaises(BackendError):
            view.scan_document_values(self.schema.identity, DocumentScanRequest(1), ('number',))
        self.assertNotIn(('document-full', self.schema.identity, self.schema), view._view._validated_sources)

    def test_projection_continuation_bound_to_fields(self):
        self.seed(3); view = self.view()
        first = view.scan_document_values(self.schema.identity, DocumentScanRequest(1), ('number',))
        with self.assertRaises(BackendError):
            view.scan_document_values(self.schema.identity, DocumentScanRequest(1, first.continuation), ('date',))

    def test_projection_and_card_scans_invalidate_each_other(self):
        self.seed(3); view = self.view()
        first = view.scan_document_values(self.schema.identity, DocumentScanRequest(1), ('number',))
        view.scan_documents(self.schema.identity, DocumentScanRequest(1))
        with self.assertRaises(BackendError):
            view.scan_document_values(self.schema.identity, DocumentScanRequest(1, first.continuation), ('number',))


class QueryIndexTests(unittest.TestCase):
    def test_uuid_index_supplies_default_order_and_write_collation(self):
        import sqlite3
        from uuid import UUID
        from yadinassi.catalog_backend import CatalogSchema
        from yadinassi.sqlite_query_indexes import register_query_collations, catalog_query_index_ddls
        from yadinassi.sqlite_catalog_layout import build_layout, quote_identifier
        schema = CatalogSchema(UUID(int=9), 'Items', 10, 20)
        layout = build_layout((schema,)); name = quote_identifier(layout.table_name(schema.identity))
        db = sqlite3.connect(':memory:'); self.addCleanup(db.close)
        register_query_collations(db)
        db.execute('CREATE TABLE '+name+'(record_id TEXT)')
        ddl, = catalog_query_index_ddls((schema,), layout)
        db.execute(ddl)
        db.executemany('INSERT INTO '+name+' VALUES(?)', [(str(UUID(int=i)),) for i in (3, 1, 2)])
        sql = 'SELECT record_id FROM '+name+' ORDER BY record_id COLLATE yadinassi_uuid_v1,rowid'
        self.assertEqual([r[0] for r in db.execute(sql)], [str(UUID(int=i)) for i in (1,2,3)])
        explain = ' '.join(str(r) for r in db.execute('EXPLAIN QUERY PLAN '+sql))
        self.assertIn('query_catalog_', explain)
        self.assertNotIn('TEMP B-TREE', explain)

    def test_no_implicit_index_creation(self):
        import sqlite3
        from yadinassi.sqlite_query_indexes import register_query_collations
        db = sqlite3.connect(':memory:'); self.addCleanup(db.close)
        register_query_collations(db)
        self.assertEqual(db.execute('SELECT count(*) FROM sqlite_master').fetchone()[0], 0)
