"""Private storage mechanics, not main-demo source admission or runtime parity."""
from dataclasses import replace
from types import SimpleNamespace
from uuid import UUID
import sqlite3
import unittest
from unittest import mock
from yadinassi.catalog_backend import BackendError, CatalogSchema, FieldSchema, TabularSectionSchema
from yadinassi.enum_storage_values import EnumValueDomain
from yadinassi import sqlite_main_demo_profile as profile

class MainDemoStorageShapeTests(unittest.TestCase):
    def fixture(self):
        warehouse=CatalogSchema(UUID(int=1),'Склады',9,100,numbering='decimal_v1')
        field=FieldSchema(UUID(int=3),'Склад','catalog_ref',target_catalog_id=warehouse.identity)
        section=TabularSectionSchema(UUID(int=4),'Склады',(field,))
        products=CatalogSchema(UUID(int=2),'Номенклатура',9,150,tabular_sections=(section,),numbering='decimal_v1')
        return (warehouse,products),EnumValueDomain(UUID(int=9),())

    def test_reference_section_shape_builds_before_allocation(self):
        catalogs,domain=self.fixture()
        layout,sections=profile._catalog_shape(catalogs,domain)
        ddl=profile._storage().section_ddl(catalogs[1],catalogs[1].tabular_sections[0],layout,sections)
        self.assertIn('DEFERRABLE INITIALLY DEFERRED',ddl)
        self.assertIn('UNIQUE(owner_id,row_number)',ddl)

    def test_missing_reference_target_rejected(self):
        catalogs,domain=self.fixture()
        with self.assertRaises(BackendError):profile._catalog_shape((catalogs[1],),domain)

    def test_header_reference_target_also_validated(self):
        catalogs,domain=self.fixture()
        field=FieldSchema(UUID(int=8),'Other','catalog_ref',target_catalog_id=UUID(int=88))
        with self.assertRaises(BackendError):profile._catalog_shape((replace(catalogs[0],fields=(field,)),),domain)

    def test_duplicate_catalog_identity_rejected(self):
        catalogs,domain=self.fixture()
        with self.assertRaises(BackendError):profile._catalog_shape((catalogs[0],catalogs[0]),domain)

    def test_nonexact_container_and_domain_rejected(self):
        catalogs,domain=self.fixture()
        for cs,d in [(list(catalogs),domain),(catalogs,object())]:
            with self.assertRaises(BackendError):profile._catalog_shape(cs,d)

    def test_enum_section_cell_does_not_expand_grant(self):
        catalogs,domain=self.fixture()
        field=FieldSchema(UUID(int=5),'Enum','enum_ref',target_enum_id=UUID(int=6))
        section=replace(catalogs[1].tabular_sections[0],fields=(field,))
        with self.assertRaises(BackendError):profile._catalog_shape((catalogs[0],replace(catalogs[1],tabular_sections=(section,))),domain)

    def test_create_requires_outer_transaction(self):
        catalogs,domain=self.fixture();config=SimpleNamespace(catalogs=catalogs,enumerations=())
        with sqlite3.connect(':memory:',isolation_level=None) as db, mock.patch.object(profile,'_require_config'):
            with self.assertRaises(BackendError):profile.create_catalog_tables(db,config,domain)

    def test_create_and_exact_ddl_include_sections(self):
        catalogs,domain=self.fixture();config=SimpleNamespace(catalogs=catalogs,enumerations=())
        # Exact source admission is deliberately not mocked as proven here.
        with sqlite3.connect(':memory:',isolation_level=None) as db, mock.patch.object(profile,'_require_config'):
            profile._storage().register_query_collations(db)
            db.execute('BEGIN')
            for ddl in profile._base_ddls():db.execute(ddl)
            layout,sections=profile.create_catalog_tables(db,config,domain)
            for ddl in profile._storage().transaction_profile.profile_index_ddls(7,catalogs,layout):db.execute(ddl)
            profile.validate_main_demo_ddl(db,config,domain)
            self.assertTrue(db.in_transaction)
            db.execute('DROP TABLE '+profile._storage().quote_identifier(sections.table_name(catalogs[1].identity,catalogs[1].tabular_sections[0].identity)))
            with self.assertRaises(BackendError):profile.validate_main_demo_ddl(db,config,domain)
            db.execute('ROLLBACK')

    def test_failed_ddl_rolls_back_mapping_without_committing_parent(self):
        catalogs,domain=self.fixture();config=SimpleNamespace(catalogs=catalogs,enumerations=())
        with sqlite3.connect(':memory:',isolation_level=None) as db, mock.patch.object(profile,'_require_config'):
            profile._storage().register_query_collations(db)
            db.execute('BEGIN')
            for ddl in profile._base_ddls():db.execute(ddl)
            with mock.patch.object(profile,'catalog_section_ddls',return_value=('CREATE TABLE owned(x)', 'invalid SQL')):
                with self.assertRaises(sqlite3.Error):profile.create_catalog_tables(db,config,domain)
            self.assertTrue(db.in_transaction)
            self.assertIsNone(db.execute("SELECT name FROM sqlite_master WHERE name='owned'").fetchone())
            self.assertEqual(db.execute('SELECT COUNT(*) FROM catalog_storage_map').fetchone()[0],0)
            db.execute('ROLLBACK')
