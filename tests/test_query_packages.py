"""Temporary-table report pipelines: host contract, not native parity evidence."""
from decimal import Decimal
import unittest
from unittest.mock import patch

from yadinassi import Interpreter
from yadinassi.queries import BSLQuery
from yadinassi.sqlite_catalog import _View
from yadinassi.values import NULL
import test_catalog_queries as fixtures


class QueryPackageTests(unittest.TestCase):
    setUp = fixtures.CatalogQueryTests.setUp
    tearDown = fixtures.CatalogQueryTests.tearDown

    def manager(self):
        return self.vm.execute('New TempTablesManager')

    def query(self, text, manager=None):
        query=BSLQuery(self.vm._catalogs,text)
        if manager is not None:query.set_member('TempTablesManager',manager)
        return query

    def rows(self,text,manager=None):
        return self.query(text,manager).execute()._rows

    def test_materialize_filter_then_group_pipeline(self):
        text=('SELECT Code AS Item,Amount*2 AS Gross,Active INTO Prepared FROM Catalog.Products WHERE Amount>=20; '
              'SELECT Active,SUM(Gross) AS Total FROM Prepared GROUP BY Active ORDER BY Active')
        self.assertEqual(self.rows(text),((False,Decimal(40)),(True,Decimal(60))))

    def test_materialized_aggregate_can_be_joined_back_to_catalog(self):
        text=('SELECT Category,SUM(Amount) AS Total INTO Totals FROM Catalog.Products GROUP BY Category; '
              'SELECT C.Code AS Category,T.Total FROM Totals AS T JOIN Catalog.Categories AS C ON T.Category=C.Ref')
        self.assertEqual(self.rows(text),(('01',Decimal(60)),))

    def test_two_temporary_tables_join_and_computed_aggregate(self):
        text=('SELECT Code AS Item,Amount INTO First FROM Catalog.Products; '
              'SELECT Code AS Item,Amount*2 AS Gross INTO Second FROM Catalog.Products; '
              'SELECT SUM(S.Gross-F.Amount) AS Difference FROM First AS F JOIN Second AS S ON F.Item=S.Item')
        self.assertEqual(self.rows(text),((Decimal(60),),))

    def test_parameters_are_shared_across_statements(self):
        query=self.query('SELECT Amount*&Rate AS Amount INTO Prepared FROM Catalog.Products WHERE Amount>=&Minimum; '
                         'SELECT SUM(Amount)+&Offset AS Total FROM Prepared')
        for name,value in [('Rate',Decimal(2)),('Minimum',Decimal(20)),('Offset',Decimal(1))]:
            query.set_parameter(name,value)
        self.assertEqual(query.execute()._rows,((Decimal(101),),))

    def test_execute_batch_returns_detached_per_statement_results(self):
        query=self.query('SELECT Code AS Item INTO Prepared FROM Catalog.Products; '
                         'SELECT COUNT(*) AS N FROM Prepared; DESTROY Prepared')
        results=query.execute_batch().items
        self.assertEqual(len(results),3)
        self.assertEqual(results[0]._rows,((Decimal(3),),))
        self.assertEqual(results[1]._rows,((Decimal(3),),))
        self.assertEqual(results[2]._rows,())

    def test_bsl_batch_manager_type_and_typed_unload(self):
        self.vm.execute('''M=New TempTablesManager;Q=New Query;Q.TempTablesManager=M;
Q.Text="SELECT Amount*2 AS Gross INTO Prepared FROM Catalog.Products; SELECT SUM(Gross) AS Total FROM Prepared";
A=Q.ExecuteBatch();Message(A.Count());Message(A[1].Unload()[0].Total);
Message(TypeOf(M)=Type("TempTablesManager"));Message(Q.TempTablesManager=M);M.Close();''')
        self.assertEqual(self.output,['2','120','Да','Да'])

    def test_russian_pipeline_and_manager_alias(self):
        self.vm.execute('''М=Новый МенеджерВременныхТаблиц;З=Новый Запрос;З.МенеджерВременныхТаблиц=М;
З.Текст="ВЫБРАТЬ Amount*2 КАК Сумма ПОМЕСТИТЬ Подготовлено ИЗ Справочник.Products; ВЫБРАТЬ СУММА(Сумма) КАК Итог ИЗ Подготовлено";
Message(З.ВыполнитьПакет()[1].Выгрузить()[0].Итог);М.Закрыть();''')
        self.assertEqual(self.output,['120'])

    def test_explicit_manager_retains_tables_between_queries(self):
        manager=self.manager()
        self.rows('SELECT Code AS Item,Amount INTO Prepared FROM Catalog.Products',manager)
        self.assertEqual(self.rows('SELECT SUM(Amount) AS Total FROM Prepared',manager),((Decimal(60),),))
        self.rows('DESTROY Prepared',manager)
        with self.assertRaises(ValueError):self.rows('SELECT Amount FROM Prepared',manager)

    def test_implicit_manager_is_scoped_to_one_execution(self):
        query=self.query('SELECT Amount INTO Prepared FROM Catalog.Products; SELECT SUM(Amount) AS Total FROM Prepared')
        self.assertEqual(query.execute()._rows,((Decimal(60),),))
        self.assertEqual(query.execute()._rows,((Decimal(60),),))
        query.set_member('Text','SELECT Amount FROM Prepared')
        with self.assertRaises(ValueError):query.execute()

    def test_managers_are_isolated(self):
        first,second=self.manager(),self.manager()
        self.rows('SELECT Amount INTO Prepared FROM Catalog.Products',first)
        with self.assertRaises(ValueError):self.rows('SELECT Amount FROM Prepared',second)
        self.assertEqual(self.rows('SELECT COUNT(*) AS N FROM Prepared',first),((Decimal(3),),))

    def test_manager_rejects_foreign_interpreter_snapshot(self):
        manager=self.manager()
        self.rows("SELECT Amount INTO Prepared FROM Catalog.Products",manager)
        other=Interpreter(database_context=self.context)
        query=BSLQuery(other._catalogs,'SELECT Code FROM Catalog.Products')
        with self.assertRaises((ValueError,TypeError)):
            query.set_member('TempTablesManager',manager)
            query.execute()

    def test_manager_close_is_idempotent_and_prevents_reuse(self):
        manager=self.manager()
        self.rows('SELECT Amount INTO Prepared FROM Catalog.Products',manager)
        manager.close();manager.close()
        with self.assertRaises(ValueError):self.rows('SELECT Amount FROM Prepared',manager)

    def test_destroy_then_recreate_in_same_package(self):
        manager=self.manager()
        self.rows('SELECT Amount INTO Prepared FROM Catalog.Products',manager)
        self.rows('DESTROY Prepared; SELECT Amount*3 AS Gross INTO Prepared FROM Catalog.Products',manager)
        self.assertEqual(self.rows('SELECT SUM(Gross) AS Total FROM Prepared',manager),((Decimal(180),),))

    def test_duplicate_table_fails_without_overwriting_existing(self):
        manager=self.manager()
        self.rows('SELECT Amount INTO Prepared FROM Catalog.Products',manager)
        with self.assertRaises(ValueError):
            self.rows('SELECT Amount*3 AS Amount INTO Prepared FROM Catalog.Products',manager)
        self.assertEqual(self.rows('SELECT SUM(Amount) AS Total FROM Prepared',manager),((Decimal(60),),))

    def test_failure_rolls_back_created_and_destroyed_tables(self):
        manager=self.manager()
        self.rows('SELECT Amount INTO Original FROM Catalog.Products',manager)
        with self.assertRaises((ValueError,ArithmeticError)):
            self.rows('DESTROY Original; SELECT Amount INTO NewTable FROM Catalog.Products; '
                      'SELECT Amount/(Amount-20) AS Broken FROM NewTable',manager)
        self.assertEqual(self.rows('SELECT SUM(Amount) AS Total FROM Original',manager),((Decimal(60),),))
        with self.assertRaises(ValueError):self.rows('SELECT Amount FROM NewTable',manager)
        self.context.backend.begin_read().close()

    def test_malformed_final_statement_does_not_commit_first_statement(self):
        manager=self.manager()
        with self.assertRaises(ValueError):
            self.rows('SELECT Amount INTO Prepared FROM Catalog.Products; DELETE FROM Prepared',manager)
        with self.assertRaises(ValueError):self.rows('SELECT Amount FROM Prepared',manager)

    def test_missing_table_and_missing_destroy_target_are_explicit(self):
        for text in ('SELECT Amount FROM Missing','DESTROY Missing'):
            with self.subTest(text=text),self.assertRaises(ValueError):self.rows(text)

    def test_table_names_and_columns_are_case_insensitive(self):
        self.assertEqual(self.rows('SELECT Amount AS Gross INTO Prepared FROM Catalog.Products; '
                                   'SELECT SUM(p.gRoSs) AS Total FROM pRePaReD AS P'),((Decimal(60),),))

    def test_empty_table_retains_schema_and_reference_identity(self):
        text=('SELECT Category,Amount INTO EmptyTable FROM Catalog.Products WHERE Amount>100; '
              'SELECT C.Code AS Category,COUNT(E.Category) AS N,ISNULL(SUM(E.Amount),0) AS Total '
              'FROM Catalog.Categories AS C LEFT JOIN EmptyTable AS E ON C.Ref=E.Category GROUP BY C.Code')
        self.assertEqual(self.rows(text),(('01',Decimal(0),Decimal(0)),))

    def test_wrong_reference_family_in_empty_temporary_table_is_rejected(self):
        manager=self.manager()
        self.rows('SELECT Category INTO EmptyTable FROM Catalog.Products WHERE Amount>100',manager)
        with patch.object(_View,'scan_catalog_values',side_effect=AssertionError('must not scan')):
            with self.assertRaises(TypeError):
                self.rows('SELECT P.Code FROM Catalog.Products AS P JOIN EmptyTable AS E ON P.Ref=E.Category',manager)

    def test_nullable_column_survives_materialization(self):
        text=('SELECT P.Code AS Item,C.Description AS Caption INTO Prepared FROM Catalog.Products AS P '
              'LEFT JOIN Catalog.Categories AS C ON P.Category=C.Ref AND P.Amount>20; '
              'SELECT Item,ISNULL(Caption,"missing") AS Caption FROM Prepared ORDER BY Item')
        self.assertEqual(self.rows(text),(('1','missing'),('2','missing'),('3','target')))

    def test_unload_preserves_materialized_decimal_and_string_metadata(self):
        query=self.query('SELECT Amount/3 AS Third,CASE WHEN Active=TRUE THEN "long caption" ELSE "x" END AS Label '
                         'INTO Prepared FROM Catalog.Products; SELECT Third,Label FROM Prepared ORDER BY Third')
        result=query.execute();table=result.unload()
        self.assertEqual(table.rows[0].get_member('Third'),Decimal('3.3333333333'))
        self.assertEqual(table.rows[0].get_member('Label'),'long caption')
        self.assertEqual(table.columns.items[0].value_type.number_qualifiers.fraction_digits,Decimal(10))

    def test_all_catalog_statements_share_one_read_view(self):
        original,views=_View.scan_catalog_values,[]
        def scan(view,*args):views.append(view);return original(view,*args)
        with patch.object(_View,'scan_catalog_values',scan):
            result=self.rows('SELECT Amount INTO Prepared FROM Catalog.Products; '
                             'SELECT C.Code AS Category,SUM(P.Amount) AS Total FROM Catalog.Categories AS C '
                             'JOIN Catalog.Products AS P ON C.Ref=P.Category GROUP BY C.Code; '
                             'SELECT SUM(Amount) AS Total FROM Prepared')
        self.assertEqual(result,((Decimal(60),),));self.assertEqual(len({id(view) for view in views}),1)
        self.context.backend.begin_read().close()

    def test_temporary_only_execution_does_not_open_backend(self):
        manager=self.manager()
        self.rows('SELECT Amount INTO Prepared FROM Catalog.Products',manager)
        with patch.object(self.context.backend,'begin_read',side_effect=AssertionError('no backend read')):
            self.assertEqual(self.rows('SELECT SUM(Amount) AS Total FROM Prepared',manager),((Decimal(60),),))

    def test_materialized_rows_are_detached_from_later_database_writes(self):
        manager=self.manager();self.rows('SELECT Amount INTO Prepared FROM Catalog.Products',manager)
        self.vm.execute('O=Catalogs.Products.FindByCode("1").GetObject();O.Amount=500;O.Write();')
        self.assertEqual(self.rows('SELECT SUM(Amount) AS Total FROM Prepared',manager),((Decimal(60),),))

    def test_trailing_semicolon_and_semicolon_inside_string(self):
        self.assertEqual(self.rows('SELECT "a;b" AS Label INTO Prepared FROM Catalog.Products; '
                                   'SELECT DISTINCT Label FROM Prepared;'),(('a;b',),))

    def test_query_manager_property_requires_manager_or_undefined(self):
        query=self.query('SELECT Code FROM Catalog.Products')
        with self.assertRaises(TypeError):query.set_member('TempTablesManager','wrong')
        query.set_member('TempTablesManager',None)
        self.assertEqual(len(query.execute()._rows),3)

    def test_manager_cannot_be_serialized_or_expose_private_state(self):
        for code in ('ValueToStringInternal(New TempTablesManager)',
                     '(New TempTablesManager)._tables'):
            with self.subTest(code=code),self.assertRaises(Exception):self.vm.execute(code)

    def test_manager_table_count_budget_rolls_back_package(self):
        manager=self.manager()
        self.rows('SELECT Amount INTO Original FROM Catalog.Products',manager)
        with patch('yadinassi.query_packages.MAX_TABLES',1):
            with self.assertRaises(ValueError):
                self.rows('SELECT Amount INTO Added FROM Catalog.Products',manager)
        self.assertEqual(self.rows('SELECT COUNT(*) AS N FROM Original',manager),((Decimal(3),),))
        with self.assertRaises(ValueError):self.rows('SELECT Amount FROM Added',manager)

    def test_manager_row_cell_and_text_budgets_fail_atomically(self):
        for limit,value,projection in [('MAX_ROWS',2,'Amount'),('MAX_CELLS',2,'Amount'),('MAX_TEXT',2,'Text')]:
            manager=self.manager()
            with self.subTest(limit=limit),patch('yadinassi.query_packages.'+limit,value):
                with self.assertRaises(ValueError):
                    self.rows('SELECT '+projection+' INTO Prepared FROM Catalog.Products',manager)
            with self.assertRaises(ValueError):self.rows('SELECT '+projection+' FROM Prepared',manager)

    def test_package_output_budget_counts_all_results(self):
        with patch('yadinassi.query_packages.MAX_CELLS',5):
            with self.assertRaises(ValueError):
                self.query('SELECT Amount FROM Catalog.Products; SELECT Amount FROM Catalog.Products').execute_batch()

    def test_package_statement_budget_is_checked_before_scanning(self):
        with patch('yadinassi.query_parser.MAX_STATEMENTS',2):
            with patch.object(_View,'scan_catalog_values',side_effect=AssertionError('must not scan')):
                with self.assertRaises(ValueError):
                    self.query(';'.join(['SELECT Amount FROM Catalog.Products']*3)).execute_batch()

    def test_materialization_does_not_hide_source_overflow_behind_top(self):
        with patch('yadinassi.query_parser.MAX_ROWS',2):
            with self.assertRaises(ValueError):
                self.rows('SELECT TOP 1 Amount INTO Prepared FROM Catalog.Products; SELECT Amount FROM Prepared')
        self.context.backend.begin_read().close()

    def test_old_result_survives_destroy_and_manager_close(self):
        manager=self.manager()
        self.rows('SELECT Amount INTO Prepared FROM Catalog.Products',manager)
        result=self.query('SELECT SUM(Amount) AS Total FROM Prepared',manager).execute()
        self.rows('DESTROY Prepared',manager);manager.close()
        self.assertEqual(result.unload().rows[0].get_member('Total'),Decimal(60))

    def test_single_select_batch_has_one_result(self):
        result=self.query('SELECT SUM(Amount) AS Total FROM Catalog.Products').execute_batch()
        self.assertEqual(len(result.items),1)
        self.assertEqual(result.items[0]._rows,((Decimal(60),),))



class QueryPackageSectionTests(unittest.TestCase):
    def setUp(self):
        import test_relational_queries
        test_relational_queries.RelationalSectionTests.setUp(self)

    def test_owner_section_staged_report(self):
        text=('SELECT Ref AS Owner,SUM(Amount*1.2) AS Total INTO Totals FROM Catalog.Products.Lines GROUP BY Ref; '
              'SELECT P.Code AS Owner,ISNULL(T.Total,0) AS Total FROM Catalog.Products AS P '
              'LEFT JOIN Totals AS T ON P.Ref=T.Owner ORDER BY P.Code')
        self.assertEqual(BSLQuery(self.vm._catalogs,text).execute()._rows,
                         (('10',Decimal('26.82')),('20',Decimal('118.8')),('30',Decimal(0))))


if __name__=='__main__':unittest.main()
