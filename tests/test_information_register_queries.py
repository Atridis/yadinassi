"""Independent register reporting over owned SQLite, not native parity evidence."""
from contextlib import closing
from dataclasses import replace
from decimal import Decimal
from pathlib import Path
import json
import re
import sqlite3
import tempfile
import unittest
from unittest.mock import patch
from uuid import uuid4

from yadinassi import Interpreter
from yadinassi.catalog_backend import BackendError
from yadinassi.configuration_xml import import_configuration
from yadinassi.database_context import SQLiteDBContext
from yadinassi.queries import BSLQuery
from yadinassi.sqlite_catalog import SQLiteCatalogBackend
from yadinassi.sqlite_documents import DocumentView
from test_document_configuration_xml import document_files


def register_files(*, catalogs=True, documents=True):
    files = document_files(catalogs=catalogs, fields=catalogs)
    if not documents:
        files['Configuration.xml'] = files['Configuration.xml'].replace(b'<Document>Orders</Document>', b'')
        del files['Documents/Orders.xml']
    source = document_files()['Documents/Orders.xml'].decode()
    attributes = re.findall(r'<Attribute uuid="[^"]+">.*?</Attribute>', source)
    fields = []
    for original, name, kind in [('Text','Key','Dimension'),('Category','Category','Dimension'),
                                  ('Amount','Amount','Resource'),('Active','Enabled','Attribute'),('Stamp','Stamp','Attribute')]:
        if not catalogs and original == 'Category': continue
        item = next(a for a in attributes if f'<Name>{original}</Name>' in a)
        item = re.sub(r'uuid="[^"]+"', f'uuid="{uuid4()}"', item, count=1)
        item = item.replace(f'<Name>{original}</Name>', f'<Name>{name}</Name>')
        fields.append(item.replace('<Attribute ', '<'+kind+' ').replace('</Attribute>', '</'+kind+'>'))
    prefix = files['Configuration.xml'].decode().split('<Configuration ')[0]
    files['Configuration.xml'] = files['Configuration.xml'].replace(b'</ChildObjects>', b'<InformationRegister>Rates</InformationRegister></ChildObjects>')
    files['InformationRegisters/Rates.xml'] = (prefix+f'<InformationRegister uuid="{uuid4()}"><Properties><Name>Rates</Name><InformationRegisterPeriodicity>Nonperiodical</InformationRegisterPeriodicity><WriteMode>Independent</WriteMode></Properties><ChildObjects>'+''.join(fields)+'</ChildObjects></InformationRegister></MetaDataObject>').encode()
    return files


class InformationRegisterQueryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name)/'register.sqlite'
        self.files = register_files()
        self.context = SQLiteDBContext.create(self.path, import_configuration(self.files))
        self.addCleanup(self.context.close)
        self.output = []
        self.vm = Interpreter(database_context=self.context, output=self.output.append)

    def query(self, text, manager=None):
        query = BSLQuery(self.vm._catalogs, text, self.vm._documents, self.vm._information_registers)
        if manager is not None: query.set_member('TempTablesManager', manager)
        return query

    def rows(self, text, manager=None): return self.query(text, manager).execute()._rows

    def seed(self):
        self.vm.execute('''C=Catalogs.Categories.CreateItem();C.Code="C";C.Description="Customer";C.Write();
For I=1 To 3 Do
 R=InformationRegisters.Rates.CreateRecordManager();R.Key=String(I);R.Category=C.Ref;
 R.Amount=I*10;R.Enabled=I<>2;R.Stamp=Date(2026,11,I);R.Write();
EndDo;
D=Documents.Orders.CreateDocument();D.Category=C.Ref;D.Amount=100;D.Write();''')

    def test_english_bsl_report_and_exact_parameters(self):
        self.seed()
        self.vm.execute('''Q=New Query("SELECT Key,Amount*2 AS Gross FROM InformationRegister.Rates WHERE Enabled=TRUE AND Amount>=&Minimum ORDER BY Key DESC");
Q.SetParameter("Minimum",10);S=Q.Execute().Select();While S.Next() Do Message(S.Key);Message(S.Gross);EndDo;''')
        self.vm.execute((Path(__file__).resolve().parents[1]/'examples/information-register-report.bsl').read_text())
        self.assertEqual(self.output, ['3','60','1','20','Customer','40'])

    def test_russian_source_group_having_and_order(self):
        self.seed()
        self.assertEqual(self.rows('ВЫБРАТЬ Enabled, СУММА(Amount) КАК Total ИЗ РегистрСведений.Rates '
            'СГРУППИРОВАТЬ ПО Enabled ИМЕЮЩИЕ СУММА(Amount)>20 УПОРЯДОЧИТЬ ПО Total'), ((True,Decimal(40)),))

    def test_empty_result_has_typed_dimensions_resources_attributes(self):
        table = self.query('SELECT Key,Amount,Enabled,Stamp FROM InformationRegister.Rates').execute().unload()
        self.assertEqual(table.rows, [])
        self.assertEqual([c.name for c in table.columns.items], ['Key','Amount','Enabled','Stamp'])
        self.assertEqual(table.columns.items[0].value_type.string_qualifiers.length, Decimal(32))
        self.assertEqual(table.columns.items[1].value_type.number_qualifiers.fraction_digits, Decimal(2))
        self.assertEqual(self.rows('SELECT COUNT(*) AS N FROM InformationRegister.Rates'), ((Decimal(0),),))

    def test_mixed_catalog_document_register_join(self):
        self.seed()
        self.assertEqual(self.rows('SELECT C.Description AS Customer,SUM(R.Amount) AS Total,MAX(D.Amount) AS DocumentAmount '
            'FROM InformationRegister.Rates AS R JOIN Catalog.Categories AS C ON R.Category=C.Ref '
            'JOIN Document.Orders AS D ON D.Category=C.Ref GROUP BY C.Description'), (('Customer',Decimal(60),Decimal(100)),))

    def test_catalog_first_package_initializes_register_metadata_before_one_view(self):
        self.seed(); self.vm = Interpreter(database_context=self.context)
        backend = self.context.backend
        with patch.object(backend, 'begin_query_read', wraps=backend.begin_query_read) as begin:
            self.assertEqual(self.rows('SELECT Ref INTO Customers FROM Catalog.Categories; '
                'SELECT SUM(R.Amount) AS Total FROM InformationRegister.Rates AS R JOIN Customers AS C ON R.Category=C.Ref'), ((Decimal(60),),))
        self.assertEqual(begin.call_count, 1)
        self.assertIsNone(backend._active)

    def test_register_first_package_then_document_uses_same_view(self):
        self.seed(); self.vm = Interpreter(database_context=self.context)
        backend = self.context.backend
        with patch.object(backend, 'begin_query_read', wraps=backend.begin_query_read) as begin:
            self.assertEqual(self.rows('SELECT Category,SUM(Amount) AS Total INTO Totals FROM InformationRegister.Rates GROUP BY Category; '
                'SELECT T.Total,D.Amount FROM Totals AS T JOIN Document.Orders AS D ON T.Category=D.Category'), ((Decimal(60),Decimal(100)),))
        self.assertEqual(begin.call_count, 1)

    def test_register_only_database_and_unreferenced_document_metadata(self):
        context = SQLiteDBContext.create(Path(self.temp.name)/'only.sqlite', import_configuration(register_files(catalogs=False,documents=False)))
        try:
            vm = Interpreter(database_context=context)
            vm.execute('R=InformationRegisters.Rates.CreateRecordManager();R.Key="A";R.Amount=4;R.Write();')
            query = BSLQuery(vm._catalogs, 'SELECT Amount INTO T FROM InformationRegister.Rates; SELECT SUM(Amount) AS Total FROM T', information_registers=vm._information_registers)
            with patch.object(vm._documents._metadata, '_snapshot', side_effect=AssertionError('unneeded document metadata')):
                self.assertEqual(query.execute()._rows, ((Decimal(4),),))
        finally: context.close()

    def test_union_compatible_scalars_and_reference_identity(self):
        self.seed()
        self.assertEqual(self.rows('SELECT Amount FROM InformationRegister.Rates UNION ALL SELECT Amount FROM Document.Orders ORDER BY Amount'),
                         ((Decimal(10),),(Decimal(20),),(Decimal(30),),(Decimal(100),)))
        refs = self.rows('SELECT Category FROM InformationRegister.Rates UNION SELECT Ref FROM Catalog.Categories')
        self.assertEqual(refs, ((self.vm.execute('C.Ref'),),))
        with self.assertRaises(TypeError):
            self.rows('SELECT Category FROM InformationRegister.Rates UNION SELECT Ref FROM Document.Orders')

    def test_reference_parameter_target_snapshot_and_dynamic_unload(self):
        self.seed()
        ref = self.vm.execute('C.Ref')
        query = self.query('SELECT COUNT(*) AS N FROM InformationRegister.Rates WHERE Category=&Category')
        query.set_parameter('Category', ref)
        self.assertEqual(query.execute()._rows, ((Decimal(3),),))
        other = Interpreter(database_context=self.context)
        for value in (other.execute('Catalogs.Categories.EmptyRef()'), self.vm.execute('D.Ref')):
            query.set_parameter('Category', value)
            with self.assertRaises(TypeError): query.execute()
        self.assertEqual(len(self.query('SELECT Category FROM InformationRegister.Rates').execute().unload().rows), 3)
        with self.assertRaises(TypeError): query.set_parameter('Category', self.vm.execute('R'))

    def test_no_fabricated_standard_fields_or_virtual_tables(self):
        for field in ('Ref','Period','Recorder','LineNumber','Number'):
            with self.subTest(field=field), self.assertRaises(ValueError): self.rows('SELECT '+field+' FROM InformationRegister.Rates')
        for source in ('InformationRegister.Rates.SliceLast','РегистрСведений.Rates.СрезПоследних','Catalog.Rates','Document.Rates','InformationRegister.Orders'):
            with self.subTest(source=source), self.assertRaises(ValueError): self.rows('SELECT Amount FROM '+source)

    def test_external_table_join_and_computed_temporary_report(self):
        self.seed()
        self.vm.execute('''T=New ValueTable;T.Columns.Add("Key",New TypeDescription("String",,New StringQualifiers(32)));
Row=T.Add();Row.Key="2";Q=New Query;Q.SetParameter("Input",T);
Q.Text="SELECT R.Amount*2 AS Total INTO Prepared FROM &Input AS I JOIN InformationRegister.Rates AS R ON I.Key=R.Key; SELECT SUM(Total) AS Total FROM Prepared";
Message(Q.Execute().Unload()[0].Total);''')
        self.assertEqual(self.output, ['40'])

    def test_package_failure_rolls_back_temporaries_and_closes_view(self):
        self.seed(); manager = self.vm.execute('New TempTablesManager')
        self.rows('SELECT Amount INTO Original FROM InformationRegister.Rates', manager)
        with self.assertRaises(ValueError):
            self.rows('DESTROY Original; SELECT Amount INTO Lost FROM InformationRegister.Rates; SELECT Amount/(Amount-20) AS Failed FROM Lost', manager)
        self.assertEqual(self.rows('SELECT SUM(Amount) AS Total FROM Original', manager), ((Decimal(60),),))
        self.assertNotIn('lost', manager._tables)
        self.assertIsNone(self.context.backend._active)

    def test_unprojected_malformed_value_and_revision_fail_closed(self):
        self.seed(); original = DocumentView.scan_register
        for mode in ('value','revision'):
            def corrupt(view, identity, request):
                page = original(view, identity, request); record = page.rows[0]
                bad = (replace(record, values=("bad",)+record.values[1:]) if mode == 'value' else
                       replace(record, revision=replace(record.revision, register_id=uuid4())))
                return replace(page, rows=(bad,)+page.rows[1:])
            with self.subTest(mode=mode), patch.object(DocumentView, 'scan_register', corrupt), self.assertRaises(BackendError):
                self.rows('SELECT Key FROM InformationRegister.Rates')
            self.assertIsNone(self.context.backend._active)

    def test_duplicate_logical_dimension_keys_and_digests_fail(self):
        self.seed(); original = DocumentView.scan_register
        def duplicate(view, identity, request):
            page = original(view, identity, request)
            return replace(page, rows=(page.rows[0], page.rows[0]))
        with patch.object(DocumentView, 'scan_register', duplicate), self.assertRaises(BackendError):
            self.rows('SELECT COUNT(*) AS N FROM InformationRegister.Rates')
        self.assertIsNone(self.context.backend._active)

    def test_case_distinct_dimensions_are_not_dropped_as_duplicate_records(self):
        self.seed()
        self.vm.execute('R=InformationRegisters.Rates.CreateRecordManager();R.Key="a";R.Category=C.Ref;R.Write();R=InformationRegisters.Rates.CreateRecordManager();R.Key="A";R.Category=C.Ref;R.Write();')
        self.assertEqual(self.rows('SELECT COUNT(*) AS N FROM InformationRegister.Rates'), ((Decimal(5),),))
        self.assertEqual(self.rows('SELECT COUNT(DISTINCT Key) AS N FROM InformationRegister.Rates'), ((Decimal(4),),))

    def test_input_budget_and_row_bound_fail_before_top_result(self):
        self.seed()
        with patch('yadinassi.queries._MAX_CELLS', 1), self.assertRaisesRegex(ValueError, 'input resource'):
            self.rows('SELECT TOP 1 Key FROM InformationRegister.Rates')
        with patch('yadinassi.query_parser.MAX_ROWS', 2), self.assertRaisesRegex(ValueError, 'input row'):
            self.rows('SELECT TOP 1 Key FROM InformationRegister.Rates')
        self.assertIsNone(self.context.backend._active)

    def test_more_than_1000_records_are_scanned_without_truncation(self):
        self.seed()
        with closing(sqlite3.connect(self.path)) as connection, connection:
            identity, key, revision, values = connection.execute('SELECT * FROM information_register_record LIMIT 1').fetchone()
            dimensions = json.loads(key)
            additions = []
            for i in range(4,1002):
                new = list(dimensions); new[0] = ['s',str(i)]
                additions.append((identity,json.dumps(new,ensure_ascii=False,separators=(',',':')),revision,values))
            connection.executemany('INSERT INTO information_register_record VALUES(?,?,?,?)', additions)
        self.assertEqual(self.rows('SELECT COUNT(*) AS N FROM InformationRegister.Rates'), ((Decimal(1001),),))

    def test_readonly_report_does_not_mutate_database(self):
        self.seed(); self.context.close()
        self.context._backend = SQLiteCatalogBackend(self.path, read_only=True)
        self.vm = Interpreter(database_context=self.context)
        before = self.path.read_bytes()
        self.assertEqual(self.rows('SELECT SUM(Amount) AS Total FROM InformationRegister.Rates'), ((Decimal(60),),))
        self.assertEqual(self.path.read_bytes(), before)
        self.assertEqual(self.context.backend.export_configuration(), self.files)

    def test_close_failure_does_not_publish_register_temporaries(self):
        self.seed(); manager = self.vm.execute('New TempTablesManager'); original = DocumentView.close
        def fail(view): original(view); raise ValueError('close failure')
        with patch.object(DocumentView, 'close', fail), self.assertRaisesRegex(ValueError, 'close failure'):
            self.rows('SELECT Key INTO Lost FROM InformationRegister.Rates', manager)
        self.assertEqual(manager._tables, {})
        self.assertIsNone(self.context.backend._active)

    def test_catalog_fast_path_does_not_require_register_methods(self):
        self.seed()
        with patch.object(self.context.backend, 'begin_query_read', side_effect=AssertionError('not needed')):
            self.assertEqual(self.rows('SELECT Code AS Code FROM Catalog.Categories'), (('C',),))
