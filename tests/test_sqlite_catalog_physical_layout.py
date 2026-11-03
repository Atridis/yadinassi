from contextlib import closing
import sqlite3
import tempfile
import unittest
from pathlib import Path
from uuid import uuid4

from yadinassi.sqlite_catalog import SQLiteCatalogBackend
from yadinassi.sqlite_catalog_layout import quote_identifier
from yadinassi.catalog_backend import BackendError
from test_sqlite_catalog_backend import configuration


class PhysicalCatalogLayoutTests(unittest.TestCase):
    def test_per_catalog_tables_and_fields_are_separate(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'owned.sqlite'
            config = configuration()
            backend = SQLiteCatalogBackend.create(path, config)
            layout = backend._layout
            backend.close()
            with closing(sqlite3.connect(path)) as connection, connection:
                self.assertEqual(connection.execute('PRAGMA user_version').fetchone()[0], 2)
                tables = {x[0] for x in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
                self.assertNotIn('catalog_record', tables)
                for schema in config.catalogs:
                    table = layout.table_name(schema.identity)
                    self.assertIn(table, tables)
                    columns = {r[1] for r in connection.execute('PRAGMA table_info(%s)' % quote_identifier(table))}
                    self.assertEqual(columns, {'record_id','revision','code','description','deletion_mark'} | {layout.field_name(schema.identity, f.identity) for f in schema.fields})
                reference_schema = config.catalogs[1]
                foreign = connection.execute('PRAGMA foreign_key_list(%s)' % quote_identifier(layout.table_name(reference_schema.identity))).fetchall()
                self.assertEqual(len(foreign), 1)
                self.assertEqual(foreign[0][2], layout.table_name(config.catalogs[0].identity))

    def test_unexpected_index_is_refused_on_open(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'owned.sqlite'
            config = configuration()
            backend = SQLiteCatalogBackend.create(path, config); layout = backend._layout; backend.close()
            with closing(sqlite3.connect(path)) as connection, connection:
                connection.execute('CREATE INDEX attacker ON %s (description)' % quote_identifier(layout.table_name(config.catalogs[0].identity)))
            with self.assertRaisesRegex(BackendError, 'unsupported'):
                SQLiteCatalogBackend(path)

    def test_version_change_after_open_is_refused(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'owned.sqlite'
            backend = SQLiteCatalogBackend.create(path, configuration())
            with closing(sqlite3.connect(path)) as connection, connection:
                connection.execute('PRAGMA user_version=1')
            with self.assertRaisesRegex(BackendError, 'schema_changed'):
                backend.begin_write(uuid4())
            backend.close()

    def test_mapping_is_readable_and_escaped_for_sql(self):
        from dataclasses import replace
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'owned.sqlite'
            config = configuration()
            category, product = config.catalogs
            # Metadata input here bypasses XML's stricter identifier syntax. It is
            # intentionally hostile to prove the SQLite boundary still quotes it.
            product = replace(product, name='Товары"; DROP TABLE catalog_schema;--',
                              fields=(replace(product.fields[0], name='Цена";--'),) + product.fields[1:])
            backend = SQLiteCatalogBackend.create(path, replace(config, catalogs=(category, product)))
            mapping = backend.inspect_storage_mapping()
            row = next(row for row in mapping if row[0] == product.identity)
            self.assertTrue(row[2].startswith('catalog_Товары'))
            self.assertTrue(row[3][0][2].startswith('attr_Цена'))
            backend.close()
            reopened = SQLiteCatalogBackend(path)
            self.assertEqual(reopened.inspect_storage_mapping(), mapping)
            reopened.close()

    def test_name_normalization_and_reserved_collision_are_stable(self):
        from dataclasses import replace
        from yadinassi.sqlite_catalog_layout import build_layout
        config = configuration()
        a, b = config.catalogs
        # These differ in code points but normalize to the same identifier.
        a = replace(a, name='É')
        b = replace(b, name='E\u0301')
        forward = build_layout((a, b))
        backward = build_layout((b, a))
        self.assertEqual(forward.table_name(a.identity), backward.table_name(a.identity))
        self.assertEqual(forward.table_name(b.identity), backward.table_name(b.identity))
        self.assertNotEqual(forward.table_name(a.identity).casefold(), forward.table_name(b.identity).casefold())
        reserved = build_layout((replace(a, name='schema'),))
        self.assertNotEqual(reserved.table_name(a.identity).casefold(), 'catalog_schema')

    def test_mapping_rejects_tampering(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'owned.sqlite'
            config = configuration()
            backend = SQLiteCatalogBackend.create(path, config); backend.close()
            with closing(sqlite3.connect(path)) as connection, connection:
                connection.execute('UPDATE catalog_storage_map SET physical_name=? WHERE catalog_id=?',
                                   ('catalog_different', str(config.catalogs[0].identity)))
            with self.assertRaises(BackendError):
                SQLiteCatalogBackend(path)

    def test_external_ddl_after_open_fails_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'owned.sqlite'
            config = configuration(); backend = SQLiteCatalogBackend.create(path, config)
            schema = config.catalogs[1]
            table = quote_identifier(backend._layout.table_name(schema.identity))
            column = quote_identifier(backend._layout.field_name(schema.identity, schema.fields[0].identity))
            with closing(sqlite3.connect(path)) as connection, connection:
                connection.execute('ALTER TABLE %s RENAME COLUMN %s TO changed' % (table,column))
            with self.assertRaisesRegex(BackendError, 'schema_changed'): backend.begin_read()
            backend.close()

    def test_hundreds_of_distinct_catalog_tables(self):
        from dataclasses import replace
        from yadinassi.catalog_backend import CatalogSchema
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'owned.sqlite'
            config = replace(configuration(), catalogs=tuple(CatalogSchema(uuid4(), 'Catalog%d' % i, 8, 32) for i in range(200)))
            backend = SQLiteCatalogBackend.create(path, config); backend.close()
            backend = SQLiteCatalogBackend(path, read_only=True)
            try: self.assertEqual(len(backend.inspect_storage_mapping()),200)
            finally: backend.close()

    def test_sqlite_prefix_lookalike_is_not_hidden(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'owned.sqlite'
            backend = SQLiteCatalogBackend.create(path, configuration()); backend.close()
            with closing(sqlite3.connect(path)) as connection, connection:
                connection.execute('CREATE TABLE sqliteXhidden(secret TEXT)')
                connection.execute("INSERT INTO sqliteXhidden VALUES ('keep')")
            with self.assertRaises(BackendError): SQLiteCatalogBackend(path)
            with closing(sqlite3.connect(path)) as connection, connection:
                self.assertEqual(connection.execute('SELECT secret FROM sqliteXhidden').fetchone(), ('keep',))
