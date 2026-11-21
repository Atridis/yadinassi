"""Dry-run-only configuration evolution safety checks."""
from contextlib import closing
import sqlite3
import tempfile
import unittest
from pathlib import Path
from uuid import uuid4
from yadinassi.configuration.configuration_xml import import_configuration
from yadinassi.db.sqlite.sqlite_catalog import SQLiteCatalogBackend
from yadinassi.db.sqlite.sqlite_migration_plan import prepare as transaction_plan, apply as upgrade
from yadinassi.db.sqlite.sqlite_configuration_update import prepare
from yadinassi.db.catalog.catalog_backend import BackendError
from sqlite_catalog_fixture import configuration_files
from test_configuration_evolution import append_field


class ConfigurationUpdatePlanningTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / 'database.sqlite'
        self.files = configuration_files()
        self.source = import_configuration(self.files)
        self.target = import_configuration(append_field(self.files))
        backend = SQLiteCatalogBackend.create(self.path, self.source)
        backend.close()
        plan = transaction_plan(self.path, maintenance=True)
        upgrade(self.path, plan, maintenance=True)

    def test_deterministic_pinned_dry_run_does_not_write(self):
        before = self.path.read_bytes()
        operation = uuid4()
        first = prepare(self.path, self.target, maintenance=True, operation_id=operation)
        second = prepare(self.path, self.target, maintenance=True, operation_id=operation)
        self.assertEqual(first, second)
        self.assertEqual(self.path.read_bytes(), before)
        self.assertEqual(first.source_generation, 1)
        self.assertEqual(first.base_profile, 2)
        self.assertEqual(len(first.appended_fields), 1)

    def test_requires_maintenance(self):
        with self.assertRaises(BackendError): prepare(self.path, self.target)

    def test_preserves_existing_mapping(self):
        backend = SQLiteCatalogBackend(self.path, read_only=True)
        try:
            tables = dict(backend._layout._tables); fields = dict(backend._layout._fields)
        finally: backend.close()
        plan = prepare(self.path, self.target, maintenance=True)
        self.assertTrue(set((str(k),v) for k,v in tables.items()) <= set(plan.table_mapping))
        self.assertTrue(set((str(c),str(f),v) for (c,f),v in fields.items()) <= set(plan.field_mapping))

    def test_rejects_non_v11_source(self):
        path = Path(self.directory.name) / 'legacy.sqlite'
        backend = SQLiteCatalogBackend.create(path, self.source); backend.close()
        with self.assertRaises(BackendError): prepare(path, self.target, maintenance=True)

    def test_operation_identity_changes_binding(self):
        first = prepare(self.path, self.target, maintenance=True)
        second = prepare(self.path, self.target, maintenance=True)
        self.assertNotEqual(first.plan_hash, second.plan_hash)
        self.assertEqual(first.source_hash, second.source_hash)


