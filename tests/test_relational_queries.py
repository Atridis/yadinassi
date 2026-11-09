"""Functional relational query block on owned SQLite and an engine-neutral port.

These are host reference-model tests, not native 1C parity observations.
"""
from decimal import Decimal, Inexact, Rounded, localcontext
from unittest.mock import patch
import unittest

from yadinassi import Interpreter
from yadinassi.queries import BSLQuery
from yadinassi import query_parser as syntax
from yadinassi.sqlite_catalog import _View
from yadinassi.values import NULL
import test_catalog_queries as fixtures


class RelationalQueryTests(unittest.TestCase):
    setUp = fixtures.CatalogQueryTests.setUp
    tearDown = fixtures.CatalogQueryTests.tearDown

    def query(self, text):
        return BSLQuery(self.vm._catalogs, text)

    def rows(self, text):
        return self.query(text).execute()._rows

    def test_inner_reference_join_and_bsl_cursor(self):
        self.vm.execute('''Q=New Query("SELECT P.Code AS Product, C.Description AS Category FROM Catalog.Products AS P INNER JOIN Catalog.Categories AS C ON P.Category=C.Ref ORDER BY P.Amount DESC");
S=Q.Execute().Select();While S.Next() Do Message(S.Product);Message(S.Category);EndDo;''')
        self.assertEqual(self.output, ['3','target','2','target','1','target'])

    def test_left_join_missing_rows_and_null_predicate(self):
        self.vm.execute('C2=Catalogs.Categories.CreateItem();C2.Code="02";C2.Description="unused";C2.Write();')
        query = ('SELECT C.Code AS Category, P.Code AS Product FROM Catalog.Categories AS C '
                 'LEFT JOIN Catalog.Products AS P ON C.Ref=P.Category ORDER BY C.Code,P.Code')
        self.assertEqual(self.rows(query), (('01','1'),('01','2'),('01','3'),('02',NULL)))
        self.assertEqual(self.rows(query.replace(' ORDER BY C.Code,P.Code', ' WHERE P.Ref IS NULL')), (('02',NULL),))
        self.assertEqual(len(self.rows(query.replace(' ORDER BY C.Code,P.Code', ' WHERE P.Ref IS NOT NULL'))), 3)
        self.assertEqual(self.rows('SELECT Code AS Product FROM Catalog.Products WHERE Amount IS NULL'), ())

    def test_left_join_on_filters_preserve_unmatched_left(self):
        text = ('SELECT P.Code AS Product,C.Description AS Caption FROM Catalog.Products AS P '
                'LEFT OUTER JOIN Catalog.Categories AS C ON P.Category=C.Ref AND P.Amount>20 ORDER BY P.Code')
        self.assertEqual(self.rows(text), (('1',NULL),('2',NULL),('3','target')))

    def test_group_aggregate_having_parameter_and_order_alias(self):
        query = self.query('SELECT Active,COUNT(*) AS N,SUM(Amount) AS Total,AVG(Amount) AS Mean,MIN(Amount) AS Low,MAX(Amount) AS High '
                           'FROM Catalog.Products GROUP BY Active HAVING SUM(Amount)>=&Minimum ORDER BY Total DESC')
        query.set_parameter('Minimum', Decimal(30))
        self.assertEqual(query.execute()._rows, ((True,Decimal(2),Decimal(40),Decimal(20),Decimal(10),Decimal(30)),))

    def test_all_aggregate_and_empty_aggregate(self):
        text = 'SELECT COUNT(*) AS N,SUM(Amount) AS Total,AVG(Amount) AS Mean,MIN(Text) AS Low,MAX(Stamp) AS Latest FROM Catalog.Products'
        row = self.rows(text)[0]
        self.assertEqual(row[:4], (Decimal(3),Decimal(60),Decimal(20),'text'))
        self.assertEqual(self.rows(text + ' WHERE Amount>100'), ((Decimal(0),NULL,NULL,NULL,NULL),))
        self.assertEqual(self.rows('SELECT Active,COUNT(*) AS N FROM Catalog.Products WHERE Amount>100 GROUP BY Active'), ())

    def test_distinct_projection_and_aggregate_values(self):
        self.assertEqual(self.rows('SELECT DISTINCT Text,Active FROM Catalog.Products ORDER BY Active'), (('text',False),('text',True)))
        self.assertEqual(self.rows('SELECT COUNT(DISTINCT Text) AS N,SUM(DISTINCT Amount) AS Total FROM Catalog.Products'), ((Decimal(1),Decimal(60)),))

    def test_group_without_aggregate_and_top_after_group_order(self):
        self.assertEqual(self.rows('SELECT TOP 1 Active FROM Catalog.Products GROUP BY Active ORDER BY Active'), ((False,),))
        self.assertEqual(self.rows('SELECT TOP 1 Active,SUM(Amount) AS Total FROM Catalog.Products GROUP BY Active ORDER BY Total DESC'), ((True,Decimal(40)),))

    def test_russian_join_group_and_having(self):
        text = ('ВЫБРАТЬ C.Код КАК Категория, КОЛИЧЕСТВО(*) КАК Строк, СУММА(P.Amount) КАК Итого '
                'ИЗ Справочник.Products КАК P ВНУТРЕННЕЕ СОЕДИНЕНИЕ Справочник.Categories КАК C ПО P.Category=C.Ссылка '
                'СГРУППИРОВАТЬ ПО C.Код ИМЕЮЩИЕ КОЛИЧЕСТВО(*)>1 УПОРЯДОЧИТЬ ПО Итого УБЫВ')
        self.assertEqual(self.rows(text), (('01',Decimal(3),Decimal(60)),))

    def test_self_join_and_second_join(self):
        text = ('SELECT P.Code AS Product,Q.Code AS Same,C.Code AS Category FROM Catalog.Products AS P '
                'INNER JOIN Catalog.Products AS Q ON P.Ref=Q.Ref '
                'INNER JOIN Catalog.Categories AS C ON Q.Category=C.Ref ORDER BY P.Code')
        self.assertEqual(self.rows(text), (('1','1','01'),('2','2','01'),('3','3','01')))

    def test_field_comparisons_and_non_equality_join(self):
        self.assertEqual(self.rows('SELECT Code AS Product FROM Catalog.Products WHERE Amount=Amount ORDER BY Code'), (('1',),('2',),('3',)))
        text = ('SELECT P.Code AS Product,Q.Code AS Greater FROM Catalog.Products AS P '
                'INNER JOIN Catalog.Products AS Q ON P.Amount<Q.Amount ORDER BY P.Code,Q.Code')
        self.assertEqual(self.rows(text), (('1','2'),('1','3'),('2','3')))

    def test_casefold_group_distinct_and_join(self):
        self.vm.execute('O=Catalogs.Products.FindByCode("1").GetObject();O.Text="TEXT";O.Write();')
        self.assertEqual(len(self.rows('SELECT DISTINCT Text FROM Catalog.Products')), 1)
        self.assertEqual(self.rows('SELECT COUNT(DISTINCT Text) AS N FROM Catalog.Products'), ((Decimal(1),),))
        self.assertEqual(self.rows('SELECT COUNT(*) AS N FROM Catalog.Products AS P JOIN Catalog.Products AS Q ON P.Text=Q.Text'), ((Decimal(9),),))

    def test_nulls_are_ignored_by_aggregates(self):
        self.vm.execute('C2=Catalogs.Categories.CreateItem();C2.Code="02";C2.Write();')
        text = ('SELECT C.Code AS Category,COUNT(*) AS Rows,COUNT(P.Ref) AS Items,SUM(P.Amount) AS Total '
                'FROM Catalog.Categories AS C LEFT JOIN Catalog.Products AS P ON C.Ref=P.Category '
                'GROUP BY C.Code ORDER BY C.Code')
        self.assertEqual(self.rows(text), (('01',Decimal(3),Decimal(3),Decimal(60)),('02',Decimal(1),Decimal(0),NULL)))

    def test_decimal_aggregation_owns_context_and_average_scale(self):
        self.vm.execute('O=Catalogs.Products.FindByCode("1").GetObject();O.Amount=10.01;O.Write();')
        with localcontext() as context:
            context.prec = 2
            context.traps[Inexact] = context.traps[Rounded] = True
            before = dict(context.flags)
            result = self.rows('SELECT SUM(Amount) AS Total,AVG(Amount) AS Mean FROM Catalog.Products')
            self.assertEqual(result, ((Decimal('60.01'),Decimal('20.0033333333')),))
            self.assertEqual(context.flags, before)

    def test_aggregate_unload_and_nullable_left_join_unload(self):
        table = self.query('SELECT SUM(Amount) AS Total,COUNT(*) AS N FROM Catalog.Products').execute().unload()
        self.assertEqual(table.rows[0].get_member('Total'), Decimal(60))
        self.assertEqual(table.columns.items[0].value_type.number_qualifiers.digits, Decimal(38))
        table = self.query('SELECT P.Code AS Product,C.Description AS Caption FROM Catalog.Products AS P '
                           'LEFT JOIN Catalog.Categories AS C ON P.Category=C.Ref AND P.Amount>30').execute().unload()
        self.assertIs(table.rows[0].get_member('Caption'), NULL)

    def test_schema_errors_fail_before_scan(self):
        texts = [
            'SELECT Code FROM Catalog.Products AS P JOIN Catalog.Categories AS C ON P.Category=C.Ref',
            'SELECT P.Code FROM Catalog.Products AS P JOIN Catalog.Categories AS C ON Later.Ref=C.Ref',
            'SELECT Code,SUM(Amount) AS Total FROM Catalog.Products',
            'SELECT Amount FROM Catalog.Products GROUP BY Active',
            'SELECT SUM(Text) AS Total FROM Catalog.Products',
            'SELECT MIN(Active) AS Low FROM Catalog.Products',
            'SELECT Code FROM Catalog.Products WHERE SUM(Amount)>0',
            'SELECT Code FROM Catalog.Products HAVING Amount>0',
            'SELECT COUNT(*) AS N FROM Catalog.Products HAVING Amount>0',
            'SELECT DISTINCT Active FROM Catalog.Products ORDER BY Amount',
            'SELECT SUM(Amount) AS Total FROM Catalog.Products WHERE Amount=&Missing',
            'SELECT SUM(Amount) AS Total FROM Catalog.Products WHERE Amount="wrong"',
            'SELECT P.Code FROM Catalog.Products AS P JOIN Catalog.Categories AS C ON P.Ref=C.Ref',
        ]
        with patch.object(_View, 'scan_catalog_values', side_effect=AssertionError('must not scan')):
            for text in texts:
                with self.subTest(text=text), self.assertRaises((ValueError,TypeError)): self.rows(text)

    def test_foreign_reference_parameter_rejected_before_read(self):
        other = Interpreter(database_context=self.context)
        query = self.query('SELECT COUNT(*) AS N FROM Catalog.Products WHERE Category=&Target')
        for reference in (other.execute('Catalogs.Categories.EmptyRef()'), self.vm.execute('Catalogs.Products.EmptyRef()')):
            query.set_parameter('Target', reference)
            with patch.object(_View, 'scan_catalog_values', side_effect=AssertionError('must not scan')):
                with self.assertRaises(TypeError): query.execute()

    def test_result_detached_and_all_sources_share_one_view(self):
        original, views = _View.scan_catalog_values, []
        def scan(view, *args): views.append(view); return original(view, *args)
        with patch.object(_View, 'scan_catalog_values', scan):
            result = self.query('SELECT C.Code AS Category,SUM(P.Amount) AS Total FROM Catalog.Products AS P '
                                'JOIN Catalog.Categories AS C ON P.Category=C.Ref GROUP BY C.Code').execute()
        self.assertEqual(len({id(view) for view in views}), 1)
        self.vm.execute('O=Catalogs.Products.FindByCode("1").GetObject();O.Amount=500;O.Write();')
        self.assertEqual(result._rows, (('01',Decimal(60)),))
        self.context.backend.begin_read().close()

    def test_input_and_intermediate_limits_fail_not_truncate(self):
        with patch('yadinassi.relational_queries.syntax.MAX_ROWS', 2):
            with self.assertRaisesRegex(ValueError, 'input resource'): self.rows('SELECT TOP 1 SUM(Amount) AS Total FROM Catalog.Products')
        with patch('yadinassi.relational_queries.MAX_INTERMEDIATE_ROWS', 2):
            with self.assertRaisesRegex(ValueError, 'intermediate'): self.rows('SELECT COUNT(*) AS N FROM Catalog.Products AS P JOIN Catalog.Products AS Q ON P.Text=Q.Text')
        with patch('yadinassi.relational_queries.MAX_JOIN_PAIRS', 1):
            with self.assertRaisesRegex(ValueError, 'join work'): self.rows('SELECT COUNT(*) AS N FROM Catalog.Products AS P JOIN Catalog.Products AS Q ON P.Amount<Q.Amount')
        self.context.backend.begin_read().close()

    def test_left_empty_right_and_both_sources_empty(self):
        self.vm.execute('C2=Catalogs.Categories.CreateItem();C2.Code="02";C2.Write();')
        text = ('SELECT COUNT(*) AS N FROM Catalog.Categories AS C LEFT JOIN Catalog.Products AS P '
                'ON C.Ref=P.Category WHERE P.Ref IS NULL')
        self.assertEqual(self.rows(text), ((Decimal(1),),))


