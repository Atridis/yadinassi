"""Read-plan optimizations on explicitly migrated, indexed v11 databases."""
from dataclasses import replace
from contextlib import closing
from unittest.mock import patch
from uuid import uuid4
import unittest

import test_catalog_scan_optimization as catalog_fixture
import test_sqlite_unit_of_work as transaction_fixture
from yadinassi.catalog_backend import CatalogScanRequest, BackendError
from yadinassi.document_backend import DocumentScanRequest
from yadinassi.sqlite_catalog import SQLiteCatalogBackend
from yadinassi.sqlite_migration_plan import prepare, apply
from yadinassi.transaction_backend import TransactionRequest


class MigratedCatalogReadTests(unittest.TestCase):
    values = catalog_fixture.ScanOptimizationTests.values
    section = catalog_fixture.ScanOptimizationTests.section
    row = catalog_fixture.ScanOptimizationTests.row
    draft = catalog_fixture.ScanOptimizationTests.draft
    create = catalog_fixture.ScanOptimizationTests.create
    sql = catalog_fixture.ScanOptimizationTests.sql
    table = catalog_fixture.ScanOptimizationTests.table
    expected = catalog_fixture.ScanOptimizationTests.expected
    seed = catalog_fixture.ScanOptimizationTests.seed
    view = catalog_fixture.ScanOptimizationTests.view

    def setUp(self):
        catalog_fixture.ScanOptimizationTests.setUp(self)
        self.backend.close()
        plan = prepare(self.path, maintenance=True)
        apply(self.path, plan, maintenance=True)
        self.backend = SQLiteCatalogBackend(self.path)
        self.addCleanup(self.backend.close)

    def test_migrated_keyset_uses_admitted_index_and_no_offset(self):
        self.seed(7); view = self.view(); sql = []
        view._connection.set_trace_callback(sql.append)
        request = CatalogScanRequest(page_size=2); records = []
        while True:
            page = view.scan_catalog_values(self.product.identity, request, ('ref',))
            records.extend(row.key.record_id for row in page.rows)
            if page.continuation is None: break
            request = replace(request, continuation=page.continuation)
        self.assertEqual(len(records), 7)
        self.assertEqual(records, sorted(records, key=lambda v: v.int))
        scans = [q for q in sql if 'ORDER BY record_id COLLATE yadinassi_uuid_v1' in q]
        self.assertTrue(scans)
        self.assertFalse(any('OFFSET' in q for q in scans))
        plan = view._connection.execute('EXPLAIN QUERY PLAN '+scans[-1]).fetchall()
        self.assertTrue(any('query_catalog_' in row[3] for row in plan), plan)
        self.assertFalse(any('TEMP B-TREE' in row[3] for row in plan), plan)

    def test_migrated_repeat_scans_reuse_integrity_pass(self):
        self.seed(4); view = self.view()
        with patch.object(view, '_preflight_v2', wraps=view._preflight_v2) as check:
            for _ in range(2):
                view.scan_catalog_values(self.product.identity, CatalogScanRequest(), ('code',))
            self.assertEqual(check.call_count, 1)
        view.close()
        self.assertFalse(view._validated_sources)

    def test_v11_catalog_writes_keep_registered_index_comparator(self):
        self.seed(3)
        self.backend.close()
        self.backend = SQLiteCatalogBackend(self.path); self.addCleanup(self.backend.close)
        draft = self.draft(code='late')
        with closing(self.backend.begin_write(uuid4())) as tx:
            tx.create(draft); tx.commit()
        page = self.view().scan_catalog_values(self.product.identity, CatalogScanRequest(), ('code',))
        self.assertEqual(len(page.rows), 4)


class MigratedDocumentReadTests(unittest.TestCase):
    setUp = transaction_fixture.UnitOfWorkTests.setUp
    document = transaction_fixture.UnitOfWorkTests.document
    catalog = transaction_fixture.UnitOfWorkTests.catalog

    def test_migrated_document_projection_and_index_share_snapshot(self):
        doc = self.document()
        with self.backend.begin_unit_of_work(uuid4()) as tx:
            tx.stage(TransactionRequest('document_create', doc)); tx.commit()
        view = self.backend.begin_query_read(); self.addCleanup(view.close)
        schema = view.document_schema(doc.key.document_id)
        self.assertEqual(view._validate_query_source(schema)[0], 1)
        sql = []; view._connection.set_trace_callback(sql.append)
        with patch.object(view, '_card', side_effect=AssertionError('full-card materialization')):
            page = view.scan_document_values(schema.identity, DocumentScanRequest(), ('number',))
        self.assertEqual(page.rows[0].values, ('A',))
        scans = [q for q in sql if 'ORDER BY date,number,record_id' in q]
        self.assertTrue(scans)
        self.assertTrue(all('sections_json' not in q and 'values_json' not in q for q in scans))
        plan = view._connection.execute('EXPLAIN QUERY PLAN '+scans[-1]).fetchall()
        self.assertTrue(any('document_query_order_v1' in row[3] for row in plan), plan)

    def test_unit_of_work_never_sets_read_validation_markers(self):
        request = TransactionRequest('catalog_create', self.catalog())
        with self.backend.begin_unit_of_work(uuid4()) as tx:
            tx.stage(request)
            self.assertEqual(tx.read_catalog(request.draft.key).code, 'item')
            # UoW read-your-writes must not consume a prior read-only proof.
            self.assertEqual(tx._view._validated_sources, {})
