"""Fresh-only posting admission, canonical source, and atomic host boundary."""
from contextlib import closing
from dataclasses import replace
from pathlib import Path
import sqlite3
import tempfile
import unittest
from uuid import uuid4
from yadinassi.catalog_backend import BackendError
from yadinassi.configuration_posting import import_posting_configuration,PROFILE
from yadinassi.sqlite_catalog import SQLiteCatalogBackend
from test_configuration_posting import source

class PostingProfileTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.path=Path(self.temp.name)/'posting.sqlite'
        self.config=import_posting_configuration(source(),posting_runtime=PROFILE)
    def create(self):
        b=SQLiteCatalogBackend.create_posting(self.path,self.config);self.addCleanup(b.close);return b
    def test_fresh_create_open_canonical(self):
        b=self.create()
        self.assertEqual((b.format_version,b.storage_version),(13,7))
        self.assertEqual(b.posting_configuration,self.config)
        with closing(SQLiteCatalogBackend(self.path)) as other:
            self.assertEqual(other.posting_configuration,self.config)
            self.assertEqual(other.database_id,b.database_id)
    def test_no_fake_migration_profile(self):
        self.create()
        with closing(sqlite3.connect(self.path)) as c:
            names={r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            self.assertNotIn('transaction_profile',names)
            self.assertNotIn('transaction_migration',names)
            self.assertIn('posting_profile',names)
    def test_original_source_bytes_preserved(self):
        self.create()
        with closing(sqlite3.connect(self.path)) as c:
            self.assertEqual(dict(c.execute('SELECT path,content FROM configuration_file')),dict(self.config.files))
    def test_existing_destination_never_overwritten(self):
        self.path.write_bytes(b'owned')
        with self.assertRaises(BackendError):self.create()
        self.assertEqual(self.path.read_bytes(),b'owned')
    def test_forged_configuration_rejected_before_allocation(self):
        with self.assertRaises(BackendError):
            SQLiteCatalogBackend.create_posting(self.path,replace(self.config,name='forged'))
        self.assertFalse(self.path.exists())
    def test_tampered_source_refused_on_open(self):
        self.create()
        with closing(sqlite3.connect(self.path)) as c:
            c.execute("UPDATE configuration_file SET content=x'00'");c.commit()
        with self.assertRaises(BackendError):SQLiteCatalogBackend(self.path)
    def test_tampered_source_refused_on_existing_backend_begin(self):
        b=self.create()
        with closing(sqlite3.connect(self.path)) as c:
            c.execute("UPDATE configuration_file SET sha256=?",('0'*64,));c.commit()
        with self.assertRaises(BackendError):b.begin_read()
    def test_unknown_table_refused(self):
        self.create()
        with closing(sqlite3.connect(self.path)) as c:c.execute('CREATE TABLE unknown(value)')
        with self.assertRaises(BackendError):SQLiteCatalogBackend(self.path)
    def test_generation_conversion_refused(self):
        self.create()
        with closing(sqlite3.connect(self.path)) as c:
            c.execute('UPDATE database_info SET generation=2');c.commit()
        with self.assertRaises(BackendError):SQLiteCatalogBackend(self.path)
    def test_migration_refused(self):
        self.create()
        from yadinassi.sqlite_migration_plan import prepare
        with self.assertRaises(BackendError):prepare(self.path,maintenance=True)
    def test_additive_update_refused(self):
        self.create()
        from yadinassi.sqlite_configuration_update import prepare
        with self.assertRaises(BackendError):prepare(self.path,self.config,maintenance=True)
    def test_empty_unit_of_work_can_rollback(self):
        b=self.create();unit=b.begin_unit_of_work(uuid4());unit.rollback()
        with closing(b.begin_read()) as view:self.assertEqual(view.database_id,b.database_id)
