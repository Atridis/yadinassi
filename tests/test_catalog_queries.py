"""Logical Query reference-model tests on owned temporary SQLite, not native proof."""
from pathlib import Path
import sys
import tempfile
import unittest
from decimal import Decimal
from unittest.mock import patch
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from yadinassi import Interpreter
from yadinassi.configuration_xml import import_configuration
from yadinassi.database_context import SQLiteDBContext
from yadinassi.queries import BSLQuery
from yadinassi.sqlite_catalog import _View
from sqlite_catalog_fixture import configuration_files


class CatalogQueryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.context = SQLiteDBContext.create(Path(self.temp.name)/'owned.sqlite',
                                             import_configuration(configuration_files()))
        self.output = []
        self.vm = Interpreter(database_context=self.context, output=self.output.append)
        self.vm.execute('''C=Catalogs.Categories.CreateItem();C.Code="01";C.Description="target";C.Write();
For I=1 To 3 Do P=Catalogs.Products.CreateItem();P.Code=String(I);P.Description="item";
P.Amount=I*10;P.Text="text";P.Active=I<>2;P.Stamp=Date(2024,2,29);P.Category=C.Ref;P.Write();EndDo;''')

    def tearDown(self):
        self.context.close()
        self.temp.cleanup()

    def test_bsl_query_parameters_projection_and_order(self):
        self.vm.execute('''Q=New Query;Q.Text="SELECT P.Code AS Item, P.Amount FROM Catalog.Products AS P WHERE P.Amount>=&Min AND (P.Active=TRUE OR P.Amount=20) ORDER BY P.Amount DESC";
Q.SetParameter("Min",20);R=Q.Execute();S=R.Select();While S.Next() Do Message(S.Item);Message(S.Amount);EndDo;
Message(S.Next());Message(TypeOf(Q)=Type("Query"));Message(TypeOf(R)=Type("QueryResult"));
Message(TypeOf(S)=Type("QueryResultSelection"));''')
        self.assertEqual(self.output, ['3','30','2','20','Нет','Да','Да','Да'])

    def test_scalar_unload_is_typed_detached_and_independent(self):
        self.vm.execute('''Q=New Query("SELECT Code,Amount,Active,Stamp FROM Catalog.Products ORDER BY Amount");
R=Q.Execute();T=R.Unload();Message(T.Count());Message(T.Columns[0].ValueType.ContainsType(Type("String")));
Message(T.Columns[1].ValueType.NumberQualifiers.Digits);Message(T.Columns[0].ValueType.StringQualifiers.Length);
T[0].Amount=999;S=R.Select();S.Next();Message(S.Amount);Message(Catalogs.Products.FindByCode("1").Amount);''')
        self.assertEqual(self.output, ['3','Да','12','8','10','10'])

    def test_reference_parameter_and_projection_keep_snapshot_identity(self):
        self.vm.execute('''Q=New Query("SELECT Ref,Category FROM Catalog.Products WHERE Category=&Target ORDER BY Code");
Q.SetParameter("Target",C.Ref);R=Q.Execute();S=R.Select();S.Next();Message(S.Category=C.Ref);
Message(S.Ref.Code);Message(S.Category.Description);Try T=R.Unload();Except Message("unsupported-reference-column");EndTry;''')
        self.assertEqual(self.output, ['Да','1','target','unsupported-reference-column'])

    def test_empty_result_and_cursor_boundaries_are_explicit(self):
        self.vm.execute('''Q=New Запрос("ВЫБРАТЬ Код ИЗ Справочник.Products ГДЕ Amount>100");
R=Q.Выполнить();Message(R.Пустой());S=R.Выбрать();Message(S.Следующий());Message(S.Следующий());Message(R.Выгрузить().Count());''')
        self.assertEqual(self.output, ['Да','Нет','Нет','0'])
        result = BSLQuery(self.vm._catalogs, 'SELECT Code FROM Catalog.Products').execute()
        self.assertIsNone(result.select().get_member('Code'))
        with self.assertRaises(ValueError): result.get_member('Columns')

    def test_wrong_missing_and_foreign_parameters_refused_before_scan(self):
        query = BSLQuery(self.vm._catalogs, 'SELECT Code FROM Catalog.Products WHERE Amount=&N')
        with patch.object(_View, 'scan_catalog', side_effect=AssertionError('must not scan')):
            with self.assertRaises(ValueError): query.execute()
            query.set_parameter('N', True)
            with self.assertRaises(TypeError): query.execute()
            query.set_member('Text', 'SELECT X.Code FROM Catalog.Products AS P')
            with self.assertRaises(ValueError): query.execute()
        other = Interpreter(database_context=self.context)
        foreign = other.execute('Catalogs.Categories.EmptyRef()')
        query.set_member('Text', 'SELECT Code FROM Catalog.Products WHERE Category=&Ref')
        query.set_parameter('Ref', foreign)
        with self.assertRaises(TypeError): query.execute()

    def test_result_snapshot_does_not_rerun_or_hold_read_view(self):
        query = BSLQuery(self.vm._catalogs, 'SELECT Code,Amount FROM Catalog.Products ORDER BY Code')
        result = query.execute()
        self.vm.execute('O=Catalogs.Products.FindByCode("1").GetObject();O.Amount=500;O.Write();')
        selection = result.select(); self.assertTrue(selection.next())
        self.assertEqual(selection.get_member('Amount'), Decimal(10))
        newer = query.execute().select(); newer.next()
        self.assertEqual(newer.get_member('Amount'), Decimal(500))

    def test_query_objects_and_types_have_no_codec_or_result_constructor(self):
        for code in ('Q=New Query;ValueToStringInternal(Q);',
                     'ValueToStringInternal(Type("QueryResult"));',
                     'R=New QueryResult;',
                     'Q=New Query("SELECT Code FROM Catalog.Products");ValueToStringInternal(Q.Execute());'):
            with self.subTest(code=code), self.assertRaises(Exception): self.vm.execute(code)

    def test_top_and_no_parameter_coercion(self):
        self.vm.execute('''Q=New Query("SELECT TOP 1 Code FROM Catalog.Products ORDER BY Amount DESC");
S=Q.Execute().Select();Message(S.Next());Message(S.Code);Message(S.Next());''')
        self.assertEqual(self.output, ['Да','3','Нет'])
        query = BSLQuery(self.vm._catalogs)
        for value in (None, object(), Decimal('NaN'), Decimal('1e1000')):
            with self.assertRaises((ValueError, TypeError)): query.set_parameter('X', value)

    def test_continuation_keeps_page_size_and_top_truncates_only_last_page(self):
        from dataclasses import replace
        from uuid import UUID
        from yadinassi.catalog_backend import CatalogPage, CatalogSelection
        manager = self.vm._catalogs.get_index('Products')
        view = manager._view()
        try:
            card = view.select_catalog(manager._schema.identity,
                CatalogSelection())[0]
        finally:
            view.close()
        cards = tuple(replace(card, key=replace(card.key, record_id=UUID(int=i+1))) for i in range(1002))
        requests = []
        def scan(view, identity, request):
            requests.append(request)
            return CatalogPage(cards[:1000], 'a'*32) if len(requests) == 1 else CatalogPage(cards[1000:], None)
        with patch.object(_View, 'scan_catalog', scan):
            result = BSLQuery(self.vm._catalogs, 'SELECT TOP 1001 Code FROM Catalog.Products').execute()
        self.assertEqual(len(result._rows), 1001)
        self.assertEqual([r.page_size for r in requests], [1000, 1000])
        self.assertEqual([r.continuation for r in requests], [None, 'a'*32])
        self.vm.execute('O=Catalogs.Products.FindByCode("1").GetObject();O.Write();')

    def test_hostile_page_and_resources_refuse_and_close_read_view(self):
        from yadinassi.catalog_backend import CatalogPage, BackendError
        query = BSLQuery(self.vm._catalogs, 'SELECT Code FROM Catalog.Products')
        for page in (CatalogPage((), object()), CatalogPage((), 'x'), CatalogPage((), 'a'*32)):
            with patch.object(_View, 'scan_catalog', return_value=page), self.assertRaises(BackendError):
                query.execute()
            # A refused read never strands the one-active-view lease.
            view = self.context.backend.begin_read(); view.close()
        with self.assertRaises(ValueError):
            query.set_parameter('Large', Decimal('1'*20000))

    def test_date_boolean_and_reference_exact_predicates(self):
        self.vm.execute('''Q=New Query("SELECT Code FROM Catalog.Products WHERE Stamp>=&D AND Active=&A AND Ref<> &R ORDER BY Amount");
Q.SetParameter("D",Date(2024,2,29));Q.SetParameter("A",True);Q.SetParameter("R",Catalogs.Products.FindByCode("1"));
S=Q.Execute().Select();While S.Next() Do Message(S.Code);EndDo;''')
        self.assertEqual(self.output, ['3'])

    def test_measured_cursor_boundaries_keep_last_row_and_explicit_aliases(self):
        result = BSLQuery(self.vm._catalogs, 'SELECT Code FROM Catalog.Products ORDER BY Amount').execute()
        rows = result.select()
        self.assertIsNone(rows.get_member('Code'))
        self.assertIsNone(rows.get_member('Код'))
        while rows.next(): pass
        self.assertEqual(rows.get_member('Code'), '3')
        self.assertFalse(rows.next())
        self.assertEqual(rows.get_member('Код'), '3')
        aliased = BSLQuery(self.vm._catalogs, 'SELECT Code AS English FROM Catalog.Products').execute()
        self.assertEqual(aliased.unload().columns.items[0].name, 'English')
        rows = aliased.select(); rows.next()
        with self.assertRaises(ValueError): rows.get_member('Code')

    def test_measured_nullable_scalar_metadata_and_exact_assignment(self):
        from yadinassi.values import BSLType, NULL
        result = BSLQuery(self.vm._catalogs, 'SELECT Code,Amount,Active,Stamp FROM Catalog.Products ORDER BY Amount').execute()
        table = result.unload()
        self.assertEqual([c.name for c in table.columns.items], ['Код','Amount','Active','Stamp'])
        descriptions = [c.value_type for c in table.columns.items]
        self.assertEqual([str(d) for d in descriptions], ['Строка, Null','Null, Число','Булево, Null','Дата, Null'])
        for d in descriptions: self.assertTrue(d.contains_type(BSLType.NULL))
        self.assertEqual(descriptions[0].string_qualifiers.length, Decimal(8))
        self.assertEqual((descriptions[1].number_qualifiers.digits, descriptions[1].number_qualifiers.fraction_digits), (Decimal(12), Decimal(2)))
        table.rows[0].set_member('Amount', Decimal(999))
        self.assertEqual(table.rows[0].get_member('Amount'), Decimal(999))
        rows=result.select();rows.next();self.assertEqual(rows.get_member('Amount'), Decimal(10))
        for value in (NULL,None,'999',True):
            with self.assertRaises(ValueError): table.rows[0].set_member('Amount', value)
        with self.assertRaises(ValueError): table.add()
        with self.assertRaises(ValueError): table.copy()

    def test_nullable_query_schema_does_not_admit_public_union_or_codec(self):
        from yadinassi.type_descriptions import BSLTypeDescription, _query_nullable_description
        query = BSLQuery(self.vm._catalogs, 'SELECT Amount FROM Catalog.Products')
        description = query.execute().unload().columns.items[0].value_type
        for source in ('Number,Null', description):
            with self.assertRaises(ValueError): BSLTypeDescription(source)
        with self.assertRaises(ValueError): _query_nullable_description(BSLTypeDescription('UUID'))
        with self.assertRaises(TypeError): _query_nullable_description(description)
        with self.assertRaises(ValueError): description.adjust_value()
        self.vm.execute('Q=New Query("SELECT Amount FROM Catalog.Products");T=Q.Execute().Unload();')
        for code in ('ValueToStringInternal(T);','ValueToStringInternal(T.Columns[0].ValueType);'):
            with self.assertRaises(Exception): self.vm.execute(code)
        # Ordinary scalar tables, defaults and codecs remain unchanged.
        self.vm.execute('T=New ValueTable;T.Columns.Add("N",New TypeDescription("Number"));T.Add();Message(T[0].N);Message(ValueToStringInternal(T)<>"");')
        self.assertEqual(self.output[-2:], ['0','Да'])

    def test_unmeasured_default_labels_refuse_unload_but_alias_is_supported(self):
        query=BSLQuery(self.vm._catalogs,'SELECT Description FROM Catalog.Products')
        result=query.execute();rows=result.select();rows.next()
        self.assertEqual(rows.get_member('Description'),'item')
        with self.assertRaises(ValueError): result.unload()
        query.set_member('Text','SELECT Description AS Caption FROM Catalog.Products')
        self.assertEqual(query.execute().unload().columns.items[0].name,'Caption')


if __name__ == '__main__': unittest.main()