class ConfigurationUpdateApplyTests(ConfigurationUpdatePlanningTests):
    def plan(self): return prepare(self.path,self.target,maintenance=True)

    def test_apply_backfill_source_and_generation(self):
        from yadinassi.db.catalog.catalog_backend import CatalogDraft, CatalogKey
        from yadinassi.db.sqlite.sqlite_configuration_update import apply, resolve
        backend=SQLiteCatalogBackend(self.path)
        key=CatalogKey(backend.database_id,self.source.catalogs[0].identity,uuid4())
        draft=CatalogDraft(key,'saved','saved',False,())
        with closing(backend.begin_write(uuid4())) as tx:
            tx.create(draft);revision,=tx.commit()
        backend.close()
        plan=self.plan();apply(self.path,plan,maintenance=True)
        self.assertEqual(resolve(self.path,plan,maintenance=True),'committed')
        backend=SQLiteCatalogBackend(self.path)
        try:
            self.assertEqual((backend.format_version,backend.storage_version,backend.configuration_generation),(12,2,2))
            self.assertIsNone(backend._enum_domain)  # Legacy maintenance grants no enum domain.
            self.assertEqual(backend.export_configuration(),{f.path:f.content for f in self.target.files})
            with closing(backend.begin_read()) as view:
                record=view.read_catalog(key)
                self.assertEqual((record.code,record.description,record.values),('saved','saved',(False,)))
                self.assertEqual(record.revision.token,revision.token)
                self.assertEqual(record.revision.configuration_generation,2)
        finally:backend.close()

    def test_update_adds_only_configuration_metadata_table(self):
        from yadinassi.db.sqlite.sqlite_configuration_update import apply

        def table_names():
            with closing(sqlite3.connect(self.path)) as db:
                return {name for name, in db.execute("SELECT name FROM sqlite_schema WHERE type='table'")}

        old=table_names()
        apply(self.path,self.plan(),maintenance=True)
        self.assertEqual(table_names(),old|{'configuration_update'})

    def test_stale_backend_refuses_after_update(self):
        from yadinassi.db.sqlite.sqlite_configuration_update import apply
        old=SQLiteCatalogBackend(self.path)
        try:
            apply(self.path,self.plan(),maintenance=True)
            with self.assertRaises(BackendError):old.begin_read()
        finally:old.close()

    def test_changed_database_rejects_plan_without_ddl(self):
        from yadinassi.db.catalog.catalog_backend import CatalogDraft, CatalogKey
        from yadinassi.db.sqlite.sqlite_configuration_update import apply
        plan=self.plan();backend=SQLiteCatalogBackend(self.path)
        tx=backend.begin_write(uuid4());tx.create(CatalogDraft(CatalogKey(backend.database_id,self.source.catalogs[0].identity,uuid4()),'later','',False,()));tx.commit();backend.close()
        before=self.path.read_bytes()
        with self.assertRaises(BackendError):apply(self.path,plan,maintenance=True)
        self.assertEqual(self.path.read_bytes(),before)

    def test_precommit_failure_rolls_back_exactly(self):
        from unittest.mock import patch
        from yadinassi.db.sqlite.sqlite_configuration_update import apply
        plan=self.plan();before=self.path.read_bytes()
        with patch('yadinassi.db.sqlite.sqlite_configuration_history.validate',side_effect=BackendError('integrity')):
            with self.assertRaises(BackendError):apply(self.path,plan,maintenance=True)
        self.assertEqual(self.path.read_bytes(),before)

    def test_update_cannot_be_replayed_or_chained_implicitly(self):
        from yadinassi.db.sqlite.sqlite_configuration_update import apply
        plan=self.plan();apply(self.path,plan,maintenance=True)
        with self.assertRaises(BackendError):apply(self.path,plan,maintenance=True)

    def test_old_unit_record_keeps_value_and_gets_default_after_schema_addition(self):
        from yadinassi.db.catalog.catalog_backend import CatalogDraft, CatalogKey
        from yadinassi.db.transaction_backend import TransactionRequest
        from yadinassi.db.sqlite.sqlite_configuration_update import apply
        backend=SQLiteCatalogBackend(self.path);operation=uuid4()
        draft=CatalogDraft(CatalogKey(backend.database_id,self.source.catalogs[0].identity,uuid4()),'unit','',False,())
        request=TransactionRequest('catalog_create',draft)
        with backend.begin_unit_of_work(operation) as tx:
            tx.stage(request);outcome,=tx.commit()
        backend.close();apply(self.path,self.plan(),maintenance=True)
        backend=SQLiteCatalogBackend(self.path)
        try:
            with closing(backend.begin_read()) as view:
                record=view.read_catalog(draft.key)
                self.assertEqual((record.code,record.values),('unit',(False,)))
                self.assertEqual(record.revision.token,outcome.result.revision.token)
                self.assertEqual(record.revision.configuration_generation,2)
        finally:backend.close()

    def test_new_generation_writes_are_visible_on_read(self):
        from yadinassi.db.catalog.catalog_backend import CatalogDraft, CatalogKey
        from yadinassi.db.sqlite.sqlite_configuration_update import apply
        apply(self.path,self.plan(),maintenance=True)
        backend=SQLiteCatalogBackend(self.path);operation=uuid4()
        draft=CatalogDraft(CatalogKey(backend.database_id,self.source.catalogs[0].identity,uuid4()),'new','',False,(True,))
        try:
            with closing(backend.begin_write(operation)) as tx:
                tx.create(draft);revision,=tx.commit()
            with closing(backend.begin_read()) as view:
                record=view.read_catalog(draft.key)
                self.assertEqual((record.code,record.values),('new',(True,)))
                self.assertEqual(record.revision,revision)
                self.assertEqual(record.revision.configuration_generation,2)
        finally:backend.close()

    def test_wrong_operation_cannot_resolve_update(self):
        from dataclasses import replace
        from yadinassi.db.sqlite.sqlite_configuration_update import apply,resolve
        plan=self.plan();apply(self.path,plan,maintenance=True)
        self.assertEqual(resolve(self.path,replace(plan,operation_id=uuid4()),maintenance=True),'uncertain')
