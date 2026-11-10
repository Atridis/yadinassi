"""Document grant cannot migrate or export stale persisted metadata."""
from contextlib import closing
from dataclasses import replace
from pathlib import Path
import hashlib
import json
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from document_form_fixture import sources
from test_document_configuration_xml import document_files
from yadinassi.catalog_backend import BackendError
from yadinassi.configuration_xml import import_configuration
from yadinassi.sqlite_catalog import SQLiteCatalogBackend
from yadinassi.sqlite_migration_plan import prepare, apply


class DocumentAdmissionBoundaryTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup)
        self.path=Path(temp.name)/'forms.sqlite';self.files=sources()
        self.backend=SQLiteCatalogBackend.create_document_forms(self.path,self.files)
        self.addCleanup(self.backend.close)

    def digest(self):return hashlib.sha256(self.path.read_bytes()).hexdigest()

    def reopen(self):
        with closing(SQLiteCatalogBackend(self.path)) as backend:
            self.assertEqual(backend.format_version,7)
            self.assertEqual(backend.export_configuration(),self.files)

    def test_prepare_refuses_grant_without_file_mutation(self):
        before=self.digest()
        with self.assertRaises(BackendError) as caught:prepare(self.path,maintenance=True)
        self.assertEqual(caught.exception.code,'unsupported')
        self.assertEqual(self.digest(),before);self.reopen()

    def test_apply_valid_plan_refuses_grant_before_writer_or_mutation(self):
        ordinary=self.path.with_name('ordinary.sqlite')
        SQLiteCatalogBackend.create(ordinary,import_configuration(document_files(catalogs=False,fields=False))).close()
        plan=prepare(ordinary,maintenance=True)
        before=self.digest()
        with patch('yadinassi.sqlite_migration_plan._open',side_effect=AssertionError('migration file must not open')):
            with self.assertRaises(BackendError) as caught:apply(self.path,plan,maintenance=True)
        self.assertEqual(caught.exception.code,'unsupported')
        self.assertEqual(self.digest(),before);self.reopen()

    def test_ordinary_document_v7_migration_still_supported(self):
        ordinary=self.path.with_name('ordinary.sqlite')
        SQLiteCatalogBackend.create(ordinary,import_configuration(document_files(catalogs=False,fields=False))).close()
        plan=prepare(ordinary,maintenance=True);apply(ordinary,plan,maintenance=True)
        with closing(SQLiteCatalogBackend(ordinary)) as backend:self.assertEqual(backend.format_version,11)

    def test_live_valid_persisted_schema_tamper_rejects_export_and_reopen(self):
        with closing(sqlite3.connect(self.path)) as db:
            identity,definition=db.execute('SELECT identity,definition FROM document_schema').fetchone()
            from yadinassi.sqlite_documents import schema_data
            definition=schema_data(replace(self.backend._document_schemas[0],number_length=8))
            db.execute('UPDATE document_schema SET definition=? WHERE identity=?',(json.dumps(definition,ensure_ascii=False,separators=(',',':')),identity));db.commit()
        with self.assertRaises(BackendError):self.backend.export_configuration()
        with self.assertRaises(BackendError):SQLiteCatalogBackend(self.path)

    def test_live_sequence_metadata_tamper_rejects_export(self):
        with closing(sqlite3.connect(self.path)) as db:
            db.execute('DELETE FROM document_sequence');db.commit()
        with self.assertRaises(BackendError):self.backend.export_configuration()

    def test_live_layout_ddl_tamper_rejects_export(self):
        with closing(sqlite3.connect(self.path)) as db:
            db.execute('ALTER TABLE document_record ADD COLUMN injected TEXT');db.commit()
        with self.assertRaises(BackendError):self.backend.export_configuration()
