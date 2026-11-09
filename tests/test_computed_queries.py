"""Computed catalog reports: bounded host contract, not native parity evidence."""
from decimal import Decimal, Inexact, InvalidOperation, Rounded, localcontext
import unittest
from unittest.mock import patch

from yadinassi import Interpreter
from yadinassi.queries import BSLQuery
from yadinassi.query_parser import parse_query
from yadinassi.sqlite_catalog import _View
from yadinassi.values import NULL
import test_catalog_queries as fixtures


class ComputedQueryTests(unittest.TestCase):
    setUp = fixtures.CatalogQueryTests.setUp
    tearDown = fixtures.CatalogQueryTests.tearDown

    def query(self, text):
        return BSLQuery(self.vm._catalogs, text)

    def rows(self, text):
        return self.query(text).execute()._rows

    def test_arithmetic_precedence_parentheses_and_unary(self):
        self.assertEqual(self.rows('SELECT Amount+2*3 AS A,(Amount+2)*3 AS B,-Amount AS C,+Amount AS D '
                                   'FROM Catalog.Products ORDER BY Code'),
                         tuple((Decimal(n+6),Decimal((n+2)*3),Decimal(-n),Decimal(n)) for n in (10,20,30)))

    def test_literals_parameters_and_reexecution(self):
        query = self.query('SELECT Code,&Rate*Amount AS Total,"label" AS Caption,TRUE AS Flag,3 AS N '
                           'FROM Catalog.Products ORDER BY Code')
        query.set_parameter('Rate',Decimal('1.25'))
        first = query.execute()
        query.set_parameter('Rate',Decimal(2))
        self.assertEqual(first._rows[0],('1',Decimal('12.5'),'label',True,Decimal(3)))
        self.assertEqual(query.execute()._rows[0][1],Decimal(20))
        self.assertEqual(first._rows[0][1],Decimal('12.5'))

    def test_arithmetic_conditions_and_order(self):
        self.assertEqual(self.rows('SELECT Code AS Item,Amount/2 AS Half FROM Catalog.Products '
                                   'WHERE (Amount+5)>=25 AND Amount*2<65 ORDER BY Amount*-1'),
                         (('3',Decimal(15)),('2',Decimal(10))))

    def test_searched_case_first_match_and_lazy_arms(self):
        text = ('SELECT CASE WHEN Amount>=20 THEN Amount*2 WHEN Amount=10 THEN 10 ELSE 1/0 END AS Value '
                'FROM Catalog.Products ORDER BY Code')
        self.assertEqual(self.rows(text),((Decimal(10),),(Decimal(40),),(Decimal(60),)))

    def test_case_without_else_returns_null(self):
        self.assertEqual(self.rows('SELECT CASE WHEN Amount=20 THEN "middle" END AS Label '
                                   'FROM Catalog.Products ORDER BY Code'),((NULL,),('middle',),(NULL,)))

    def test_nested_case_and_coalesce(self):
        self.assertEqual(self.rows('SELECT ISNULL(CASE WHEN Active=TRUE THEN CASE WHEN Amount>10 THEN 7 END END,9) AS N '
                                   'FROM Catalog.Products ORDER BY Code'),((Decimal(9),),(Decimal(9),),(Decimal(7),)))

    def test_isnull_lazy_fallback_and_null_literal(self):
        self.assertEqual(self.rows('SELECT ISNULL(Amount,1/0) AS N,ISNULL(NULL,42) AS F '
                                   'FROM Catalog.Products ORDER BY Code'),
                         tuple((Decimal(n),Decimal(42)) for n in (10,20,30)))

    def test_russian_computed_report(self):
        text = ('ВЫБРАТЬ ВЫБОР КОГДА Amount>10 ТОГДА Amount*2 ИНАЧЕ 0 КОНЕЦ КАК Итог, '
                'ЕСТЬNULL(NULL, "нет") КАК Подпись ИЗ Справочник.Products УПОРЯДОЧИТЬ ПО Amount')
        self.assertEqual(self.rows(text),((Decimal(0),'нет'),(Decimal(40),'нет'),(Decimal(60),'нет')))

    def test_conditional_aggregate_and_aggregate_arithmetic(self):
        self.assertEqual(self.rows('SELECT SUM(CASE WHEN Active=TRUE THEN Amount*2 ELSE 0 END) AS ActiveTotal, '
                                   'SUM(Amount)/COUNT(*) AS Mean,MAX(Amount)-MIN(Amount) AS Spread FROM Catalog.Products'),
                         ((Decimal(80),Decimal(20),Decimal(20)),))

    def test_having_and_order_aggregate_expressions(self):
        text = ('SELECT Active,SUM(Amount)/COUNT(*) AS Mean FROM Catalog.Products GROUP BY Active '
                'HAVING SUM(Amount)*2>=80 ORDER BY SUM(Amount)/COUNT(*) DESC')
        self.assertEqual(self.rows(text),((True,Decimal(20)),))

    def test_grouped_field_inside_case(self):
        self.assertEqual(self.rows('SELECT CASE WHEN Active=TRUE THEN "yes" ELSE "no" END AS Label, '
                                   'SUM(Amount)+1 AS Total FROM Catalog.Products GROUP BY Active ORDER BY Label'),
                         (('no',Decimal(21)),('yes',Decimal(41))))

    def test_computed_group_key(self):
        text = ('SELECT CASE WHEN Amount>10 THEN "high" ELSE "low" END AS Band,COUNT(*) AS N '
                'FROM Catalog.Products GROUP BY CASE WHEN Amount>10 THEN "high" ELSE "low" END ORDER BY Band')
        self.assertEqual(self.rows(text),(('high',Decimal(2)),('low',Decimal(1))))

    def test_distinct_computed_values_and_top_after_order(self):
        self.assertEqual(self.rows('SELECT DISTINCT TOP 1 CASE WHEN Active=TRUE THEN 1 ELSE 0 END AS N '
                                   'FROM Catalog.Products ORDER BY N DESC'),((Decimal(1),),))

    def test_left_join_null_arithmetic_and_default(self):
        text = ('SELECT P.Code AS Item,C.Description AS Caption,ISNULL(CASE WHEN C.Ref IS NOT NULL THEN P.Amount*2 END,0) AS Total '
                'FROM Catalog.Products AS P LEFT JOIN Catalog.Categories AS C ON P.Category=C.Ref AND P.Amount>10 ORDER BY P.Code')
        self.assertEqual(self.rows(text),(('1',NULL,Decimal(0)),('2','target',Decimal(40)),('3','target',Decimal(60))))
        self.assertEqual(self.rows('SELECT P.Amount+Q.Amount AS N FROM Catalog.Products AS P '
                                   'LEFT JOIN Catalog.Products AS Q ON P.Ref=Q.Ref AND Q.Amount>50'),((NULL,),(NULL,),(NULL,)))

    def test_computed_join_condition(self):
        self.assertEqual(self.rows('SELECT P.Code AS Item,Q.Code AS NextItem FROM Catalog.Products AS P '
                                   'JOIN Catalog.Products AS Q ON P.Amount+10=Q.Amount ORDER BY P.Code'),(('1','2'),('2','3')))

    def test_empty_aggregate_default_and_zero_count(self):
        self.assertEqual(self.rows('SELECT ISNULL(SUM(Amount*2),0) AS Total,COUNT(CASE WHEN Active=TRUE THEN Amount END) AS N '
                                   'FROM Catalog.Products WHERE Amount>100'),((Decimal(0),Decimal(0)),))

    def test_computed_distinct_aggregate(self):
        self.assertEqual(self.rows('SELECT SUM(DISTINCT CASE WHEN Active=TRUE THEN 1 ELSE 2 END) AS Total '
                                   'FROM Catalog.Products'),((Decimal(3),),))

    def test_typed_unload_preserves_computed_values(self):
        result = self.query('SELECT Amount*1.25 AS Price,Amount/3 AS Third,CASE WHEN Active=TRUE THEN "long caption" ELSE "x" END AS Label '
                            'FROM Catalog.Products ORDER BY Code').execute()
        table=result.unload()
        for index,row in enumerate(result._rows):
            self.assertEqual(tuple(table.rows[index].get_member(name) for name in ('Price','Third','Label')),row)
        self.assertEqual(table.rows[0].get_member('Third'),Decimal('3.3333333333'))

    def test_bsl_cursor_and_unload_end_to_end(self):
        self.vm.execute('''Q=New Query("SELECT SUM(Amount*2) AS Total, SUM(Amount)/COUNT(*) AS Mean FROM Catalog.Products");
R=Q.Execute();S=R.Select();S.Next();Message(S.Total);Message(S.Mean);T=R.Unload();Message(T[0].Total);''')
        self.assertEqual(self.output,['120','20','120'])

    def test_decimal_context_is_owned(self):
        with localcontext() as context:
            context.prec=2
            context.traps[Inexact]=context.traps[Rounded]=True
            try: Decimal('invalid')
            except InvalidOperation: pass
            before=dict(context.flags)
            self.assertEqual(self.rows('SELECT Amount/3 AS Third,Amount*1.234 AS Product FROM Catalog.Products ORDER BY Code')[0],
                             (Decimal('3.3333333333'),Decimal('12.34')))
            self.assertEqual(dict(context.flags),before)

    def test_invalid_static_types_and_grouping_fail_before_scan(self):
        texts=[
            'SELECT Amount+Text AS N FROM Catalog.Products',
            'SELECT Active*2 AS N FROM Catalog.Products',
            'SELECT CASE WHEN Active=TRUE THEN Amount ELSE Text END AS N FROM Catalog.Products',
            'SELECT ISNULL(Amount,Text) AS N FROM Catalog.Products',
            'SELECT &Missing+1 AS N FROM Catalog.Products',
            'SELECT Amount+COUNT(*) AS N FROM Catalog.Products',
            'SELECT CASE WHEN Amount>0 THEN SUM(Amount) ELSE 0 END AS N FROM Catalog.Products',
            'SELECT SUM(Amount)+1 AS N FROM Catalog.Products HAVING Amount+1>0',
            'SELECT SUM(SUM(Amount)) AS N FROM Catalog.Products',
            'SELECT SUM(CASE WHEN Active=TRUE THEN MAX(Amount) ELSE 0 END) AS N FROM Catalog.Products',
            'SELECT Code FROM Catalog.Products WHERE SUM(Amount)+1>0',
            'SELECT P.Code FROM Catalog.Products AS P JOIN Catalog.Categories AS C ON P.Amount+Later.Amount>0',
        ]
        with patch.object(_View,'scan_catalog_values',side_effect=AssertionError('must not scan')):
            for text in texts:
                with self.subTest(text=text),self.assertRaises((TypeError,ValueError)):self.rows(text)

    def test_inactive_branch_is_statically_validated(self):
        with patch.object(_View,'scan_catalog_values',side_effect=AssertionError('must not scan')):
            for text in ('SELECT CASE WHEN 1=1 THEN Amount ELSE Unknown END AS N FROM Catalog.Products',
                         'SELECT ISNULL(Amount,&Missing) AS N FROM Catalog.Products'):
                with self.subTest(text=text),self.assertRaises((TypeError,ValueError)):self.rows(text)

    def test_divide_by_zero_fails_and_closes_snapshot(self):
        with self.assertRaises((ValueError,ArithmeticError)):
            self.rows('SELECT Amount/(Amount-20) AS N FROM Catalog.Products')
        self.context.backend.begin_read().close()

    def test_numeric_overflow_fails_instead_of_silent_truncation(self):
        with self.assertRaises((ValueError,ArithmeticError)):
            self.rows('SELECT Amount*99999999999999999999999999999999999999 AS N FROM Catalog.Products')
        self.context.backend.begin_read().close()

    def test_snapshot_detached_and_reopen(self):
        from yadinassi.database_context import SQLiteDBContext
        query='SELECT SUM(Amount*2) AS Total FROM Catalog.Products'
        result=self.query(query).execute()
        from pathlib import Path
        self.context.close()
        self.context=SQLiteDBContext(Path(self.temp.name)/'owned.sqlite')
        self.vm=Interpreter(database_context=self.context)
        self.assertEqual(self.rows(query),result._rows)

    def test_null_aggregate_argument_is_not_wildcard(self):
        self.assertEqual(self.rows('SELECT COUNT(NULL) AS N,SUM(NULL) AS Total,AVG(NULL) AS Mean FROM Catalog.Products'),
                         ((Decimal(0),NULL,NULL),))

    def test_projected_parameter_has_bounded_numeric_metadata(self):
        query=self.query('SELECT &N AS N FROM Catalog.Products')
        query.set_parameter('N',Decimal('1e38'))
        with self.assertRaises(ValueError):query.execute()

    def test_conditional_number_output_fits_merged_metadata(self):
        for expression in ('CASE WHEN Active=TRUE THEN 99999999999999999999999999999999999999 ELSE 0.1 END',
                           'ISNULL(99999999999999999999999999999999999999,0.1)'):
            with self.subTest(expression=expression), self.assertRaises(ValueError):
                self.rows('SELECT '+expression+' AS N FROM Catalog.Products')

    def test_null_comparison_and_constant_predicate(self):
        self.assertEqual(self.rows('SELECT Code FROM Catalog.Products WHERE Amount=NULL'),())
        self.assertEqual(self.rows('SELECT Code FROM Catalog.Products WHERE NULL=Amount'),())
        self.assertEqual(self.rows('SELECT COUNT(*) AS N FROM Catalog.Products WHERE 2*3=6'),((Decimal(3),),))

    def test_reference_branches_preserve_identity_and_reject_cross_catalog(self):
        result=self.rows('SELECT CASE WHEN Active=TRUE THEN Category ELSE Category END AS Category FROM Catalog.Products')
        expected=self.vm.execute('C.Ref')
        self.assertTrue(all(row[0]==expected for row in result))
        with patch.object(_View,'scan_catalog_values',side_effect=AssertionError('must not scan')):
            with self.assertRaises(TypeError):
                self.rows('SELECT ISNULL(Category,Ref) AS R FROM Catalog.Products')