class RelationalParserTests(unittest.TestCase):
    def test_complete_ast_and_legacy_shape(self):
        q=syntax.parse_query('SELECT DISTINCT TOP 4 P.Code AS Item,SUM(P.Amount) AS Total FROM Catalog.Products AS P '
                             'LEFT JOIN Catalog.Categories AS C ON P.Category=C.Ref GROUP BY P.Code HAVING SUM(P.Amount)>1 ORDER BY Total DESC')
        self.assertTrue(q.distinct); self.assertEqual(q.limit,4)
        self.assertEqual(q.joins[0].kind,'left'); self.assertEqual(q.groups[0].parts,('P','Code'))
        self.assertIsInstance(q.projections[1].field,syntax.Aggregate)
        old=syntax.parse_query('SELECT Code FROM Catalog.Products WHERE Code="1"')
        self.assertEqual((old.joins,old.groups,old.having,old.distinct),((),(),None,False))

    def test_closed_grammar_rejects_unsupported_or_malformed(self):
        for text in (
            'SELECT * FROM Catalog.Products', 'SELECT SUM(*) FROM Catalog.Products',
            'SELECT COUNT(DISTINCT *) FROM Catalog.Products', 'SELECT SUM(AVG(Amount)) FROM Catalog.Products',
            'SELECT P.Code FROM Catalog.Products AS P CROSS JOIN Catalog.Products AS Q',
            'SELECT P.Code FROM Catalog.Products AS P RIGHT JOIN Catalog.Products AS Q ON P.Ref=Q.Ref',
            'SELECT P.Code FROM Catalog.Products AS P JOIN Catalog.Products AS P ON P.Ref=P.Ref',
            'SELECT Code+Amount FROM Catalog.Products','SELECT Code FROM Catalog.Products; DELETE FROM catalog_records',
            'SELECT Code FROM Catalog.Products UNION SELECT Code FROM Catalog.Products',
        ):
            with self.subTest(text=text),self.assertRaises(ValueError): syntax.parse_query(text)




