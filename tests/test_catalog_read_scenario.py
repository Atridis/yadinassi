"""Logical catalog read/write scenario on an owned SQLite application database."""
from pathlib import Path
import tempfile,unittest
from yadinassi import Interpreter, BSLRuntimeError
from yadinassi.configuration_xml import import_configuration
from yadinassi.database_context import SQLiteDBContext
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
    def test_foreign_database_reference_rejected(self):
        other=SQLiteDBContext.create(Path(self.temp.name)/'other.sqlite',import_configuration(configuration_files()))
        self.addCleanup(other.close)
        vm=Interpreter(database_context=other);vm.execute('C=Catalogs.Categories.CreateItem();C.Code="1";C.Write();')
        self.vm.execute('P=Catalogs.Products.CreateItem();')
        with self.assertRaises(TypeError):self.vm.execute('P').set_member('Category',vm.execute('C.Ref'))
