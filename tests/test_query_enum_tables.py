"""Durable enum reports: bounded host contract, not a native parity assertion."""
from dataclasses import replace
from decimal import Decimal
import sqlite3
import unittest
from unittest.mock import patch

from yadinassi import Interpreter, BSLRuntimeError
from yadinassi.catalog_backend import BackendError
from yadinassi.query_packages import BSLTempTablesManager
from yadinassi.values import NULL, BSLType
from yadinassi.sqlite_catalog import _View
from yadinassi.sqlite_documents import DocumentView
import test_inventory_enum_queries as enum_fixtures


class EnumTableTests(unittest.TestCase):
    setUp = enum_fixtures.InventoryEnumQueryTests.setUp

    def q(self, text, table=None, manager=None, vm=None):
        q = (vm or self.vm).execute('New Query')
        q.set_member('Text', text)
        if table is not None: q.set_parameter('Input', table)
        if manager is not None: q.set_member('TempTablesManager', manager)
        return q

    def table(self):
        return self.q('SELECT Ref AS Item,Unit,Code FROM Catalog.Products ORDER BY Code').execute().unload()

    def test_full_report_roundtrip(self):
        t = self.table()
        r = self.q('SELECT Item,Unit INTO Prepared FROM &Input; '
                   'SELECT T.Unit,COUNT(*) AS N FROM Prepared AS T '
                   'JOIN Catalog.Products AS P ON T.Item=P.Ref GROUP BY T.Unit', t).execute().unload()
        self.assertEqual(len(r.rows), 3)
        self.assertTrue(all(row.get_member('N') == Decimal(1) for row in r.rows))

    def test_manager_reuse_reissues_descriptors(self):
        m = BSLTempTablesManager()
        self.q('SELECT Unit INTO Saved FROM Catalog.Products', manager=m).execute()
        self.assertIsNone(m._tables['saved'].columns[0].enum_descriptor)
        for _ in range(2):
            r = self.q('SELECT Unit FROM Saved', manager=m).execute()
            self.assertIsNone(r._columns[0].enum_descriptor)
            self.assertEqual(len(r.unload().rows), 3)

    def test_unload_no_scope_or_lease_and_no_io(self):
        r = self.q('SELECT Unit FROM Catalog.Products').execute()
        with patch.object(self.context.backend, 'begin_read', side_effect=AssertionError('point read')):
            t = r.unload()
            self.assertTrue(t.columns.items[0].value_type.contains_type(BSLType.NULL))
            t.rows[0].set_member('Unit', self.piece)
        self.assertIsNone(self.context.backend._active)

    def test_defaults_casts_and_codecs_remain_closed(self):
        t = self.table()
        for action in (t.add, lambda: t.rows[0].set_member('Unit', NULL),
                       lambda: t.rows[0].set_member('Unit', 'Piece')):
            with self.assertRaises((TypeError, ValueError, BackendError)): action()
        self.vm.variables['report'] = t
        for code in ('ValueToStringInternal(Report)', 'New ValueStorage(Report)'):
            with self.assertRaises(BSLRuntimeError): self.vm.execute(code)

    def test_wrong_enum_assignment_is_not_empty_conversion(self):
        t = self.table()
        with self.assertRaises(BackendError): t.rows[0].set_member('Unit', self.vm.execute('Enums.States.Draft'))

    def test_forged_equal_enum_instance_rejected(self):
        t = self.table()
        c = t.columns.items[1]
        t.rows[0].cells[c] = replace(self.piece)
        with self.assertRaises(BackendError): self.q('SELECT Code FROM &Input WHERE Code="missing"', t).execute()

    def test_empty_table_keeps_enum_domain(self):
        t = self.q('SELECT Unit FROM Catalog.Products WHERE Code="missing"').execute().unload()
        self.assertEqual(t.rows, [])
        self.assertIs(t.columns.items[0].value_type.get_types().items[0], self.piece.value_type)
        self.assertEqual(self.q('SELECT Unit FROM &Input', t).execute()._rows, ())

    def test_null_and_typed_empty_are_distinct(self):
        t = self.q('SELECT NULL AS Unit FROM Catalog.Products WHERE Code="P" '
                   'UNION ALL SELECT Unit FROM Catalog.Products WHERE Code="E"').execute().unload()
        r = self.q('SELECT Unit FROM &Input', t).execute()
        self.assertEqual(r._rows, ((NULL,), (self.empty,)))

    def test_array_and_external_parameters_snapshot_once(self):
        from yadinassi.query_sources import _snapshot
        import yadinassi.query_sources as sources
        t = self.table()
        with patch.object(sources, '_snapshot', wraps=_snapshot) as snapshot:
            r = self.q('SELECT Unit INTO A FROM &Input; SELECT Unit FROM A '
                       'UNION ALL SELECT Unit FROM &Input', t).execute()
        self.assertEqual(snapshot.call_count, 1)
        self.assertEqual(len(r._rows), 6)

    def test_foreign_table_snapshot_refused(self):
        t = self.table()
        other = Interpreter(database_context=self.context); self.addCleanup(other.close)
        with self.assertRaises((BackendError, TypeError)): self.q('SELECT Unit FROM &Input', t, vm=other).execute()

    def test_foreign_parameter_refused_before_lease(self):
        other = Interpreter(database_context=self.context); self.addCleanup(other.close)
        q = self.q('SELECT Unit FROM Catalog.Products WHERE Unit=&Unit')
        q.set_parameter('Unit', other.execute('Enums.Units.Piece'))
        with patch.object(self.context.backend, 'begin_query_read', side_effect=AssertionError('foreign lease')):
            with self.assertRaises(BackendError): q.execute()

    def test_cold_first_query_uses_one_lease(self):
        other = Interpreter(database_context=self.context); self.addCleanup(other.close)
        self.assertIsNone(other._catalogs._metadata._items)
        backend = self.context.backend
        with patch.object(backend, 'begin_query_read', wraps=backend.begin_query_read) as query_view, \
                patch.object(backend, 'begin_read', wraps=backend.begin_read) as base_read:
            r = self.q('SELECT Ref AS Item,Unit FROM Catalog.Products', vm=other).execute().unload()
        self.assertEqual(query_view.call_count, 1)
        self.assertEqual(base_read.call_count, 1)
        self.assertEqual(len(r.rows), 3)

    def test_external_and_persistent_reads_share_one_view(self):
        t = self.table(); backend = self.context.backend
        with patch.object(backend, 'begin_query_read', wraps=backend.begin_query_read) as query_view, \
                patch.object(backend, 'begin_read', wraps=backend.begin_read) as base_read:
            self.q('SELECT T.Unit FROM &Input AS T JOIN Catalog.Products AS P ON T.Item=P.Ref', t).execute()
        self.assertEqual(query_view.call_count, 1)
        self.assertEqual(base_read.call_count, 1)

    def test_failed_package_rolls_back_destroy(self):
        m = BSLTempTablesManager()
        self.q('SELECT Unit INTO Saved FROM Catalog.Products', manager=m).execute()
        before = m._tables
        with self.assertRaises(ValueError):
            self.q('DESTROY Saved; SELECT Missing FROM Catalog.Products', manager=m).execute()
        self.assertIs(m._tables, before)

    def test_close_failure_does_not_publish(self):
        m = BSLTempTablesManager(); original = _View.close
        def close(view):
            original(view); raise ValueError('close failure')
        with patch.object(_View, 'close', close):
            with self.assertRaisesRegex(ValueError, 'close failure'):
                self.q('SELECT Unit INTO Saved FROM Catalog.Products', manager=m).execute()
        self.assertEqual(m._tables, {})
        m._lock.acquire()
        try:
            with self.assertRaisesRegex(ValueError, 'busy'):
                self.q('SELECT Unit INTO Saved FROM Catalog.Products', manager=m).execute()
            self.assertIsNone(self.context.backend._active)
        finally:
            m._lock.release()

    def test_manager_close_releases_stale_tables(self):
        m = BSLTempTablesManager()
        self.q('SELECT Unit INTO Saved FROM Catalog.Products', manager=m).execute()
        self.context.close()
        m.close(); m.close()
        self.assertEqual(m._tables, {})

    def test_external_empty_generation_change_fails(self):
        t = self.q('SELECT Unit FROM Catalog.Products WHERE Code="missing"').execute().unload()
        with sqlite3.connect(self.context.path) as c: c.execute('UPDATE database_info SET generation=generation+1')
        with self.assertRaises(BackendError): self.q('SELECT Unit FROM &Input', t).execute()

    def test_warm_metadata_corruption_refused_before_scan(self):
        item = self.vm._catalogs._metadata._items['products']
        item._root = object()
        with patch.object(_View, 'scan_catalog_values', side_effect=AssertionError('scan')):
            with self.assertRaises(BackendError): self.q('SELECT Unit FROM Catalog.Products').execute()

    def test_cold_metadata_failure_leaves_no_partial_cache(self):
        other = Interpreter(database_context=self.context); self.addCleanup(other.close)
        with patch.object(DocumentView, 'documents', side_effect=ValueError('metadata failure')):
            with self.assertRaisesRegex(ValueError, 'metadata failure'):
                self.q('SELECT Unit FROM Catalog.Products', vm=other).execute()
        self.assertIsNone(other._catalogs._metadata._items)
        self.assertIsNone(other._documents._metadata._items)

    def test_document_wrapper_identity_must_match_underlying_view(self):
        original = self.context.backend.begin_query_read
        def opened():
            view = original(); view.configuration_generation += 1; return view
        with patch.object(self.context.backend, 'begin_query_read', opened):
            with self.assertRaises(BackendError): self.q('SELECT Unit FROM Catalog.Products').execute()

    def test_no_query_scope_retained_by_published_columns(self):
        m = BSLTempTablesManager()
        r = self.q('SELECT Unit INTO Saved FROM Catalog.Products; SELECT Unit FROM Saved', manager=m).execute()
        from yadinassi.query_enum_tables import _EnumBinding
        for c in (r._columns[0], m._tables['saved'].columns[0]):
            self.assertIsNone(c.enum_descriptor)
            self.assertIs(type(c.reference_binding), _EnumBinding)
            self.assertFalse(hasattr(c.reference_binding, '_scope'))

    def test_budgets_fail_before_publish(self):
        from yadinassi import query_packages
        m = BSLTempTablesManager()
        with patch.object(query_packages, 'MAX_CELLS', 2):
            with self.assertRaises(ValueError):
                self.q('SELECT Unit INTO Saved FROM Catalog.Products', manager=m).execute()
        self.assertEqual(m._tables, {})

    def test_mixed_enum_schema_refused_before_source_scan(self):
        q = self.q('SELECT Unit FROM Catalog.Products UNION ALL SELECT &State AS Unit FROM Catalog.Products')
        q.set_parameter('State', self.vm.execute('Enums.States.Draft'))
        with patch.object(_View, 'scan_catalog_values', side_effect=AssertionError('scan')):
            with self.assertRaises(TypeError): q.execute()
        other = Interpreter(database_context=self.context); self.addCleanup(other.close)
        cold = self.q('SELECT Unit FROM Catalog.Products UNION ALL SELECT &State AS Unit FROM Catalog.Products', vm=other)
        cold.set_parameter('State', other.execute('Enums.States.Draft'))
        self.assertIsNone(other._catalogs._metadata._items)
        with patch.object(_View, 'scan_catalog_values', side_effect=AssertionError('cold scan')):
            with self.assertRaises(TypeError): cold.execute()
        self.assertIsNone(self.context.backend._active)

    def test_cold_information_register_refused_without_reader(self):
        other = Interpreter(database_context=self.context); self.addCleanup(other.close)
        with patch.object(self.context.backend, 'begin_query_read', side_effect=AssertionError('query reader')), \
                patch.object(self.context.backend, 'begin_read', side_effect=AssertionError('point reader')):
            with self.assertRaises(ValueError):
                self.q('SELECT Amount FROM InformationRegister.Unknown', vm=other).execute()

    def test_transaction_query_uses_one_registered_lease(self):
        from yadinassi.database_transactions import Transaction
        original = Transaction.read_lease; calls = []
        def read(tx):
            calls.append(tx); return original(tx)
        with patch.object(Transaction, 'read_lease', read):
            self.vm.execute('BeginTransaction(); Q=New Query("SELECT Unit INTO T FROM Catalog.Products; SELECT Unit FROM T"); R=Q.Execute().Unload(); RollbackTransaction();')
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0].leases, 0)
        self.assertEqual(calls[0]._read_leases, {})

    def test_registered_lease_rejects_forgery_and_closed_identity(self):
        from yadinassi.database_transactions import require_registered_query_lease
        def probe():
            wrapped = self.context.backend.begin_query_read(); lease = wrapped._view
            self.assertIs(require_registered_query_lease(self.context.backend, lease), lease)
            forged = object.__new__(type(lease)); forged.__dict__.update(lease.__dict__)
            class Arbitrary(_View): pass
            for bad in (forged, object.__new__(Arbitrary)):
                with self.assertRaises(BackendError): require_registered_query_lease(self.context.backend, bad)
            wrapped.close(); wrapped.close()
            with self.assertRaises(BackendError): require_registered_query_lease(self.context.backend, lease)
        self.vm.register_function('Probe', probe, returns_value=False)
        self.vm.execute('BeginTransaction(); Probe(); RollbackTransaction();')

    def test_registered_lease_rejects_wrong_execution_token(self):
        import yadinassi.database_transactions as tx
        def probe():
            wrapped = self.context.backend.begin_query_read()
            token = tx._execution.set(object())
            try:
                with self.assertRaises(BackendError): tx.require_registered_query_lease(self.context.backend, wrapped._view)
            finally:
                tx._execution.reset(token); wrapped.close()
        self.vm.register_function('Probe', probe, returns_value=False)
        self.vm.execute('BeginTransaction(); Probe(); RollbackTransaction();')

    def test_failed_transaction_lease_cleanup_retains_owner_until_retry(self):
        import yadinassi.database_transactions as tx
        from yadinassi.sqlite_catalog import _close_document_scan
        def probe():
            current = tx.current(self.context.backend)
            with patch('yadinassi.sqlite_catalog._close_document_scan', wraps=_close_document_scan) as cleanup:
                wrapped = self.context.backend.begin_query_read(); lease = wrapped._view
                entry = current._read_leases[id(lease)]
                cleanup.side_effect = ValueError('cleanup failure')
                with self.assertRaisesRegex(ValueError, 'cleanup failure'): wrapped.close()
                self.assertFalse(lease._closed)
                self.assertEqual(current.leases, 1)
                self.assertIs(current._read_leases[id(lease)], entry)
                with self.assertRaises(BackendError): current.commit()
                cleanup.side_effect = None
                wrapped.close(); wrapped.close()
                self.assertEqual(current.leases, 0)
                self.assertEqual(current._read_leases, {})
        self.vm.register_function('Probe', probe, returns_value=False)
        self.vm.execute('BeginTransaction(); Probe(); RollbackTransaction();')

    def test_lease_registration_failure_does_not_leak_count(self):
        import yadinassi.database_transactions as tx
        class Broken(dict):
            def __setitem__(self, key, value): raise MemoryError('allocation')
        def probe():
            current = tx.current(self.context.backend)
            with patch.object(current, '_read_leases', Broken()):
                with self.assertRaises(MemoryError): current.read_lease()
            self.assertEqual(current.leases, 0)
            self.assertEqual(current._read_leases, {})
        self.vm.register_function('Probe', probe, returns_value=False)
        self.vm.execute('BeginTransaction(); Probe(); RollbackTransaction();')

    def test_retired_family_generation_refused(self):
        t = self.table()
        self.vm._family_owner._family_generation += 1
        with self.assertRaises(BackendError): self.q('SELECT Unit FROM &Input', t).execute()


if __name__ == '__main__': unittest.main()
