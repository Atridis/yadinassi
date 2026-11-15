"""Main-demo format16 creation/admission, without UI or native parity claims."""
from pathlib import Path
from dataclasses import replace
import sqlite3
import tempfile
import unittest
from yadinassi.configuration_main_demo import import_main_demo_configuration, PROFILE
from yadinassi.sqlite_inventory_enum_profile import create_main_demo, create, read_source
from yadinassi.catalog_backend import BackendError
from yadinassi.sqlite_catalog import register_query_collations

ROOT=Path(__file__).resolve().parents[1]

class MainDemoStorageAdmissionTests(unittest.TestCase):
    def config(self):
        root=ROOT/'examples/demo'
        return import_main_demo_configuration({p.relative_to(root).as_posix():p.read_bytes()
            for p in root.rglob('*') if p.is_file()},profile=PROFILE)

    def open(self,path):
        db=sqlite3.connect(path,isolation_level=None);register_query_collations(db)
        self.addCleanup(db.close);return db

    def test_create_reopen_full_source_and_section_tables_without_seed(self):
        config=self.config()
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'main.sqlite'
            self.assertEqual(create_main_demo(str,path,config),str(path.resolve()))
            db=self.open(path);fresh,domain,_=read_source(db)
            self.assertEqual(fresh,config)
            self.assertEqual(db.execute('PRAGMA user_version').fetchone(),(16,))
            self.assertEqual(db.execute('SELECT profile FROM inventory_profile').fetchone(),(PROFILE,))
            from yadinassi.sqlite_main_demo_profile import preflight_catalog_sections
            layout,sections=preflight_catalog_sections(config,domain)
            for cat in config.catalogs:
                self.assertEqual(db.execute('SELECT COUNT(*) FROM "'+layout.table_name(cat.identity)+'"').fetchone()[0],0)
                for sec in cat.tabular_sections:
                    self.assertEqual(db.execute('SELECT COUNT(*) FROM "'+sections.table_name(cat.identity,sec.identity)+'"').fetchone()[0],0)
            db.close()

    def test_forged_configuration_fails_before_file_allocation(self):
        config=replace(self.config(),catalog_handlers=())
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'main.sqlite'
            with self.assertRaises(BackendError):create_main_demo(str,path,config)
            self.assertFalse(path.exists())

    def test_old_core_creator_does_not_accept_main_demo(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'main.sqlite'
            with self.assertRaises(BackendError):create(str,path,self.config())
            self.assertFalse(path.exists())

    def test_marker_change_cannot_reinterpret_source(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'main.sqlite';create_main_demo(str,path,self.config());db=self.open(path)
            db.execute("UPDATE inventory_profile SET profile='inventory-enum-v1'")
            with self.assertRaises(BackendError):read_source(db)
            db.close()

    def test_missing_section_table_rejected_on_reopen(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'main.sqlite';create_main_demo(str,path,self.config());db=self.open(path)
            table=db.execute('SELECT physical_name FROM catalog_section_storage_map LIMIT 1').fetchone()[0]
            db.execute('DROP TABLE "'+table+'"')
            with self.assertRaises(BackendError):read_source(db)
            db.close()

    def test_source_blob_drift_rejected_even_with_rehashed_row(self):
        from hashlib import sha256
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'main.sqlite';create_main_demo(str,path,self.config());db=self.open(path)
            raw=db.execute("SELECT content FROM configuration_file WHERE path='Configuration.xml'").fetchone()[0]+b'\n'
            db.execute("UPDATE configuration_file SET content=?,sha256=? WHERE path='Configuration.xml'",(raw,sha256(raw).hexdigest()))
            with self.assertRaises(BackendError):read_source(db)
            db.close()
