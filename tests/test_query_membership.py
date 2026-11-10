"""Owned three-valued query predicate contract, not native parity evidence."""
from decimal import Decimal
from unittest.mock import patch
import unittest

from yadinassi import query_parser as syntax
from yadinassi.queries import BSLQuery
from yadinassi.query_packages import BSLTempTablesManager
from yadinassi.values import BSLArray, BSLFixedArray, NULL
from yadinassi.relational_queries import _compare
import test_catalog_queries as fixtures
import test_document_queries as document_fixtures


def array(*items):
    result = BSLArray()
    result.items.extend(items)
    return result


class MembershipTests(unittest.TestCase):
    setUp = fixtures.CatalogQueryTests.setUp
    tearDown = fixtures.CatalogQueryTests.tearDown

    def query(self, text, params=(), manager=None):
        # Fixture comparisons assert an explicit output order, never UUID scan order.
        if text.startswith('SELECT Code FROM Catalog.Products') and ';' not in text and 'ORDER BY' not in text:
            text += ' ORDER BY Code'
        result = BSLQuery(self.vm._catalogs, text)
        for name, value in params: result.set_parameter(name, value)
        if manager is not None: result.set_member('TempTablesManager', manager)
        return result

    def rows(self, text, params=(), manager=None):
        return self.query(text, params, manager).execute()._rows

    def test_not_and_between_precedence(self):
        self.assertEqual(self.rows('SELECT Code FROM Catalog.Products WHERE NOT Amount BETWEEN 10 AND 20'), (('3',),))
        self.assertEqual(self.rows('SELECT Code FROM Catalog.Products WHERE Amount NOT BETWEEN 10 AND 20'), (('3',),))
        self.assertEqual(self.rows('SELECT Code FROM Catalog.Products WHERE NOT NOT Amount=20'), (('2',),))
        self.assertEqual(self.rows('SELECT Code FROM Catalog.Products WHERE Amount BETWEEN 10 AND 20 AND NOT Active=FALSE'), (('1',),))

    def test_in_lists_and_computed_expressions(self):
        self.assertEqual(self.rows('SELECT Code FROM Catalog.Products WHERE Amount IN (10,20+10)'), (('1',),('3',)))
        self.assertEqual(self.rows('SELECT Code FROM Catalog.Products WHERE (Amount+0) NOT IN (10,20)'), (('3',),))
        self.assertEqual(self.rows('SELECT Code FROM Catalog.Products WHERE Amount IN (Amount+0,0)'), (('1',),('2',),('3',)))
        self.assertEqual(self.rows('SELECT Code FROM Catalog.Products WHERE Amount IN (&A,30)', [('A', Decimal(10))]), (('1',),('3',)))

    def test_russian_membership_and_negation(self):
        self.assertEqual(self.rows('ВЫБРАТЬ Code ИЗ Справочник.Products ГДЕ НЕ Amount В (10,20)'), (('3',),))
        self.assertEqual(self.rows('ВЫБРАТЬ Code ИЗ Справочник.Products ГДЕ Amount НЕ МЕЖДУ 10 И 20'), (('3',),))

    def test_casefold_string_and_exact_boolean(self):
        self.assertEqual(self.rows('SELECT Code FROM Catalog.Products WHERE Text IN ("TEXT")'), (('1',),('2',),('3',)))
        self.assertEqual(self.rows('SELECT Code FROM Catalog.Products WHERE Active IN (FALSE)'), (('2',),))
        with self.assertRaises(TypeError): self.rows('SELECT Code FROM Catalog.Products WHERE Active IN (0)')

    def test_array_and_fixed_array_parameters(self):
        for value in (array(Decimal(10), Decimal(30)), BSLFixedArray(array(Decimal(10), Decimal(30)))):
            with self.subTest(type=type(value).__name__):
                self.assertEqual(self.rows('SELECT Code FROM Catalog.Products WHERE Amount IN &Values', [('Values', value)]), (('1',),('3',)))

    def test_array_snapshot_observes_changes_before_execution_not_during_read(self):
        values = array(Decimal(10))
        query = self.query('SELECT Code FROM Catalog.Products WHERE Amount IN &Values', [('Values', values)])
        values.items.append(Decimal(20))
        from yadinassi.sqlite_catalog import _View
        original = _View.scan_catalog_values
        def scan(view, *args, **kwargs):
            values.items[:] = [Decimal(30)]
            return original(view, *args, **kwargs)
        with patch.object(_View, 'scan_catalog_values', scan):
            self.assertEqual(query.execute()._rows, (('1',),('2',)))
        self.assertEqual(query.execute()._rows, (('3',),))

    def test_empty_and_null_list_truth(self):
        self.assertEqual(self.rows('SELECT Code FROM Catalog.Products WHERE Amount IN &V', [('V', array())]), ())
        self.assertEqual(len(self.rows('SELECT Code FROM Catalog.Products WHERE Amount NOT IN &V', [('V', array())])), 3)
        self.assertEqual(self.rows('SELECT Code FROM Catalog.Products WHERE Amount NOT IN &V', [('V', array(Decimal(10), NULL))]), ())
        self.assertEqual(self.rows('SELECT Code FROM Catalog.Products WHERE Amount IN &V', [('V', array(Decimal(10), NULL))]), (('1',),))

    def test_unknown_not_and_truth_tables(self):
        self.assertIsNone(_compare(NULL, Decimal(1), 'eq'))
        for predicate, count in [
            ('NOT (NULL=1)', 0), ('NOT (NULL=1 AND 1=0)', 3),
            ('NOT (NULL=1 OR 1=1)', 0), ('NULL=1 OR 1=1', 3),
            ('NOT (NULL=1 OR 1=0)', 0), ('NOT (NULL=1 AND 1=1)', 0),
            ('NULL IN (1,NULL)',0), ('NULL NOT IN (1)',0),
            ('1 NOT IN (2,NULL)',0), ('1 IN (1,NULL)',3),
        ]:
            with self.subTest(predicate=predicate):
                self.assertEqual(len(self.rows('SELECT Code FROM Catalog.Products WHERE '+predicate)), count)

    def test_unknown_case_else(self):
        self.assertEqual(self.rows('SELECT CASE WHEN NOT (NULL=1) THEN 7 ELSE 9 END AS N FROM Catalog.Products'),
                         ((Decimal(9),),)*3)

    def test_list_types_checked_on_empty_sources(self):
        for predicate in ('Amount IN (10,"x")', 'Amount BETWEEN TRUE AND FALSE', 'NULL IN (1,"x")'):
            with self.subTest(predicate=predicate), self.assertRaises(TypeError):
                self.rows('SELECT Code FROM Catalog.Products WHERE Code="missing" AND '+predicate)

    def test_bad_array_types_and_bounds(self):
        for value in (array(Decimal(1), '1'), array(array(Decimal(1))), array(object()), array(Decimal('NaN'))):
            with self.subTest(value=type(value).__name__), self.assertRaises((TypeError,ValueError)):
                self.rows('SELECT Code FROM Catalog.Products WHERE Amount IN &V', [('V', value)])
        with self.assertRaises(ValueError):
            self.rows('SELECT Code FROM Catalog.Products WHERE Amount IN &V', [('V', array(*([Decimal(1)]*10001)))])

    def test_scalar_and_table_parameters_are_not_membership_lists(self):
        for value in (Decimal(10), '10', True):
            with self.subTest(value=value), self.assertRaises(TypeError):
                self.rows('SELECT Code FROM Catalog.Products WHERE Amount IN &V', [('V',value)])
        with self.assertRaises(TypeError):
            self.rows('SELECT Code FROM Catalog.Products WHERE Amount=&V', [('V',array(Decimal(10)))])

    def test_hostile_type_rejected_without_hooks(self):
        calls=[]
        class Meta(type):
            def __eq__(cls, other): calls.append('eq'); raise AssertionError()
            def __hash__(cls): calls.append('hash'); raise AssertionError()
        class Bad(metaclass=Meta): pass
        with self.assertRaises(TypeError):
            self.rows('SELECT Code FROM Catalog.Products WHERE Amount IN &V', [('V',array(Bad()))])
        self.assertEqual(calls,[])

    def test_in_subquery(self):
        self.assertEqual(self.rows('SELECT Code FROM Catalog.Products WHERE Amount IN (SELECT Amount FROM Catalog.Products WHERE Active=TRUE) ORDER BY Code'), (('1',),('3',)))

    def test_not_in_subquery_and_empty_result(self):
        self.assertEqual(self.rows('SELECT Code FROM Catalog.Products WHERE Amount NOT IN (SELECT Amount FROM Catalog.Products WHERE Active=TRUE)'), (('2',),))
        self.assertEqual(len(self.rows('SELECT Code FROM Catalog.Products WHERE Amount NOT IN (SELECT Amount FROM Catalog.Products WHERE Amount>100)')),3)

    def test_nested_subqueries(self):
        self.assertEqual(self.rows('SELECT Code FROM Catalog.Products WHERE Amount IN (SELECT Amount FROM Catalog.Products WHERE Amount IN (SELECT Amount FROM Catalog.Products WHERE Amount=20))'), (('2',),))

    def test_subquery_union(self):
        self.assertEqual(self.rows('SELECT Code FROM Catalog.Products WHERE Amount IN (SELECT Amount FROM Catalog.Products WHERE Amount=10 UNION ALL SELECT Amount FROM Catalog.Products WHERE Amount=30)'), (('1',),('3',)))

    def test_subquery_aggregate_and_null(self):
        self.assertEqual(self.rows('SELECT Code FROM Catalog.Products WHERE Amount IN (SELECT MAX(Amount) AS N FROM Catalog.Products)'), (('3',),))
        self.assertEqual(self.rows('SELECT Code FROM Catalog.Products WHERE Amount NOT IN (SELECT MAX(Amount) AS N FROM Catalog.Products WHERE Amount>100)'), ())
        self.assertEqual(self.rows('SELECT Code FROM Catalog.Products WHERE Amount NOT IN (SELECT NULL AS N FROM Catalog.Products)'), ())

    def test_subquery_type_and_width_validation(self):
        for text in ('SELECT Code FROM Catalog.Products WHERE Amount IN (SELECT Code FROM Catalog.Products)',
                     'SELECT Code FROM Catalog.Products WHERE Amount IN (SELECT Code,Amount FROM Catalog.Products)'):
            with self.subTest(text=text), self.assertRaises((TypeError,ValueError)): self.rows(text)

    def test_correlation_is_not_admitted(self):
        with self.assertRaises(ValueError):
            self.rows('SELECT P.Code FROM Catalog.Products AS P WHERE P.Amount IN (SELECT Q.Amount FROM Catalog.Products AS Q WHERE Q.Amount=P.Amount)')

    def test_reference_membership_identity(self):
        self.assertEqual(len(self.rows('SELECT Code FROM Catalog.Products WHERE Category IN (SELECT Ref FROM Catalog.Categories)')),3)
        with self.assertRaises(TypeError):
            self.rows('SELECT Code FROM Catalog.Products WHERE Ref IN (SELECT Ref FROM Catalog.Categories)')

    def test_group_having_case_and_between(self):
        self.assertEqual(self.rows('SELECT Active,SUM(Amount) AS Total FROM Catalog.Products GROUP BY Active HAVING SUM(Amount) IN (20,40) ORDER BY Total'),
                         ((False,Decimal(20)),(True,Decimal(40))))
        self.assertEqual(self.rows('SELECT Active,SUM(Amount) AS Total FROM Catalog.Products GROUP BY Active HAVING SUM(Amount) IN (SELECT SUM(Amount) AS N FROM Catalog.Products WHERE Active=TRUE)'), ((True,Decimal(40)),))

    def test_join_membership_and_unknown_preserve_left(self):
        self.assertEqual(self.rows('SELECT P.Code,C.Code AS C FROM Catalog.Products AS P LEFT JOIN Catalog.Categories AS C ON P.Category=C.Ref AND P.Amount IN (10,NULL) ORDER BY P.Code'),
                         (('1','01'),('2',NULL),('3',NULL)))

    def test_temporary_membership_package(self):
        query = self.query('SELECT Amount INTO T FROM Catalog.Products WHERE Active=TRUE; SELECT Code FROM Catalog.Products WHERE Amount IN (SELECT Amount FROM T) ORDER BY Code; DESTROY T')
        output=query.execute_batch()
        self.assertEqual(output.items[1]._rows, (('1',),('3',)))

    def test_subquery_sources_share_one_view(self):
        backend=self.context.backend
        original=backend.begin_read
        with patch.object(backend,'begin_read',wraps=original) as begin:
            self.assertEqual(self.rows('SELECT Code FROM Catalog.Products WHERE Amount IN (SELECT Amount FROM Catalog.Products WHERE Amount IN (SELECT Amount FROM Catalog.Products))'),(('1',),('2',),('3',)))
            self.assertEqual(begin.call_count,1)

    def test_membership_work_limit(self):
        import yadinassi.relational_queries as relational
        with patch.object(relational,'MAX_MEMBERSHIP_WORK',1):
            with self.assertRaisesRegex(ValueError,'work limit'):
                self.rows('SELECT Code FROM Catalog.Products WHERE Amount IN (10,20,30)')
        self.assertEqual(len(self.rows('SELECT Code FROM Catalog.Products')),3)

    def test_resource_budget_shared_across_subqueries(self):
        import yadinassi.queries as queries
        with patch.object(queries,'_MAX_CELLS',5):
            with self.assertRaisesRegex(ValueError,'resource limit'):
                self.rows('SELECT Code FROM Catalog.Products WHERE Amount IN (SELECT Amount FROM Catalog.Products)')
        self.assertEqual(len(self.rows('SELECT Code FROM Catalog.Products')),3)

    def test_bsl_array_parameter_end_to_end(self):
        self.vm.execute('A=New Array;A.Add(10);A.Add(30);Q=New Query("SELECT Code FROM Catalog.Products WHERE Amount IN &List ORDER BY Code");Q.SetParameter("List",A);S=Q.Execute().Select();While S.Next() Do Message(S.Code);EndDo;')
        self.assertEqual(self.output,['1','3'])

    def test_external_source_nested_in_membership(self):
        self.vm.execute('T=New ValueTable;T.Columns.Add("N",New TypeDescription("Number",New NumberQualifiers(12,2)));R=T.Add();R.N=20;Q=New Query("SELECT Code FROM Catalog.Products WHERE Amount IN (SELECT N FROM &Input)");Q.SetParameter("Input",T);S=Q.Execute().Select();While S.Next() Do Message(S.Code);EndDo;')
        self.assertEqual(self.output,['2'])

    def test_external_outer_database_subquery(self):
        self.vm.execute('T=New ValueTable;T.Columns.Add("N",New TypeDescription("Number",New NumberQualifiers(12,2)));R=T.Add();R.N=20;Q=New Query("SELECT N FROM &Input WHERE N IN (SELECT Amount FROM Catalog.Products)");Q.SetParameter("Input",T);S=Q.Execute().Select();While S.Next() Do Message(S.N);EndDo;')
        self.assertEqual(self.output,['20'])

    def test_failure_does_not_publish_temporary_tables(self):
        manager=BSLTempTablesManager()
        q=self.query('SELECT Code AS Product INTO NewTable FROM Catalog.Products; SELECT Code FROM Catalog.Products WHERE Amount IN (SELECT Product FROM NewTable)', manager=manager)
        with self.assertRaises(TypeError): q.execute_batch()
        self.assertEqual(manager._tables,{})
        self.assertEqual(len(self.rows('SELECT Code FROM Catalog.Products')),3)

    def test_parameter_lists_are_frozen_for_entire_package(self):
        values=array(Decimal(10))
        q=self.query('SELECT Code FROM Catalog.Products WHERE Amount IN &V ORDER BY Code; SELECT Code FROM Catalog.Products WHERE Amount IN &V ORDER BY Code',[('V',values)])
        from yadinassi.sqlite_catalog import _View
        original=_View.scan_catalog_values
        def scan(view,*args,**kwargs):
            values.items[:]=[Decimal(30)]
            return original(view,*args,**kwargs)
        with patch.object(_View,'scan_catalog_values',scan):
            output=q.execute_batch()
        self.assertEqual([x._rows for x in output.items],[(('1',),),(('1',),)])

    def test_grammar_limits_and_closed_shapes(self):
        for text in (
            'SELECT Code FROM Catalog.Products WHERE Amount IN ()',
            'SELECT Code FROM Catalog.Products WHERE Amount IN (SELECT Amount INTO T FROM Catalog.Products)',
            'SELECT Code FROM Catalog.Products WHERE Amount NOT=10',
            'SELECT Code FROM Catalog.Products WHERE Amount IN (SELECT Amount FROM Catalog.Products; DESTROY T)',
            'SELECT Code FROM Catalog.Products WHERE Amount IN ('+','.join(['1']*257)+')',
            'SELECT Code FROM Catalog.Products WHERE '+'NOT '*34+'Amount=1',
        ):
            with self.subTest(text=text),self.assertRaises(ValueError): syntax.parse_query(text)
        inner='SELECT Amount FROM Catalog.Products'
        for _ in range(9): inner='SELECT Amount FROM Catalog.Products WHERE Amount IN ('+inner+')'
        with self.assertRaisesRegex(ValueError,'subquery budget'): syntax.parse_query(inner)


