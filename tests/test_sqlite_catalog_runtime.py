from pathlib import Path
import sys,tempfile,unittest
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from yadinassi import Interpreter
from yadinassi.configuration_xml import import_configuration
from yadinassi.database_context import SQLiteDBContext
from sqlite_catalog_fixture import configuration_files

class SQLiteCatalogRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.path=Path(self.temp.name)/'application.sqlite'
        self.files=configuration_files();self.context=SQLiteDBContext.create(self.path,import_configuration(self.files))
    def tearDown(self):self.context.close();self.temp.cleanup()
    def execute(self,code):
        lines=[];vm=Interpreter(output=lines.append,database_context=self.context);vm.execute(code);return lines
    def test_create_edit_cancel_and_reopen_typed_cards(self):
        out=self.execute('''C=Catalogs.Categories.CreateItem(); C.Code="10"; C.Description="Category"; C.Write();
P=Catalogs.Products.CreateItem(); Message(P.IsNew()); Message(P.Ref.IsEmpty());
P.Code="20"; P.Description="Product"; P.Text="hello"; P.Amount=12.50; P.Active=True; P.Stamp=Date(2024,2,29,12,34,56); P.Category=C.Ref;
P.Write(); Message(P.IsNew()); Message(P.Ref.IsEmpty());
R=Catalogs.Products.FindByCode("20"); O=R.GetObject(); Message(O.Category.Description); Message(O.Text);
O.Text="cancelled"; O=Undefined; Message(R.Text);
O=R.GetObject(); O.Text="edited"; O.Write(); Message(R.Text); Message(TypeOf(O)=Type("CatalogObject.Products"));''')
        self.assertEqual(out,['Да','Да','Нет','Нет','Category','hello','hello','edited','Да'])
        self.context.close();self.context=SQLiteDBContext(self.path)
        self.assertEqual(self.execute('P=Catalogs.Products.FindByCode("20"); Message(P.Text); Message(P.Category.Description); Message(XMLString(P.Stamp));'),['edited','Category','2024-02-29T12:34:56'])
        self.assertEqual(self.context.backend.export_configuration(),self.files)
    def test_failed_write_preserves_buffer_and_isnew(self):
        self.assertEqual(self.execute('''P=Catalogs.Products.CreateItem();P.Code="10";P.Write();
O=Catalogs.Products.CreateItem();O.Code="10";O.Text="dirty";
Try O.Write(); Except Message("rejected"); EndTry;
Message(O.IsNew());Message(O.Text);Message(O.Ref.IsEmpty());
S=Catalogs.Products.Select();N=0;While S.Next() Do N=N+1;EndDo;Message(N);'''),['rejected','Да','dirty','Да','1'])
    def test_stale_object_and_foreign_reference_refused(self):
        self.assertEqual(self.execute('''P=Catalogs.Products.CreateItem();P.Code="10";P.Write();A=P.Ref.GetObject();B=P.Ref.GetObject();A.Text="first";A.Write();B.Text="stale";
Try B.Write();Except Message("conflict");EndTry;Message(B.Text);Message(P.Ref.Text);'''),['conflict','stale','first'])
    def test_documents_registers_and_object_codec_not_falsely_admitted(self):
        self.assertEqual(self.execute('Message(Metadata.Documents.Count());Message(Metadata.InformationRegisters.Count());'),['0','0'])
        for code in ('Documents.Orders.CreateDocument();','InformationRegisters.Rows.CreateRecordSet();',
                     'P=Catalogs.Products.CreateItem();Message(ValueToStringInternal(P));'):
            with self.subTest(code=code),self.assertRaises(Exception):self.execute(code)

    def test_uncertain_commit_resolves_exact_intent_without_second_write(self):
        from unittest.mock import patch
        from yadinassi.sqlite_catalog import _View
        from yadinassi.catalog_backend import BackendError
        vm=Interpreter(database_context=self.context)
        vm.execute('P=Catalogs.Products.CreateItem();P.Code="30";P.Text="original";')
        obj=vm.execute('P');commit=_View.commit
        def lose_response(tx):
            commit(tx)
            raise BackendError('uncertain_commit')
        with patch.object(_View,'commit',lose_response),self.assertRaises(BackendError):obj.write()
        self.assertTrue(obj.is_new())
        self.assertTrue(obj.get_member('Ref').is_empty())
        with self.assertRaises(BackendError):obj.set_member('Text','changed')
        with patch.object(_View,'commit',side_effect=AssertionError('must not recommit')):obj.write()
        self.assertFalse(obj.is_new())
        self.assertEqual(vm.execute('Catalogs.Products.FindByCode("30").Text'),'original')
        obj.set_member('Text','next');obj.write()
        self.assertEqual(vm.execute('Catalogs.Products.FindByCode("30").Text'),'next')

    def test_inactive_code_archive_cannot_execute_even_scalar_bsl(self):
        from yadinassi.catalog_backend import BackendError
        files=configuration_files();files['Catalogs/Products/Ext/ObjectModule.bsl']=b'Procedure BeforeWrite(Cancel)\nCancel=True;\nEndProcedure'
        archive=SQLiteDBContext.create(Path(self.temp.name)/'inactive.sqlite',import_configuration(files),activate=False)
        try:
            self.assertEqual(archive.backend.export_configuration(),files)
            with self.assertRaises(BackendError):Interpreter(database_context=archive)
            with self.assertRaises(BackendError):archive.backend.begin_read()
        finally:archive.close()
