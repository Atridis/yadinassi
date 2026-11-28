"""ORDER/TOP keeps query-language comparison semantics, not SQLite defaults."""
from contextlib import closing
from dataclasses import replace
from decimal import Decimal
import datetime
import sqlite3
import unittest
from unittest.mock import patch
from uuid import UUID, uuid4

import test_main_demo_runtime as main
import test_sqlite_catalog_sections as generic
from yadinassi import Interpreter
from yadinassi.db.catalog.catalog_backend import CatalogDraft, CatalogKey
from yadinassi.db.database_context import SQLiteDBContext
from yadinassi.db.sqlite.sqlite_catalog import _View
from yadinassi.db.sqlite.sqlite_documents import DocumentView
from yadinassi.db.sqlite.sqlite_query_indexes import register_query_collations


class OrderedTopMainDemoTests(unittest.TestCase):
    setUp = main.MainDemoRuntimeTests.setUp

    def query(self, text):
        quoted = text.replace('"', '""')
        return self.vm.execute('Q=New Query("' + quoted + '"); Q.Execute()')._rows

    def seed(self):
        manager = self.vm._catalogs.get_member('Склады')
        self.manager = manager
        entries = (('1','Straße'), ('2','STRASSE'), ('3','Ёж'), ('4','ёж'),
                   ('5','a\0A'), ('6','a\0z'), ('7','Я'))
        identities = {}
        for code, description in entries:
            saved = manager.create_item()
            saved.set_member('Code',code)
            saved.set_member('Description',description)
            saved.write()
            identities[code] = saved._key.record_id.int
        return entries, identities

    def actual_trace(self):
        backend = self.context.backend
        connect = backend._connect
        statements = []
        def traced_connect(**kwargs):
            connection = connect(**kwargs)
            connection.set_trace_callback(statements.append)
            return connection
        if backend._read_handle is not None:
            backend._read_handle.connection.set_trace_callback(statements.append)
        return statements, patch.object(backend,'_connect',side_effect=traced_connect)

    def test_literal_projection_and_unordered_point_query_select_one_page(self):
        self.seed()
        texts = (
            ('SELECT TOP 1 Description, "literal" AS Marker FROM Catalog.Склады ORDER BY Code', ('Straße','literal')),
            ('SELECT TOP 1 Description, &Marker AS Mark FROM Catalog.Склады WHERE Code=&Key', ('STRASSE','param')),
            ('SELECT TOP 1 Description FROM Catalog.Склады WHERE Code=&Key', ('STRASSE',)),
            ('SELECT TOP 1 "constant" AS Marker FROM Catalog.Склады ORDER BY Code', ('constant',)),
            ('SELECT TOP 1 "constant" AS Marker FROM Catalog.Склады WHERE Code="missing"', None),
        )
        from yadinassi.db.query.relational_queries import _Plan
        for text, expected in texts:
            with self.subTest(text=text):
                self.vm.execute('Q=New Query("' + text.replace('"','""') + '");')
                query=self.vm.variables['q']
                if '&Key' in text:query.set_parameter('Key','2')
                if '&Marker' in text:query.set_parameter('Marker','param')
                trace,traced=self.actual_trace()
                with traced, patch.object(_Plan,'load',side_effect=AssertionError('materialized input')), \
                        patch.object(_View,'_validate_scan_scalars',side_effect=AssertionError('whole scan')):
                    result=query.execute()
                self.assertEqual(result._rows,() if expected is None else (expected,))
                if '&Marker' in text:
                    self.assertEqual((result._columns[1].name,result._columns[1].kind),('Mark','string'))
                self.assertEqual(len(trace),1,trace)
                self.assertTrue(trace[0].endswith('LIMIT 1'),trace)
                self.assertNotIn('literal',trace[0])
                self.assertNotIn('constant',trace[0])

    def test_closed_case_projection_keeps_one_ordered_sql_page(self):
        self.seed()
        cases = (
            ('CASE WHEN TRUE=TRUE THEN Description ELSE Description END', 'Straße'),
            ('CASE WHEN NULL = NULL THEN "unused" WHEN FALSE=FALSE THEN Description ELSE "other" END', 'Straße'),
            ('CASE WHEN (1+1=2 AND 2<>3) THEN "fixed" ELSE Description END', 'fixed'),
        )
        from yadinassi.db.query.relational_queries import _Plan
        for expression, expected in cases:
            for where, rows in (('', ((expected,),)), (' WHERE Code="missing"', ())):
                with self.subTest(expression=expression, where=where):
                    query = self.bound(f'SELECT TOP 1 {expression} AS Caption FROM Catalog.Склады{where} ORDER BY Code')
                    trace,traced = self.actual_trace()
                    with traced, patch.object(_Plan, 'load', side_effect=AssertionError('materialized input')):
                        result = query.execute()
                    self.assertEqual(result._rows, rows)
                    self.assertEqual((result._columns[0].name, result._columns[0].kind), ('Caption', 'string'))
                    self.assertEqual(len(trace), 1, trace)
                    self.assertTrue(trace[0].endswith('LIMIT 1'),trace)

    def _seed_ascii_case_page(self):
        manager = self.vm._catalogs.get_member('Склады')
        for code, text in (('1', 'First'), ('2', 'Second'), ('3', 'Third')):
            save = manager.create_item()
            save.set_member('Code', code)
            save.set_member('Description', text)
            save.write()
        return manager

    def test_same_arms_keep_original_budget_horizon_in_one_statement(self):
        from yadinassi.db.query.relational_queries import _Plan

        expression = 'CASE WHEN Code>="2" THEN Description ELSE Description END'
        text = f'SELECT TOP 2 {expression} AS Caption FROM Catalog.Склады ORDER BY Code DESC'
        query = self.bound(text)
        for expected in ((), (('Third',), ('Second',))):
            if expected:
                self._seed_ascii_case_page()
            trace, traced = self.actual_trace()
            with traced, patch.object(_Plan, 'load', side_effect=AssertionError('materialized input')):
                result = query.execute()
            self.assertEqual(result._rows, expected)
            self.assertEqual((result._columns[0].name, result._columns[0].kind), ('Caption', 'string'))
            self.assertEqual(len(trace), 1, trace)
            self.assertIn('WITH proof AS', trace[0])
            self.assertIn('LIMIT 2', trace[0])

    def test_same_arms_keep_casefold_tie_order_from_residual(self):
        from yadinassi.db.query import query_pushdown

        manager = self._seed_ascii_case_page()
        other = manager.create_item()
        other.set_member('Code', '9')
        other.set_member('Description', 'FIRST')
        other.write()
        query = self.bound('SELECT TOP 2 CASE WHEN Code=Code THEN Description ELSE Description END '
                           'AS Caption, Code FROM Catalog.Склады ORDER BY Description')
        with patch.object(query_pushdown, '_witnessed_case_projection', return_value=None):
            original = query.execute()._rows
        self.assertEqual({row[0] for row in original}, {'FIRST', 'First'})
        trace, traced = self.actual_trace()
        with traced:
            self.assertEqual(query.execute()._rows, original)
        self.assertEqual(len(trace), 1, trace)

    def test_same_arms_keep_hidden_corruption_and_separate_budgets(self):
        from yadinassi.db.catalog.catalog_backend import BackendError

        manager = self._seed_ascii_case_page()
        one = 'CASE WHEN Code=Code THEN Description ELSE Description END'
        with patch('yadinassi.db.query.query_parser.MAX_ROWS', 2):
            with self.assertRaisesRegex(ValueError, 'input resource'):
                self.bound(f'SELECT TOP 1 {one} AS Caption FROM Catalog.Склады ORDER BY Code').execute()
        with patch('yadinassi.db.sqlite.sqlite_catalog._MAX_ROWS', 2):
            with self.assertRaisesRegex(BackendError, 'unsupported'):
                self.bound(f'SELECT TOP 1 {one} AS Caption FROM Catalog.Склады ORDER BY Code').execute()
        with patch('yadinassi.db.query.queries._MAX_RESULT_TEXT', 17):
            with self.assertRaisesRegex(ValueError, 'input resource'):
                self.bound(f'SELECT TOP 1 {one} AS Caption FROM Catalog.Склады ORDER BY Code').execute()
        two = 'CASE WHEN Description=Description THEN Description ELSE Description END'
        with patch('yadinassi.db.query.queries._MAX_RESULT_TEXT', 24):
            with self.assertRaisesRegex(ValueError, 'result resource'):
                self.bound(f'SELECT TOP 1 {two} AS A,{two} AS B FROM Catalog.Склады ORDER BY Description').execute()

        table = self.context.backend._layout.table_name(manager._schema.identity)
        text = f'SELECT TOP 1 {one} AS Caption FROM Catalog.Склады ORDER BY Code'
        with closing(sqlite3.connect(self.path)) as connection, connection:
            register_query_collations(connection)
            connection.execute(f'UPDATE "{table}" SET description=? WHERE code=?', ('Живой', '3'))
        self.assertEqual(self.bound(text).execute()._rows, (('First',),))
        with closing(sqlite3.connect(self.path)) as connection, connection:
            register_query_collations(connection)
            connection.execute(f'UPDATE "{table}" SET description=? WHERE code=?', ('bad'*100, '3'))
        with self.assertRaisesRegex(BackendError, 'integrity'):
            self.bound(text).execute()

    def test_same_arms_and_total_true_where_share_unicode_page_witness(self):
        self._seed_ascii_case_page()
        self.vm.execute('W=Catalogs.Склады.FindByCode("3").GetObject();W.Description="Ё😀";W.Write();')
        expression = 'CASE WHEN Code=Code THEN Description ELSE Description END'
        statement = f'SELECT TOP 1 {expression} AS Caption FROM Catalog.Склады'
        from yadinassi.db.query.relational_queries import _Plan

        for predicate in ('1=1', '1=1 AND (NULL IS NULL OR 2=3)'):
            query = self.bound(statement+f' WHERE {predicate} ORDER BY Description')
            with patch('yadinassi.db.query.query_pushdown._witnessed_case_projection', return_value=None):
                expected = query.execute()._rows
            trace, traced = self.actual_trace()
            with traced, patch.object(_Plan, 'load', side_effect=AssertionError('materialized input')):
                self.assertEqual(query.execute()._rows, expected)
            self.assertEqual(len(trace), 1, trace)
            self.assertIn('WITH proof AS', trace[0])
        self.assertEqual(self.bound(statement+' WHERE NULL=NULL ORDER BY Code').execute()._rows, ())
        with self.assertRaisesRegex(ValueError, 'division by zero'):
            self.bound(statement+' WHERE 1/0=1 ORDER BY Code').execute()

    def test_same_arms_decline_when_cold_statement_capability_is_too_low(self):
        self._seed_ascii_case_page()
        query = self.bound('SELECT TOP 1 CASE WHEN Code=Code THEN Description ELSE Description END '
                           'AS Caption FROM Catalog.Склады ORDER BY Code')
        backend = self.context.backend
        backend._close_idle_read_handle()
        with closing(backend.begin_query_read(query_language=True)):
            pass
        connection = backend._read_handle.connection
        limit = getattr(connection, 'setlimit', None)
        if limit is None:
            self.assertEqual(query.execute()._rows, (('First',),))
            return
        old = limit(sqlite3.SQLITE_LIMIT_SQL_LENGTH, 700)
        try:
            with patch('yadinassi.db.sqlite.sqlite_case_page.fetch_all',
                       side_effect=AssertionError('attempted optional SQL')):
                self.assertEqual(query.execute()._rows, (('First',),))
        finally:
            limit(sqlite3.SQLITE_LIMIT_SQL_LENGTH, old)
        trace, traced = self.actual_trace()
        with traced:
            self.assertEqual(query.execute()._rows, (('First',),))
        self.assertEqual(len(trace), 1, trace)

    def test_row_dependent_or_raising_case_does_not_use_top_fast_path(self):
        self.seed()
        for expression, expected in (
            ('CASE WHEN Code="1" THEN Description ELSE "other" END', 'Straße'),
            ('CASE WHEN 1/0=0 THEN Description ELSE "other" END', None),
        ):
            with self.subTest(expression=expression):
                query = self.bound(f'SELECT TOP 1 {expression} AS Caption FROM Catalog.Склады ORDER BY Code')
                trace,traced = self.actual_trace()
                with traced:
                    if expected is None:
                        with self.assertRaisesRegex(ValueError, 'division by zero'):
                            query.execute()
                    else:
                        self.assertEqual(query.execute()._rows, ((expected,),))
                self.assertTrue(trace)
                self.assertFalse(any(sql.endswith('LIMIT 1') for sql in trace), trace)
        empty = self.bound('SELECT TOP 1 CASE WHEN 1/0=0 THEN Description ELSE "other" END '
                           'AS Caption FROM Catalog.Склады WHERE Code="missing" ORDER BY Code')
        self.assertEqual(empty.execute()._rows, ())

    def seed_folded_codes(self, size=2, codes=('CaseFold','casefold')):
        manager = self.vm._catalogs.get_member('Склады')
        backend = self.context.backend
        records = [(codes[0],'first marked',True), (codes[1],'second live',False)]
        records += [(str(i),f'Warehouse {i:04}',False) for i in range(3,size+1)]
        with closing(backend.begin_write(uuid4())) as writer:
            for index,(code,description,marked) in enumerate(records,1):
                key = CatalogKey(backend.database_id,manager._schema.identity,UUID(int=index))
                writer.create(CatalogDraft(key,code,description,marked,()))
            writer.commit()

    def bound(self, text, **parameters):
        from yadinassi.db.query.queries import BSLQuery
        q = BSLQuery(self.vm._catalogs,text,self.vm._documents)
        for name,value in parameters.items(): q.set_parameter(name,value)
        return q

    def test_folded_arithmetic_uses_one_top_page_and_keeps_decimal_descriptor(self):
        from yadinassi.db.query import query_pushdown
        from yadinassi.db.query.relational_queries import _Plan
        self.seed_folded_codes()
        query = self.bound('SELECT TOP 1 Description, (&Value+0.025)*2 AS Marker, 1/3 AS Fraction '
                           'FROM Catalog.Склады ORDER BY Description', Value=Decimal('1.200'))
        with patch.object(query_pushdown,'try_ordered_select',return_value=None):
            expected = query.execute()
        from yadinassi.db.query import query_parser
        value = _Plan.value
        evaluated = []
        def watched(plan, expression, row, group=None):
            if type(expression) is query_parser.Expression and expression.operator in ('/','*'):
                evaluated.append((expression.operator,row))
            return value(plan,expression,row,group)
        trace,traced = self.actual_trace()
        with traced, patch.object(_Plan,'load',side_effect=AssertionError('residual input')), \
                patch.object(_View,'_validate_scan_scalars',side_effect=AssertionError('whole scan')), \
                patch.object(_Plan,'value',watched):
            got = query.execute()
        self.assertEqual(evaluated,[('*',()),('/',())])
        self.assertEqual(len(trace),1,trace)
        self.assertTrue(trace[0].endswith('LIMIT 1'),trace)
        self.assertNotIn('1.200',trace[0])
        self.assertEqual(got._columns,expected._columns)
        self.assertEqual(got._columns[1].qualifiers,(38,3,'Any'))
        self.assertEqual(got._columns[2].qualifiers,(38,10,'Any'))
        self.assertEqual(got._rows,(('first marked',Decimal('2.450'),Decimal('0.3333333333')),))
        self.assertEqual(tuple(v.as_tuple() for v in got._rows[0][1:]),
                         tuple(v.as_tuple() for v in expected._rows[0][1:]))

    def test_faulting_or_row_dependent_projection_keeps_residual_errors(self):
        from yadinassi.types.values import NULL
        divide='SELECT TOP 1 1/0 AS Marker FROM Catalog.Склады ORDER BY Description'
        with patch.object(DocumentView,'ordered_catalog_values',side_effect=AssertionError('unproven projection')):
            self.assertEqual(self.query(divide),())  # No projection evaluation without a row.
            self.seed_folded_codes()
            with self.assertRaisesRegex(ValueError,'division by zero'):self.bound(divide).execute()
            overflow=('SELECT TOP 1 99999999999999999999999999999999999999+1 AS Marker '
                      'FROM Catalog.Склады ORDER BY Description')
            with self.assertRaisesRegex(ValueError,'Number range exceeded'):self.bound(overflow).execute()
            rows=self.query('SELECT TOP 1 Null+1 AS Marker FROM Catalog.Склады ORDER BY Description')
            self.assertIs(rows[0][0],NULL)

    def test_unordered_point_applies_full_and_before_limit(self):
        from yadinassi.db.query import query_pushdown
        from yadinassi.db.query.relational_queries import _Plan
        self.seed_folded_codes()
        start='SELECT TOP 1 Description FROM Catalog.Склады WHERE '
        self.assertEqual(self.bound(start+'Code=&Key',Key='CASEFOLD').execute()._rows,(('first marked',),))
        for condition in ('Code=&Key AND DeletionMark=FALSE',
                          'DeletionMark=FALSE AND (Description<>"never" AND Code=&Key)'):
            with self.subTest(condition=condition):
                query=self.bound(start+condition,Key='CASEFOLD')
                with patch.object(query_pushdown,'try_ordered_select',return_value=None):
                    self.assertEqual(query.execute()._rows,(('second live',),))
                trace,traced=self.actual_trace()
                with traced, patch.object(_Plan,'load',side_effect=AssertionError('residual input')), \
                        patch.object(_View,'_validate_scan_scalars',side_effect=AssertionError('whole scan')):
                    self.assertEqual(query.execute()._rows,(('second live',),))
                self.assertEqual(len(trace),1,trace)
                where,sep,tail=trace[0].partition(' ORDER BY ')
                self.assertIn('"code" COLLATE yadinassi_casefold_v1',where)
                self.assertIn('"deletion_mark" COLLATE BINARY = 0',where)
                self.assertTrue(sep and tail.endswith('LIMIT 1'),trace)

    def test_point_implied_by_compound_predicate_filters_before_limit(self):
        from yadinassi.db.query import query_pushdown
        from yadinassi.db.query.relational_queries import _Plan
        self.seed_folded_codes(512,codes=('ЁЖ','ёж'))
        start='SELECT TOP 1 Description FROM Catalog.Склады WHERE '
        for condition, second_sql in (
                ('Code=&Key AND (DeletionMark=FALSE OR Description="never")',' OR '),
                ('(Description="never" OR DeletionMark=FALSE) AND Code=&Key',' OR '),
                ('Code=&Key AND DeletionMark=FALSE AND Description=Description',
                 '"description" COLLATE yadinassi_casefold_v1 = "description"'),
                ('Code=&Key AND DeletionMark=FALSE AND Code<>Description',
                 '"code" COLLATE yadinassi_casefold_v1 != "description"'),
                ('(Code=&Key AND Description="never") OR (DeletionMark=FALSE AND Code=&Key)',' OR ')):
            with self.subTest(condition=condition):
                query=self.bound(start+condition,Key='Ёж')
                with patch.object(query_pushdown,'try_ordered_select',return_value=None):
                    self.assertEqual(query.execute()._rows,(('second live',),))
                trace,traced=self.actual_trace()
                with traced, patch.object(_Plan,'load',side_effect=AssertionError('residual input')):
                    self.assertEqual(query.execute()._rows,(('second live',),))
                self.assertEqual(len(trace),1,trace)
                where,sep,tail=trace[0].partition(' ORDER BY ')
                self.assertIn(' WHERE ',where)
                self.assertIn(second_sql,where)
                self.assertIn('"code" COLLATE yadinassi_casefold_v1 =',where)
                self.assertTrue(sep and tail.endswith('LIMIT 1'),trace)

    def test_bound_top_normalizes_equivalent_typed_predicates_to_same_sql(self):
        from yadinassi.db.query import query_pushdown
        from yadinassi.db.query.relational_queries import _Plan
        self.seed_folded_codes(1000,codes=('ЁЖ','ёж'))
        prefix = 'SELECT TOP 1 Description FROM Catalog.Склады WHERE '
        cases = (
            (('Code=&Key', '&Key=Code', '(&Key=Code OR 1=0) AND 1=1'), (('first marked',),)),
            (('Code=&Key AND DeletionMark=FALSE',
              '&Key=Code AND DeletionMark=FALSE',
              'Code=&Key AND DeletionMark=FALSE AND 1=1',
              'Code=&Key AND (DeletionMark=FALSE OR 1=0)',
              '&Key=Code AND (DeletionMark=FALSE OR 1=0)',
              '(1+2=3 AND &Key=Code) AND (1=0 OR FALSE=DeletionMark)'),
             (('second live',),)),
        )
        for variants, expected in cases:
            canonical = None
            for condition in variants:
                with self.subTest(condition=condition):
                    q = self.bound(prefix+condition,Key='Ёж')
                    with patch.object(query_pushdown,'try_ordered_select',return_value=None):
                        self.assertEqual(q.execute()._rows,expected)
                    trace,traced = self.actual_trace()
                    with traced, patch.object(_Plan,'load',side_effect=AssertionError('residual load')):
                        self.assertEqual(q.execute()._rows,expected)
                    self.assertEqual(len(trace),1,trace)
                    self.assertTrue(trace[0].endswith('LIMIT 1'),trace)
                    if canonical is None: canonical = trace[0]
                    else: self.assertEqual(trace[0],canonical)

    def test_top_normalization_preserves_residual_error_order_and_null(self):
        self.seed_folded_codes()
        prefix='SELECT TOP 1 Description FROM Catalog.Склады WHERE '
        cases = (
            ('(1/0=1 OR 1=1) AND &Key=Code','missing', 'division by zero'),
            ('(1=1 OR 1/0=1) AND &Key=Code','CASEFOLD', (('first marked',),)),
            ('&Key=Code AND (1=0 OR 1/0=1)','missing', ()),
            ('&Key=Code AND (1=0 OR 1/0=1)','CASEFOLD', 'division by zero'),
            ('&Key=Code AND (1=1 OR Description=NULL)','CASEFOLD', (('first marked',),)),
            ('&Key=Code AND (1=0 OR Description=NULL)','CASEFOLD', ()),
            ('(&Key=Code OR Description="second live") AND 1=1','missing', (('second live',),)),
        )
        for condition, key, expected in cases:
            with self.subTest(condition=condition,key=key), patch.object(
                    DocumentView,'ordered_catalog_values',side_effect=AssertionError('not eligible')):
                q = self.bound(prefix+condition,Key=key)
                if type(expected) is str:
                    with self.assertRaisesRegex(ValueError,expected):q.execute()
                else:
                    self.assertEqual(q.execute()._rows,expected)

    def test_unordered_point_does_not_accept_partial_or_negative_predicate(self):
        self.seed_folded_codes()
        start='SELECT TOP 1 Description FROM Catalog.Склады WHERE '
        controls=(
            ('Code=&Key OR Description="second live"', 'missing','second live'),
            ('(Code=&Key AND DeletionMark=FALSE) OR Code="CaseFold"','missing','first marked'),
            ('Code=&Key AND (Description=NULL OR DeletionMark=FALSE)','CASEFOLD','second live'),
            ('Code=&Key AND Description=Null','CASEFOLD',None),
            ('Code<>&Key AND DeletionMark=FALSE','CASEFOLD',None),
        )
        for condition, key, expected in controls:
            with self.subTest(condition=condition), patch.object(
                    DocumentView,'ordered_catalog_values',side_effect=AssertionError('partial predicate')):
                self.assertEqual(self.bound(start+condition,Key=key).execute()._rows,
                                 () if expected is None else ((expected,),))
        for condition,key in (
                ('Code=&Key AND (DeletionMark=FALSE OR 1/0=1)','missing'),
                ('Code=&Key AND (DeletionMark=FALSE OR 1/0=1)','CASEFOLD')):
            with self.subTest(key=key), patch.object(
                    DocumentView,'ordered_catalog_values',side_effect=AssertionError('partial predicate')):
                query=self.bound(start+condition,Key=key)
                if key=='missing':
                    self.assertEqual(query.execute()._rows,())
                else:
                    with self.assertRaises((ArithmeticError,ValueError)):
                        query.execute()
        # The configured source's own policy rejects NOT before scanning.
        with self.assertRaisesRegex(ValueError,'NOT remains limited'):
            self.bound(start+'Code=&Key AND NOT (DeletionMark=TRUE)',Key='CASEFOLD').execute()

    def test_distinct_top_one_preserves_concrete_casefold_representative(self):
        self.seed()
        for suffix in (' ORDER BY Description ASC', ' ORDER BY Description DESC'):
            with self.subTest(suffix=suffix):
                text=('SELECT DISTINCT TOP 1 Description, "tag" AS Marker FROM Catalog.Склады '
                      'WHERE Code<="2"'+suffix)
                with patch.object(DocumentView,'ordered_catalog_values',return_value=None) as decline:
                    expected=self.query(text)
                decline.assert_called_once()
                self.assertIn(expected,((('Straße','tag'),),(('STRASSE','tag'),)))
                trace,traced=self.actual_trace()
                with traced, patch.object(_View,'_validate_scan_scalars',side_effect=AssertionError('whole scan')):
                    self.assertEqual(self.query(text),expected)
                self.assertEqual(len(trace),1,trace)
                self.assertNotIn('DISTINCT',trace[0])

    def test_distinct_hidden_order_and_throwing_expression_stay_residual(self):
        self.seed()
        with patch.object(DocumentView,'ordered_catalog_values',side_effect=AssertionError('unsupported pushdown')):
            with self.assertRaisesRegex(Exception,'DISTINCT ordering must use projected expressions'):
                self.query('SELECT DISTINCT TOP 1 Description FROM Catalog.Склады ORDER BY Code')
            self.assertEqual(len(self.query('SELECT DISTINCT TOP 2 Description FROM Catalog.Склады ORDER BY Description')),2)
            with self.assertRaisesRegex(Exception,'division by zero'):
                self.query('SELECT TOP 1 Code, CASE WHEN Code="1" THEN 1 ELSE 1/0 END AS Marker '
                           'FROM Catalog.Склады ORDER BY Code')

    def test_qualified_multiple_keys_filter_and_top_in_one_query(self):
        self.seed()
        trace, traced = self.actual_trace()
        with traced, patch.object(_View,'_validate_scan_scalars',side_effect=AssertionError('whole scan')):
            result = self.query('SELECT TOP 4 W.Code AS C FROM Catalog.Склады AS W '
                                'WHERE W.Code > "1" AND W.DeletionMark = FALSE '
                                'ORDER BY W.Description DESC, C DESC')
        self.assertEqual(result,(('4',),('3',),('7',),('2',)))
        self.assertEqual(len(trace),1,trace)
        self.assertIn('ORDER BY "description" COLLATE yadinassi_casefold_v1 DESC',trace[0])
        self.assertTrue(trace[0].endswith('LIMIT 4'),trace)

    def test_casefold_ties_are_ascending_uuid_even_on_descending_order(self):
        entries, identities = self.seed()
        for descending in (False,True):
            with self.subTest(descending=descending):
                expected = sorted(entries,key=lambda item:identities[item[0]])
                expected.sort(key=lambda item:item[1].casefold(),reverse=descending)
                self.assertEqual(self.query('SELECT TOP 7 W.Code FROM Catalog.Склады AS W '
                                            'ORDER BY W.Description '+('DESC' if descending else 'ASC')),
                                 tuple((code,) for code,_ in expected))

    def test_provider_decline_keeps_exact_order_and_empty_result(self):
        self.seed()
        text = 'SELECT TOP 4 W.Code FROM Catalog.Склады AS W ORDER BY W.Description, W.Code DESC'
        expected = self.query(text)
        with patch.object(DocumentView,'ordered_catalog_values',return_value=None) as decline:
            self.assertEqual(self.query(text),expected)
        decline.assert_called_once()
        self.assertEqual(self.query('SELECT TOP 2 Code FROM Catalog.Склады WHERE Code = "missing" ORDER BY Description'),())

    def test_selected_corrupt_sort_field_rejected_without_materialization(self):
        self.seed()
        table = self.context.backend._layout.table_name(self.manager._schema.identity)
        with closing(sqlite3.connect(self.path)) as connection:
            register_query_collations(connection)
            connection.execute(f'UPDATE "{table}" SET description=? WHERE code=?',('Z'*1000,'1'))
            connection.commit()
        with self.assertRaisesRegex(Exception,'integrity'):
            self.query('SELECT TOP 1 Code FROM Catalog.Склады WHERE Code = "1" ORDER BY Description')
        self.assertEqual(self.query('SELECT TOP 1 Code FROM Catalog.Склады WHERE Code = "2" ORDER BY Description'),(('2',),))
        from yadinassi.db.catalog.catalog_backend import BackendError
        from yadinassi.db.query.relational_queries import _Plan
        with patch.object(_Plan,'load',side_effect=AssertionError('materialized input')), \
                self.assertRaisesRegex(BackendError,'integrity'):
            self.bound('SELECT TOP 1 Code FROM Catalog.Склады WHERE Code="1" AND '
                       '(DeletionMark=FALSE OR Description=Description)').execute()

    def test_explicit_transaction_keeps_existing_scan_and_sees_own_write(self):
        self.seed()
        with patch.object(_View,'_validate_scan_scalars',autospec=True,side_effect=_View._validate_scan_scalars) as validate:
            self.vm.execute('BeginTransaction(); W=Catalogs.Склады.CreateItem(); W.Code="99"; '
                            'W.Description="transaction"; W.Write(); '
                            'Q=New Query("SELECT TOP 1 Code FROM Catalog.Склады WHERE Code = ""99"" ORDER BY Description");'
                            'R=Q.Execute(); RollbackTransaction();')
        self.assertEqual(self.vm.variables['r']._rows,(('99',),))
        self.assertTrue(validate.called)
        self.assertEqual(self.query('SELECT TOP 1 Code FROM Catalog.Склады WHERE Code = "99" ORDER BY Description'),())