class DocumentMembershipTests(unittest.TestCase):
    setUp=document_fixtures.DocumentQueryTests.setUp
    tearDown=document_fixtures.DocumentQueryTests.tearDown
    seed=document_fixtures.DocumentQueryTests.seed

    def test_catalog_outer_document_inner_initializes_before_snapshot(self):
        self.seed()
        from yadinassi import Interpreter
        self.vm=Interpreter(database_context=self.context)
        q=BSLQuery(self.vm._catalogs,'SELECT Code FROM Catalog.Categories WHERE Ref IN (SELECT Category FROM Document.Orders WHERE Amount>10)',documents=self.vm._documents)
        backend=self.context.backend
        with patch.object(backend,'begin_query_read',wraps=backend.begin_query_read) as begin:
            self.assertEqual(q.execute()._rows,(('01',),))
            self.assertEqual(begin.call_count,1)

    def test_document_references_and_sections(self):
        self.seed()
        q=BSLQuery(self.vm._catalogs,'SELECT Number FROM Document.Orders WHERE Ref IN (SELECT Ref FROM Document.Orders.Lines WHERE Amount>=9)',documents=self.vm._documents)
        self.assertEqual(q.execute()._rows,(('000000003',),))


import test_periodic_information_registers as periodic_fixtures


class RegisterMembershipTests(unittest.TestCase):
    setUp=periodic_fixtures.PeriodicRegisterTests.setUp
    execute=periodic_fixtures.PeriodicRegisterTests.execute
    seed=periodic_fixtures.PeriodicRegisterTests.seed
    query=periodic_fixtures.PeriodicRegisterTests.query

    def test_periodic_slice_subquery_on_same_snapshot(self):
        from yadinassi.dates import literal_date
        self.seed()
        q=self.query('SELECT Item,Price FROM InformationRegister.Prices.SliceLast(&At) WHERE Price IN (SELECT Price FROM InformationRegister.Prices WHERE Price>=20)',literal_date('20240102120000'))
        with patch.object(self.context.backend,'begin_query_read',wraps=self.context.backend.begin_query_read) as begin:
            self.assertEqual(q.execute()._rows,(('A',Decimal(20)),))
            self.assertEqual(begin.call_count,1)

    def test_register_subquery_external_outer(self):
        self.seed()
        self.vm.execute('T=New ValueTable;T.Columns.Add("N",New TypeDescription("Number",New NumberQualifiers(12,2)));R=T.Add();R.N=20;Q=New Query("SELECT N FROM &Input WHERE N IN (SELECT Price FROM InformationRegister.Prices)");Q.SetParameter("Input",T);S=Q.Execute().Select();While S.Next() Do Message(S.N);EndDo;')
        self.assertEqual(self.output,['20'])
