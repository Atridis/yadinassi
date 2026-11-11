"""Admitted metadata graph; local contract tests are not new native evidence."""
from contextlib import closing
from decimal import Decimal
from pathlib import Path
import sqlite3
import tempfile
import unittest
from uuid import uuid4

from yadinassi import Interpreter, BSLRuntimeError
from yadinassi.catalog_backend import BackendError
from yadinassi.configuration_xml import import_configuration
from yadinassi.configuration_runtime import ConfigurationApplication
from yadinassi.database_context import SQLiteDBContext
from yadinassi.metadata import BSLMetadata, is_metadata_collection
from sqlite_catalog_fixture import configuration_files
from test_document_configuration_xml import document_files
from test_information_registers import register_files
from test_periodic_information_registers import periodic_files
from configuration_runtime_fixture import module_files


class MetadataGraphTests(unittest.TestCase):
    def runtime(self, files=None):
        directory = tempfile.TemporaryDirectory(); self.addCleanup(directory.cleanup)
        context = SQLiteDBContext.create(Path(directory.name)/'app.sqlite',import_configuration(files or configuration_files()))
        self.addCleanup(context.close)
        vm = Interpreter(database_context=context); self.addCleanup(vm.close)
        return vm, context

    def test_configuration_name_and_empty_presentation(self):
        vm,_ = self.runtime()
        self.assertEqual(vm.execute('Metadata.Name'),'OwnedApplication')
        self.assertEqual(vm.execute('Метаданные.Синоним + Metadata.Comment'),'')

    def test_attribute_collection_does_not_include_standard_fields(self):
        vm,_ = self.runtime()
        self.assertEqual(vm.execute('Metadata.Catalogs.Products.Attributes.Count()'),Decimal(5))
        self.assertIsNone(vm.execute('Metadata.Catalogs.Products.Attributes.Find("Code")'))

    def test_source_tree_order_not_sql_alphabetical(self):
        files=configuration_files()
        files['Configuration.xml']=files['Configuration.xml'].replace(b'<Catalog>Categories</Catalog><Catalog>Products</Catalog>',b'<Catalog>Products</Catalog><Catalog>Categories</Catalog>')
        vm,_=self.runtime(files)
        self.assertEqual(vm.execute('Metadata.Catalogs[0].Name'),'Products')
        self.assertEqual(vm.execute('Metadata.Catalogs.Get(1).Name'),'Categories')

    def test_declared_field_order_and_iteration(self):
        vm,_=self.runtime()
        vm.execute('Names=""; For Each A In Metadata.Catalogs.Products.Attributes Do Names=Names+A.Name+";"; EndDo;')
        self.assertEqual(vm.execute('Names'),'Text;Amount;Active;Stamp;Category;')
        self.assertEqual(vm.execute('Metadata.Catalogs.Products.Attributes.Get(1).Name'),'Amount')

    def test_collection_identity_operations(self):
        vm,_=self.runtime()
        vm.execute('A=Metadata.Catalogs.Products.Attributes; F=A.Find("TEXT");')
        self.assertTrue(vm.execute('A.Contains(F)'))
        self.assertEqual(vm.execute('A.IndexOf(F)'),Decimal(0))
        self.assertEqual(vm.execute('A.IndexOf(Metadata.Catalogs.Products)'),Decimal(-1))
        self.assertFalse(vm.execute('A.Contains(Undefined)'))
        self.assertIs(vm.execute('A["text"]'),vm.execute('F'))

    def test_string_qualifier_and_adjustment(self):
        vm,_=self.runtime()
        vm.execute('D=Метаданные.Справочники.Products.Реквизиты.Text.Тип;')
        self.assertEqual(vm.execute('D.КвалификаторыСтроки.Длина'),Decimal(32))
        self.assertTrue(vm.execute('D.ContainsType(Type("String"))'))
        self.assertEqual(vm.execute('D.AdjustValue("abc")'),'abc')

    def test_number_qualifiers(self):
        vm,_=self.runtime()
        vm.execute('Q=Metadata.Catalogs.Products.Attributes.Amount.Type.NumberQualifiers;')
        self.assertEqual(vm.execute('Q.Digits'),Decimal(12))
        self.assertEqual(vm.execute('Q.FractionDigits'),Decimal(2))
        self.assertTrue(vm.execute('(Q.AllowedSign=AllowedSign.Any)'))

    def test_boolean_and_date_types(self):
        vm,_=self.runtime()
        self.assertTrue(vm.execute('Metadata.Catalogs.Products.Attributes.Active.Type.ContainsType(Type("Boolean"))'))
        self.assertTrue(vm.execute('(Metadata.Catalogs.Products.Attributes.Stamp.Type.DateQualifiers.DateFractions=DateFractions.DateTime)'))

    def test_bound_reference_field_can_be_inspected_and_assigned(self):
        vm,_=self.runtime()
        vm.execute('D=Metadata.Catalogs.Products.Attributes.Category.Type; R=Catalogs.Categories.EmptyRef(); P=Catalogs.Products.CreateItem(); P.Category=D.AdjustValue(R);')
        self.assertTrue(vm.execute('(D.Types()[0]=Type("CatalogRef.Categories"))'))
        self.assertIs(vm.execute('D.AdjustValue(R)'),vm.execute('R'))
        self.assertTrue(vm.execute('(P.Category=R)'))

    def test_foreign_reference_descriptor_is_not_rebound_by_uuid(self):
        vm,context=self.runtime(); other=Interpreter(database_context=context); self.addCleanup(other.close)
        vm.set_variable('Foreign',other.execute('Catalogs.Categories.EmptyRef()'))
        with self.assertRaises(BSLRuntimeError): vm.execute('Metadata.Catalogs.Products.Attributes.Category.Type.AdjustValue(Foreign)')

    def test_catalog_standard_attributes_are_separate(self):
        vm,_=self.runtime()
        vm.execute('S=Metadata.Catalogs.Products.StandardAttributes;')
        self.assertEqual(vm.execute('S.Count()'),Decimal(4))
        self.assertEqual(vm.execute('S["Код"].Type.StringQualifiers.Length'),Decimal(8))
        self.assertEqual(vm.execute('S["Description"].Type.StringQualifiers.Length'),Decimal(64))
        self.assertTrue(vm.execute('S["Ref"].Type.ContainsType(Type("CatalogRef.Products"))'))
        self.assertEqual(vm.execute('S["Code"].Name'),'Код')

    def test_standard_collection_is_not_metadata_object_collection(self):
        vm,_=self.runtime()
        for code in ('Metadata.Catalogs.Products.StandardAttributes.Find("Code")',
                     'Metadata.Catalogs.Products.StandardAttributes.Get(0)',
                     'Metadata.Catalogs.Products.StandardAttributes[0].FullName()',
                     'Metadata.Catalogs.Products.StandardAttributes.Code'):
            with self.subTest(code=code),self.assertRaises(BSLRuntimeError): vm.execute(code)

    def test_standard_iteration(self):
        vm,_=self.runtime()
        vm.execute('N=0; For Each F In Metadata.Catalogs.Products.StandardAttributes Do N=N+1; EndDo;')
        self.assertEqual(vm.execute('N'),Decimal(4))

    def test_full_names_and_roundtrip(self):
        vm,_=self.runtime()
        for path in ('Catalog.Products','Справочник.Products','Catalog.Products.Attribute.Text','Справочник.Products.Реквизит.Text'):
            with self.subTest(path=path):
                item=vm.execute(f'Metadata.FindByFullName("{path}")'); self.assertIsNotNone(item)
                self.assertIs(vm._metadata.find_by_full_name(item.full_name()),item)
        self.assertIsNone(vm.execute('Metadata.FindByFullName("Catalog.Missing")'))
        self.assertIsNone(vm.execute('Metadata.FindByFullName("Catalog.Products.Resource.X")'))
        self.assertIsNone(vm.execute('Metadata.FindByFullName("Catalog.Products.Attribute.Text.Bad.X")'))

    def test_find_by_type_all_admitted_catalog_families(self):
        vm,_=self.runtime()
        for family in ('Ref','Manager','Object','Selection'):
            with self.subTest(family=family):
                self.assertIs(vm.execute(f'Metadata.FindByType(Type("Catalog{family}.Products"))'),vm.execute('Metadata.Catalogs.Products'))
        self.assertIsNone(vm.execute('Metadata.FindByType(Type("String"))'))

    def test_find_by_type_rejects_foreign_snapshot(self):
        vm,context=self.runtime(); other=Interpreter(database_context=context); self.addCleanup(other.close)
        vm.set_variable('Foreign',other.execute('Type("CatalogRef.Products")'))
        with self.assertRaisesRegex(BSLRuntimeError,'another runtime snapshot'): vm.execute('Metadata.FindByType(Foreign)')

    def test_all_graph_members_readonly(self):
        vm,_=self.runtime()
        for code in ('Metadata.Name="x";', 'Metadata.Catalogs.Products.Attributes=Undefined;',
                     'Metadata.Catalogs.Products.Attributes.Text.Type=Undefined;',
                     'Metadata.Catalogs.Products.Attributes[0]=Undefined;',
                     'Metadata.Catalogs.Products.StandardAttributes[0]=Undefined;',
                     'Metadata.Catalogs.Products.StandardAttributes[0].Name="x";'):
            with self.subTest(code=code),self.assertRaises(BSLRuntimeError): vm.execute(code)

    def test_collection_bounds_and_argument_validation(self):
        vm,_=self.runtime()
        for arg in ('-1','5','0.5','True','Undefined','"missing"'):
            with self.subTest(arg=arg),self.assertRaises(BSLRuntimeError): vm.execute(f'Metadata.Catalogs.Products.Attributes[{arg}]')
        for code in ('Metadata.FindByFullName(1)','Metadata.FindByType("String")','Metadata.Catalogs.Get("0")'):
            with self.assertRaises(BSLRuntimeError): vm.execute(code)

    def test_hostile_equality_not_used_by_collection_membership(self):
        vm,_=self.runtime(); collection=vm.execute('Metadata.Catalogs.Products.Attributes')
        class Hostile:
            def __eq__(self,other): raise AssertionError('host equality')
        self.assertFalse(collection.contains(Hostile()));self.assertEqual(collection.index_of(Hostile()),Decimal(-1))
        self.assertFalse(is_metadata_collection(Hostile()))

    def test_document_attributes_sections_and_bound_standard_ref(self):
        vm,_=self.runtime(document_files())
        self.assertEqual(vm.execute('Metadata.Documents.Orders.Attributes.Count()'),Decimal(5))
        self.assertEqual(vm.execute('Metadata.Documents.Orders.TabularSections.Lines.Attributes[0].Name'),'Flag')
        self.assertTrue(vm.execute('Metadata.Documents.Orders.StandardAttributes["Ref"].Type.ContainsType(Type("DocumentRef.Orders"))'))
        self.assertEqual(vm.execute('Metadata.Documents.Orders.StandardAttributes["Number"].Type.StringQualifiers.Length'),Decimal(9))

    def test_section_lookup_roundtrip(self):
        vm,_=self.runtime(document_files())
        path='Document.Orders.TabularSection.Lines.Attribute.Flag'
        item=vm.execute(f'Metadata.FindByFullName("{path}")')
        self.assertIs(item,vm.execute('Metadata.Documents.Orders.TabularSections.Lines.Attributes.Flag'))
        self.assertEqual(item.full_name(),'Документ.Orders.ТабличнаяЧасть.Lines.Реквизит.Flag')
        self.assertIs(vm._metadata.find_by_full_name(item.full_name()),item)
        self.assertEqual(vm.execute('Metadata.Documents.Orders.TabularSections.Lines.StandardAttributes["LineNumber"].Type.NumberQualifiers.Digits'),Decimal(9))

    def test_document_find_by_type(self):
        vm,_=self.runtime(document_files())
        for family in ('Ref','Manager','Object','Selection'):
            self.assertIs(vm.execute(f'Metadata.FindByType(Type("Document{family}.Orders"))'),vm.execute('Metadata.Documents.Orders'))

    def test_register_collections_are_distinct(self):
        vm,_=self.runtime(register_files())
        self.assertEqual(vm.execute('Metadata.InformationRegisters.Prices.Dimensions.Count()'),Decimal(2))
        self.assertEqual(vm.execute('Metadata.InformationRegisters.Prices.Resources[0].Name'),'Price')
        self.assertEqual(vm.execute('Metadata.InformationRegisters.Prices.Attributes[0].Name'),'Enabled')
        self.assertEqual(vm.execute('Metadata.InformationRegisters.Prices.StandardAttributes.Count()'),Decimal(0))
        self.assertIsNone(vm.execute('Metadata.InformationRegisters.Prices.Attributes.Find("Item")'))
        self.assertIs(vm.execute('Metadata.FindByFullName("InformationRegister.Prices.Dimension.Item")'),vm.execute('Metadata.InformationRegisters.Prices.Dimensions.Item'))

    def test_periodic_metadata_no_recorder_invention(self):
        vm,_=self.runtime(periodic_files())
        self.assertEqual(vm.execute('Metadata.InformationRegisters.Prices.StandardAttributes.Count()'),Decimal(1))
        self.assertTrue(vm.execute('Metadata.InformationRegisters.Prices.StandardAttributes["Period"].Type.ContainsType(Type("Date"))'))
        self.assertIsNone(vm.execute('Metadata.InformationRegisters.Prices.Dimensions.Find("Period")'))
        with self.assertRaises(BSLRuntimeError): vm.execute('Metadata.InformationRegisters.Prices.StandardAttributes["Recorder"]')

    def test_register_find_by_type(self):
        vm,_=self.runtime(register_files())
        for family in ('Manager','RecordManager','RecordSet','Record','Selection'):
            self.assertIs(vm.execute(f'Metadata.FindByType(Type("InformationRegister{family}.Prices"))'),vm.execute('Metadata.InformationRegisters.Prices'))

    def test_common_module_registry_without_database(self):
        source='Function Fields() Export Return Metadata.Name; EndFunction'
        app=ConfigurationApplication.from_files(module_files([('Tools',source,{})])); self.addCleanup(app.close)
        vm=app.interpreter
        self.assertEqual(vm.execute('Metadata.CommonModules.Get(0).FullName()'),'ОбщийМодуль.Tools')
        self.assertTrue(vm.execute('Metadata.CommonModules.Contains(Metadata.FindByFullName("CommonModule.Tools"))'))
        vm.execute('N=0; For Each M In Metadata.CommonModules Do N=N+1; EndDo;')
        self.assertEqual(vm.execute('N'),Decimal(1))
        self.assertEqual(vm.execute('Tools.Fields()'),app.configuration.name)

    def test_current_generation_mismatch_is_rejected(self):
        vm,_=self.runtime(document_files());vm.execute('Metadata.Catalogs.Count()')
        with self.assertRaises(BackendError): vm._metadata._accept_snapshot(uuid4(),1)

    def test_presentation_metadata_gate_not_bypassed(self):
        files=configuration_files()
        files['Catalogs/Products.xml']=files['Catalogs/Products.xml'].replace(b'<Name>Products</Name>',b'<Name>Products</Name><Comment>not admitted</Comment>')
        self.assertTrue(import_configuration(files).activation_issues)

    def test_metadata_graph_not_generic_serializable(self):
        vm,_=self.runtime()
        for source in ('Metadata','Metadata.Catalogs','Metadata.Catalogs.Products.Attributes.Text','Metadata.Catalogs.Products.StandardAttributes[0]'):
            with self.subTest(source=source),self.assertRaises(BSLRuntimeError): vm.execute(f'ValueToStringInternal({source})')

    def test_lazy_without_database(self):
        vm=Interpreter(); self.addCleanup(vm.close)
        self.assertIsNotNone(vm.execute('Metadata.Catalogs'))
        for source in ('Metadata.Name','Metadata.Catalogs.Get(0)','Metadata.FindByFullName("Catalog.Products")'):
            with self.assertRaisesRegex(BSLRuntimeError,'db required'): vm.execute(source)

    def test_empty_metadata_families_are_iterable(self):
        vm,_=self.runtime()
        self.assertEqual(vm.execute('Metadata.Documents.Count()'),Decimal(0))
        self.assertEqual(vm.execute('Metadata.InformationRegisters.Count()'),Decimal(0))
        vm.execute('For Each D In Metadata.Documents Do Raise "unexpected"; EndDo;')
        self.assertIsNone(vm.execute('Metadata.FindByFullName("Document.Missing")'))

    def test_metadata_property_passes_through_bsl_parameter_readonly(self):
        vm,_=self.runtime()
        vm.execute('Function Read(M) Return M.Name; EndFunction Procedure Change(M) M=Undefined; EndProcedure')
        self.assertEqual(vm.execute('Read(Metadata.Catalogs.Products.Attributes.Text)'),'Text')
        with self.assertRaises(BSLRuntimeError): vm.execute('Change(Metadata.Catalogs.Products.Attributes.Text);')
        self.assertEqual(vm.execute('Read(Metadata.Catalogs.Products.Attributes[0])'),'Text')

    def test_metadata_index_parameter_remains_readonly(self):
        vm,_=self.runtime()
        vm.execute('Function Read(M) Return M.Name; EndFunction Procedure Change(M) M=Undefined; EndProcedure')
        self.assertEqual(vm.execute('Read(Metadata.Catalogs.Products.StandardAttributes[0])'),'Ссылка')
        with self.assertRaises(BSLRuntimeError): vm.execute('Change(Metadata.Catalogs.Products.StandardAttributes[0]);')

    def test_imported_helper_owns_reference_metadata_context(self):
        vm,_=self.runtime()
        folder=Path(tempfile.mkdtemp()); self.addCleanup(__import__('shutil').rmtree,folder)
        (folder/'helper.bsl').write_text('Function Check() Export D=Metadata.Catalogs.Products.Attributes.Category.Type; Return D.ContainsType(Type("CatalogRef.Categories")); EndFunction')
        vm.execute('// #Import helper.bsl\n',source=str(folder/'main.bsl'))
        self.assertTrue(vm.execute('Helper.Check()'))

    def test_server_activation_owns_reference_metadata_context(self):
        vm,_=self.runtime()
        vm.execute('&AtServerNoContext\nFunction Check() D=Metadata.Catalogs.Products.Attributes.Category.Type; Return D.ContainsType(Type("CatalogRef.Categories")); EndFunction')
        self.assertTrue(vm.execute('Check()'))

    def test_source_bytes_not_changed_by_graph_read(self):
        vm,context=self.runtime(document_files())
        before=context.backend.export_configuration()
        vm.execute('For Each M In Metadata.Documents Do For Each A In M.Attributes Do T=A.Type; EndDo; EndDo;')
        self.assertEqual(context.backend.export_configuration(),before)

    def test_root_configuration_source_digest_checked(self):
        vm,context=self.runtime()
        with closing(sqlite3.connect(context.path)) as c, c:
            c.execute("UPDATE configuration_file SET content=? WHERE path='Configuration.xml'",(b'<bad/>',))
        with self.assertRaises(BackendError): vm._metadata._ensure_source_info()

    def test_failures_do_not_install_partial_snapshot(self):
        vm,context=self.runtime(); original=vm._metadata._accept_snapshot
        def reject(*args): raise ValueError('reject graph')
        vm._metadata._accept_snapshot=reject
        with self.assertRaises(ValueError): vm._metadata._catalogs._snapshot()
        self.assertIsNone(vm._metadata._catalogs._items)
        vm._metadata._accept_snapshot=original
        self.assertEqual(vm.execute('Metadata.Catalogs.Count()'),Decimal(2))