class OrderedTopGenericTests(unittest.TestCase):
    setUp = generic.CatalogSectionTests.setUp
    values = generic.CatalogSectionTests.values
    draft = generic.CatalogSectionTests.draft
    create = generic.CatalogSectionTests.create

    def test_unordered_point_on_non_enum_fast_catalog_path(self):
        card = self.draft(code='1')
        self.create(card)
        self.create(self.draft(code='2'))
        db = SQLiteDBContext(self.path)
        self.addCleanup(db.close)
        vm = Interpreter(database_context=db)
        self.addCleanup(vm.close)
        for key,text in (
            ('1','SELECT TOP 1 Code FROM Catalog.Products WHERE Code=&Key'),
            (vm._catalogs.get_index('Products')._ref(card.key.record_id),
             'SELECT TOP 1 Code FROM Catalog.Products WHERE Ref=&Key'),
        ):
            with self.subTest(text=text):
                vm.execute('Q=New Query("' + text + '");')
                query=vm.variables['q'];query.set_parameter('Key',key)
                with patch.object(_View,'_validate_scan_scalars',side_effect=AssertionError('whole scan')):
                    self.assertEqual(query.execute()._rows,(('1',),))

    def test_underlying_document_and_catalog_share_exact_numeric_field_contract(self):
        from yadinassi.db.catalog.catalog_backend import BackendError, CatalogFieldComparison, FieldSchema
        from yadinassi.db.sqlite.sqlite_ordered_predicates import ordered_where
        from yadinassi.db.sqlite.sqlite_typed_rows import encode_number
        with closing(sqlite3.connect(':memory:')) as raw:
            raw.execute('CREATE TABLE probe(a,b)')
            for precision in (12,38):
                field=FieldSchema(uuid4(),'A','number',(precision,2,'Any'))
                other=replace(field,identity=uuid4(),name='B')
                fields={'a':(field,'a'),'b':(other,'b')}
                predicate=CatalogFieldComparison('a','lt','b')
                clause,args=ordered_where(predicate,fields)
                raw.execute('DELETE FROM probe')
                # Use the exact production INTEGER / BLOB ordering and real SQL NULL.
                left,right=Decimal('-1.01'),Decimal('-1.00')
                raw.executemany('INSERT INTO probe VALUES (?,?)',(
                    (encode_number(left,field),encode_number(right,other)),
                    (encode_number(right,field),encode_number(left,other)), (None,None)))
                self.assertEqual(raw.execute('SELECT rowid FROM probe WHERE '+clause,args).fetchall(),[(1,)])
                for differing in ((precision,1,'Any'),(38 if precision==12 else 12,2,'Any')):
                    with self.assertRaisesRegex(BackendError,'unsupported'):
                        ordered_where(predicate,{'a':(field,'a'),'b':(replace(other,qualifiers=differing),'b')})

    def test_out_of_range_bound_decimal_is_not_reordered_or_hidden(self):
        from yadinassi.db.query.queries import BSLQuery
        db=SQLiteDBContext(self.path)
        self.addCleanup(db.close)
        vm=Interpreter(database_context=db)
        self.addCleanup(vm.close)
        self.create(self.draft(code='1'))
        start = 'SELECT TOP 1 Code FROM Catalog.Products WHERE Code=&Key AND '
        for comparison in ('Amount<&Huge', '&Huge>Amount'):
            q=BSLQuery(vm._catalogs,start+'('+comparison+' AND Description=Description)')
            q.set_parameter('Huge',Decimal('1e38'))
            with self.subTest(comparison=comparison), patch.object(
                    _View,'ordered_catalog_values',side_effect=AssertionError('partial filter')):
                q.set_parameter('Key','missing')
                self.assertEqual(q.execute()._rows,())
                q.set_parameter('Key','1')
                with self.assertRaisesRegex(ValueError,'Number range exceeded'):
                    q.execute()

    def test_unordered_key_not_stays_on_generic_residual(self):
        self.create(self.draft(code='1'))
        db=SQLiteDBContext(self.path)
        self.addCleanup(db.close)
        vm=Interpreter(database_context=db)
        self.addCleanup(vm.close)
        with patch.object(_View,'ordered_catalog_values',side_effect=AssertionError('partial predicate')):
            q=vm.execute('New Query("SELECT TOP 1 Code FROM Catalog.Products '
                         'WHERE Code=&Key AND NOT (DeletionMark=TRUE)")')
            q.set_parameter('Key','1')
            self.assertEqual(q.execute()._rows,(('1',),))

    def test_exact_numbers_dates_and_empty_reference_order(self):
        # Direct non-enum path, with custom physical columns and a reference.
        first = self.backend.begin_write(UUID(int=100))
        try:
            category_key = CatalogKey(self.backend.database_id,self.category.identity,UUID(int=1))
            from yadinassi.db.catalog.catalog_backend import CatalogDraft
            first.create(CatalogDraft(category_key,'C1','Category',False,()))
            first.commit()
        finally: first.close()
        for code, amount, day, ref in (('1','10',2,category_key), ('2','2',2,category_key),
                                       ('3','2',1,None), ('4','-1',2,None)):
            draft = self.draft(code=code)
            values = self.values(amount=amount)
            values = (*values[:3],datetime.datetime(2024,1,day),values[-1] if ref is None else ref)
            self.create(replace(draft,values=values))
        db = SQLiteDBContext(self.path)
        self.addCleanup(db.close)
        vm = Interpreter(database_context=db)
        self.addCleanup(vm.close)
        with patch.object(_View,'_validate_scan_scalars',side_effect=AssertionError('whole scan')):
            rows = vm.execute('Q=New Query("SELECT TOP 3 P.Code AS C, P.Amount '
                              'FROM Catalog.Products AS P ORDER BY P.Amount, P.Date DESC, P.Category"); Q.Execute()')._rows
            self.assertEqual(rows,(('4',Decimal('-1.00')),('2',Decimal('2.00')),('3',Decimal('2.00'))))
            rows = vm.execute('Q=New Query("SELECT TOP 2 P.Code AS C FROM Catalog.Products AS P '
                              'ORDER BY P.Category, C"); Q.Execute()')._rows
            self.assertEqual(rows,(('3',),('4',)))


