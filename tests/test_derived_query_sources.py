"""Bounded derived-table reporting contract, not native parity evidence."""
from decimal import Decimal
import unittest
from unittest.mock import patch

from yadinassi import Interpreter, query_parser as syntax
from yadinassi.queries import BSLQuery
from yadinassi.query_packages import BSLTempTablesManager
from yadinassi.values import NULL
from yadinassi.sqlite_catalog import _View
import test_catalog_queries as catalog_fixtures
import test_document_queries as document_fixtures
import test_periodic_information_registers as register_fixtures
from test_query_sources import table, number, string


class DerivedGrammarTests(unittest.TestCase):
    def test_alias_and_closed_recursive_ast(self):
        q = syntax.parse_query('SELECT D.N FROM (SELECT Amount AS N FROM Catalog.Products) AS D')
        self.assertEqual(q.source_alias, 'D')
        self.assertEqual(q.derived.projections[0].alias, 'N')
        self.assertEqual(len(tuple(syntax.selects((q,)))), 2)
        self.assertTrue(syntax.extended_filters(q))

    def test_join_derived_union_ast(self):
        q = syntax.parse_query('SELECT P.Code FROM Catalog.Products AS P FULL OUTER JOIN '
            '(SELECT Code AS C FROM Catalog.Products UNION ALL SELECT Code FROM Catalog.Products) AS D ON P.Code=D.C')
        self.assertEqual(q.joins[0].kind, 'full')
        self.assertIs(type(q.joins[0].source.derived), syntax.Union)

    def test_derived_alias_is_required(self):
        for text in ('SELECT Code FROM (SELECT Code FROM Catalog.Products)',
                     'SELECT D.Code FROM (SELECT Code FROM Catalog.Products) D',
                     'SELECT D.Code FROM (Catalog.Products) AS D'):
            with self.subTest(text=text), self.assertRaises(ValueError): syntax.parse_query(text)

    def test_nested_into_and_writes_are_closed(self):
        for inner in ('SELECT Code INTO T FROM Catalog.Products',
                      'SELECT Code INTO T FROM Catalog.Products UNION SELECT Code FROM Catalog.Products',
                      'DESTROY T', 'DELETE FROM Catalog.Products'):
            with self.subTest(inner=inner), self.assertRaises(ValueError):
                syntax.parse_query('SELECT D.Code FROM (' + inner + ') AS D')

    def test_duplicate_source_and_output_names(self):
        for text in (
            'SELECT D.N FROM (SELECT Amount AS N, Amount AS n FROM Catalog.Products) AS D',
            'SELECT D.N FROM (SELECT Amount AS N FROM Catalog.Products) AS D JOIN Catalog.Products AS d ON D.N=d.Amount',
        ):
            with self.subTest(text=text), self.assertRaises(ValueError): syntax.parse_query(text)

    def test_shared_depth_bound_with_membership(self):
        text = 'SELECT Amount AS N FROM Catalog.Products'
        for _ in range(9): text = 'SELECT D.N FROM (' + text + ') AS D'
        with self.assertRaisesRegex(ValueError, 'subquery budget'): syntax.parse_query(text)
        text = 'SELECT Amount AS N FROM Catalog.Products WHERE Amount IN (SELECT Amount FROM Catalog.Products)'
        for _ in range(8): text = 'SELECT D.N FROM (' + text + ') AS D'
        with self.assertRaisesRegex(ValueError, 'subquery budget'): syntax.parse_query(text)

    def test_right_full_require_predicate_and_lateral_is_closed(self):
        for text in ('SELECT P.Code FROM Catalog.Products AS P RIGHT JOIN Catalog.Products AS Q',
                     'SELECT D.N FROM LATERAL (SELECT Amount AS N FROM Catalog.Products) AS D',
                     'SELECT P.Code FROM Catalog.Products AS P FULL CROSS JOIN Catalog.Products AS Q ON P.Ref=Q.Ref'):
            with self.subTest(text=text), self.assertRaises(ValueError): syntax.parse_query(text)