class RelationalSectionTests(unittest.TestCase):
    def setUp(self):
        import test_catalog_tabular_runtime
        test_catalog_tabular_runtime.CatalogTabularRuntimeTests.setUp(self)
        self.vm.execute('''C=Catalogs.Categories.CreateItem();C.Code="C";C.Description="category";C.Write();
O=Catalogs.Products.CreateItem();O.Code="10";O.Description="owner";
R=O.Lines.Add();R.Text="first";R.Amount=20.10;R.Category=C.Ref;
R=O.Lines.Add();R.Text="second";R.Amount=2.25;R.Category=C.Ref;O.Write();
P=Catalogs.Products.CreateItem();P.Code="20";R=P.Lines.Add();R.Amount=99;P.Write();
E=Catalogs.Products.CreateItem();E.Code="30";E.Write();''')

    def rows(self, text): return BSLQuery(self.vm._catalogs,text).execute()._rows

    def test_owner_section_and_reference_join_report(self):
        text = ('SELECT P.Code AS Owner,C.Description AS Category,SUM(L.Amount) AS Total,COUNT(*) AS N '
                'FROM Catalog.Products AS P JOIN Catalog.Products.Lines AS L ON P.Ref=L.Ref '
                'LEFT JOIN Catalog.Categories AS C ON L.Category=C.Ref '
                'GROUP BY P.Code,C.Description ORDER BY P.Code')
        self.assertEqual(self.rows(text),(('10','category',Decimal('22.35'),Decimal(2)),('20',NULL,Decimal(99),Decimal(1))))

    def test_left_section_join_includes_owner_without_lines(self):
        text = ('SELECT P.Code AS Owner,COUNT(L.Ref) AS N,SUM(L.Amount) AS Total FROM Catalog.Products AS P '
                'LEFT JOIN Catalog.Products.Lines AS L ON P.Ref=L.Ref GROUP BY P.Code ORDER BY P.Code')
        self.assertEqual(self.rows(text),(('10',Decimal(2),Decimal('22.35')),('20',Decimal(1),Decimal(99)),('30',Decimal(0),NULL)))

    def test_filtered_section_group_and_reopen(self):
        from yadinassi.database_context import SQLiteDBContext
        text = 'SELECT L.Ref AS Owner,SUM(L.Amount) AS Total FROM Catalog.Products.Lines AS L WHERE L.Amount<50 GROUP BY L.Ref'
        before=self.rows(text);self.context.close();self.context=SQLiteDBContext(self.path)
        self.vm=Interpreter(database_context=self.context)
        after=self.rows(text)
        self.assertEqual(before[0][0].reference_uuid,after[0][0].reference_uuid)
        self.assertEqual(after[0][1],Decimal('22.35'))

    def test_empty_right_source_left_join(self):
        # Notes are empty for every owner; COUNT(field) ignores their NULLs.
        text = ('SELECT COUNT(*) AS Owners,COUNT(N.Ref) AS Notes FROM Catalog.Products AS P '
                'LEFT JOIN Catalog.Products.Notes AS N ON P.Ref=N.Ref')
        self.assertEqual(self.rows(text),((Decimal(3),Decimal(0)),))

    def test_port_has_no_sql_or_backend_handle_dependency(self):
        from yadinassi.catalog_backend import CatalogValueRow,CatalogValuePage,CatalogSectionPage
        # Capture detached logical rows, then remove every SQLite execution path.
        managers=[self.vm._catalogs.get_index(name) for name in ('Products','Categories')]
        backend=self.context.backend
        view=backend.begin_read()
        schemas={m._schema.identity:m._schema for m in managers}
        cards={key:view.select_catalog(key,__import__('yadinassi.catalog_backend',fromlist=['CatalogSelection']).CatalogSelection()) for key in schemas}
        database_id,generation=view.database_id,view.configuration_generation
        view.close()
        class LogicalView:
            def __init__(self):
                self.database_id,self.configuration_generation=database_id,generation
                self.closed=False
            def catalog_schema(self,identity):return schemas[identity]
            def scan_catalog_values(self,identity,request,fields):
                rows=[]
                schema=schemas[identity]
                for card in cards[identity]:
                    values={'ref':card.key,'code':card.code,'description':card.description,'deletion_mark':card.deletion_mark}
                    values.update((f.identity,v) for f,v in zip(schema.fields,card.values))
                    rows.append(CatalogValueRow(card.key,tuple(values[f] for f in fields)))
                return CatalogValuePage(tuple(rows),None)
            def scan_catalog_section(self,identity,section_id,request):
                from yadinassi.catalog_backend import CatalogSectionRecord
                return CatalogSectionPage(tuple(CatalogSectionRecord(card.key,section_id,row)
                    for card in cards[identity] for section in card.tabular_sections if section.section_id==section_id
                    for row in section.rows),None)
            def close(self):self.closed=True
        logical=LogicalView()
        with patch.object(backend,'begin_read',return_value=logical):
            result=self.rows('SELECT P.Code AS Owner,SUM(L.Amount) AS Total FROM Catalog.Products AS P '
                             'JOIN Catalog.Products.Lines AS L ON P.Ref=L.Ref GROUP BY P.Code ORDER BY P.Code')
        self.assertEqual(result,(('10',Decimal('22.35')),('20',Decimal(99))))
        self.assertTrue(logical.closed)


if __name__ == '__main__': unittest.main()
