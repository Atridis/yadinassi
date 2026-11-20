"""Format16 metadata proof is connection-local and separate from row proofs."""
from contextlib import closing
from dataclasses import replace
from hashlib import sha256
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch
from uuid import uuid4
from sqlite_test_templates import copy_main_demo

from test_main_demo_configuration import source
from yadinassi.db.sqlite.sqlite_catalog import SQLiteCatalogBackend
from yadinassi.db.sqlite.sqlite_read_handles import ReadHandle
from yadinassi.db.catalog.catalog_backend import BackendError

class AdmissionEpochTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(); self.addCleanup(tmp.cleanup)
        self.path = Path(tmp.name)/'main.sqlite'
        copy_main_demo(self.path)
        self.backend = SQLiteCatalogBackend(self.path); self.addCleanup(self.backend.close)

    def read(self):
        with closing(self.backend.begin_read()) as view:
            return view.catalogs()

    def mutate(self, sql, args=()):
        with closing(sqlite3.connect(self.path)) as db:
            db.execute(sql, args); db.commit()

    def test_warm_reads_skip_full_source_admission_and_keep_data_proofs_separate(self):
        from yadinassi.db.sqlite.sqlite_inventory_enum_profile import read_source
        with patch('yadinassi.db.sqlite.sqlite_inventory_enum_profile.read_source', wraps=read_source) as read:
            self.read(); self.assertEqual(read.call_count, 1)
            for _ in range(3): self.read()
            self.assertEqual(read.call_count, 1)
        self.assertIsNotNone(self.backend._read_handle.admission)
        self.assertEqual(self.backend._read_handle.proofs, {})

    def test_rehashed_source_change_same_generation_is_not_new_authority(self):
        self.read()
        raw = source()['Configuration.xml'] + b'\n'
        self.mutate("UPDATE configuration_file SET content=?, sha256=? WHERE path='Configuration.xml'", (raw, sha256(raw).hexdigest()))
        with self.assertRaises(BackendError): self.read()
        self.assertIsNone(self.backend._read_handle)

    def test_external_metadata_mutation_revalidates(self):
        self.read(); self.mutate("UPDATE catalog_schema SET name='changed' WHERE identity=(SELECT identity FROM catalog_schema LIMIT 1)")
        with self.assertRaises(BackendError): self.read()

    def test_external_valid_data_commit_revalidates(self):
        self.read()
        self.mutate('UPDATE catalog_sequence SET next_value=next_value+1')
        with patch.object(self.backend, '_validate_transaction_admission', wraps=self.backend._validate_transaction_admission) as validate:
            self.read(); self.assertEqual(validate.call_count, 1)

    def test_own_rolled_back_write_invalidates(self):
        self.read(); handle = self.backend._read_handle
        with closing(self.backend.begin_write(uuid4())):
            self.assertIsNone(handle.admission)
        with patch.object(self.backend, '_validate_transaction_admission', wraps=self.backend._validate_transaction_admission) as validate:
            self.read(); self.assertEqual(validate.call_count, 1)

    def test_local_configuration_drift_is_not_hidden(self):
        self.read()
        self.backend.accumulation_configuration = replace(self.backend.accumulation_configuration, catalog_handlers=())
        with self.assertRaisesRegex(BackendError, 'schema_changed'): self.read()

    def test_after_rollback_commit_cannot_relabel_admission(self):
        original = ReadHandle.complete
        def complete(handle, proofs):
            self.mutate("UPDATE configuration_file SET content=x'00' WHERE path='Configuration.xml'")
            return original(handle, proofs)
        with patch.object(ReadHandle, 'complete', complete): self.read()
        with self.assertRaises(BackendError): self.read()

    def test_new_connection_cold(self):
        self.read(); self.backend._close_idle_read_handle()
        with patch.object(self.backend, '_validate_transaction_admission', wraps=self.backend._validate_transaction_admission) as validate:
            self.read(); self.assertEqual(validate.call_count, 1)

    def test_failed_full_admission_not_published(self):
        with patch.object(self.backend, '_validate_transaction_admission', side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt): self.read()
        self.assertIsNone(self.backend._read_handle)
        self.read()

    def test_snapshot_is_pinned_before_epoch(self):
        self.read(); original = ReadHandle.pin
        def pin(handle):
            with closing(sqlite3.connect(self.path, timeout=0)) as db:
                with self.assertRaises(sqlite3.OperationalError):
                    db.execute('UPDATE database_info SET generation=generation'); db.commit()
            return original(handle)
        with patch.object(ReadHandle, 'pin', pin): self.read()

    def test_external_ddl_commit_rejected(self):
        self.read(); self.mutate('CREATE TABLE injected(x)')
        with self.assertRaises(BackendError): self.read()

    def test_mutated_frozen_configuration_does_not_alias_descriptor(self):
        self.read()
        config = self.backend.accumulation_configuration
        old = config.catalog_handlers
        try:
            object.__setattr__(config, 'catalog_handlers', ())
            with self.assertRaisesRegex(BackendError, 'schema_changed'): self.read()
        finally:
            object.__setattr__(config, 'catalog_handlers', old)

    def test_source_snapshot_reused_only_for_exact_owned_connection(self):
        from yadinassi.db.sqlite.sqlite_inventory_enum_profile import read_source
        with closing(self.backend.begin_read()) as view:
            with patch('yadinassi.db.sqlite.sqlite_inventory_enum_profile.read_source', wraps=read_source) as read:
                self.assertIs(self.backend._main_demo_source_snapshot(view._connection), self.backend.accumulation_configuration)
                self.assertEqual(read.call_count, 0)
                with closing(self.backend._connect()) as other:
                    other.execute('BEGIN')
                    self.backend._main_demo_source_snapshot(other)
                    self.assertEqual(read.call_count, 1)
                    other.execute('ROLLBACK')

    def test_mutated_live_descriptor_fields_detected_inside_same_view(self):
        with closing(self.backend.begin_read()) as view:
            old = self.backend.accumulation_configuration
            self.backend.accumulation_configuration = replace(old, catalog_handlers=())
            try:
                with self.assertRaisesRegex(BackendError, 'schema_changed'):
                    self.backend._main_demo_source_snapshot(view._connection)
            finally:
                self.backend.accumulation_configuration = old

    def test_separate_backends_do_not_share_admission(self):
        self.read()
        with closing(SQLiteCatalogBackend(self.path)) as other:
            self.assertIsNone(other._read_handle)
            with patch.object(other, '_validate_transaction_admission', wraps=other._validate_transaction_admission) as validate:
                with closing(other.begin_read()): pass
                self.assertEqual(validate.call_count, 1)

    def test_failed_rollback_never_retains_admission(self):
        from test_sqlite_catalog_admission_cleanup import AdmissionFaultConnection
        self.read(); view = self.backend.begin_read()
        proxy = AdmissionFaultConnection(view._connection,
            rollback_error=sqlite3.OperationalError('rollback'),
            close_error=sqlite3.OperationalError('close'))
        view._connection = proxy; handle = self.backend._read_handle
        handle.connection = proxy
        with self.assertRaises(BackendError): view.close()
        self.assertIsNone(handle.admission)
        self.assertIsNone(handle._pending_admission)
        proxy.disable_faults(); view.close()

    def test_changed_journal_mode_not_supported(self):
        self.read()
        self.mutate('PRAGMA journal_mode=WAL')
        with self.assertRaisesRegex(BackendError, 'unsupported'): self.read()

    def test_nested_frozen_schema_mutation_does_not_alias_proof(self):
        self.read(); schema = self.backend._schemas[0]; old = schema.name
        try:
            object.__setattr__(schema, 'name', 'changed')
            with self.assertRaisesRegex(BackendError, 'schema_changed'): self.read()
        finally:
            object.__setattr__(schema, 'name', old)

    def test_layout_dictionary_drift_rejected(self):
        self.read(); tables = self.backend._layout._tables
        key = next(iter(tables)); old = tables[key]
        try:
            tables[key] = 'injected'
            with self.assertRaisesRegex(BackendError, 'schema_changed'): self.read()
        finally:
            tables[key] = old

    def test_reset_schema_cookie_does_not_hide_foreign_ddl(self):
        self.read()
        with closing(sqlite3.connect(self.path)) as db:
            version = db.execute('PRAGMA schema_version').fetchone()[0]
            db.execute('CREATE TABLE injected(x)')
            db.execute('PRAGMA schema_version='+str(version)); db.commit()
        with self.assertRaises(BackendError): self.read()
