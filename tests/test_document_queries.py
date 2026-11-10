"""Owned document report contract; not native 1C compatibility evidence."""
from dataclasses import replace
from decimal import Decimal
from pathlib import Path
import re
import tempfile
import unittest
from unittest.mock import patch
from uuid import uuid4

from yadinassi import Interpreter, BSLRuntimeError
from yadinassi.configuration_xml import import_configuration
from yadinassi.database_context import SQLiteDBContext
from yadinassi.document_types import BSLDocumentReference
from yadinassi.queries import BSLQuery
from yadinassi.sqlite_catalog import SQLiteCatalogBackend
from test_document_configuration_xml import document_files


def report_files():
    """Extend the authored fixture with qualified section amounts and refs."""
    files = document_files()
    source = files['Documents/Orders.xml'].decode()
    attributes = re.findall(r'<Attribute uuid="[^"]+">.*?</Attribute>', source)
    extra = ''.join(attribute.replace(re.search(r'uuid="([^"]+)"', attribute)[1], str(uuid4()), 1)
                    for attribute in attributes
                    if '<Name>Amount</Name>' in attribute or '<Name>Category</Name>' in attribute)
    source = source.replace('</ChildObjects></TabularSection>', extra+'</ChildObjects></TabularSection>')
    files['Documents/Orders.xml'] = source.encode()
    return files


class DocumentQueryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name)/'reports.sqlite'
        self.files = report_files()
        self.context = SQLiteDBContext.create(self.path, import_configuration(self.files))
        self.output = []
        self.vm = Interpreter(database_context=self.context, output=self.output.append)

    def tearDown(self):
        self.context.close()
        self.temp.cleanup()

    def seed(self):
        self.vm.execute('''C=Catalogs.Categories.CreateItem();C.Code="01";C.Description="Customer";C.Write();
For I=1 To 3 Do
 D=Documents.Orders.CreateDocument();D.Date=Date(2026,11,I,12,30,5);
 D.Text="order";D.Amount=I*10;D.Active=I<>2;D.Category=C.Ref;
 R=D.Lines.Add();R.Flag=True;R.Amount=I*2;R.Category=C.Ref;
 R=D.Lines.Add();R.Flag=False;R.Amount=I*3;R.Category=C.Ref;
 D.Write();
EndDo;''')

    def query(self, text, manager=None):
        query = BSLQuery(self.vm._catalogs, text, documents=self.vm._documents)
        if manager is not None:
            query.set_member('TempTablesManager', manager)
        return query

    def rows(self, text, manager=None):
        return self.query(text, manager).execute()._rows

    def test_standard_fields_parameters_order_and_top_in_bsl(self):
        self.seed()
        self.vm.execute('''Q=New Query("SELECT TOP 2 Number,Date,Posted,DeletionMark AS Deleted,Amount FROM Document.Orders WHERE Date>=&Since AND Active=&Active ORDER BY Number DESC");
Q.SetParameter("Since",Date(2026,11,1));Q.SetParameter("Active",True);
S=Q.Execute().Select();While S.Next() Do Message(S.Number);Message(S.Amount);Message(S.Posted);Message(S.Deleted);EndDo;''')
        self.assertEqual(self.output, ['000000003','30','Нет','Нет','000000001','10','Нет','Нет'])

    def test_russian_source_and_standard_aliases(self):
        self.seed()
        self.vm.execute('''З=Новый Запрос("ВЫБРАТЬ Номер КАК Н, Дата КАК Д, ПометкаУдаления КАК У, Проведён КАК П, Проведен КАК П2 ИЗ Документ.Orders ГДЕ Номер = &Номер");
З.УстановитьПараметр("Номер","000000002");С=З.Выполнить().Выбрать();
Сообщить(С.Следующий());Сообщить(С.Н);Сообщить(С.Д=Дата(2026,11,2,12,30,5));Сообщить(С.У);Сообщить(С.П);Сообщить(С.П2);''')
        self.assertEqual(self.output, ['Да','000000002','Да','Нет','Нет','Нет'])

    def test_scalar_unload_labels_qualifiers_and_detachment(self):
        self.seed()
        self.vm.execute('''Q=New Query("SELECT Number,Date,Posted,Amount,DeletionMark AS Deleted FROM Document.Orders ORDER BY Number");
R=Q.Execute();T=R.Unload();Message(T.Columns[0].Name);Message(T.Columns[1].Name);Message(T.Columns[2].Name);
Message(T.Columns[0].ValueType.StringQualifiers.Length);
Message(T.Columns[1].ValueType.ContainsType(Type("Date")));Message(T.Columns[2].ValueType.ContainsType(Type("Boolean")));
Message(T.Columns[3].ValueType.NumberQualifiers.Digits);Message(T.Columns[3].ValueType.NumberQualifiers.FractionDigits);
T[0].Amount=999;S=R.Select();S.Next();Message(S.Amount);Message(Documents.Orders.FindByNumber("000000001").Amount);''')
        self.assertEqual(self.output, ['Number','Date','Posted','9','Да','Да','12','2','10','10'])

    def test_empty_scalar_result_preserves_typed_schema(self):
        table = self.query('SELECT Number,Date,Posted,Amount FROM Document.Orders').execute().unload()
        self.assertEqual(len(table.rows), 0)
        self.assertEqual([column.name for column in table.columns.items], ['Number','Date','Posted','Amount'])
        self.assertEqual(table.columns.items[0].value_type.string_qualifiers.length, Decimal(9))

    def test_document_reference_filter_and_cursor_identity(self):
        self.seed()
        self.vm.execute('''Q=New Query("SELECT Ref,Number FROM Document.Orders WHERE Ref=&Ref");
Q.SetParameter("Ref",D.Ref);S=Q.Execute().Select();Message(S.Next());Message(S.Ref=D.Ref);
Message(TypeOf(S.Ref)=Type("DocumentRef.Orders"));Message(S.Ref.Amount);Message(S.Next());''')
        self.assertEqual(self.output, ['Да','Да','Да','30','Нет'])

    def test_catalog_join_and_aggregate_report(self):
        self.seed()
        text = ('SELECT C.Description AS Customer,COUNT(*) AS Orders,SUM(D.Amount*2) AS Gross '
                'FROM Document.Orders AS D JOIN Catalog.Categories AS C ON D.Category=C.Ref '
                'WHERE D.Amount>=20 GROUP BY C.Description HAVING SUM(D.Amount)>40 ORDER BY Customer')
        self.assertEqual(self.rows(text), (('Customer',Decimal(2),Decimal(100)),))

    def test_section_owner_join_and_one_based_line_numbers(self):
        self.seed()
        text = ('SELECT D.Number,L.LineNumber,L.Amount FROM Document.Orders.Lines AS L '
                'JOIN Document.Orders AS D ON L.Ref=D.Ref WHERE D.Number="000000002" ORDER BY L.LineNumber')
        self.assertEqual(self.rows(text), (('000000002',Decimal(1),Decimal(4)),('000000002',Decimal(2),Decimal(6))))

    def test_russian_section_fields_and_catalog_join(self):
        self.seed()
        text = ('ВЫБРАТЬ Л.НомерСтроки КАК Строка, С.Код КАК Клиент ИЗ Документ.Orders.Lines КАК Л '
                'СОЕДИНЕНИЕ Справочник.Categories КАК С ПО Л.Category=С.Ссылка '
                'ГДЕ Л.Ссылка=&Владелец УПОРЯДОЧИТЬ ПО Строка')
        query = self.query(text)
        query.set_parameter('Владелец', self.vm.execute('D.Ref'))
        self.assertEqual(query.execute()._rows, ((Decimal(1),'01'),(Decimal(2),'01')))

    def test_section_does_not_inherit_owner_fields(self):
        for field in ('Number','Date','Posted','DeletionMark'):
            with self.subTest(field=field), self.assertRaises(ValueError):
                self.rows(f'SELECT {field} FROM Document.Orders.Lines')

    def test_package_retains_document_refs_and_joins_owners(self):
        self.seed()
        text = ('SELECT Ref,Amount INTO Orders FROM Document.Orders WHERE Amount>=20; '
                'SELECT D.Number,SUM(L.Amount) AS Total FROM Orders AS O '
                'JOIN Document.Orders AS D ON O.Ref=D.Ref JOIN Document.Orders.Lines AS L ON L.Ref=O.Ref '
                'GROUP BY D.Number ORDER BY D.Number')
        self.assertEqual(self.rows(text), (('000000002',Decimal(10)),('000000003',Decimal(15))))

    def test_union_preserves_document_identity_and_distinctness(self):
        self.seed()
        text = ('SELECT Ref FROM Document.Orders WHERE Amount>=20 UNION SELECT Ref FROM Document.Orders WHERE Amount<=20')
        refs = [row[0] for row in self.rows(text)]
        self.assertEqual(len(refs), 3)
        self.assertTrue(all(type(ref) is BSLDocumentReference for ref in refs))
        self.assertEqual(len(set(refs)), 3)
        self.assertEqual(len(self.rows(text.replace(' UNION ', ' UNION ALL '))), 4)

    def test_wrong_source_namespace_and_unknown_sections_rejected_empty(self):
        for source in ('Catalog.Orders','Document.Categories','Document.Orders.Unknown'):
            with self.subTest(source=source), self.assertRaises(ValueError):
                self.rows('SELECT Ref FROM '+source)

    def test_reference_family_mismatch_rejected_even_empty(self):
        for text in ('SELECT D.Ref FROM Document.Orders AS D JOIN Catalog.Categories AS C ON D.Ref=C.Ref',
                     'SELECT Ref FROM Document.Orders UNION SELECT Ref FROM Catalog.Categories',
                     'SELECT Ref INTO EmptyOrders FROM Document.Orders; SELECT C.Ref FROM Catalog.Categories AS C JOIN EmptyOrders AS D ON C.Ref=D.Ref'):
            with self.subTest(text=text), self.assertRaises(TypeError):
                self.rows(text)

    def test_reference_parameter_rejects_wrong_kind_target_and_snapshot_empty(self):
        local = self.vm.execute('Documents.Orders.EmptyRef()')
        other = Interpreter(database_context=self.context)
        bad_target = replace(local, value_type=replace(local.value_type, metadata_uuid=uuid4(), name='Other'))
        values = [self.vm.execute('Catalogs.Categories.EmptyRef()'),
                  other.execute('Documents.Orders.EmptyRef()'),bad_target, '000000001',Decimal(1)]
        for value in values:
            query = self.query('SELECT Number FROM Document.Orders WHERE Ref=&Target')
            with self.subTest(kind=type(value).__name__), self.assertRaises(TypeError):
                query.set_parameter('Target', value)
                query.execute()
        # Exact host-type admission must not invoke equality/hash hooks on an
        # unsupported value's metaclass, either at SetParameter or key binding.
        from yadinassi.relational_queries import _key
        calls = []
        class HostileMeta(type):
            def __eq__(cls, other):
                calls.append('eq')
                raise AssertionError('host metaclass equality invoked')
            def __hash__(cls):
                calls.append('hash')
                raise AssertionError('host metaclass hash invoked')
        class Hostile(metaclass=HostileMeta):
            pass
        hostile = Hostile()
        query = self.query('SELECT Number FROM Document.Orders WHERE Ref=&Target')
        with self.assertRaises(TypeError): query.set_parameter('Target', hostile)
        with self.assertRaises(TypeError): _key(hostile)
        self.assertEqual(calls, [])

    def test_dynamic_reference_unload_and_codec_remain_rejected(self):
        for seeded in (False, True):
            if seeded:
                self.seed()
            for text in ('SELECT Ref FROM Document.Orders','SELECT Ref FROM Document.Orders.Lines',
                         'SELECT Category FROM Document.Orders'):
                with self.subTest(seeded=seeded,text=text), self.assertRaises((TypeError,ValueError)):
                    self.query(text).execute().unload()
        for code in ('ValueToStringInternal(D.Ref)', 'New TypeDescription("DocumentRef.Orders")'):
            with self.subTest(code=code), self.assertRaises(BSLRuntimeError):
                self.vm.execute(code)

    def test_document_result_is_detached_and_read_view_is_released(self):
        self.seed()
        query = self.query('SELECT Number,Amount FROM Document.Orders ORDER BY Number')
        result = query.execute()
        self.vm.execute('O=Documents.Orders.FindByNumber("000000001").GetObject();O.Amount=99;O.Write();')
        self.assertEqual(result._rows[0], ('000000001',Decimal(10)))
        self.assertEqual(query.execute()._rows[0], ('000000001',Decimal(99)))
        self.assertIsNone(self.context.backend._active)

    def test_catalog_first_mixed_package_uses_one_composite_view(self):
        self.seed()
        backend = self.context.backend
        with patch.object(backend, 'begin_query_read', wraps=backend.begin_query_read) as begin:
            self.assertEqual(self.rows('SELECT Ref INTO Customers FROM Catalog.Categories; '
                'SELECT COUNT(*) AS N FROM Document.Orders AS D JOIN Customers AS C ON D.Category=C.Ref'), ((Decimal(3),),))
        self.assertEqual(begin.call_count, 1)
        self.assertIsNone(backend._active)

    def test_mixed_join_uses_one_composite_view(self):
        self.seed()
        backend = self.context.backend
        with patch.object(backend, 'begin_query_read', wraps=backend.begin_query_read) as begin:
            self.assertEqual(self.rows('SELECT COUNT(*) AS N FROM Catalog.Categories AS C '
                'JOIN Document.Orders AS D ON C.Ref=D.Category'), ((Decimal(3),),))
        self.assertEqual(begin.call_count, 1)
        self.assertIsNone(backend._active)

    def test_failed_package_restores_temp_tables_and_releases_view(self):
        self.seed()
        manager = self.vm.execute('New TempTablesManager')
        self.rows('SELECT Ref,Amount INTO Original FROM Document.Orders', manager)
        with self.assertRaises((ValueError,ArithmeticError)):
            self.rows('DESTROY Original; SELECT Ref,Amount INTO NewTable FROM Document.Orders; '
                      'SELECT Amount/(Amount-20) AS Broken FROM NewTable', manager)
        self.assertEqual(self.rows('SELECT SUM(Amount) AS Total FROM Original',manager), ((Decimal(60),),))
        with self.assertRaises(ValueError):
            self.rows('SELECT Ref FROM NewTable',manager)
        self.assertIsNone(self.context.backend._active)

    def test_readonly_report_preserves_database_and_configuration_bytes(self):
        self.seed()
        self.context.close()
        self.context._backend = SQLiteCatalogBackend(self.path, read_only=True)
        self.vm = Interpreter(database_context=self.context)
        before = self.path.read_bytes()
        self.assertEqual(self.rows('SELECT SUM(Amount) AS Total FROM Document.Orders'), ((Decimal(60),),))
        self.assertEqual(self.rows('SELECT COUNT(*) AS N FROM Document.Orders.Lines'), ((Decimal(6),),))
        self.assertEqual(self.context.backend.export_configuration(), self.files)
        self.assertEqual(self.path.read_bytes(), before)
        self.assertIsNone(self.context.backend._active)

    def test_document_only_database_needs_no_catalog_schemas(self):
        context = SQLiteDBContext.create(Path(self.temp.name)/'documents-only.sqlite',
            import_configuration(document_files(catalogs=False,fields=False)))
        try:
            vm = Interpreter(database_context=context)
            vm.execute('D=Documents.Orders.CreateDocument();D.Write();Q=New Query("SELECT Number FROM Document.Orders");')
            self.assertEqual(vm.execute('Q.Execute().Unload()[0].Number'), '000000001')
        finally:
            context.close()

    def test_checked_in_report_example_executes_end_to_end(self):
        self.seed()
        self.vm.execute((Path(__file__).resolve().parents[1]/'examples/document-query-report.bsl').read_text())
        self.assertEqual(self.output, ['Customer','3','60','30'])


    def test_reference_conditionals_preserve_identity_and_reject_wrong_kinds(self):
        from yadinassi.values import NULL
        self.seed()
        query = self.query('SELECT CASE WHEN Active=TRUE THEN Ref ELSE NULL END AS Maybe, ISNULL(Ref,&Empty) AS Owner FROM Document.Orders ORDER BY Number')
        query.set_parameter('Empty', self.vm.execute('Documents.Orders.EmptyRef()'))
        rows = query.execute()._rows
        self.assertIs(rows[1][0], NULL)
        self.assertTrue(all(type(row[1]) is BSLDocumentReference for row in rows))
        self.assertEqual(rows[0][0], rows[0][1])
        for expression in ('CASE WHEN Active=TRUE THEN Ref ELSE &Wrong END', 'ISNULL(Ref,&Wrong)'):
            for wrong in (self.vm.execute('Catalogs.Categories.EmptyRef()'),
                          Interpreter(database_context=self.context).execute('Documents.Orders.EmptyRef()')):
                query = self.query('SELECT '+expression+' AS R FROM Document.Orders WHERE Amount<0')
                query.set_parameter('Wrong', wrong)
                with self.assertRaises(TypeError): query.execute()

    def test_group_and_count_distinct_document_references(self):
        self.seed()
        self.assertEqual(self.rows('SELECT COUNT(DISTINCT Ref) AS N FROM Document.Orders.Lines'), ((Decimal(3),),))
        rows = self.rows('SELECT Ref,COUNT(*) AS N FROM Document.Orders.Lines GROUP BY Ref')
        self.assertEqual(len(rows), 3)
        self.assertTrue(all(type(ref) is BSLDocumentReference and count == 2 for ref, count in rows))

    def test_typed_null_union_retains_document_reference_metadata(self):
        self.seed()
        query = self.query('SELECT NULL AS Owner INTO Owners FROM Document.Orders WHERE Number="000000001" '
                           'UNION SELECT Ref FROM Document.Orders; '
                           'SELECT COUNT(*) AS N FROM Owners AS O JOIN Document.Orders AS D ON O.Owner=D.Ref')
        self.assertEqual(query.execute()._rows, ((Decimal(3),),))

    def test_catalog_first_package_initializes_fresh_document_metadata(self):
        self.seed()
        self.vm = Interpreter(database_context=self.context)
        self.assertIsNone(self.vm._documents._metadata._items)
        self.assertEqual(self.rows('SELECT Ref INTO Customers FROM Catalog.Categories; '
            'SELECT COUNT(*) AS N FROM Document.Orders AS D JOIN Customers AS C ON D.Category=C.Ref'), ((Decimal(3),),))
        self.assertIsNone(self.context.backend._active)

    def test_external_scalar_table_joins_document_package(self):
        self.seed()
        self.vm.execute('''Input=New ValueTable;Input.Columns.Add("Number",New TypeDescription("String",,New StringQualifiers(9)));
R=Input.Add();R.Number="000000002";Q=New Query;
Q.SetParameter("Input",Input);Q.Text="SELECT D.Ref,D.Amount INTO Matched FROM &Input AS I JOIN Document.Orders AS D ON I.Number=D.Number; SELECT SUM(Amount) AS Total FROM Matched";
Message(Q.Execute().Unload()[0].Total);''')
        self.assertEqual(self.output, ['20'])

    def test_narrow_projection_validates_unprojected_card_and_sections(self):
        from yadinassi.catalog_backend import BackendError
        from yadinassi.sqlite_documents import DocumentView
        self.seed()
        original = DocumentView.scan_documents
        def corrupt(view, identity, request):
            page = original(view, identity, request)
            card = page.rows[0]
            values = ('bad',) + card.values[1:]
            return replace(page, rows=(replace(card, deletion_mark=1, values=values),))
        with patch.object(DocumentView, 'scan_documents', corrupt), self.assertRaises(BackendError):
            self.rows('SELECT Number FROM Document.Orders')
        self.assertIsNone(self.context.backend._active)
        def corrupt_section(view, identity, request):
            page = original(view, identity, request)
            card = page.rows[0]
            section = card.tabular_sections[0]
            line = section.rows[0]
            bad = replace(line, values=(1,) + line.values[1:])
            return replace(page, rows=(replace(card, tabular_sections=(replace(section, rows=(bad,) + section.rows[1:]),)),))
        with patch.object(DocumentView, 'scan_documents', corrupt_section), self.assertRaises(BackendError):
            self.rows('SELECT Number FROM Document.Orders')
        self.assertIsNone(self.context.backend._active)

    def test_document_input_budget_fails_instead_of_returning_top_partial(self):
        self.seed()
        with patch('yadinassi.queries._MAX_CELLS', 4), self.assertRaisesRegex(ValueError, 'input resource'):
            self.rows('SELECT TOP 1 Number FROM Document.Orders')
        self.assertIsNone(self.context.backend._active)

    def test_duplicate_document_records_and_invalid_page_refused(self):
        from yadinassi.catalog_backend import BackendError
        from yadinassi.sqlite_documents import DocumentView
        self.seed()
        original = DocumentView.scan_documents
        first = []
        def duplicate(view, identity, request):
            page = original(view, identity, request)
            if not first: first.extend(page.rows)
            return replace(page, rows=tuple(first))
        with patch.object(DocumentView, 'scan_documents', duplicate), self.assertRaises(BackendError):
            self.rows('SELECT Number FROM Document.Orders')
        self.assertIsNone(self.context.backend._active)
        def oversized(view, identity, request):
            page = original(view, identity, request)
            return replace(page, rows=page.rows*2)
        with patch.object(DocumentView, 'scan_documents', oversized), self.assertRaises(BackendError):
            self.rows('SELECT COUNT(*) AS N FROM Document.Orders')
        self.assertIsNone(self.context.backend._active)

    def test_composite_close_failure_does_not_publish_temporaries(self):
        from yadinassi.sqlite_documents import DocumentView
        self.seed()
        manager = self.vm.execute('New TempTablesManager')
        original = DocumentView.close
        def close(view):
            original(view)
            raise ValueError('synthetic close failure')
        with patch.object(DocumentView, 'close', close), self.assertRaisesRegex(ValueError, 'close failure'):
            self.rows('SELECT Ref INTO Unpublished FROM Document.Orders', manager)
        self.assertEqual(manager._tables, {})
        self.assertIsNone(self.context.backend._active)
        self.rows('SELECT Ref INTO Published FROM Document.Orders', manager)
        self.assertIn('published', manager._tables)


if __name__ == '__main__':
    unittest.main()
