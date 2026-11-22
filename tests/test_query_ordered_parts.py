"""Native bounded read for owned SQLite tabular parts, not raw scans."""
from contextlib import closing
from decimal import Decimal
import sqlite3
from uuid import uuid4
import unittest
from unittest.mock import patch

import test_catalog_section_queries as catalog
import test_document_queries as document
import test_query_ordered_top_pushdown as trace_fixture
from yadinassi.db.catalog.catalog_backend import BackendError
from yadinassi.db.sqlite.sqlite_catalog import _View
from yadinassi.db.sqlite.sqlite_catalog_layout import quote_identifier
from yadinassi.db.sqlite.sqlite_documents import DocumentView


class OrderedCatalogPartTests(unittest.TestCase):
    setUp = catalog.CatalogSectionQueryTests.setUp
    seed = catalog.CatalogSectionQueryTests.seed
    query = catalog.CatalogSectionQueryTests.query
    actual_trace = trace_fixture.OrderedTopMainDemoTests.actual_trace

    def test_bounded_catalog_part_with_literal_projection(self):
        self.seed()
        text='SELECT TOP 1 Text, 7 AS Marker FROM Catalog.Products.Lines WHERE Active=FALSE ORDER BY Amount DESC'
        with patch.object(_View,'ordered_catalog_part',return_value=None) as decline:
            expected=self.query(text).execute()._rows
        decline.assert_called_once()
        self.assertEqual(len(expected),1)
        trace,traced=self.actual_trace()
        with traced, patch.object(_View,'scan_catalog_section',side_effect=AssertionError('full part')):
            self.assertEqual(self.query(text).execute()._rows,expected)
        self.assertEqual(len(trace),1,trace)
        self.assertTrue(trace[0].endswith('LIMIT 1'),trace)

    def test_exact_filter_order_and_owner_one_select(self):
        self.seed()
        text = ('SELECT TOP 2 L.Ref AS Owner, L.Text AS Caption, L.Amount FROM Catalog.Products.Lines AS L '
                'WHERE (L.Amount > 30.001 OR L.Text = "HIGH") AND L.Active=FALSE ORDER BY L.Amount DESC, L.Text')
        with patch.object(_View,'ordered_catalog_part',return_value=None) as decline:
            expected = self.query(text).execute()._rows
        decline.assert_called_once()
        self.assertEqual(tuple(row[1] for row in expected),('other owner','high'))
        trace,traced = self.actual_trace()
        with traced, patch.object(_View,'scan_catalog_section',side_effect=AssertionError('full typed part')):
            self.assertEqual(self.query(text).execute()._rows,expected)
        self.assertEqual(len(trace),1,trace)
        self.assertIn(' ORDER BY ',trace[0])
        self.assertTrue(trace[0].endswith('LIMIT 2'),trace)

    def test_winner_with_invalid_row_identity_rejected(self):
        self.seed()
        backend = self.context.backend
        schema = self.vm._catalogs.get_index('Products')._schema
        part = next(p for p in schema.tabular_sections if p.name=='Lines')
        table = quote_identifier(backend._section_layout.table_name(schema.identity,part.identity))
        with closing(sqlite3.connect(backend.path)) as connection, connection:
            connection.execute(f'UPDATE {table} SET row_id=? WHERE owner_id=? AND row_number=1',
                ('00000000-0000-0000-0000-000000000000',str(self.vm.variables['p']._key.record_id)))
        with self.assertRaisesRegex(BackendError,'integrity'):
            self.query('SELECT TOP 1 Amount FROM Catalog.Products.Lines ORDER BY Amount DESC').execute()


    def test_winner_with_dangling_unprojected_reference_rejected(self):
        self.seed()
        backend = self.context.backend
        schema = self.vm._catalogs.get_index('Products')._schema
        part = next(p for p in schema.tabular_sections if p.name=='Lines')
        field = next(field for field in part.fields if field.name=='Category')
        table = quote_identifier(backend._section_layout.table_name(schema.identity,part.identity))
        column = quote_identifier(backend._section_layout.field_name(schema.identity,part.identity,field.identity))
        with closing(sqlite3.connect(backend.path)) as connection, connection:
            connection.execute(f'UPDATE {table} SET {column}=? WHERE owner_id=? AND row_number=1',
                               (str(uuid4()),str(self.vm.variables['o']._key.record_id)))
        with self.assertRaisesRegex(BackendError,'integrity'):
            self.query('SELECT TOP 1 L.Amount FROM Catalog.Products.Lines AS L '
                       'WHERE L.Amount < 99 ORDER BY L.Amount DESC').execute()


class OrderedDocumentPartTests(unittest.TestCase):
    setUp = document.DocumentQueryTests.setUp
    tearDown = document.DocumentQueryTests.tearDown
    seed = document.DocumentQueryTests.seed
    query = document.DocumentQueryTests.query
    actual_trace = trace_fixture.OrderedTopMainDemoTests.actual_trace

    def test_document_native_projection_and_stable_line_order(self):
        self.seed()
        text = ('SELECT TOP 4 L.Ref AS Owner, L.LineNumber, L.Amount FROM Document.Orders.Lines AS L '
                'WHERE L.LineNumber >= 1.001 OR L.Amount >= 5 ORDER BY L.Amount DESC')
        with patch.object(DocumentView,'ordered_document_part',return_value=None) as decline:
            expected = self.query(text).execute()._rows
        decline.assert_called_once()
        self.assertEqual(tuple(row[1:] for row in expected),((Decimal(2),Decimal(9)),
            (Decimal(2),Decimal(6)),(Decimal(1),Decimal(6)),(Decimal(2),Decimal(3))))
        trace,traced = self.actual_trace()
        with traced, patch.object(DocumentView,'scan_document_values',side_effect=AssertionError('full typed part')):
            self.assertEqual(self.query(text).execute()._rows,expected)
        self.assertEqual(len(trace),1,trace)
        self.assertIn('FROM "document_part_',trace[0])
        self.assertTrue(trace[0].endswith('LIMIT 4'),trace)

    def test_reference_filter_remains_residual(self):
        self.seed()
        text = ('SELECT TOP 1 L.Amount FROM Document.Orders.Lines AS L '
                'WHERE L.Category = &Owner ORDER BY L.Amount DESC')
        query = self.query(text)
        query.set_parameter('Owner',self.vm.variables['c'].get_member('Ref'))
        with patch.object(DocumentView,'ordered_document_part',side_effect=AssertionError('reference pushdown')):
            self.assertEqual(query.execute()._rows,((Decimal(9),),))
