"""Logical catalog read/write scenario on an owned SQLite application database."""
from pathlib import Path
import tempfile,unittest
from yadinassi import Interpreter, BSLRuntimeError
from yadinassi.configuration.configuration_xml import import_configuration
from yadinassi.db.database_context import SQLiteDBContext
from sqlite_catalog_fixture import configuration_files

class CatalogScenarioTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.context=SQLiteDBContext.create(Path(self.temp.name)/'app.sqlite',import_configuration(configuration_files()))
        self.addCleanup(self.context.close)
        self.output=[];self.vm=Interpreter(self.output.append,database_context=self.context)
    def test_managers_refs_types_and_metadata(self):
        self.vm.execute('''M=Catalogs.Products;R=M.GetRef(New UUID("33333333-3333-4333-8333-333333333333"));
Message(TypeOf(R)=Type("CatalogRef.Products"));Message(TypeOf(TypeOf(R))=Type("Type"));
Message(R.Metadata()=Metadata.Catalogs.Products);Message(ValueIsFilled(R));
Message(ValueIsFilled(M.EmptyRef()));Message(R=Catalogs.Categories.GetRef(R.UUID()));''')
        self.assertEqual(self.output,['Да','Да','Да','Да','Нет','Нет'])
    def test_select_lookup_cursor_restart_and_retained_last_row(self):
        self.vm.execute('''M=Catalogs.Products;S=M.Select();Message(S.Code=Undefined);Message(S.Next());
P=M.CreateItem();P.Code="20";P.Description="Second";P.Text="payload";P.Amount=1.25;P.Write();
P=M.CreateItem();P.Code="10";P.Description="First";P.Write();
S=M.Select();While S.Next() Do Message(S.Code);Message(S.Ref=M.FindByCode(S.Code));EndDo;
Message(S.Code);Message(S.Next());Message(S.Code);
Message(M.FindByDescription("Second",True)=M.FindByCode("20"));Message(M.FindByCode("absent").IsEmpty());''')
        self.assertEqual(self.output,['Да','Нет','10','Да','20','Да','20','Да','10','Да','Да'])
    def test_readonly_reference_and_unsupported_partial_lookup(self):
        for source in ('Catalogs.Products.FindByDescription("a");','Catalogs.Products.EmptyRef().Code="x";',
                       'R=New (Type("CatalogRef.Products"));'):
            with self.subTest(source=source),self.assertRaises(BSLRuntimeError):self.vm.execute(source)
    def test_no_database_lazy_and_unrelated_types_preserved(self):
        vm=Interpreter()
        vm.execute('If False Then S=Catalogs.Products.Select();EndIf;Type("String");')
        with self.assertRaisesRegex(BSLRuntimeError,'db required'):vm.execute('Catalogs.Products;')
    def test_db_root_names_resolve_lazily_without_reserving_bindings(self):
        vm=Interpreter()
        self.addCleanup(vm.close)
        aliases=('Catalogs','Справочники','Documents','Документы',
                 'InformationRegisters','РегистрыСведений')
        for name in aliases:
            with self.subTest(name=name):
                vm.execute(f'If False Then Result={name}.Unknown; EndIf;')
                with self.assertRaisesRegex(BSLRuntimeError,'db required'):
                    vm.execute(f'{name}.Unknown;')
                self.assertEqual(vm.execute(
                    f'Function Read(Val {name}) Return {name}; EndFunction Read(17);'),17)
        for fragment in ('Eval("Documents.Unknown")','Execute("Documents.Unknown;")'):
            with self.subTest(fragment=fragment),self.assertRaisesRegex(BSLRuntimeError,'db required'):
                vm.execute(fragment)
        vm.execute('Documents=19;')
        self.assertEqual(vm.execute('Documents;'),19)
        self.assertIs(vm.execute('Metadata;'), vm.execute('Метаданные;'))
        with self.assertRaisesRegex(BSLRuntimeError, 'db required'):
            vm.execute('Metadata.Documents.Count();')
        self.assertEqual(vm.execute(
            'Function Read(Val Metadata) Return Metadata; EndFunction Read(17);'),17)
        vm.execute('Metadata=23;')
        self.assertEqual(vm.execute('Metadata;'),23)
        self.assertEqual(vm.execute('Eval("Metadata");'),23)
        explicit = Interpreter(allow_extensions=True)
        self.addCleanup(explicit.close)
        explicit.register_function('Metadata', lambda: 'host')
        self.assertEqual(explicit.execute('Metadata()'), 'host')
        for name in ('Enums','UnknownName'):
            with self.subTest(name=name),self.assertRaises(BSLRuntimeError) as raised:
                vm.execute(name+';')
            self.assertNotIn('db required',str(raised.exception))

    def test_standalone_database_roots_use_normal_python_lookup(self):
        vm = Interpreter()
        self.addCleanup(vm.close)
        vm.execute('If False Then R=Catalogs.Products; EndIf;')
        plan = vm.prepare('R=Справочники.Products;')
        source = plan._plan.generated_source
        self.assertIn("справочники, 'Products'", source)
        self.assertNotIn('external_get', source)
        with self.assertRaisesRegex(BSLRuntimeError, 'db required'):
            vm.execute_prepared(plan)
        vm.execute('Справочники=New Structure("Products", 23);')
        vm.execute_prepared(plan)
        self.assertEqual(vm.variables['r'], 23)
        with self.assertRaisesRegex(BSLRuntimeError, 'UnknownName'):
            vm.execute('UnknownName.Products;')

    def test_standalone_metadata_shadow_is_live_on_prepared_reads(self):
        vm = Interpreter()
        self.addCleanup(vm.close)
        read = vm.prepare('R=Metadata;')
        vm.execute_prepared(read)
        original = vm.variables['r']
        self.assertIs(original, vm.execute('Метаданные;'))
        vm.execute_prepared(vm.prepare('Metadata=23;'))
        vm.execute_prepared(read)
        self.assertEqual(vm.variables['r'], 23)
        self.assertEqual(vm.execute('Вычислить("Metadata");'), 23)
        self.assertIs(original, vm.execute('Метаданные;'))

    def test_fragments_resolve_only_unbound_database_namespace_reads(self):
        for (expr, expected) in (
            ('Eval("Metadata.Catalogs.Count()");', 2),
            ('R=0; Execute("R=Метаданные.Справочники.Количество();"); R;', 2),
            ('Eval("TypeOf(Catalogs.Products.EmptyRef())=Type(""CatalogRef.Products"")");', True),
            ('Function Read(Val Metadata) Return Eval("Metadata"); EndFunction Read(17);', 17),
            ('Function Update(Val Metadata) Execute("Metadata=23;"); Return Metadata; EndFunction Update(17);', 23),
        ):
            with self.subTest(expr=expr):
                self.assertEqual(self.vm.execute(expr), expected)

        standalone=Interpreter()
        self.addCleanup(standalone.close)
        standalone.execute('Execute("If False Then X=Documents.Unknown; EndIf;");')
        with self.assertRaisesRegex(BSLRuntimeError,'db required'):
            standalone.execute('Eval("Documents.Unknown");')

    def test_foreign_database_reference_rejected(self):
        other=SQLiteDBContext.create(Path(self.temp.name)/'other.sqlite',import_configuration(configuration_files()))
        self.addCleanup(other.close)
        vm=Interpreter(database_context=other);vm.execute('C=Catalogs.Categories.CreateItem();C.Code="1";C.Write();')
        self.vm.execute('P=Catalogs.Products.CreateItem();')
        with self.assertRaises(TypeError):self.vm.execute('P').set_member('Category',vm.execute('C.Ref'))
