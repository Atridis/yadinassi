"""Mixed source, data owners and live source pins share one explicit grant."""
from contextlib import closing
from dataclasses import replace
from hashlib import sha256
from pathlib import Path
import json
import sqlite3
import tempfile
import unittest

from business_configuration_fixture import sources
from test_configuration_catalog_profile import CATALOG, FORM
from yadinassi.catalog_backend import BackendError
from yadinassi.catalog_object_preparation import CatalogWriteRefused
from yadinassi.catalogs import BSLCatalogs
from yadinassi.configuration_business_profile import import_business_configuration
from yadinassi.configuration_runtime import ConfigurationApplication
from yadinassi.database_context import SQLiteDBContext
from yadinassi.metadata import BSLCatalogMetadataCollection
from yadinassi.sqlite_catalog import SQLiteCatalogBackend
from yadinassi.sqlite_migration_plan import prepare


class BusinessAdmissionTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(); self.addCleanup(temporary.cleanup)
        self.path = Path(temporary.name) / 'business.sqlite'
        self.files = sources()
        self.backend = SQLiteCatalogBackend.create_business_application(self.path, self.files)
        self.addCleanup(self.backend.close)

    def mutate(self, sql, args=()):
        with closing(sqlite3.connect(self.path)) as db:
            db.execute(sql, args); db.commit()

    def object(self):
        context = SQLiteDBContext(self.path); self.addCleanup(context.close)
        return BSLCatalogs(BSLCatalogMetadataCollection(context), context).get_index('Items').create_item()

    def test_exact_mixed_grant_reopens_and_exports(self):
        self.assertEqual(self.backend.format_version, 7)
        self.assertEqual(self.backend.active_form_catalogs(), ())
        self.assertEqual(self.backend.read_form_source(CATALOG).identity.form_id, FORM)
        with closing(SQLiteCatalogBackend(self.path)) as reopened:
            self.assertEqual(reopened.export_configuration(), self.files)
            with closing(reopened.begin_read()) as view: self.assertEqual(len(view.catalogs()), 1)
            with closing(reopened.begin_document_read()) as view: self.assertEqual(len(view.documents()), 1)

    def test_regular_create_cannot_acquire_grant(self):
        target = self.path.with_name('forged.sqlite')
        with self.assertRaises(BackendError): SQLiteCatalogBackend.create(target, import_business_configuration(self.files))
        self.assertFalse(target.exists())

    def test_catalog_before_write_normalizes(self):
        obj = self.object(); obj.set_member('Code', '1'); obj.set_member('Description', '  normalized  ')
        obj.write(); ref = obj.get_member('Ref')
        self.assertEqual(ref.get_object(ref).get_member('Description'), 'normalized')

    def test_catalog_before_write_refusal_is_not_bypassed(self):
        obj = self.object(); obj.set_member('Code', '1'); obj.set_member('Description', 'blocked')
        with self.assertRaises(CatalogWriteRefused): obj.write()
        self.assertTrue(obj.is_new())

    def test_source_rehash_rejected_by_all_live_owners(self):
        path = 'CommonModules/Tools/Ext/Module.bsl'; content = self.files[path] + b'\n// changed'
        self.mutate('UPDATE configuration_file SET content=?,sha256=? WHERE path=?', (content, sha256(content).hexdigest(), path))
        for read in (self.backend.export_configuration, self.backend.begin_read, self.backend.begin_document_read):
            with self.subTest(read=read.__name__), self.assertRaises(BackendError): read()
        with self.assertRaises(BackendError): SQLiteCatalogBackend(self.path)

    def test_document_metadata_tamper_rejected_on_export(self):
        from yadinassi.sqlite_documents import schema_data
        schema = self.backend._document_schemas[0]
        definition = json.dumps(schema_data(replace(schema, number_length=8)), ensure_ascii=False, separators=(',', ':'))
        self.mutate('UPDATE document_schema SET definition=? WHERE identity=?', (definition, str(schema.identity)))
        with self.assertRaises(BackendError): self.backend.export_configuration()

    def test_catalog_metadata_tamper_rejected_on_export(self):
        self.mutate("UPDATE catalog_schema SET name='Altered'")
        with self.assertRaises(BackendError): self.backend.export_configuration()

    def test_layout_tamper_rejected_on_export(self):
        self.mutate('ALTER TABLE document_record ADD COLUMN injected TEXT')
        with self.assertRaises(BackendError): self.backend.export_configuration()

    def test_application_identity_tamper_rejected(self):
        self.mutate('PRAGMA application_id=0')
        with self.assertRaises(BackendError): self.backend.export_configuration()

    def test_document_sequence_tamper_rejected(self):
        self.mutate('DELETE FROM document_sequence')
        with self.assertRaises(BackendError): self.backend.export_configuration()

    def test_migration_cannot_convert_grant(self):
        before = sha256(self.path.read_bytes()).hexdigest()
        with self.assertRaises(BackendError): prepare(self.path, maintenance=True)
        self.assertEqual(sha256(self.path.read_bytes()).hexdigest(), before)

    def test_server_runtime_requires_exact_database_source(self):
        context = SQLiteDBContext(self.path); self.addCleanup(context.close)
        app = ConfigurationApplication.from_database(context, side='server')
        app.start(); app.close()
        changed = dict(self.files); changed['Ext/ManagedApplicationModule.bsl'] += b'\n// change'
        with self.assertRaises(ValueError):
            ConfigurationApplication(import_business_configuration(changed), side='server', database_context=context)

    def test_forged_runtime_cannot_leave_partly_created_file(self):
        from yadinassi.configuration_business_profile import BUSINESS_PROFILE
        canonical = import_business_configuration(self.files)
        forged = replace(canonical, module_runtime=None, common_modules=(), modules=())
        target = self.path.with_name('forged-runtime.sqlite')
        with self.assertRaises(BackendError):
            SQLiteCatalogBackend.create(target, forged, _source_profile=BUSINESS_PROFILE)
        self.assertFalse(target.exists())
