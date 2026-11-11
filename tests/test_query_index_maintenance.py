"""Closed optional indexes and explicit maintenance recovery contracts."""
import dataclasses
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from yadinassi.catalog_backend import BackendError
from yadinassi.configuration_xml import import_configuration
from yadinassi.sqlite_catalog import SQLiteCatalogBackend
from yadinassi.sqlite_query_indexes import (
    _index_name, admit_query_indexes, canonical_index_ddls,
    catalog_query_index_ddls, read_index_bundle_ddls, register_query_collations)
from yadinassi.sqlite_query_index_maintenance import prepare, apply, resolve, _fingerprint
from sqlite_catalog_fixture import configuration_files


class QueryIndexMaintenanceTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / 'database.sqlite'
        self.configuration = import_configuration(configuration_files())
        backend = SQLiteCatalogBackend.create(self.path, self.configuration)
        self.schemas, self.layout = backend._schemas, backend._layout
        self.storage, self.version = backend.storage_version, backend.format_version
        backend.close()
        # Model an existing pre-bundle database even when fresh creation opts in.
        with sqlite3.connect(self.path) as db:
            for (name,) in db.execute("SELECT name FROM sqlite_master WHERE type='index' AND sql IS NOT NULL").fetchall():
                db.execute('DROP INDEX "' + name + '"')
        self.bundle = read_index_bundle_ddls(self.storage, self.schemas, self.layout,
                                            format_version=self.version)

    def open(self):
        db = sqlite3.connect(self.path)
        register_query_collations(db)
        self.addCleanup(db.close)
        return db

    def test_baseline_function_is_unchanged(self):
        baseline = catalog_query_index_ddls(self.schemas, self.layout)
        self.assertEqual(len(baseline), len(self.schemas))
        self.assertTrue(all('(record_id COLLATE yadinassi_uuid_v1)' in ddl for ddl in baseline))
        self.assertEqual(self.bundle, canonical_index_ddls(self.bundle))
        self.assertFalse(any('UNIQUE' in ddl or 'NOCASE' in ddl for ddl in self.bundle))

    def test_admission_absent_and_complete_without_ddl(self):
        db = self.open(); before = db.total_changes
        self.assertFalse(admit_query_indexes(db, (), self.bundle))
        self.assertEqual(db.total_changes, before)
        for ddl in self.bundle: db.execute(ddl)
        self.assertTrue(admit_query_indexes(db, (), self.bundle))

    def test_partial_bundle_is_refused(self):
        db = self.open(); db.execute(self.bundle[0])
        with self.assertRaises(BackendError): admit_query_indexes(db, (), self.bundle)

    def test_unknown_index_is_refused(self):
        db = self.open(); db.execute('CREATE INDEX unknown_index ON database_info(generation)')
        with self.assertRaises(BackendError): admit_query_indexes(db, (), self.bundle)

    def test_modified_known_index_is_refused(self):
        db = self.open()
        for ddl in self.bundle: db.execute(ddl)
        ddl = self.bundle[-1]; db.execute('DROP INDEX "' + _index_name(ddl) + '"')
        db.execute(ddl.replace('yadinassi_casefold_v1', 'BINARY'))
        with self.assertRaises(BackendError): admit_query_indexes(db, (), self.bundle)

    def test_document_order_is_optional_only_on_bare_profile(self):
        bare = read_index_bundle_ddls(7, self.schemas, self.layout, format_version=7)
        profiled = read_index_bundle_ddls(7, self.schemas, self.layout, format_version=11)
        self.assertTrue(any('document_query_order_v1' in ddl for ddl in bare))
        self.assertFalse(any('document_query_order_v1' in ddl for ddl in profiled))
        self.assertTrue(any('document_query_number_casefold_v1' in ddl for ddl in profiled))

    def test_casefold_lookup_plan_uses_nonunique_index(self):
        db = self.open()
        for ddl in self.bundle: db.execute(ddl)
        table = self.layout.table_name(self.schemas[0].identity)
        rows = db.execute('EXPLAIN QUERY PLAN SELECT record_id FROM "' + table +
            '" WHERE code COLLATE yadinassi_casefold_v1=? ORDER BY record_id COLLATE yadinassi_uuid_v1,rowid', ('STRASSE',)).fetchall()
        self.assertTrue(any('SEARCH' in row[3] and 'query_exact_' in row[3] for row in rows))
        self.assertEqual(db.execute("SELECT 'Straße' = 'STRASSE' COLLATE yadinassi_casefold_v1").fetchone(), (1,))

    def test_prepare_is_deterministic_read_only(self):
        before = self.path.read_bytes()
        plan = prepare(self.path, maintenance=True)
        self.assertEqual(plan, prepare(self.path, maintenance=True))
        self.assertEqual(self.path.read_bytes(), before)
        self.assertEqual(resolve(self.path, plan, maintenance=True), 'not_committed')

    def test_maintenance_required(self):
        with self.assertRaises(BackendError): prepare(self.path)

    def test_apply_preserves_data_format_generation(self):
        plan = prepare(self.path, maintenance=True)
        apply(self.path, plan, maintenance=True)
        self.assertEqual(resolve(self.path, plan, maintenance=True), 'committed')
        db = self.open()
        self.assertEqual(db.execute('PRAGMA user_version').fetchone(), (plan.format_version,))
        self.assertEqual(_fingerprint(db, exclude=plan.additions), plan.source_hash)
        backend = SQLiteCatalogBackend(self.path, read_only=True)
        self.assertEqual(backend.configuration_generation, plan.configuration_generation)
        backend.close()
        with self.assertRaises(BackendError): apply(self.path, plan, maintenance=True)

    def test_stale_raw_data_refuses_apply(self):
        plan = prepare(self.path, maintenance=True)
        with sqlite3.connect(self.path) as db:
            db.execute('UPDATE database_info SET generation=generation+1')
        with self.assertRaises(BackendError): apply(self.path, plan, maintenance=True)
        self.assertEqual(resolve(self.path, plan, maintenance=True), 'uncertain')
        self.assertFalse(admit_query_indexes(self.open(), (), self.bundle))

    def test_forged_plan_is_refused(self):
        plan = prepare(self.path, maintenance=True)
        bad = dataclasses.replace(plan, additions=('CREATE INDEX evil ON database_info(generation)',))
        with self.assertRaises(BackendError): apply(self.path, bad, maintenance=True)

    def test_replaced_file_is_not_replayed(self):
        plan = prepare(self.path, maintenance=True)
        replacement = self.path.with_suffix('.replacement')
        replacement.write_bytes(self.path.read_bytes()); replacement.replace(self.path)
        with self.assertRaises(BackendError): apply(self.path, plan, maintenance=True)
        self.assertEqual(resolve(self.path, plan, maintenance=True), 'uncertain')

    def test_commit_ack_loss_resolves_without_replay(self):
        from yadinassi import sqlite_query_index_maintenance as maintenance
        plan = prepare(self.path, maintenance=True)
        original = maintenance._open
        class LostAck:
            def __init__(self, db): self.db = db
            def execute(self, sql, *args):
                result = self.db.execute(sql, *args)
                if sql == 'COMMIT': raise sqlite3.OperationalError('lost acknowledgement')
                return result
            def close(self): self.db.close()
        with patch.object(maintenance, '_open', side_effect=lambda *a, **k: LostAck(original(*a, **k))):
            with self.assertRaises(BackendError) as caught: apply(self.path, plan, maintenance=True)
        self.assertEqual(caught.exception.code, 'uncertain_commit')
        self.assertEqual(resolve(self.path, plan, maintenance=True), 'committed')

    def test_precommit_failure_rolls_back_complete_bundle(self):
        from yadinassi import sqlite_query_index_maintenance as maintenance
        plan = prepare(self.path, maintenance=True)
        original = maintenance._open
        class FailDDL:
            def __init__(self, db): self.db = db; self.count = 0
            def execute(self, sql, *args):
                if sql.startswith('CREATE INDEX'):
                    self.count += 1
                    if self.count == 2: raise sqlite3.OperationalError('injected')
                return self.db.execute(sql, *args)
            def close(self): self.db.close()
        with patch.object(maintenance, '_open', side_effect=lambda *a, **k: FailDDL(original(*a, **k))):
            with self.assertRaises(BackendError): apply(self.path, plan, maintenance=True)
        self.assertEqual(resolve(self.path, plan, maintenance=True), 'not_committed')

    def test_configuration_rebuild_preserves_optional_bundle(self):
        from yadinassi.sqlite_migration_plan import prepare as upgrade_plan, apply as upgrade
        from yadinassi.sqlite_configuration_update import prepare as update_plan, apply as update
        from yadinassi.sqlite_transaction_profile import profile_index_ddls
        from test_configuration_evolution import append_field
        upgrade(self.path, upgrade_plan(self.path, maintenance=True), maintenance=True)
        plan = prepare(self.path, maintenance=True)
        apply(self.path, plan, maintenance=True)
        target = import_configuration(append_field(configuration_files()))
        update(self.path, update_plan(self.path, target, maintenance=True), maintenance=True)
        backend = SQLiteCatalogBackend(self.path, read_only=True)
        try:
            view = backend.begin_read()
            try:
                self.assertTrue(admit_query_indexes(view._connection,
                    profile_index_ddls(backend.storage_version, backend._schemas, backend._layout),
                    read_index_bundle_ddls(backend.storage_version, backend._schemas, backend._layout,
                                          format_version=backend.format_version)))
            finally: view.close()
        finally: backend.close()

    def test_explicit_fresh_bundle_is_admitted_without_default_change(self):
        other=self.path.with_name('indexed.sqlite')
        backend=SQLiteCatalogBackend.create(other,self.configuration,query_indexes=True)
        try:
            self.assertTrue(backend._query_indexes)
            with self.assertRaises(BackendError):
                from yadinassi.sqlite_migration_plan import prepare as upgrade_plan
                upgrade_plan(other,maintenance=True)
        finally: backend.close()
        backend=SQLiteCatalogBackend(self.path,read_only=True)
        try: self.assertFalse(backend._query_indexes)
        finally: backend.close()
