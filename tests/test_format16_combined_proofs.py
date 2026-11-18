"""One real format16 handle owns metadata and COUNT proofs independently."""
from contextlib import closing
from decimal import Decimal
from hashlib import sha256
import sqlite3
import unittest
from unittest.mock import patch
from uuid import uuid4

import test_main_demo_runtime as fixtures
from test_sqlite_catalog_admission_cleanup import AdmissionFaultConnection
from yadinassi.catalog_backend import BackendError, CatalogAggregateRequest
from yadinassi.queries import BSLQuery
from yadinassi.sqlite_catalog_layout import quote_identifier
from yadinassi.sqlite_read_handles import ReadHandle


class Format16CombinedProofTests(unittest.TestCase):
    def setUp(self):
        fixtures.MainDemoRuntimeTests.setUp(self)
        self.vm.execute(fixtures.SEED)
        self.backend = self.context.backend
        self.schema = next(s for s in self.backend._schemas if s.name == 'Номенклатура')
        self.table = quote_identifier(self.backend._layout.table_name(self.schema.identity))

    def count(self):
        # Provider-level coexistence: enum-bound query plans currently decline
        # COUNT pushdown; do not bypass that planner boundary in this test.
        with closing(self.backend.begin_read()) as view:
            result = view.aggregate_catalog(self.schema.identity, CatalogAggregateRequest())
            self.assertIsNotNone(result)
            return Decimal(result.count)

    def warm(self):
        self.assertEqual(self.count(), Decimal(1))
        handle = self.backend._read_handle
        self.assertIsNotNone(handle.admission)
        self.assertTrue(any(k[0] == 'catalog-count-unique-v1' for k in handle.proofs))
        self.assertEqual(self.count(), Decimal(1))
        self.assertIs(self.backend._read_handle, handle)
        return handle

    def mutate(self, sql, args=()):
        with closing(sqlite3.connect(self.path)) as db:
            db.execute(sql, args); db.commit()

    def delete_products(self):
        with closing(sqlite3.connect(self.path)) as db:
            for section in self.schema.tabular_sections:
                table = self.backend._section_layout.table_name(self.schema.identity, section.identity)
                db.execute('DELETE FROM '+quote_identifier(table))
            db.execute('DELETE FROM '+self.table); db.commit()

    def assert_invalidated(self, handle):
        self.assertIsNone(handle.admission)
        self.assertIsNone(handle._pending_admission)
        self.assertEqual(handle.proofs, {})

    def test_both_warm_proofs_skip_admission_and_row_validation(self):
        self.warm()
        from yadinassi.sqlite_catalog import _View
        with patch.object(self.backend, '_validate_transaction_admission', side_effect=AssertionError('admission repeated')), \
                patch.object(_View, '_scalar', side_effect=AssertionError('rows decoded')):
            self.assertEqual(self.count(), Decimal(1))

    def test_external_unprojected_reference_corruption_invalidates_both(self):
        handle = self.warm()
        field = self.schema.fields[0]
        col = quote_identifier(self.backend._layout.field_name(self.schema.identity, field.identity))
        self.mutate('UPDATE '+self.table+' SET '+col+'=?', ('not-a-uuid',))
        with self.assertRaises(BackendError): self.count()
        self.assert_invalidated(handle)

    def test_external_rehashed_source_is_not_new_authority(self):
        handle = self.warm()
        with closing(sqlite3.connect(self.path)) as db:
            raw = db.execute("SELECT content FROM configuration_file WHERE path='Configuration.xml'").fetchone()[0]+b'\n'
        self.mutate("UPDATE configuration_file SET content=?,sha256=? WHERE path='Configuration.xml'", (raw, sha256(raw).hexdigest()))
        with self.assertRaises(BackendError): self.count()
        self.assert_invalidated(handle)

    def test_external_ddl_with_reset_cookie_invalidates_both(self):
        handle = self.warm()
        with closing(sqlite3.connect(self.path)) as db:
            version = db.execute('PRAGMA schema_version').fetchone()[0]
            db.execute('CREATE TABLE injected(x)')
            db.execute('PRAGMA schema_version='+str(version)); db.commit()
        with self.assertRaises(BackendError): self.count()
        self.assert_invalidated(handle)

    def test_valid_external_change_revalidates_and_returns_fresh_count(self):
        handle = self.warm()
        self.delete_products()
        with patch.object(self.backend, '_validate_transaction_admission', wraps=self.backend._validate_transaction_admission) as admission:
            self.assertEqual(self.count(), Decimal(0))
            self.assertEqual(admission.call_count, 1)
        self.assertIs(self.backend._read_handle, handle)
        self.assertIsNotNone(handle.admission)
        self.assertEqual([v for k,v in handle.proofs.items() if k[0]=='catalog-count-unique-v1'], [(0,)])

    def test_own_rolled_back_writer_invalidates_both(self):
        handle = self.warm()
        with closing(self.backend.begin_write(uuid4())):
            self.assert_invalidated(handle)
        self.assertEqual(self.count(), Decimal(1))

    def test_own_committed_write_returns_fresh_count(self):
        handle = self.warm()
        self.vm.execute(fixtures.SEED)
        self.assertEqual(self.count(), Decimal(2))
        self.assertIs(self.backend._read_handle, handle)
        self.assertEqual([v for k,v in handle.proofs.items() if k[0]=='catalog-count-unique-v1'], [(2,)])

    def test_failed_close_retires_both_proofs(self):
        handle = self.warm(); view = self.backend.begin_read()
        self.assertEqual(view.aggregate_catalog(self.schema.identity, CatalogAggregateRequest()).count, 1)
        proxy = AdmissionFaultConnection(view._connection, rollback_error=sqlite3.OperationalError('rollback'), close_error=sqlite3.OperationalError('close'))
        view._connection = proxy; handle.connection = proxy
        try:
            with self.assertRaises(BackendError): view.close()
            self.assert_invalidated(handle)
            self.assertIsNone(self.backend._read_handle)
            with self.assertRaisesRegex(BackendError, 'busy'): self.count()
        finally:
            proxy.disable_faults(); view.close()
        self.assertEqual(self.count(), Decimal(1))
        self.assertIsNot(self.backend._read_handle, handle)

    def test_commit_after_rollback_does_not_relabel_either_proof(self):
        handle = self.warm(); complete = ReadHandle.complete; changed = []
        def after_rollback(owner, proofs):
            if not changed:
                changed.append(True); self.delete_products()
            return complete(owner, proofs)
        with patch.object(ReadHandle, 'complete', after_rollback):
            self.assertEqual(self.count(), Decimal(1))
        self.assertEqual(self.count(), Decimal(0))
        self.assertIs(self.backend._read_handle, handle)
        self.assertEqual([v for k,v in handle.proofs.items() if k[0]=='catalog-count-unique-v1'], [(0,)])

    def test_enum_bound_query_uses_sql_and_retains_both_proofs(self):
        from yadinassi.relational_queries import _Plan
        with patch.object(_Plan, 'load', side_effect=AssertionError('unexpected materialization')):
            for _ in range(2):
                result = BSLQuery(self.vm._catalogs, 'SELECT COUNT(*) AS N FROM Catalog.Номенклатура').execute()
                self.assertEqual(result._rows, ((Decimal(1),),))
        handle = self.backend._read_handle
        self.assertIsNotNone(handle.admission)
        self.assertEqual([value for key, value in handle.proofs.items()
                          if key[0] == 'catalog-count-unique-v1'], [(1,)])