class DerivedQueryTests(unittest.TestCase):
    setUp = catalog_fixtures.CatalogQueryTests.setUp
    tearDown = catalog_fixtures.CatalogQueryTests.tearDown

    def query(self, text, parameters=(), manager=None):
        q = BSLQuery(self.vm._catalogs, text)
        for name, value in parameters: q.set_parameter(name, value)
        if manager is not None: q.set_member('TempTablesManager', manager)
        return q

    def rows(self, text, parameters=(), manager=None):
        return self.query(text, parameters, manager).execute()._rows

    def test_projection_filter_and_order(self):
        self.assertEqual(self.rows('SELECT D.Item,D.N FROM '
            '(SELECT Code AS Item, Amount+5 AS N FROM Catalog.Products) AS D WHERE D.N>15 ORDER BY D.Item DESC'),
            (('3',Decimal(35)),('2',Decimal(25))))

    def test_nested_derived_aggregate_having(self):
        self.assertEqual(self.rows('SELECT X.N FROM (SELECT SUM(D.Amount) AS N FROM '
            '(SELECT Amount FROM Catalog.Products WHERE Active=TRUE) AS D HAVING SUM(D.Amount)>30) AS X'),
            ((Decimal(40),),))

    def test_union_inside_derived_and_outer_grouping(self):
        self.assertEqual(self.rows('SELECT D.N,COUNT(*) AS C FROM '
            '(SELECT Amount AS N FROM Catalog.Products UNION ALL SELECT Amount FROM Catalog.Products) AS D '
            'GROUP BY D.N ORDER BY D.N'), ((Decimal(10),Decimal(2)),(Decimal(20),Decimal(2)),(Decimal(30),Decimal(2))))

    def test_top_inner_then_top_outer(self):
        self.assertEqual(self.rows('SELECT TOP 1 D.Item FROM '
            '(SELECT TOP 2 Code AS Item FROM Catalog.Products ORDER BY Code DESC) AS D ORDER BY D.Item'),(('2',),))

    def test_derived_inside_union(self):
        self.assertEqual(self.rows('SELECT D.N FROM (SELECT Amount AS N FROM Catalog.Products WHERE Amount=10) AS D '
            'UNION SELECT E.N FROM (SELECT Amount AS N FROM Catalog.Products WHERE Amount=20) AS E ORDER BY N'),
            ((Decimal(10),),(Decimal(20),)))

    def test_distinct_and_reused_alias_scope(self):
        self.assertEqual(self.rows('SELECT DISTINCT D.N FROM '
            '(SELECT D.Amount AS N FROM Catalog.Products AS D JOIN Catalog.Categories AS C ON D.Category=C.Ref) AS D ORDER BY D.N'),
            ((Decimal(10),),(Decimal(20),),(Decimal(30),)))

    def test_derived_join_catalog_and_references(self):
        # Reference ordering stays closed; equality retains exact snapshot identity.
        result = self.query('SELECT D.Item,D.R FROM (SELECT Code AS Item,Ref AS R,Category AS C FROM Catalog.Products) AS D '
            'JOIN Catalog.Categories AS C ON D.C=C.Ref ORDER BY D.Item').execute()
        self.assertEqual([r[0] for r in result._rows], ['1','2','3'])
        self.assertEqual(result._rows[0][1].get_member('Code'), '1')
        with self.assertRaisesRegex(ValueError, 'dynamic reference'): result.unload()

    def test_reference_type_mismatch_rejected_before_scan(self):
        text = 'SELECT D.R FROM (SELECT Ref AS R FROM Catalog.Products) AS D JOIN Catalog.Categories AS C ON D.R=C.Ref'
        with patch.object(_View, 'scan_catalog_values', side_effect=AssertionError('must not scan')):
            with self.assertRaises(TypeError): self.rows(text)

    def test_right_join_unmatched_left(self):
        self.assertEqual(self.rows('SELECT D.Item,P.Code AS Code FROM '
            '(SELECT Code AS Item FROM Catalog.Products WHERE Amount<20) AS D '
            'RIGHT JOIN Catalog.Products AS P ON D.Item=P.Code ORDER BY Code'),
            (('1','1'),(NULL,'2'),(NULL,'3')))

    def test_full_join_both_unmatched_sides(self):
        self.assertEqual(self.rows('SELECT L.N AS A,R.N AS B FROM '
            '(SELECT Amount AS N FROM Catalog.Products WHERE Amount<=20) AS L '
            'FULL JOIN (SELECT Amount AS N FROM Catalog.Products WHERE Amount>=20) AS R ON L.N=R.N ORDER BY A,B'),
            ((NULL,Decimal(30)),(Decimal(10),NULL),(Decimal(20),Decimal(20))))

    def test_full_join_residual_predicate_and_duplicate_rows(self):
        self.assertEqual(self.rows('SELECT L.N AS A,R.N AS B FROM '
            '(SELECT Amount AS N FROM Catalog.Products WHERE Amount=10) AS L '
            'FULL JOIN (SELECT Amount AS N FROM Catalog.Products WHERE Amount=10 UNION ALL '
            'SELECT Amount FROM Catalog.Products WHERE Amount=10) AS R ON L.N=R.N AND L.N>20 ORDER BY A,B'),
            ((NULL,Decimal(10)),(NULL,Decimal(10)),(Decimal(10),NULL)))

    def test_right_join_preserves_duplicate_matches(self):
        self.assertEqual(self.rows('SELECT L.N AS A,R.N AS B FROM '
            '(SELECT Amount AS N FROM Catalog.Products WHERE Amount=10) AS L '
            'RIGHT JOIN (SELECT Amount AS N FROM Catalog.Products WHERE Amount=10 UNION ALL '
            'SELECT Amount FROM Catalog.Products WHERE Amount=10) AS R ON L.N=R.N'),
            ((Decimal(10),Decimal(10)),(Decimal(10),Decimal(10))))

    def test_right_join_nullifies_all_prior_sources(self):
        self.assertEqual(self.rows('SELECT P.Code AS P,C.Code AS C,Q.Code AS Q FROM Catalog.Products AS P '
            'JOIN Catalog.Categories AS C ON P.Category=C.Ref '
            'RIGHT JOIN Catalog.Products AS Q ON P.Code=Q.Code AND P.Amount<20 ORDER BY Q'),
            (('1','01','1'),(NULL,NULL,'2'),(NULL,NULL,'3')))

    def test_outer_join_empty_input_and_aggregate(self):
        self.assertEqual(self.rows('SELECT COUNT(*) AS C,COUNT(L.N) AS L,SUM(R.N) AS Total FROM '
            '(SELECT Amount AS N FROM Catalog.Products WHERE Amount>99) AS L '
            'FULL JOIN (SELECT Amount AS N FROM Catalog.Products) AS R ON L.N=R.N'),
            ((Decimal(3),Decimal(0),Decimal(60)),))
        for kind, expected in (('RIGHT', Decimal(0)), ('FULL', Decimal(3))):
            self.assertEqual(self.rows('SELECT COUNT(*) AS C FROM '
                '(SELECT Amount AS N FROM Catalog.Products) AS L ' + kind + ' JOIN '
                '(SELECT Amount AS N FROM Catalog.Products WHERE Amount>99) AS R ON L.N=R.N'),
                ((expected,),))
        self.assertEqual(self.rows('SELECT COUNT(*) AS C FROM '
            '(SELECT Amount AS N FROM Catalog.Products WHERE Amount>99) AS L FULL JOIN '
            '(SELECT Amount AS N FROM Catalog.Products WHERE Amount>99) AS R ON L.N=R.N'), ((Decimal(0),),))

    def test_null_equality_is_not_a_join_match(self):
        self.assertEqual(self.rows('SELECT COUNT(*) AS C FROM '
            '(SELECT CASE WHEN Amount=10 THEN NULL ELSE Amount END AS N FROM Catalog.Products WHERE Amount=10) AS L '
            'FULL JOIN (SELECT CASE WHEN Amount=10 THEN NULL ELSE Amount END AS N FROM Catalog.Products WHERE Amount=10) AS R '
            'ON L.N=R.N'), ((Decimal(2),),))

    def test_russian_derived_right_full_join(self):
        for keyword in ('ПРАВОЕ ВНЕШНЕЕ', 'ПОЛНОЕ ВНЕШНЕЕ'):
            self.assertEqual(self.rows('ВЫБРАТЬ Д.Н ИЗ (ВЫБРАТЬ Amount КАК Н ИЗ Справочник.Products) КАК Д '
                +keyword+' СОЕДИНЕНИЕ Справочник.Products КАК П ПО Д.Н=П.Amount УПОРЯДОЧИТЬ ПО Д.Н'),
                ((Decimal(10),),(Decimal(20),),(Decimal(30),)))

    def test_nested_membership_and_shared_snapshot(self):
        text = 'SELECT D.Item FROM (SELECT Code AS Item,Amount FROM Catalog.Products WHERE Amount IN '
        text += '(SELECT X.N FROM (SELECT Amount AS N FROM Catalog.Products) AS X WHERE X.N<30)) AS D ORDER BY D.Item'
        backend = self.context.backend
        with patch.object(backend, 'begin_read', wraps=backend.begin_read) as begin:
            self.assertEqual(self.rows(text), (('1',),('2',)))
            self.assertEqual(begin.call_count, 1)

    def test_external_value_table_nested_source(self):
        value = table([('N', number())], [(Decimal(20),)])
        self.assertEqual(self.rows('SELECT P.Code AS Item FROM Catalog.Products AS P JOIN '
            '(SELECT N FROM &Input) AS D ON P.Amount=D.N', [('Input',value)]), (('2',),))

    def test_derived_metadata_qualifiers_and_nullable_unload(self):
        result = self.query('SELECT D.N,D.S FROM (SELECT Amount AS N,Text AS S FROM Catalog.Products) AS D WHERE D.N>100').execute()
        self.assertEqual([c.kind for c in result._columns], ['number','string'])
        self.assertEqual(result._columns[0].qualifiers, (12,2,'Any'))
        self.assertEqual(len(result.unload().rows), 0)
        result = self.query('SELECT D.N FROM (SELECT Amount AS N FROM Catalog.Products WHERE Amount>100) AS D '
                            'RIGHT JOIN Catalog.Categories AS C ON D.N=10').execute()
        self.assertIs(result._rows[0][0],NULL)
        self.assertIs(result.unload().rows[0].get(Decimal(0)),NULL)
        full=self.query('SELECT L.N AS A,R.N AS B FROM '
            '(SELECT Amount AS N FROM Catalog.Products WHERE Amount=10) AS L FULL JOIN '
            '(SELECT Amount AS N FROM Catalog.Products WHERE Amount=20) AS R ON L.N=R.N').execute().unload()
        self.assertEqual(len(full.columns.items),2)
        self.assertEqual([c.value_type.number_qualifiers.fraction_digits for c in full.columns.items],
                         [Decimal(2),Decimal(2)])
        self.assertEqual(sum(value is NULL for row in full.rows for value in row),2)

    def test_localized_column_names_are_explicit(self):
        self.assertEqual(self.rows('SELECT D.Код FROM (SELECT Code FROM Catalog.Products WHERE Amount=10) AS D'),(('1',),))
        with self.assertRaises(ValueError): self.rows('SELECT D.Code FROM (SELECT Code FROM Catalog.Products) AS D')

    def test_ambiguous_column_and_outer_correlation_fail_before_scan(self):
        with patch.object(_View,'scan_catalog_values',side_effect=AssertionError('must not scan')):
            for text in ('SELECT N FROM (SELECT Amount AS N FROM Catalog.Products) AS A '
                         'JOIN (SELECT Amount AS N FROM Catalog.Products) AS B ON A.N=B.N',
                         'SELECT P.Code FROM Catalog.Products AS P JOIN '
                         '(SELECT Amount AS N FROM Catalog.Products AS Q WHERE Q.Amount=P.Amount) AS D ON D.N=P.Amount',
                         'SELECT D.Unknown FROM (SELECT Amount AS N FROM Catalog.Products) AS D'):
                with self.subTest(text=text),self.assertRaises(ValueError): self.rows(text)

    def test_null_only_derived_column_refused_but_typed_union_admitted(self):
        with self.assertRaises(TypeError): self.rows('SELECT D.N FROM (SELECT NULL AS N FROM Catalog.Products) AS D')
        self.assertEqual(self.rows('SELECT COUNT(*) AS C FROM (SELECT NULL AS N FROM Catalog.Products '
            'UNION ALL SELECT Amount FROM Catalog.Products) AS D'),((Decimal(6),),))

    def test_package_derived_into_and_destroy(self):
        manager=BSLTempTablesManager()
        q=self.query('SELECT Amount AS N INTO Input FROM Catalog.Products; '
            'SELECT D.N INTO Output FROM (SELECT N FROM Input WHERE N>=20) AS D; '
            'SELECT D.N FROM (SELECT N FROM Output) AS D ORDER BY D.N; DESTROY Input',manager=manager)
        outputs=q.execute_batch().items
        self.assertEqual(outputs[2]._rows,((Decimal(20),),(Decimal(30),)))
        self.assertEqual(set(manager._tables),{'output'})

    def test_failed_derived_package_does_not_publish_temps(self):
        manager=BSLTempTablesManager()
        with self.assertRaises(ValueError):
            self.query('SELECT Amount AS N INTO Input FROM Catalog.Products; '
                       'SELECT D.Bad FROM (SELECT N FROM Input) AS D',manager=manager).execute_batch()
        self.assertEqual(manager._tables,{})
        self.assertEqual(self.rows('SELECT COUNT(*) AS C FROM Catalog.Products'),((Decimal(3),),))

    def test_derived_resource_budget_includes_unprojected_columns(self):
        import yadinassi.queries as queries
        text='SELECT D.N FROM (SELECT Amount AS N,Text AS Large FROM Catalog.Products) AS D'
        with patch.object(queries,'_MAX_CELLS',7):
            with self.assertRaisesRegex(ValueError,'resource limit'): self.rows(text)
        self.assertEqual(len(self.rows(text)),3)

    def test_global_join_work_shared_across_derived_plans(self):
        import yadinassi.relational_queries as relational
        text='SELECT L.N FROM (SELECT P.Amount AS N FROM Catalog.Products AS P '
        text+='JOIN Catalog.Products AS Q ON P.Ref=Q.Ref) AS L JOIN '
        text+='(SELECT P.Amount AS N FROM Catalog.Products AS P JOIN Catalog.Products AS Q ON P.Ref=Q.Ref) AS R ON L.N=R.N'
        with patch.object(relational,'MAX_JOIN_PAIRS',5):
            with self.assertRaisesRegex(ValueError,'work limit'): self.rows(text)
        self.assertEqual(len(self.rows(text)),3)

    def test_outer_null_rows_obey_intermediate_limit(self):
        import yadinassi.relational_queries as relational
        text='SELECT P.Code FROM Catalog.Products AS P FULL JOIN Catalog.Products AS Q ON P.Amount>100'
        with patch.object(relational,'MAX_INTERMEDIATE_ROWS',4):
            with self.assertRaisesRegex(ValueError,'intermediate row'): self.rows(text)

    def test_bsl_multilayer_report_end_to_end(self):
        self.vm.execute('Q=New Query("SELECT D.Total FROM (SELECT SUM(Amount) AS Total FROM Catalog.Products WHERE Active=TRUE) AS D");'
                        'S=Q.Execute().Select();Message(S.Next());Message(S.Total);')
        self.assertEqual(self.output,['Да','40'])


