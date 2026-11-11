"""Short readonly leases: actual-connection epochs, corruption and cleanup."""
from contextlib import closing
from dataclasses import replace
import os
from pathlib import Path
import shutil
import sqlite3
from threading import Event, Thread
import unittest
from unittest.mock import patch
from uuid import uuid4

import test_catalog_scan_optimization as fixtures
from test_sqlite_catalog_admission_cleanup import AdmissionFaultConnection
from yadinassi.catalog_backend import BackendError, CatalogComparison, CatalogScanRequest
from yadinassi.sqlite_catalog import SQLiteCatalogBackend, _View
from yadinassi.sqlite_catalog_layout import quote_identifier
from yadinassi.sqlite_read_handles import ReadHandle


class ReadHandleLifecycleTests(unittest.TestCase):
    setUp = fixtures.ScanOptimizationTests.setUp
    values = fixtures.ScanOptimizationTests.values
    section = fixtures.ScanOptimizationTests.section
    row = fixtures.ScanOptimizationTests.row
    draft = fixtures.ScanOptimizationTests.draft
    create = fixtures.ScanOptimizationTests.create
    sql = fixtures.ScanOptimizationTests.sql
    table = fixtures.ScanOptimizationTests.table
    expected = fixtures.ScanOptimizationTests.expected
    seed = fixtures.ScanOptimizationTests.seed
    owner_table = fixtures.ScanOptimizationTests.owner_table

    def scan(self, code=None):
        request = CatalogScanRequest(predicate=None if code is None else CatalogComparison('code', 'eq', code))
        with closing(self.backend.begin_read()) as view:
            return view.scan_catalog_values(self.product.identity, request, ('code',))

    def test_retained_connection_is_idle_readonly_and_old_view_is_closed(self):
        self.seed(2)
        view = self.backend.begin_read(); connection = view._connection
        view.scan_catalog_values(self.product.identity, CatalogScanRequest(), ('code',))
        view.close(); view.close()
        self.assertFalse(connection.in_transaction)
        self.assertIsNone(view._connection)
        self.assertIsNone(self.backend._active)
        with self.assertRaisesRegex(BackendError, 'closed'):
            view.scan_catalog_values(self.product.identity, CatalogScanRequest(), ('code',))
        with self.assertRaises(sqlite3.OperationalError):
            connection.execute("UPDATE database_info SET name='not permitted'")
        with closing(self.backend.begin_read()) as other:
            self.assertIs(other._connection, connection)
        self.backend.close()
        with self.assertRaises(sqlite3.ProgrammingError): connection.execute('SELECT 1')

    def test_repeat_lookup_decodes_once_per_same_handle_epoch(self):
        self.seed(7)
        original = _View._scalar; calls = []
        def decode(view, *args, **kwargs):
            calls.append(1); return original(view, *args, **kwargs)
        with patch.object(_View, '_scalar', decode):
            for _ in range(10):
                self.assertEqual(self.scan('0006').rows[0].values, ('0006',))
        self.assertEqual(len(calls), 7)

    def test_external_same_generation_commit_invalidates_hidden_scalar(self):
        self.seed(3); self.scan('0000')
        generation = self.backend.configuration_generation
        column = quote_identifier(self.backend._layout.field_name(self.product.identity, self.product.fields[1].identity))
        self.sql('UPDATE '+self.owner_table()+' SET '+column+'=? WHERE code=?', ('bad-number', '0002'))
        with self.assertRaisesRegex(BackendError, 'integrity'): self.scan('0000')
        self.assertEqual(self.backend.configuration_generation, generation)
        self.assertFalse(self.backend._read_handle.proofs)
        self.sql('UPDATE '+self.owner_table()+' SET '+column+'=? WHERE code=?', ('12.30', '0002'))
        self.assertEqual(len(self.scan('0000').rows), 1)

    def test_external_valid_commit_is_fresh_and_writer_not_blocked_between_calls(self):
        self.seed(2); self.scan()
        connection = self.backend._read_handle.connection
        with closing(sqlite3.connect(self.path, timeout=0, isolation_level=None)) as writer:
            writer.execute('BEGIN IMMEDIATE')
            writer.execute('UPDATE '+self.owner_table()+" SET code='new' WHERE code='0001'")
            writer.execute('COMMIT')
        self.assertEqual(len(self.scan('new').rows), 1)
        self.assertIs(self.backend._read_handle.connection, connection)

    def test_foreign_commit_before_first_read_cannot_reuse_old_epoch(self):
        self.seed(2); self.scan()
        real = self.backend._check_file; calls = []
        def check():
            calls.append(1)
            if len(calls) == 1:
                self.sql('UPDATE '+self.owner_table()+" SET code='changed' WHERE code='0001'")
            return real()
        with patch.object(self.backend, '_check_file', side_effect=check):
            self.assertEqual(len(self.scan('changed').rows), 1)

    def test_commit_after_rollback_does_not_relabel_old_proof(self):
        self.seed(2)
        real = ReadHandle.complete
        def complete(handle, proofs):
            self.sql('UPDATE '+self.owner_table()+" SET description='new' WHERE code='0001'")
            return real(handle, proofs)
        with patch.object(ReadHandle, 'complete', complete): self.scan()
        with closing(self.backend.begin_read()) as view:
            self.assertEqual(view._validated_sources, {})
            with patch.object(view, '_preflight_v2', wraps=view._preflight_v2) as validate:
                view.scan_catalog_values(self.product.identity, CatalogScanRequest(), ('code',))
            self.assertEqual(validate.call_count, 1)

    def test_own_write_invalidates_all_read_proofs_even_after_rollback(self):
        self.seed(2); self.scan(); handle = self.backend._read_handle
        self.assertTrue(handle.proofs)
        with closing(self.backend.begin_write(uuid4())) as tx:
            self.assertFalse(handle.proofs)
            self.assertEqual(tx._validated_sources, {})
        self.assertEqual(len(self.scan().rows), 2)

    def test_new_handle_and_new_backend_are_always_cold(self):
        self.seed(2); self.scan(); old = self.backend._read_handle.connection
        self.backend._close_idle_read_handle()
        with closing(self.backend.begin_read()) as view:
            self.assertIsNot(view._connection, old)
            self.assertEqual(view._validated_sources, {})
        other = SQLiteCatalogBackend(self.path); self.addCleanup(other.close)
        with closing(other.begin_read()) as view: self.assertEqual(view._validated_sources, {})

    def test_validation_failure_never_publishes_partial_facts(self):
        self.seed(2)
        view = self.backend.begin_read()
        view.scan_catalog_values(self.category.identity, CatalogScanRequest(), ('code',))
        with patch.object(view, '_preflight_v2', side_effect=BackendError('integrity')):
            with self.assertRaises(BackendError):
                view.scan_catalog_values(self.product.identity, CatalogScanRequest(), ('code',))
        handle = self.backend._read_handle; view.close()
        self.assertEqual(handle.proofs, {})

    def test_interrupted_validation_never_publishes(self):
        self.seed(2); view = self.backend.begin_read()
        with patch.object(view, '_scalar', side_effect=KeyboardInterrupt('validation')):
            with self.assertRaises(KeyboardInterrupt):
                view.scan_catalog_values(self.product.identity, CatalogScanRequest(), ('code',))
        view.close(); self.assertEqual(self.backend._read_handle.proofs, {})

    def test_rollback_and_close_failure_retains_busy_owner_until_retry(self):
        self.seed(2); view = self.backend.begin_read(); original = view._connection
        proxy = AdmissionFaultConnection(original, rollback_error=sqlite3.OperationalError('rollback'),
                                         close_error=sqlite3.OperationalError('close'))
        view._connection = proxy
        # Exercise a registered actual lease whose cleanup itself fails.
        self.backend._read_handle.connection = proxy
        with self.assertRaisesRegex(BackendError, 'storage_error'): view.close()
        self.assertIs(self.backend._active, view)
        self.assertIsNone(self.backend._read_handle)
        with self.assertRaisesRegex(BackendError, 'busy'): self.backend.begin_read()
        proxy.disable_faults(); view.close()
        self.assertIsNone(self.backend._active)
        self.assertEqual(len(self.scan().rows), 2)

    def test_idle_close_failure_is_owned_and_retryable(self):
        self.seed(2); self.scan(); handle = self.backend._read_handle
        proxy = AdmissionFaultConnection(handle.connection, close_error=sqlite3.OperationalError('close'))
        handle.connection = proxy
        with self.assertRaisesRegex(BackendError, 'storage_error'): self.backend.close()
        self.assertIs(self.backend._active._connection, proxy)
        with self.assertRaisesRegex(BackendError, 'busy'): self.backend.begin_read()
        proxy.disable_faults(); self.backend.close()
        self.assertIsNone(self.backend._active)
        with self.assertRaisesRegex(BackendError, 'closed'): self.backend.begin_read()

    def test_observable_file_replacement_is_refused_even_same_database_identity(self):
        self.seed(2); self.scan()
        replacement = Path(self.directory.name) / 'replacement.sqlite'
        shutil.copyfile(self.path, replacement)
        try: os.replace(replacement, self.path)
        except PermissionError:
            self.skipTest('platform prevents replacing an open SQLite file')
        with self.assertRaisesRegex(BackendError, 'schema_changed'): self.scan()
        self.assertTrue(self.backend._read_handle is None or not self.backend._read_handle.proofs)

    def test_one_active_contract_is_not_changed_by_retention(self):
        self.seed(2); self.scan()
        with closing(self.backend.begin_read()):
            with self.assertRaisesRegex(BackendError, 'busy'): self.backend.begin_read()
            with self.assertRaisesRegex(BackendError, 'busy'): self.backend.begin_write(uuid4())
        self.assertEqual(len(self.scan().rows), 2)

    def test_sequential_host_threads_do_not_share_simultaneous_connection_use(self):
        self.seed(2); self.scan(); handle = self.backend._read_handle
        results = []; errors = []
        def work():
            try: results.append(self.scan('0001'))
            except BaseException as error: errors.append(error)
        thread = Thread(target=work); thread.start(); thread.join()
        self.assertEqual(errors, [])
        self.assertEqual(len(results[0].rows), 1)
        self.assertIs(self.backend._read_handle, handle)

    def test_concurrent_begin_cannot_take_or_close_reserved_handle(self):
        self.seed(2)
        self.backend._close_idle_read_handle()
        entered = Event(); release = Event(); result = []; errors = []
        original = self.backend._connect
        def connect(**kwargs):
            entered.set()
            if not release.wait(5): raise RuntimeError('test release timeout')
            return original(**kwargs)
        def first():
            try: result.append(self.backend.begin_read())
            except BaseException as error: errors.append(error)
        with patch.object(self.backend, '_connect', connect):
            thread = Thread(target=first); thread.start()
            try:
                self.assertTrue(entered.wait(5))
                reserved = self.backend._active
                with self.assertRaisesRegex(BackendError, 'busy'): self.backend.begin_read()
                with self.assertRaisesRegex(BackendError, 'busy'): self.backend.close()
                with self.assertRaisesRegex(BackendError, 'busy'): self.backend._close_idle_read_handle()
                self.assertIs(self.backend._active, reserved)
            finally:
                release.set(); thread.join()
        self.assertEqual(errors, [])
        result[0].close()
        self.assertEqual(len(self.scan().rows), 2)

    def test_interrupted_detach_recovers_exact_handle_and_releases_owner(self):
        self.seed(2)
        for attribute in ('_connection','_read_handle'):
            with self.subTest(attribute=attribute):
                view=self.backend.begin_read(); connection=view._connection
                view.scan_catalog_values(self.product.identity,CatalogScanRequest(),('code',))
                fired=[]
                def assign(owner,name,value):
                    object.__setattr__(owner,name,value)
                    if owner is view and name==attribute and value is None and not fired:
                        fired.append(True)
                        raise KeyboardInterrupt()
                with patch.object(_View,'__setattr__',assign):
                    with self.assertRaises(KeyboardInterrupt):view.close()
                self.assertEqual(fired,[True])
                self.assertIsNone(self.backend._active)
                self.assertIsNone(self.backend._read_handle)
                with self.assertRaises(sqlite3.ProgrammingError):connection.execute('SELECT 1')
                view.close()
                self.assertEqual(len(self.scan().rows),2)

    def test_retained_proof_counts_and_owner_identities_are_bounded(self):
        from yadinassi.sqlite_read_handles import _bounded_proofs, MAX_PROOFS, MAX_OWNER_IDENTITIES
        facts={('fact',i):() for i in range(MAX_PROOFS+10)}
        self.assertEqual(len(_bounded_proofs(facts)),MAX_PROOFS)
        owners=frozenset(str(i).zfill(36) for i in range(MAX_OWNER_IDENTITIES))
        retained=_bounded_proofs({'all':owners,'extra':frozenset({'one'}),'mutable':[],
                                  'bool':(True,),'bytes':b'x','cost':(1,2,3)})
        self.assertEqual(retained,{'all':owners,'cost':(1,2,3)})

    def test_document_wrapper_failure_physically_retires_and_keeps_failed_close_owner(self):
        self.seed(2);self.backend._close_idle_read_handle()
        original=self.backend._connect; proxies=[]
        def connect(**kwargs):
            raw=original(**kwargs)
            proxy=AdmissionFaultConnection(raw,close_error=sqlite3.OperationalError('close failed'))
            kwargs['_owner']._connection=proxy
            proxies.append(proxy)
            return proxy
        failure=MemoryError('wrapper admission')
        try:
            with patch.object(self.backend,'_connect',connect), \
                    patch('yadinassi.sqlite_catalog.DocumentView',side_effect=failure):
                with self.assertRaises(MemoryError) as caught:self.backend.begin_query_read()
            self.assertIs(caught.exception,failure)
            self.assertIsNone(self.backend._read_handle)
            self.assertIsNotNone(self.backend._active)
            self.assertIs(self.backend._active._connection,proxies[0])
            self.assertTrue(self.backend._active._closed)
            with self.assertRaisesRegex(BackendError,'busy'):self.backend.begin_read()
        finally:
            for proxy in proxies:proxy.disable_faults()
            if self.backend._active is not None:self.backend._active.close()
        self.assertEqual(len(self.scan().rows),2)
