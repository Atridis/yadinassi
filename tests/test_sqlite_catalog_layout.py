import sqlite3
import unittest
from uuid import UUID, uuid4

from yadinassi.catalog_backend import BackendError, CatalogSchema, FieldSchema
from yadinassi.sqlite_catalog_layout import (REGISTRY_DDL, build_layout, save_layout,
    load_layout, quote_identifier, catalog_ddl)


class LayoutTests(unittest.TestCase):
    def setUp(self):
        self.first = CatalogSchema(UUID(int=1), 'Товары', 8, 8,
            (FieldSchema(UUID(int=11), 'Цена', 'string', (32,)),))
        self.second = CatalogSchema(UUID(int=2), 'товары', 8, 8,
            (FieldSchema(UUID(int=12), 'Цена', 'boolean'),))

    def test_readable_names_and_casefold_collision(self):
        layout = build_layout((self.second, self.first))
        self.assertEqual(layout.table_name(self.first.identity), 'catalog_Товары')
        self.assertEqual(layout.table_name(self.second.identity), 'catalog_товары_00000000')
        self.assertEqual(layout.field_name(self.first.identity, self.first.fields[0].identity), 'attr_Цена')

    def test_canonical_unicode_and_uuid_extension(self):
        one = CatalogSchema(UUID(int=1), 'é', 8, 8)
        two = CatalogSchema(UUID(int=2), 'e\u0301', 8, 8)
        three = CatalogSchema(UUID(int=3), 'É', 8, 8)
        layout = build_layout((one,two,three))
        self.assertEqual(layout.table_name(one.identity), 'catalog_é')
        self.assertEqual(layout.table_name(two.identity), 'catalog_é_00000000')
        self.assertEqual(layout.table_name(three.identity), 'catalog_É_000000000000')

    def test_quote_identifier_handles_embedded_quotes(self):
        schema = CatalogSchema(uuid4(), '"; DROP TABLE database_info; --', 8, 8,
            (FieldSchema(uuid4(), '" quoted', 'boolean'),))
        layout = build_layout((schema,))
        db = sqlite3.connect(':memory:')
        try:
            db.execute('CREATE TABLE database_info(x)')
            db.execute(catalog_ddl(schema, layout))
            db.execute(f'INSERT INTO {quote_identifier(layout.table_name(schema.identity))} VALUES(?,?,?,?,?,?)', ('id',1,'c','d',0,1))
            self.assertEqual(db.execute('SELECT COUNT(*) FROM database_info').fetchone()[0], 0)
        finally: db.close()
        with self.assertRaises(BackendError): quote_identifier('bad\x00name')

    def test_registry_stays_stable_after_rename(self):
        layout = build_layout((self.first, self.second))
        renamed = CatalogSchema(self.first.identity, 'Новая', 8, 8,
            (FieldSchema(self.first.fields[0].identity, 'Стоимость', 'string', (32,)),))
        db = sqlite3.connect(':memory:')
        try:
            db.execute('CREATE TABLE catalog_schema(identity TEXT PRIMARY KEY)')
            for ddl in REGISTRY_DDL: db.execute(ddl)
            save_layout(db, layout)
            loaded = load_layout(db, (renamed, self.second))
            self.assertEqual(loaded.table_name(renamed.identity), 'catalog_Товары')
            self.assertEqual(loaded.field_name(renamed.identity, renamed.fields[0].identity), 'attr_Цена')
        finally: db.close()

    def test_reserved_name_and_corrupt_mapping_rejected(self):
        schema = CatalogSchema(uuid4(), 'schema', 8, 8)
        layout = build_layout((schema,))
        self.assertNotEqual(layout.table_name(schema.identity), 'catalog_schema')
        db = sqlite3.connect(':memory:')
        try:
            db.execute('CREATE TABLE catalog_schema(identity TEXT PRIMARY KEY)')
            for ddl in REGISTRY_DDL: db.execute(ddl)
            save_layout(db, layout)
            db.execute("UPDATE catalog_storage_map SET physical_name='catalog_schema'")
            with self.assertRaises(BackendError): load_layout(db, (schema,))
        finally: db.close()

    def test_control_characters_are_replaced_not_displayed(self):
        schema = CatalogSchema(uuid4(), 'Товар\n\x1b\u202eИмя', 8, 8)
        layout = build_layout((schema,))
        self.assertEqual(layout.table_name(schema.identity), 'catalog_Товар___Имя')
        with self.assertRaises(BackendError): quote_identifier('bad\u202ename')
        with self.assertRaises(BackendError): build_layout((CatalogSchema(uuid4(), 'bad\x00name', 8, 8),))

    def test_stored_control_name_rejected(self):
        db = sqlite3.connect(':memory:')
        try:
            db.execute('CREATE TABLE catalog_schema(identity TEXT PRIMARY KEY)')
            for ddl in REGISTRY_DDL: db.execute(ddl)
            save_layout(db, build_layout((self.first,)))
            db.execute('UPDATE catalog_storage_map SET physical_name=?', ('catalog_bad\u202e',))
            with self.assertRaises(BackendError): load_layout(db, (self.first,))
        finally: db.close()


if __name__ == '__main__': unittest.main()
