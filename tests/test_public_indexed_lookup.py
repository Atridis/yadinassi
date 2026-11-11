"""Public exact lookup, not a manually chosen SQL predicate, uses its index."""
from contextlib import closing
import sqlite3
import unittest
from unittest.mock import patch
from uuid import uuid4

import test_catalog_queries as fixtures
from yadinassi.sqlite_catalog import SQLiteCatalogBackend, _View
from yadinassi.sqlite_catalog_layout import quote_identifier
from yadinassi.sqlite_query_indexes import register_query_collations
from yadinassi.sqlite_query_index_maintenance import prepare, apply


class PublicIndexedLookupTests(unittest.TestCase):
    setUp=fixtures.CatalogQueryTests.setUp
    tearDown=fixtures.CatalogQueryTests.tearDown

    def install(self):
        self.context.close()
        apply(self.context.path,prepare(self.context.path,maintenance=True),maintenance=True)
        self.context._backend=SQLiteCatalogBackend(self.context.path)

    def test_thousand_rows_ten_public_warm_lookups_use_binary_index_and_no_scalar_scan(self):
        manager=self.vm._catalogs.get_index('Products')
        table=quote_identifier(self.context.backend._layout.table_name(manager._schema.identity))
        with closing(sqlite3.connect(self.context.path)) as db,db:
            template=db.execute('SELECT * FROM '+table+' LIMIT 1').fetchone()
            db.execute('DELETE FROM '+table)
            db.executemany('INSERT INTO '+table+' VALUES('+','.join('?' for _ in template)+')',
                [(str(uuid4()),template[1],str(i).zfill(4),*template[3:]) for i in range(1000)])
        self.install()
        decoded=[]; original=_View._scalar
        def scalar(view,*args,**kwargs):
            decoded.append(1)
            return original(view,*args,**kwargs)
        with patch.object(_View,'_scalar',scalar):
            ref=self.vm.execute('Catalogs.Products.FindByCode("0999")')
        self.assertFalse(ref.is_empty())
        self.assertEqual(len(decoded),1000)  # No cold index-only claim.
        trace=[];connection=self.context.backend._read_handle.connection
        connection.set_trace_callback(trace.append)
        with patch.object(_View,'_scalar',side_effect=AssertionError('warm scalar scan')):
            for _ in range(10):
                self.assertEqual(self.vm.execute('Catalogs.Products.FindByCode("0999")'),ref)
        reads=[sql for sql in trace if ' FROM '+table in sql]
        self.assertEqual(len(reads),10)
        self.assertTrue(all('"code" COLLATE BINARY' in sql and 'LIMIT 3' in sql for sql in reads))
        plan=connection.execute('EXPLAIN QUERY PLAN '+reads[-1]).fetchall()
        self.assertTrue(any('SEARCH' in row[3] and 'code=?' in row[3] for row in plan),plan)
        self.assertTrue(self.vm.execute('Catalogs.Products.FindByCode("missing").IsEmpty()'))

    def test_public_codepoint_case_distinctions_and_description_ambiguity_are_unchanged(self):
        manager=self.vm._catalogs.get_index('Products')
        table=quote_identifier(self.context.backend._layout.table_name(manager._schema.identity))
        self.install()
        with closing(sqlite3.connect(self.context.path)) as db,db:
            register_query_collations(db)
            db.execute('UPDATE '+table+' SET code=? WHERE code=?',('Straße','1'))
            db.execute('UPDATE '+table+' SET code=? WHERE code=?',('STRASSE','2'))
        self.assertNotEqual(manager.find_by_code('Straße'),manager.find_by_code('STRASSE'))
        self.assertTrue(manager.find_by_code('strasse').is_empty())
        trace=[];connection=self.context.backend._read_handle.connection
        connection.set_trace_callback(trace.append)
        with self.assertRaisesRegex(ValueError,'ambiguous'):
            manager.find_by_description('item',True)
        reads=[sql for sql in trace if ' FROM '+table in sql]
        self.assertEqual(len(reads),1)
        plan=connection.execute('EXPLAIN QUERY PLAN '+reads[0]).fetchall()
        self.assertTrue(any('SEARCH' in row[3] and 'query_exact_binary_' in row[3] for row in plan),plan)
