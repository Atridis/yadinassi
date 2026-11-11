"""Current-admission source data is not importer-cache or transaction authority."""
from contextlib import closing
from dataclasses import replace
from datetime import datetime
from hashlib import sha256
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch
from uuid import uuid4

from inventory_application_fixture import source, DOC_FORM, ROOT
from yadinassi.catalog_backend import BackendError
from yadinassi.configuration_inventory_application import import_inventory_application, PROFILE, validated_core
from yadinassi.database_context import SQLiteDBContext
from yadinassi.inventory_host_operations import InventoryRootOperations, _source_configuration
from yadinassi.inventory_application_reports import InventoryReports
from yadinassi.sqlite_catalog import SQLiteCatalogBackend, _View
from yadinassi.sqlite_documents import DocumentView
from yadinassi import sqlite_inventory_profile


class InventorySourceSnapshotTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(dir=ROOT.parent); self.addCleanup(tmp.cleanup)
        self.path = Path(tmp.name) / 'source.sqlite'
        self.files = source()
        self.config = import_inventory_application(self.files, inventory_runtime=PROFILE)
        self.context = SQLiteDBContext.create_inventory_application(self.path, self.config)
        self.backend = self.context.backend
        self.addCleanup(self.context.close)

    def sql(self, statement, args=()):
        with closing(sqlite3.connect(self.path)) as db:
            db.execute(statement, args); db.commit()

    def source(self, expected=None):
        with closing(self.backend.begin_read()) as view:
            return view.inventory_source(expected=self.config if expected is None else expected)

    def test_port_captures_actual_admit_return_not_backend_or_cache(self):
        original = sqlite_inventory_profile.admit
        observed = []
        def fresh(*args, **kwargs):
            result = replace(original(*args, **kwargs)); observed.append(result); return result
        with patch.object(sqlite_inventory_profile, 'admit', fresh):
            with closing(self.backend.begin_read()) as view:
                self.assertIs(view.inventory_source(expected=self.config), observed[-1])
                self.assertIsNot(observed[-1], self.backend.accumulation_configuration)
                self.assertIsNot(observed[-1], self.backend._prepared_source._entry.value)

    def test_port_does_not_read_late_backend_configuration(self):
        with closing(self.backend.begin_read()) as view:
            original = self.backend.accumulation_configuration
            try:
                self.backend.accumulation_configuration = replace(original, name='Changed')
                self.assertIs(view.inventory_source(expected=self.config), original)
            finally:
                self.backend.accumulation_configuration = original

    def test_document_wrapper_uses_same_owner_no_second_read(self):
        with closing(self.backend.begin_document_read()) as view:
            with patch.object(self.backend, 'begin_read', side_effect=AssertionError('second lease')):
                self.assertEqual(view.inventory_source(expected=self.config), self.config)

    def test_close_revokes_capture_but_detached_data_is_not_mutated(self):
        view = self.backend.begin_read(); data = view.inventory_source()
        view.close()
        self.assertIsNone(view._inventory_source)
        self.assertEqual(data, self.config)
        with self.assertRaises(BackendError): view.inventory_source()
        with closing(self.backend.begin_read()) as next_view:
            self.assertEqual(next_view.inventory_source(expected=data), data)
            self.assertIsNot(next_view, view)

    def test_backend_close_revokes_live_capture(self):
        view = self.backend.begin_read(); self.backend.close()
        self.assertIsNone(view._inventory_source)
        with self.assertRaises(BackendError): view.inventory_source()

    def test_poison_refuses_even_before_cleanup(self):
        with closing(self.backend.begin_read()) as view:
            view._poisoned = True
            with self.assertRaises(BackendError): view.inventory_source()

    def test_cleanup_failure_revokes_capture_and_retains_owner_until_closed(self):
        view = self.backend.begin_read()
        raw = view._connection
        class Connection:
            def __getattr__(self, name): return getattr(raw, name)
            def close(self): raise sqlite3.OperationalError('failed close')
        view._connection = Connection()
        with self.assertRaises(BackendError): view.close()
        self.assertIsNone(view._inventory_source)
        self.assertIs(self.backend._active, view)
        with self.assertRaises(BackendError): view.inventory_source()
        view._connection = raw
        view.close()
        self.assertIsNone(self.backend._active)

    def test_actual_transaction_read_lease_remains_outside_source_port(self):
        from yadinassi.database_transactions import Transaction
        transaction = Transaction(self.backend, object())
        try:
            with closing(transaction.read_lease()) as lease:
                with self.assertRaises(BackendError): lease.inventory_source()
                with self.assertRaises(BackendError): DocumentView(lease).inventory_source()
            self.assertEqual(transaction.leases, 0)
        finally:
            transaction.rollback()

    def test_writer_has_no_source_capture(self):
        with closing(self.backend.begin_write(uuid4())) as view:
            self.assertIsNone(view._inventory_source)
            with self.assertRaises(BackendError): view.inventory_source()
            with self.assertRaises(BackendError): DocumentView(view).inventory_source()

    def test_subclass_lease_cannot_reuse_parent_capture(self):
        class Lease(_View): pass
        with closing(self.backend.begin_read()) as view:
            lease = object.__new__(Lease); lease.__dict__.update(view.__dict__)
            with self.assertRaises(BackendError): lease.inventory_source()

    def test_exact_unregistered_view_cannot_copy_capture(self):
        with closing(self.backend.begin_read()) as view:
            other = object.__new__(_View); other.__dict__.update(view.__dict__)
            with self.assertRaises(BackendError): other.inventory_source()

    def test_foreign_capture_is_refused(self):
        with closing(SQLiteCatalogBackend(self.path)) as backend:
            with closing(self.backend.begin_read()) as one, closing(backend.begin_read()) as two:
                original = one._inventory_source
                one._inventory_source = two._inventory_source
                try:
                    with self.assertRaises(BackendError): one.inventory_source()
                finally: one._inventory_source = original

    def test_view_identity_change_is_refused(self):
        with closing(self.backend.begin_read()) as view:
            view.configuration_generation += 1
            with self.assertRaises(BackendError): view.inventory_source()

    def test_none_expected_is_not_omitted_expected(self):
        with closing(self.backend.begin_read()) as view:
            with self.assertRaises(BackendError): view.inventory_source(expected=None)

    def test_hostile_expected_equality_is_never_called(self):
        touched = []
        class Hostile:
            def __eq__(self, other): touched.append('eq'); return True
            def __ne__(self, other): touched.append('ne'); return False
        bad = Hostile()
        with closing(self.backend.begin_read()) as view:
            for expected in (bad, replace(self.config, source_digest=bad),
                             replace(self.config, catalogs=(replace(self.config.catalogs[0], fields=bad),)),
                             replace(self.config, commands=(bad,))):
                with self.subTest(expected_type=type(expected)), self.assertRaises(BackendError):
                    view.inventory_source(expected=expected)
        self.assertEqual(touched, [])

    def test_hostile_backend_expected_is_not_called_by_begin(self):
        touched = []
        class Hostile:
            def __eq__(self, other): touched.append('eq'); return True
            def __ne__(self, other): touched.append('ne'); return False
        self.backend.accumulation_configuration = Hostile()
        with self.assertRaises(BackendError): self.backend.begin_read()
        self.assertEqual(touched, [])
        self.assertIsNone(self.backend._active)

    def test_same_digest_changed_nested_grant_is_not_admitted(self):
        for expected in (replace(self.config, commands=()), replace(self.config, reports=()),
                         replace(self.config, files=self.config.files[:-1]),
                         replace(self.config, catalogs=(replace(self.config.catalogs[0], code_length=True),))):
            with self.assertRaises(BackendError): self.source(expected)

    def test_raw_source_change_same_generation_refuses_next_snapshot(self):
        self.source()
        self.sql('UPDATE configuration_file SET content=? WHERE path=?', (b'bad', DOC_FORM))
        with self.assertRaises(BackendError): self.source()
        self.assertIsNone(self.backend._active)
        self.sql('UPDATE configuration_file SET content=? WHERE path=?', (self.files[DOC_FORM], DOC_FORM))
        self.source()

    def test_rehashed_changed_form_is_not_old_source_proof(self):
        self.source(); raw = self.files[DOC_FORM] + b'\n'
        self.sql('UPDATE configuration_file SET content=?,sha256=? WHERE path=?', (raw, sha256(raw).hexdigest(), DOC_FORM))
        with self.assertRaises(BackendError): self.source()

    def test_schema_mutation_is_not_hidden_by_prepared_config(self):
        self.source(); self.sql('CREATE TABLE extra(value)')
        with self.assertRaises(BackendError): self.source()

    def test_current_source_admission_runs_for_each_read(self):
        with patch.object(sqlite_inventory_profile, 'admit', wraps=sqlite_inventory_profile.admit) as admit, \
                patch('yadinassi.configuration_inventory_application.import_inventory_application') as importer:
            for _ in range(3): self.source()
            self.assertEqual(admit.call_count, 3); importer.assert_not_called()

    def test_core15_does_not_receive_forms_source_port(self):
        with closing(SQLiteCatalogBackend.create_inventory(self.path.with_name('core.sqlite'), validated_core(self.config))) as backend:
            with closing(backend.begin_read()) as view:
                with self.assertRaises(BackendError): view.inventory_source()

    def test_caller_verify_has_one_admitted_read_no_canonical_export(self):
        host = InventoryRootOperations(self.context, self.config); self.addCleanup(host.close)
        with patch.object(self.backend, 'begin_document_read', wraps=self.backend.begin_document_read) as begin, \
                patch.object(self.backend, 'export_configuration', side_effect=AssertionError('export')), \
                patch('yadinassi.configuration_inventory_application._import_source', side_effect=AssertionError('compile')):
            host.verify_source(); self.assertEqual(begin.call_count, 1)
            host._verify(); self.assertEqual(begin.call_count, 2)

    def test_report_uses_one_current_admission_no_second_import(self):
        reports = InventoryReports(self.context, self.config)
        with patch.object(sqlite_inventory_profile, 'admit', wraps=sqlite_inventory_profile.admit) as admit, \
                patch('yadinassi.configuration_inventory_application._import_source', side_effect=AssertionError('compile')):
            reports.read('StockBalance', at=datetime(2024, 1, 1))
            self.assertEqual(admit.call_count, 1)

    def test_source_helper_cannot_accept_expected_hooks(self):
        class Hostile:
            def __eq__(self, other): raise AssertionError('hook')
        with self.assertRaises(BackendError): _source_configuration(self.backend, expected=Hostile())
        self.assertIsNone(self.backend._active)

    def test_invalid_constructor_configuration_cannot_gain_backend_source(self):
        for factory in (InventoryReports, InventoryRootOperations):
            with self.assertRaises(BackendError): factory(self.context, None)
            self.assertIsNone(self.backend._active)

    def test_host_constructor_and_verify_refuse_duck_backend_before_begin(self):
        from types import SimpleNamespace
        touched = []
        class Duck:
            format_version = 15
            def begin_document_read(self): touched.append('begin'); raise AssertionError('duck')
        class Subclass(SQLiteCatalogBackend):
            def begin_document_read(self): touched.append('subclass begin'); raise AssertionError('subclass')
        fake = object.__new__(Subclass)
        for backend in (Duck(), fake):
            context = SimpleNamespace(backend=backend, require_active=lambda **kw: touched.append('context'))
            with self.assertRaises(BackendError): InventoryRootOperations(context, self.config)
        host = InventoryRootOperations(self.context, self.config); self.addCleanup(host.close)
        original = host.context, host.backend
        try:
            for backend in (Duck(), fake):
                host.backend = backend
                host.context = SimpleNamespace(backend=backend)
                with self.assertRaises(BackendError): host.verify_source()
                with self.assertRaises(BackendError): host._verify()
        finally: host.context, host.backend = original
        self.assertEqual(touched, [])

    def test_document_wrapper_refuses_duck_source_callback(self):
        touched = []
        class Duck:
            def inventory_source(self, **kwargs): touched.append('called'); return self.config
        wrapper = object.__new__(DocumentView)
        wrapper._view = Duck()
        with self.assertRaises(BackendError): wrapper.inventory_source()
        self.assertEqual(touched, [])

    def test_report_constructor_preserves_valid_other_source_category(self):
        files = dict(self.files); files[DOC_FORM] += b'\n'
        other = import_inventory_application(files, inventory_runtime=PROFILE)
        with self.assertRaises(BackendError) as caught: InventoryReports(self.context, other)
        self.assertEqual(caught.exception.code, 'schema_changed')
        self.assertIsNone(self.backend._active)

    def test_report_constructor_expected_failure_never_calls_hooks(self):
        touched = []
        class Hostile:
            def __eq__(self, other): touched.append('eq'); return True
            def __iter__(self): touched.append('iter'); return iter(())
        for expected in (replace(self.config, files=Hostile()),
                         replace(self.config, files=((Hostile(), b'x'),)),
                         replace(self.config, source_digest=Hostile())):
            with self.assertRaises(BackendError) as caught: InventoryReports(self.context, expected)
            self.assertEqual(caught.exception.code, 'unsupported')
        self.assertEqual(touched, [])

    def test_report_constructor_does_not_relabel_current_source_failure(self):
        self.sql('UPDATE configuration_file SET content=? WHERE path=?', (b'bad', DOC_FORM))
        with self.assertRaises(BackendError) as caught: InventoryReports(self.context, self.config)
        self.assertEqual(caught.exception.code, 'integrity')
        self.assertIsNone(self.backend._active)
