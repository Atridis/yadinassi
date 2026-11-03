import sqlite3
import unittest
from dataclasses import replace
from uuid import UUID

from yadinassi.catalog_backend import (
    BackendError, CatalogSchema, FieldSchema, TabularSectionSchema,
)
from yadinassi.sqlite_catalog_layout import (
    REGISTRY_DDL, Layout, build_layout, catalog_ddl, quote_identifier, save_layout,
)
from yadinassi.sqlite_catalog_sections import (
    SECTION_REGISTRY_DDL, build_section_layout, load_section_layout,
    save_section_layout, section_ddl,
)


class SectionLayoutTests(unittest.TestCase):
    def setUp(self):
        self.section = TabularSectionSchema(UUID(int=11), 'Строки', (
            FieldSchema(UUID(int=101), 'Текст', 'string', (32,)),
            FieldSchema(UUID(int=102), 'Флаг', 'boolean'),
            FieldSchema(UUID(int=103), 'Ссылка', 'catalog_ref', (), UUID(int=2)),
        ))
        self.owner = CatalogSchema(UUID(int=1), 'Документы', 8, 8,
            tabular_sections=(self.section,))
        self.target = CatalogSchema(UUID(int=2), 'Товары', 8, 8)
        self.schemas = (self.owner, self.target)
        self.catalog_layout = build_layout(self.schemas)
        self.layout = build_section_layout(self.schemas, self.catalog_layout)
        self.db = sqlite3.connect(':memory:')
        self.addCleanup(self.db.close)

    def registry(self):
        self.db.execute('CREATE TABLE catalog_schema(identity TEXT PRIMARY KEY)')
        for schema in self.schemas:
            self.db.execute('INSERT INTO catalog_schema VALUES(?)', (str(schema.identity),))
        for ddl in REGISTRY_DDL + SECTION_REGISTRY_DDL:
            self.db.execute(ddl)
        save_layout(self.db, self.catalog_layout)
        save_section_layout(self.db, self.layout)

    def create_tables(self):
        self.db.execute('PRAGMA foreign_keys=ON')
        for schema in self.schemas:
            self.db.execute(catalog_ddl(schema, self.catalog_layout))
        self.db.execute(section_ddl(self.owner, self.section, self.catalog_layout, self.layout))
        return quote_identifier(self.layout.table_name(self.owner.identity, self.section.identity))

    def test_readable_deterministic_names(self):
        self.assertEqual(self.layout.table_name(self.owner.identity, self.section.identity), 'catalog_section_Документы_Строки')
        self.assertEqual(self.layout.field_name(self.owner.identity, self.section.identity, UUID(int=101)), 'attr_Текст')
        reverse = build_section_layout(tuple(reversed(self.schemas)), self.catalog_layout)
        self.assertEqual(reverse._tables, self.layout._tables)

    def test_rename_and_name_reuse_preserve_uuid_mapping(self):
        self.registry()
        renamed_section = replace(self.section, name='Другие', fields=tuple(
            replace(field, name='Новое' + str(index)) for index, field in enumerate(self.section.fields)))
        renamed_owner = replace(self.owner, name='Новые', tabular_sections=(renamed_section,))
        loaded = load_section_layout(self.db, (renamed_owner, self.target), self.catalog_layout)
        self.assertEqual(loaded._tables, self.layout._tables)
        self.assertEqual(loaded._fields, self.layout._fields)
        reused = replace(self.section, identity=UUID(int=12))
        with self.assertRaises(BackendError):
            load_section_layout(self.db, (replace(self.owner, tabular_sections=(reused,)), self.target), self.catalog_layout)

    def test_unicode_collisions_and_owner_table_collision(self):
        first = replace(self.section, name='é', fields=(
            FieldSchema(UUID(int=101), 'É', 'boolean'),
            FieldSchema(UUID(int=102), 'e\u0301', 'boolean'),))
        second = replace(first, identity=UUID(int=12), name='E\u0301')
        owner = replace(self.owner, tabular_sections=(first, second))
        target = replace(self.target, name='section_Документы_é')
        catalogs = build_layout((owner, target))
        layout = build_section_layout((owner, target), catalogs)
        names = tuple(layout._tables.values()) + tuple(catalogs._tables.values())
        self.assertEqual(len(names), len(set(name.casefold() for name in names)))
        self.assertNotEqual(layout.field_name(owner.identity, first.identity, UUID(int=101)), layout.field_name(owner.identity, first.identity, UUID(int=102)))

    def test_same_section_uuid_under_distinct_owners(self):
        owners = tuple(replace(self.owner, identity=UUID(int=i), name='Same') for i in range(1, 9))
        catalogs = build_layout(owners)
        layout = build_section_layout(owners, catalogs)
        self.assertEqual(len(set(layout._tables.values())), len(owners))

    def test_duplicate_schema_identity_rejected(self):
        for schemas in ((self.owner, self.owner), (replace(self.owner, tabular_sections=(self.section, self.section)),)):
            with self.assertRaises(BackendError):
                build_section_layout(schemas, self.catalog_layout)
        section = replace(self.section, fields=(self.section.fields[0], self.section.fields[0]))
        with self.assertRaises(BackendError):
            build_section_layout((replace(self.owner, tabular_sections=(section,)),), self.catalog_layout)

    def test_builder_rejects_invalid_names_and_registry_owner_collisions(self):
        for name in ('', None, 1, 'bad\x00name'):
            owner = replace(self.owner, tabular_sections=(replace(self.section, name=name),))
            with self.assertRaises(BackendError):
                build_section_layout((owner,), self.catalog_layout)
        for name in ('catalog_section_storage_map', 'catalog_section_field_storage_map'):
            catalogs = Layout({**self.catalog_layout._tables, self.target.identity: name}, {})
            with self.assertRaises(BackendError):
                build_section_layout(self.schemas, catalogs)

    def test_registry_rejects_malformed_or_reserved_table_names(self):
        self.registry()
        for name in ('catalog_section_storage_map', 'catalog_section_bad\u202e', 'catalog_section_' + 'x' * 1024, 'wrong_prefix'):
            self.db.execute('UPDATE catalog_section_storage_map SET physical_name=?', (name,))
            with self.assertRaises(BackendError):
                load_section_layout(self.db, self.schemas, self.catalog_layout)

    def test_registry_rejects_missing_extra_and_changed_identity(self):
        self.registry()
        self.db.execute("UPDATE catalog_section_storage_map SET section_id=?", (str(UUID(int=99)),))
        with self.assertRaises(BackendError):
            load_section_layout(self.db, self.schemas, self.catalog_layout)
        self.db.execute('DELETE FROM catalog_section_storage_map')
        with self.assertRaises(BackendError):
            load_section_layout(self.db, self.schemas, self.catalog_layout)
        save_section_layout(self.db, type(self.layout)(self.layout._tables, {}))
        self.db.execute('INSERT INTO catalog_section_storage_map VALUES(?,?,?)', (str(self.owner.identity), str(UUID(int=99)), 'catalog_section_extra'))
        with self.assertRaises(BackendError):
            load_section_layout(self.db, self.schemas, self.catalog_layout)

    def test_field_registry_rejects_invalid_identity_and_name(self):
        self.registry()
        self.db.execute('UPDATE catalog_section_field_storage_map SET physical_name=? WHERE field_id=?', ('owner_id', str(UUID(int=101))))
        with self.assertRaises(BackendError):
            load_section_layout(self.db, self.schemas, self.catalog_layout)
        self.db.execute('UPDATE catalog_section_field_storage_map SET physical_name=?,field_id=? WHERE field_id=?', ('attr_Текст', 'not-a-uuid', str(UUID(int=101))))
        with self.assertRaises(BackendError):
            load_section_layout(self.db, self.schemas, self.catalog_layout)

    def test_safe_quoted_ddl(self):
        section = replace(self.section, name='"; DROP TABLE catalog_schema; --', fields=(FieldSchema(UUID(int=101), '" quote', 'boolean'),))
        owner = replace(self.owner, name='" owner', tabular_sections=(section,))
        catalogs = build_layout((owner, self.target))
        layout = build_section_layout((owner, self.target), catalogs)
        self.db.execute(catalog_ddl(owner, catalogs))
        self.db.execute(section_ddl(owner, section, catalogs, layout))
        self.db.execute(f'INSERT INTO {quote_identifier(layout.table_name(owner.identity, section.identity))} VALUES(?,?,?,?)', ('owner', 'row', 1, 0))

    def test_row_keys_positions_and_boolean_constraints(self):
        table = self.create_tables()
        owner = quote_identifier(self.catalog_layout.table_name(self.owner.identity))
        self.db.execute(f'INSERT INTO {owner} VALUES(?,?,?,?,?)', ('owner', 1, '1', 'test', 0))
        self.db.execute(f'INSERT INTO {table} VALUES(?,?,?,?,?,?)', ('owner', 'row', 1, '', 0, None))
        for row in (('owner', 'row', 2, '', 0, None), ('owner', 'other', 1, '', 0, None), ('owner', 'other', 0, '', 0, None), ('owner', 'other', None, '', 0, None), ('owner', 'other', 2, '', 2, None), ('owner', None, 2, '', 0, None)):
            with self.assertRaises(sqlite3.IntegrityError):
                self.db.execute(f'INSERT INTO {table} VALUES(?,?,?,?,?,?)', row)
        self.db.commit()

    def test_owner_and_reference_fks_are_deferred(self):
        table = self.create_tables()
        self.db.execute(f'INSERT INTO {table} VALUES(?,?,?,?,?,?)', ('owner', 'row', 1, '', 1, 'target'))
        owner = quote_identifier(self.catalog_layout.table_name(self.owner.identity))
        target = quote_identifier(self.catalog_layout.table_name(self.target.identity))
        self.db.execute(f'INSERT INTO {owner} VALUES(?,?,?,?,?)', ('owner', 1, '1', '', 0))
        self.db.execute(f'INSERT INTO {target} VALUES(?,?,?,?,?)', ('target', 1, '1', '', 0))
        self.db.commit()
        self.db.execute(f'INSERT INTO {table} VALUES(?,?,?,?,?,?)', ('missing', 'row', 1, '', 0, None))
        with self.assertRaises(sqlite3.IntegrityError):
            self.db.commit()
        self.db.rollback()
        self.db.execute(f'INSERT INTO {table} VALUES(?,?,?,?,?,?)', ('owner', 'other', 2, '', 0, 'missing'))
        with self.assertRaises(sqlite3.IntegrityError):
            self.db.commit()

    def test_empty_registry_roundtrip(self):
        self.schemas = (self.target,)
        self.catalog_layout = build_layout(self.schemas)
        self.layout = build_section_layout(self.schemas, self.catalog_layout)
        self.registry()
        loaded = load_section_layout(self.db, self.schemas, self.catalog_layout)
        self.assertEqual(loaded._tables, {})
        self.assertEqual(loaded._fields, {})


if __name__ == '__main__':
    unittest.main()