class OrderedTopDocumentTests(unittest.TestCase):
    setUp = main.MainDemoRuntimeTests.setUp
    query = OrderedTopMainDemoTests.query
    actual_trace = OrderedTopMainDemoTests.actual_trace

    def seed(self):
        source = '''
For N=1 To 5 Do
 D=Documents.Receipt.CreateDocument();
 If N=1 Then D.Number="Straße"; D.Date=Date(2024,1,2);
 ElsIf N=2 Then D.Number="STRASSE"; D.Date=Date(2024,1,2);
 ElsIf N=3 Then D.Number="straße"; D.Date=Date(2024,1,1);
 ElsIf N=4 Then D.Number="Я"; D.Date=Date(2024,1,2);
 Else D.Number="ignored"; D.Date=Date(2024,1,1); D.DeletionMark=True;
 EndIf;
 D.Write();
EndDo;
'''
        self.vm.execute(source)

    def test_ordered_document_with_literal_matches_residual(self):
        self.seed()
        text='SELECT TOP 1 Number, "tag" AS Marker FROM Document.Receipt WHERE DeletionMark=FALSE ORDER BY Date,Number'
        with patch.object(DocumentView,'ordered_document_values',return_value=None) as decline:
            expected=self.query(text)
        decline.assert_called_once()
        trace,traced=self.actual_trace()
        from yadinassi.db.query.relational_queries import _Plan
        with traced, patch.object(_Plan,'load',side_effect=AssertionError('materialized input')):
            self.assertEqual(self.query(text),expected)
        self.assertEqual(len(trace),1,trace)
        self.assertTrue(trace[0].endswith('LIMIT 1'),trace)

    def test_document_top_ref_matches_indexed_point_with_or_without_order(self):
        from yadinassi.db.query.relational_queries import _Plan
        self.seed()
        self.vm.execute('R=Documents.Receipt.FindByNumber("Straße");')
        for suffix in ('',' ORDER BY D.Date'):
            with self.subTest(order=suffix):
                text=('SELECT TOP 1 D.Number,1 AS Marker FROM Document.Receipt AS D WHERE D.Ref=&Key'+suffix)
                self.vm.execute('Q=New Query("'+text+'"); Q.SetParameter("Key",R);')
                with patch.object(DocumentView,'ordered_document_values',return_value=None) as decline:
                    self.assertEqual(self.vm.execute('Q.Execute()')._rows,(('Straße',Decimal(1)),))
                decline.assert_called_once()
                trace,traced = self.actual_trace()
                with traced, patch.object(_Plan,'load',side_effect=AssertionError('materialized input')):
                    self.assertEqual(self.vm.execute('Q.Execute()')._rows,(('Straße',Decimal(1)),))
                self.assertEqual(len(trace),1,trace)
                self.assertIn('r.record_id COLLATE BINARY =',trace[0])
                self.assertTrue(trace[0].endswith('LIMIT 1'),trace)
                with closing(sqlite3.connect(self.path)) as raw:
                    register_query_collations(raw)
                    plan = tuple(row[-1] for row in raw.execute('EXPLAIN QUERY PLAN '+trace[0]))
                    self.assertTrue(any('SEARCH r' in operation and 'record_id=?' in operation
                                        for operation in plan),plan)
                self.vm.execute('Q.SetParameter("Key", Documents.Receipt.EmptyRef());')
                self.assertEqual(self.vm.execute('Q.Execute()')._rows,())

    def test_document_ref_compound_orders_and_comparisons_share_selected_page(self):
        from yadinassi.db.query.relational_queries import _Plan
        from yadinassi.db.query.queries import BSLQuery
        self.seed()
        ref=self.vm.execute('Documents.Receipt.FindByNumber("Straße")')
        prefix='SELECT TOP 1 Number FROM Document.Receipt WHERE '
        for condition, expected in (
                ('Ref=&Key AND (DeletionMark=FALSE OR Number="never")', (('Straße',),)),
                ('Ref=&Key AND (Number=Number AND Date=Date)', (('Straße',),)),
                ('Ref=&Key AND (DeletionMark=TRUE OR Number="never")', ())):
            with self.subTest(condition=condition):
                q=BSLQuery(self.vm._catalogs,prefix+condition,self.vm._documents)
                q.set_parameter('Key',ref)
                with patch.object(DocumentView,'ordered_document_values',return_value=None):
                    self.assertEqual(q.execute()._rows,expected)
                trace,traced=self.actual_trace()
                with traced,patch.object(_Plan,'load',side_effect=AssertionError('residual input')):
                    self.assertEqual(q.execute()._rows,expected)
                self.assertEqual(len(trace),1,trace)
                self.assertRegex(trace[0],r'WHERE .*r.record_id COLLATE BINARY = .* ORDER BY .* LIMIT 1$')
        q=BSLQuery(self.vm._catalogs,prefix+'Ref=&Key OR Number="Straße"',self.vm._documents)
        q.set_parameter('Key',self.vm.execute('Documents.Receipt.EmptyRef()'))
        with patch.object(DocumentView,'ordered_document_values',side_effect=AssertionError('disjunctive key')):
            self.assertEqual(q.execute()._rows,(('straße',),))
        for order in ('',' ORDER BY Date'):
            q=BSLQuery(self.vm._catalogs,prefix+'Ref=&Key AND Posted=DeletionMark'+order,self.vm._documents)
            q.set_parameter('Key',ref)
            with patch.object(DocumentView,'ordered_document_values',side_effect=AssertionError('no stored Posted rule')):
                self.assertEqual(q.execute()._rows,(('Straße',),))

    def test_document_point_normalizes_reversed_reference_and_neutral_terms(self):
        from yadinassi.db.query.queries import BSLQuery
        from yadinassi.db.query.relational_queries import _Plan
        self.seed()
        key = self.vm.execute('Documents.Receipt.FindByNumber("Straße")')
        prefix = 'SELECT TOP 1 Number FROM Document.Receipt WHERE '
        for condition in ('Ref=&Key AND DeletionMark=FALSE',
                          '(&Key=Ref OR 1=0) AND (DeletionMark=FALSE AND 1=1)'):
            q = BSLQuery(self.vm._catalogs,prefix+condition,self.vm._documents)
            q.set_parameter('Key',key)
            trace,traced = self.actual_trace()
            with self.subTest(condition=condition):
                with traced, patch.object(_Plan,'load',side_effect=AssertionError('residual load')):
                    self.assertEqual(q.execute()._rows,(('Straße',),))
                self.assertEqual(len(trace),1,trace)
                self.assertIn('r.record_id COLLATE BINARY =',trace[0])
                self.assertTrue(trace[0].endswith('LIMIT 1'),trace)

    def test_document_compounds_respect_parsed_envelope_and_raw_cycles_decline(self):
        from yadinassi.db.catalog.catalog_backend import CatalogComparison, CatalogOrder, CatalogPredicate, CatalogScanRequest
        from yadinassi.db.document.document_backend import DocumentKey
        from yadinassi.db.query.queries import BSLQuery
        from yadinassi.db.query.relational_queries import _Plan
        self.seed()
        ref=self.vm.execute('Documents.Receipt.FindByNumber("Straße")')
        predicate='Number="never"'
        for _ in range(12):
            predicate=f'DeletionMark=FALSE OR (Number="never" AND ({predicate}))'
        q=BSLQuery(self.vm._catalogs,'SELECT TOP 1 Number FROM Document.Receipt WHERE '
                   f'Ref=&Key AND ({predicate})',self.vm._documents)
        q.set_parameter('Key',ref)
        with patch.object(_Plan,'load',side_effect=AssertionError('parsed expression declined')):
            self.assertEqual(q.execute()._rows,(('Straße',),))

        backend=self.context.backend
        identity=self.vm._documents.get_member('Receipt')._schema.identity
        key=CatalogComparison('ref','eq',DocumentKey(backend.database_id,identity,ref.reference_uuid))
        bad=CatalogPredicate('and',())
        object.__setattr__(bad,'terms',(key,bad))
        with closing(backend.begin_query_read(query_language=True)) as view:
            trace=[]
            view._view._connection.set_trace_callback(trace.append)
            for order in ((),(CatalogOrder('date'),)):
                request=CatalogScanRequest(bad,order,1,string_comparison='casefold_v1')
                self.assertIsNone(view.ordered_document_values(identity,request,('number',),scalar_filter=True))
            self.assertEqual(trace,[])
            # The old flat 128-term document envelope remains admitted.
            legacy=CatalogScanRequest(CatalogPredicate('and',(key,)*128),(),1,
                                      string_comparison='casefold_v1')
            self.assertEqual(len(view.ordered_document_values(identity,legacy,('number',)).rows),1)

    def test_document_ref_and_header_filter_with_exact_arithmetic_projection(self):
        from yadinassi.db.query import query_pushdown
        from yadinassi.db.query.relational_queries import _Plan
        self.seed()
        marked=self.vm.variables['d']
        self.vm.execute('Q=New Query("SELECT TOP 1 Number, 1.25+0.75 AS Marker FROM Document.Receipt '
                        'WHERE DeletionMark=TRUE AND (Date>=&First AND Ref=&Key)");')
        q=self.vm.variables['q']
        q.set_parameter('Key',marked.get_member('Ref'))
        q.set_parameter('First',self.vm.execute('Date(2024,1,1)'))
        with patch.object(query_pushdown,'try_ordered_select',return_value=None):
            expected=q.execute()
        trace,traced=self.actual_trace()
        with traced, patch.object(_Plan,'load',side_effect=AssertionError('residual input')):
            got=q.execute()
        self.assertEqual(got._rows,expected._rows)
        self.assertEqual(got._rows,(('ignored',Decimal('2.00')),))
        self.assertEqual(got._columns,expected._columns)
        self.assertEqual(len(trace),1,trace)
        self.assertIn('r.record_id COLLATE BINARY =',trace[0])
        self.assertIn('r.deletion_mark = 1',trace[0])
        self.assertTrue(trace[0].endswith('LIMIT 1'),trace)

    def test_document_top_ref_still_sees_owned_staged_record_and_rollback(self):
        self.vm.execute('''BeginTransaction();
K=Documents.Receipt.GetRef(New UUID());
D=Documents.Receipt.CreateDocument();D.SetNewObjectRef(K);
D.Number="pending";D.Date=Date(2024,1,1);D.Write();
Q=New Query("SELECT TOP 1 D.Number,1 AS Mark FROM Document.Receipt AS D WHERE D.Ref=&Key");
Q.SetParameter("Key",K);Result=Q.Execute();RollbackTransaction();
''')
        self.assertEqual(self.vm.variables['result']._rows,(('pending',Decimal(1)),))
        self.assertEqual(self.vm.execute('Q.Execute()')._rows,())

    def test_number_date_and_ref_same_as_residual_with_stable_ties(self):
        self.seed()
        text = ('SELECT TOP 4 D.Ref AS R, D.Number AS N, D.Date FROM Document.Receipt AS D '
                'WHERE D.DeletionMark = FALSE ORDER BY N DESC, D.Date ASC')
        with patch.object(DocumentView,'ordered_document_values',return_value=None) as decline:
            expected = self.query(text)
        decline.assert_called_once()
        self.assertEqual(tuple(row[1] for row in expected),('Я','straße','STRASSE','Straße'))
        trace, traced = self.actual_trace()
        with traced, patch.object(DocumentView,'_validate_query_source',side_effect=AssertionError('full source')):
            self.assertEqual(self.query(text),expected)
        self.assertEqual(len(trace),1,trace)
        self.assertIn('ORDER BY r.number COLLATE yadinassi_casefold_v1 DESC,r.date COLLATE BINARY ASC',trace[0])
        self.assertTrue(trace[0].endswith('LIMIT 4'),trace)
        text = ('SELECT TOP 3 D.Ref AS R, D.Number FROM Document.Receipt AS D ORDER BY R DESC')
        with patch.object(DocumentView,'ordered_document_values',return_value=None):
            expected = self.query(text)
        self.assertEqual(self.query(text),expected)

    def test_physical_custom_projection_uses_only_used_column(self):
        self.seed()
        trace, traced = self.actual_trace()
        with traced, patch.object(DocumentView,'_validate_query_source',side_effect=AssertionError('full source')):
            rows = self.query('SELECT TOP 2 D.Number, D.State FROM Document.Receipt AS D ORDER BY D.Number')
        self.assertEqual(tuple(number for number,_ in rows),('ignored','straße'))
        self.assertEqual(len(trace),1,trace)
        self.assertIn('LEFT JOIN "document_data_',trace[0])
        self.assertEqual(trace[0].count('a."attr_'),1)
        self.assertNotIn('json_',trace[0])

    def test_document_top_inside_transaction_sees_write_then_rollback(self):
        with patch.object(DocumentView,'_validate_query_source',autospec=True,
                          side_effect=DocumentView._validate_query_source) as validate:
            self.vm.execute('BeginTransaction(); D=Documents.Receipt.CreateDocument(); D.Number="pending"; '
                            'D.Date=Date(2024,1,1); D.Write(); '
                            'Q=New Query("SELECT TOP 1 Number FROM Document.Receipt ORDER BY Date"); '
                            'R=Q.Execute(); RollbackTransaction();')
        self.assertEqual(self.vm.variables['r']._rows,(('pending',),))
        self.assertTrue(validate.called)
        self.assertEqual(self.query('SELECT TOP 1 Number FROM Document.Receipt ORDER BY Date'),())