class ComputedParserTests(unittest.TestCase):
    def test_expression_depth_is_bounded(self):
        for expression in ('('*40+'Amount'+')'*40,'-'*80+'Amount','ISNULL('*40+'Amount'+',0)'*40,'+'.join(['Amount']*100)):
            with self.subTest(expression=expression),self.assertRaises(ValueError):
                parse_query('SELECT '+expression+' AS N FROM Catalog.Products')

    def test_malformed_expressions_fail_closed(self):
        for expression in ('Amount+', 'CASE END', 'CASE WHEN Amount>0 THEN 1 ELSE 2',
                           'ISNULL(Amount)', 'ISNULL(Amount,0,1)', 'Unknown(Amount)', '(Amount+1'):
            with self.subTest(expression=expression),self.assertRaises(ValueError):
                parse_query('SELECT '+expression+' AS N FROM Catalog.Products')


class ComputedSectionTests(unittest.TestCase):
    def setUp(self):
        import test_relational_queries
        test_relational_queries.RelationalSectionTests.setUp(self)

    def test_owner_section_conditional_price_report(self):
        text=('SELECT P.Code AS Owner,ISNULL(SUM(CASE WHEN L.Amount>10 THEN L.Amount*1.2 ELSE 0 END),0) AS Total '
              'FROM Catalog.Products AS P LEFT JOIN Catalog.Products.Lines AS L ON P.Ref=L.Ref '
              'GROUP BY P.Code ORDER BY P.Code')
        self.assertEqual(BSLQuery(self.vm._catalogs,text).execute()._rows,
                         (('10',Decimal('24.12')),('20',Decimal('118.8')),('30',Decimal(0))))

    def test_engine_neutral_read_port_supports_expressions(self):
        import test_relational_queries
        # Reuse the independent in-memory CatalogReadView contract and upgrade
        # its report projection, without invoking SQLite from the executor.
        def rows(text):
            text=text.replace('SUM(L.Amount) AS Total','SUM(L.Amount*2) AS Total')
            result=BSLQuery(self.vm._catalogs,text).execute()._rows
            return tuple((owner,total/Decimal(2)) for owner,total in result)
        self.rows=rows
        test_relational_queries.RelationalSectionTests.test_port_has_no_sql_or_backend_handle_dependency(self)


if __name__=='__main__': unittest.main()
