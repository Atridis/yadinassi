"""V4 local numbering and v5 inert source profiles must stay separate."""
from contextlib import closing
from dataclasses import replace
from pathlib import Path
import sqlite3
import tempfile
import unittest
from uuid import uuid4

from yadinassi.catalog_backend import BackendError, CatalogDraft, CatalogKey
from yadinassi.configuration_xml import import_inert_configuration
from yadinassi.sqlite_catalog import SQLiteCatalogBackend
from test_catalog_atomic_numbering import numbered_configuration
from test_inert_configuration_sources import sources, CATALOG


class CatalogStorageProfileTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)

    def path(self, name):
        return Path(self.temp.name)/(name+'.sqlite')

    def test_numbered_scalar_v4_has_outcomes_but_no_inert_source_authority(self):
        config = numbered_configuration()
        config = replace(config, catalogs=(config.catalogs[1],))
        backend = SQLiteCatalogBackend.create(self.path('numbered'), config)
        try:
            self.assertEqual(backend.storage_version, 4)
            self.assertTrue(backend.capabilities().catalog_write_outcomes)
            with self.assertRaisesRegex(BackendError, 'unsupported'):
                backend.read_form_source(config.catalogs[0].identity)
            draft = CatalogDraft(CatalogKey(backend.database_id,config.catalogs[0].identity,uuid4()), '', 'owned', False, (), auto_number=True)
            operation = uuid4()
            tx = backend.begin_write(operation)
            try:
                tx.create(draft)
                outcome = tx.commit_outcomes()[0]
            finally: tx.close()
            self.assertEqual(outcome.code, '01')
            self.assertEqual(backend.resolve_write_outcome(operation,draft),outcome)
        finally: backend.close()

    def test_inert_v5_has_no_sequence_section_registry_or_record_outcomes(self):
        path = self.path('inert')
        backend = SQLiteCatalogBackend.create_inert(path, sources())
        try:
            self.assertEqual(backend.storage_version, 5)
            caps = backend.capabilities()
            self.assertFalse(caps.catalog_write_outcomes)
            self.assertFalse(caps.catalog_tabular_sections)
            self.assertEqual(backend.read_form_source(CATALOG).catalog_name, 'Items')
            with self.assertRaisesRegex(BackendError, 'unsupported'):
                backend.resolve_write_outcome(uuid4(), None)
            with closing(sqlite3.connect(path)) as db:
                tables = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            self.assertNotIn('catalog_sequence',tables)
            self.assertNotIn('catalog_section_storage_map',tables)
            self.assertNotIn('catalog_section_field_storage_map',tables)
        finally: backend.close()

    def test_numbered_v4_cannot_be_retagged_as_inert_v5(self):
        path = self.path('numbered')
        backend = SQLiteCatalogBackend.create(path, numbered_configuration())
        backend.close()
        with closing(sqlite3.connect(path)) as db, db: db.execute('PRAGMA user_version=5')
        with self.assertRaises(BackendError): SQLiteCatalogBackend(path)

    def test_inert_v5_cannot_be_retagged_as_numbered_v4(self):
        path = self.path('inert')
        backend = SQLiteCatalogBackend.create_inert(path,sources())
        backend.close()
        with closing(sqlite3.connect(path)) as db, db: db.execute('PRAGMA user_version=4')
        with self.assertRaises(BackendError): SQLiteCatalogBackend(path)

    def test_inert_identity_stubs_cannot_request_number_allocation(self):
        config = import_inert_configuration(sources())
        config = replace(config, catalogs=(replace(config.catalogs[0],code_length=2,numbering='decimal_v1'),))
        path = self.path('forged')
        with self.assertRaises(BackendError): SQLiteCatalogBackend.create(path,config,activate=False)
        self.assertFalse(path.exists())
