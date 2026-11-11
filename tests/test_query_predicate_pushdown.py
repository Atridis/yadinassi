"""Safe all-INNER source filtering, including failure-order counterexamples."""
from contextlib import closing
from decimal import Decimal
import sqlite3
import unittest
from unittest.mock import patch
from uuid import uuid4

import test_catalog_queries as fixtures
from yadinassi.catalog_backend import BackendError
from yadinassi.queries import BSLQuery
from yadinassi.relational_queries import _Plan
from yadinassi.sqlite_catalog import _View
from yadinassi.sqlite_catalog_layout import quote_identifier


class InnerPredicatePushdownTests(unittest.TestCase):
    setUp = fixtures.CatalogQueryTests.setUp
    tearDown = fixtures.CatalogQueryTests.tearDown

    def execute(self, text):
        return BSLQuery(self.vm._catalogs, text).execute()._rows

    def scans(self, text):
        original = _View.scan_catalog_values; scanned = []
        def scan(view, identity, request, fields):
            page = original(view, identity, request, fields)
            scanned.append((request.predicate, len(page.rows)))
            return page
        with patch.object(_View, 'scan_catalog_values', scan): result = self.execute(text)
        return result, scanned

    def test_thousand_squared_join_has_only_thousand_filtered_candidates(self):
        backend = self.context.backend; schema = self.vm._catalogs.get_index('Products')._schema
        table = quote_identifier(backend._layout.table_name(schema.identity))
        with closing(sqlite3.connect(self.context.path)) as connection, connection:
            template = connection.execute('SELECT * FROM '+table+' LIMIT 1').fetchone()
            connection.execute('DELETE FROM '+table)
            rows = [(str(uuid4()), template[1], str(i).zfill(4), *template[3:]) for i in range(1000)]
            connection.executemany('INSERT INTO '+table+' VALUES('+','.join('?' for _ in template)+')', rows)
        pairs = []; original = _Plan.join
        def join(plan, left, right, *args):
            pairs.append((len(left), len(right)))
            return original(plan, left, right, *args)
        with patch.object(_Plan, 'join', join):
            result = self.execute('SELECT TOP 1 P.Code AS A,Q.Code AS B FROM Catalog.Products AS P '
                                  'JOIN Catalog.Products AS Q ON P.Text=Q.Text WHERE P.Code="0999"')
        self.assertEqual(result[0][0], '0999')
        self.assertEqual(pairs, [(1, 1000)])

    def test_source_conjuncts_split_but_cross_source_predicate_stays_residual(self):
        result, scans = self.scans('SELECT P.Code AS A,Q.Code AS B FROM Catalog.Products AS P '
            'JOIN Catalog.Products AS Q ON P.Text=Q.Text '
            'WHERE P.Code="1" AND Q.Amount>=20 AND P.Amount<Q.Amount ORDER BY Q.Code')
        self.assertEqual(result, (('1','2'),('1','3')))
        self.assertEqual([count for _, count in scans], [1,2])
        self.assertTrue(all(predicate is not None for predicate, _ in scans))

    def test_constant_on_left_preserves_reversed_operator(self):
        result, scans = self.scans('SELECT P.Code AS A,Q.Code AS B FROM Catalog.Products AS P '
            'JOIN Catalog.Products AS Q ON P.Ref=Q.Ref WHERE 20<P.Amount ORDER BY P.Code')
        self.assertEqual(result, (('3','3'),))
        self.assertEqual([count for _, count in scans], [1,3])

    def test_right_source_only_filter_is_pushed_without_changing_join_order(self):
        result, scans = self.scans('SELECT P.Code AS A,Q.Code AS B FROM Catalog.Products AS P '
            'JOIN Catalog.Products AS Q ON P.Text=Q.Text WHERE Q.Code="2" ORDER BY P.Code')
        self.assertEqual(result, (('1','2'),('2','2'),('3','2')))
        self.assertEqual([count for _, count in scans], [3,1])

    def test_on_error_must_not_be_hidden_by_selective_where(self):
        with self.assertRaisesRegex(ValueError, 'division by zero'):
            self.execute('SELECT P.Code AS A,Q.Code AS B FROM Catalog.Products AS P '
                'JOIN Catalog.Products AS Q ON P.Amount/0=Q.Amount WHERE P.Code="absent"')

    def test_earlier_residual_error_must_not_be_hidden_by_later_conjunct(self):
        with self.assertRaisesRegex(ValueError, 'division by zero'):
            self.execute('SELECT P.Code AS A,Q.Code AS B FROM Catalog.Products AS P '
                'JOIN Catalog.Products AS Q ON P.Ref=Q.Ref WHERE P.Amount/0=1 AND P.Code="absent"')

    def test_short_circuit_before_error_retains_original_behavior_without_pushdown(self):
        result, scans = self.scans('SELECT P.Code AS A,Q.Code AS B FROM Catalog.Products AS P '
            'JOIN Catalog.Products AS Q ON P.Ref=Q.Ref WHERE P.Code="absent" AND P.Amount/0=1')
        self.assertEqual(result, ())
        self.assertTrue(all(predicate is None for predicate, _ in scans))

    def test_outer_join_and_or_regions_are_not_rewritten(self):
        for text in (
            'SELECT P.Code AS A,Q.Code AS B FROM Catalog.Products AS P LEFT JOIN Catalog.Products AS Q '
            'ON P.Ref=Q.Ref WHERE P.Code="1"',
            'SELECT P.Code AS A,Q.Code AS B FROM Catalog.Products AS P JOIN Catalog.Products AS Q '
            'ON P.Ref=Q.Ref WHERE P.Code="1" OR Q.Code="2"',
        ):
            with self.subTest(text=text):
                _, scans = self.scans(text)
                self.assertTrue(all(predicate is None for predicate, _ in scans))

    def test_unfiltered_join_still_obeys_intermediate_limit(self):
        with patch('yadinassi.relational_queries.MAX_INTERMEDIATE_ROWS', 2):
            with self.assertRaisesRegex(ValueError, 'intermediate'):
                self.execute('SELECT TOP 1 P.Code AS A,Q.Code AS B FROM Catalog.Products AS P '
                             'JOIN Catalog.Products AS Q ON P.Text=Q.Text')

    def test_hidden_corruption_is_not_removed_by_pushed_filter(self):
        backend = self.context.backend; schema = self.vm._catalogs.get_index('Products')._schema
        table = quote_identifier(backend._layout.table_name(schema.identity))
        field = next(f for f in schema.fields if f.name == 'Amount')
        column = quote_identifier(backend._layout.field_name(schema.identity, field.identity))
        with closing(sqlite3.connect(self.context.path)) as connection, connection:
            connection.execute('UPDATE '+table+' SET '+column+'=? WHERE code=?', ('invalid', '3'))
        with self.assertRaisesRegex(BackendError, 'integrity'):
            self.execute('SELECT P.Code AS A,Q.Code AS B FROM Catalog.Products AS P '
                         'JOIN Catalog.Products AS Q ON P.Text=Q.Text WHERE P.Code="1"')

    def test_many_conjuncts_use_bounded_subset_not_new_storage_refusal(self):
        result, scans=self.scans('SELECT P.Code AS A,Q.Code AS B FROM Catalog.Products AS P '
            'JOIN Catalog.Products AS Q ON P.Ref=Q.Ref WHERE '+
            ' AND '.join('P.Code="1"' for _ in range(64)))
        self.assertEqual(result,(('1','1'),))
        self.assertEqual([count for _,count in scans],[1,3])

    def test_unencodable_string_operand_stays_relational_residual(self):
        query=BSLQuery(self.vm._catalogs,'SELECT P.Code FROM Catalog.Products AS P '
            'JOIN Catalog.Products AS Q ON P.Ref=Q.Ref WHERE P.Code=&Text')
        query.set_parameter('Text',chr(0xd800))
        self.assertEqual(query.execute()._rows,())

    def test_overflow_decimal_literal_is_not_hidden_by_other_filter(self):
        with self.assertRaisesRegex(ValueError,'range exceeded'):
            self.execute('SELECT P.Code FROM Catalog.Products AS P '
                'JOIN Catalog.Products AS Q ON P.Ref=Q.Ref '
                'WHERE P.Amount<100000000000000000000000000000000000000 AND P.Code="absent"')

    def test_late_bind_error_still_fails_before_any_scan(self):
        with patch.object(_View, 'scan_catalog_values', side_effect=AssertionError('scan')):
            with self.assertRaises(TypeError):
                self.execute('SELECT P.Code AS A,Q.Code AS B FROM Catalog.Products AS P '
                    'JOIN Catalog.Products AS Q ON P.Text=Q.Text WHERE P.Code="1" AND Q.Amount="bad"')


class DocumentPredicateBoundaryTests(unittest.TestCase):
    from test_document_queries import DocumentQueryTests as _Fixture
    setUp=_Fixture.setUp
    tearDown=_Fixture.tearDown
    seed=_Fixture.seed
    query=_Fixture.query

    def test_subsecond_date_is_not_truncated_in_single_or_join_pushdown(self):
        from yadinassi.dates import BSLDate
        self.seed()
        base=self.vm.execute('Date(2026,11,1,12,30,5)')
        for source in ('Document.Orders AS D',
                'Document.Orders AS D JOIN Document.Orders AS E ON D.Ref=E.Ref'):
            for operator,expected in (('<',1),('<>',3)):
                with self.subTest(source=source,operator=operator):
                    query=self.query('SELECT D.Number FROM '+source+' WHERE D.Date'+operator+'&Edge')
                    query.set_parameter('Edge',BSLDate(base.ticks+1))
                    self.assertEqual(len(query.execute()._rows),expected)