class DerivedDocumentTests(unittest.TestCase):
    setUp=document_fixtures.DocumentQueryTests.setUp
    tearDown=document_fixtures.DocumentQueryTests.tearDown
    seed=document_fixtures.DocumentQueryTests.seed

    def test_catalog_joins_derived_document_on_one_composite_snapshot(self):
        self.seed(); self.vm=Interpreter(database_context=self.context)
        q=BSLQuery(self.vm._catalogs,'SELECT C.Code AS Item,D.Total FROM Catalog.Categories AS C JOIN '
            '(SELECT Category AS Customer,SUM(Amount) AS Total FROM Document.Orders GROUP BY Category) AS D '
            'ON C.Ref=D.Customer',documents=self.vm._documents)
        with patch.object(self.context.backend,'begin_query_read',wraps=self.context.backend.begin_query_read) as begin:
            self.assertEqual(q.execute()._rows,(('01',Decimal(60)),));self.assertEqual(begin.call_count,1)

    def test_document_reference_column_through_two_derived_layers(self):
        self.seed()
        q=BSLQuery(self.vm._catalogs,'SELECT X.R FROM (SELECT D.R FROM (SELECT Ref AS R,Number FROM Document.Orders) AS D '
                   'WHERE D.Number="000000001") AS X',documents=self.vm._documents)
        result=q.execute();self.assertEqual(result._rows[0][0].get_member('Number'),'000000001')
        with self.assertRaisesRegex(ValueError, 'dynamic reference'):result.unload()

    def test_derived_document_sections_grouped_before_join(self):
        self.seed()
        q=BSLQuery(self.vm._catalogs,'SELECT D.Number,L.Total FROM Document.Orders AS D LEFT JOIN '
            '(SELECT Ref AS Owner,SUM(Amount) AS Total FROM Document.Orders.Lines GROUP BY Ref) AS L '
            'ON D.Ref=L.Owner ORDER BY D.Number',documents=self.vm._documents)
        self.assertEqual(q.execute()._rows,(('000000001',Decimal(5)),('000000002',Decimal(10)),('000000003',Decimal(15))))


class DerivedRegisterTests(unittest.TestCase):
    setUp=register_fixtures.PeriodicRegisterTests.setUp
    execute=register_fixtures.PeriodicRegisterTests.execute
    seed=register_fixtures.PeriodicRegisterTests.seed
    query=register_fixtures.PeriodicRegisterTests.query

    def test_derived_periodic_slice_and_aggregate(self):
        from yadinassi.dates import literal_date
        self.seed()
        q=self.query('SELECT SUM(D.Price) AS Total FROM '
            '(SELECT Item,Price FROM InformationRegister.Prices.SliceLast(&At)) AS D',literal_date('20240102120000'))
        with patch.object(self.context.backend,'begin_query_read',wraps=self.context.backend.begin_query_read) as begin:
            self.assertEqual(q.execute()._rows,((Decimal(27),),));self.assertEqual(begin.call_count,1)

    def test_nested_register_membership_from_derived_source(self):
        self.seed()
        q=self.query('SELECT D.Item FROM (SELECT Item,Price FROM InformationRegister.Prices) AS D '
            'WHERE D.Price IN (SELECT X.N FROM (SELECT Price AS N FROM InformationRegister.Prices WHERE Price>20) AS X)')
        self.assertEqual(q.execute()._rows,(('A',),))
