"""Explicit BSL query dereference is set-based; script reference access stays live."""
from decimal import Decimal
from pathlib import Path
import re
import tempfile
import unittest

from yadinassi import Interpreter
from yadinassi.configuration.configuration_xml import import_configuration
from yadinassi.db.database_context import SQLiteDBContext
from yadinassi.types.values import NULL
from catalog_sections_fixture import configuration_files_with_sections
from test_document_queries import report_files
from test_information_registers import register_files


class QueryReferenceProjectionTests(unittest.TestCase):
    def open_db(self, files):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        context = SQLiteDBContext.create(Path(directory.name) / 'query.sqlite', import_configuration(files))
        self.addCleanup(context.close)
        vm = Interpreter(database_context=context)
        self.addCleanup(vm.close)
        return context, vm

    @staticmethod
    def run_query(vm, text, *, variable='R'):
        statement = text.replace('"', '""')
        return vm.execute(f'Q=New Query("{statement}"); {variable}=Q.Execute(); {variable}')

    def documents(self):
        context, vm = self.open_db(report_files())
        vm.execute('''C=Catalogs.Categories.CreateItem(); C.Code="K"; C.Description="Caption"; C.Write();
D=Documents.Orders.CreateDocument(); D.Number="A"; D.Date=Date(2026,11,1); D.Category=C.Ref;
L=D.Lines.Add(); L.Flag=True; L.Category=C.Ref; D.Write();
D=Documents.Orders.CreateDocument(); D.Number="B"; D.Date=Date(2026,11,2);
L=D.Lines.Add(); L.Flag=False; D.Write();''')
        return context, vm

    def test_document_caption_and_code_share_one_left_join_and_keep_empty_object(self):
        context, vm = self.documents()
        self.run_query(vm, 'SELECT Number FROM Document.Orders')
        target = context.backend._layout.table_name(vm._catalogs.get_index('Categories')._schema.identity)
        trace = []
        connection = context.backend._read_handle.connection
        connection.set_trace_callback(trace.append)
        try:
            result = self.run_query(vm,
                'SELECT D.Number, D.Category.Description AS Caption, D.Category.Code AS CategoryCode '
                'FROM Document.Orders AS D ORDER BY D.Number')
        finally:
            connection.set_trace_callback(None)
        self.assertEqual(result._rows, (('A', 'Caption', 'K'), ('B', NULL, NULL)))
        data = [sql for sql in trace if f'"{target}"' in sql and 'document_record' in sql]
        self.assertEqual(len(data), 1, trace)
        self.assertEqual(data[0].count(f'JOIN "{target}"'), 1, data[0])

    def test_script_ref_is_live_but_explicit_projected_column_is_captured(self):
        _, vm = self.documents()
        self.run_query(vm, 'SELECT D.Category AS LiveRef, D.Category.Description AS Caption '
                           'FROM Document.Orders AS D ORDER BY D.Number', variable='Captured')
        vm.execute('C.Description="Changed"; C.Write();')
        vm.execute('S=Captured.Select(); S.Next();')
        self.assertEqual(vm.execute('S.Caption'), 'Caption')
        self.assertEqual(vm.execute('S.LiveRef.Description'), 'Changed')

    def test_russian_path_and_explicit_source_alias_are_not_confused(self):
        _, vm = self.documents()
        result = self.run_query(vm,
            'ВЫБРАТЬ П.Ссылка.Наименование КАК Заголовок, П.Код КАК Номер '
            'ИЗ Справочник.Categories КАК П УПОРЯДОЧИТЬ ПО П.Код')
        self.assertEqual(result._rows, (('Caption', 'K'),))

    def test_document_tabular_part_can_project_its_owner_and_a_declared_reference(self):
        _, vm = self.documents()
        result = self.run_query(vm,
            'SELECT L.Ref.Number AS OwnerNumber, L.Category.Description AS Caption '
            'FROM Document.Orders.Lines AS L WHERE L.Flag=True OR L.Flag=False ORDER BY OwnerNumber')
        self.assertEqual(result._rows, (('A', 'Caption'), ('B', NULL)))

    def test_catalog_tabular_part_can_dereference_both_owner_and_field(self):
        _, vm = self.open_db(configuration_files_with_sections())
        vm.execute('''C=Catalogs.Categories.CreateItem(); C.Code="K"; C.Description="Category"; C.Write();
P=Catalogs.Products.CreateItem(); P.Code="P"; P.Description="Product";
L=P.Lines.Add(); L.Text="a"; L.Category=C.Ref;
L=P.Lines.Add(); L.Text="b"; P.Write();''')
        result = self.run_query(vm,
            'SELECT L.Ref.Description AS OwnerText, L.Category.Description AS Caption '
            'FROM Catalog.Products.Lines AS L WHERE L.Text="A" OR L.Text="B" ORDER BY L.Text')
        self.assertEqual(result._rows, (('Product', 'Category'), ('Product', NULL)))


    def test_independent_register_dereferences_its_typed_dimension(self):
        files = register_files()
        key = 'InformationRegisters/Prices.xml'
        files[key] = re.sub(rb'(<Name>Item</Name><Type>).*?(</Type>)',
            lambda m: m[1] + b'<v8:Type>cfg:CatalogRef.Categories</v8:Type>' + m[2],
            files[key], count=1)
        _, vm = self.open_db(files)
        vm.execute('''C=Catalogs.Categories.CreateItem(); C.Code="K"; C.Description="Category"; C.Write();
P=InformationRegisters.Prices.CreateRecordManager(); P.Item=C.Ref; P.Region="A"; P.Price=42; P.Write();
P=InformationRegisters.Prices.CreateRecordManager(); P.Region="B"; P.Price=10; P.Write();''')
        result = self.run_query(vm,
            'SELECT P.Region, P.Item.Description AS Caption, P.Price '
            'FROM InformationRegister.Prices AS P WHERE P.Price>41 OR P.Region="B" ORDER BY P.Region')
        self.assertEqual(result._rows, (('A', 'Category', Decimal('42')), ('B', NULL, Decimal('10'))))

    def test_main_demo_document_and_raw_accumulation_use_the_same_reference_path(self):
        from test_main_demo_runtime import MainDemoRuntimeTests, SEED

        demo = MainDemoRuntimeTests()
        self.addCleanup(demo.doCleanups)
        demo.setUp()
        demo.vm.execute(SEED+'''D=Documents.Receipt.CreateDocument(); D.Number="r1"; D.Date=Date(2024,1,1);
D.Warehouse=Склад.Ссылка; L=D.Lines.Add(); L.Product=Карточка.Ссылка; L.Quantity=5; L.Amount=10;
L.Unit=Enums.Units.Piece; D.Write(DocumentWriteMode.Posting);''')
        result = self.run_query(demo.vm,
            'SELECT R.Number, R.Warehouse.Description AS Caption FROM Document.Receipt AS R')
        self.assertEqual(result._rows, (('r1', 'Основной'),))
        result = self.run_query(demo.vm,
            'SELECT M.Warehouse.Description AS Caption, M.Product.Description AS Item, M.Quantity '
            'FROM AccumulationRegister.Stock AS M WHERE M.Quantity=5 OR M.Quantity<0')
        self.assertEqual(result._rows, (('Основной', 'Кабель', Decimal(5)),))

    def test_card_filter_and_nullable_projection_run_in_one_statement(self):
        context, vm = self.documents()
        vm.execute('Selected=Documents.Orders.FindByNumber("B");')
        trace = []
        connection = context.backend._read_handle.connection
        connection.set_trace_callback(trace.append)
        try:
            result = vm.execute('''Q=New Query("SELECT D.Number, D.Category.Description AS Caption FROM Document.Orders AS D WHERE D.Ref=&Selected AND D.Number=&Number");
Q.SetParameter("Selected",Selected); Q.SetParameter("Number","b"); R=Q.Execute(); R''')
        finally:
            connection.set_trace_callback(None)
        self.assertEqual(result._rows, (('B', NULL),))
        data = [sql for sql in trace if ' LEFT JOIN ' in sql and 'document_record' in sql]
        self.assertEqual(len(data), 1, trace)

    def test_raw_recorder_register_can_project_declared_document_header(self):
        from test_document_posting_runtime import PostingRuntimeTests

        fixture = PostingRuntimeTests()
        self.addCleanup(fixture.doCleanups)
        fixture.setUp()
        fixture.make('''Procedure Posting(Cancel, Mode)
            Row=RegisterRecords.OwnedPostingRows.Add();
            Row.Key=Number(Number); Row.Amount=5;
            RegisterRecords.OwnedPostingRows.Write=True;
        EndProcedure''')
        for number in (3, 8):
            fixture.new(number)
            fixture.post()
        result = self.run_query(fixture.vm,
            'SELECT M.Recorder.Number AS Doc, M.Amount '
            'FROM InformationRegister.OwnedPostingRows AS M WHERE M.Amount=5 OR M.Amount=99 ORDER BY Doc')
        self.assertEqual(result._rows, (('3', Decimal(5)), ('8', Decimal(5))))
