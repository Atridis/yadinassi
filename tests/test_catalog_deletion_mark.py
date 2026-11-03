"""Flat catalog deletion marks: logical SQLite behavior, not native parity."""
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from sqlite_catalog_fixture import configuration_files
from yadinassi import Interpreter
from yadinassi.catalog_backend import BackendError
from yadinassi.configuration_xml import import_configuration
from yadinassi.database_context import SQLiteDBContext
from yadinassi.sqlite_catalog import _View


class CatalogDeletionMarkTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / 'owned.sqlite'
        self.context = SQLiteDBContext.create(self.path, import_configuration(configuration_files()))
        self.out = []
        self.vm = Interpreter(database_context=self.context, output=self.out.append)
        self.vm.execute('P=Catalogs.Products.CreateItem();P.Code="10";P.Description="original";P.Write();')

    def tearDown(self):
        self.context.close()
        self.temp.cleanup()

    def test_assignment_is_detached_until_write_and_reopens(self):
        self.vm.execute('''O=P.Ref.GetObject();O.DeletionMark=True;
Message(O.DeletionMark);Message(P.Ref.DeletionMark);O.Write();Message(P.Ref.DeletionMark);''')
        self.assertEqual(self.out, ['Да', 'Нет', 'Да'])
        self.context.close()
        self.context = SQLiteDBContext(self.path)
        vm = Interpreter(database_context=self.context)
        self.assertTrue(vm.execute('Catalogs.Products.FindByCode("10").DeletionMark'))

    def test_method_writes_dirty_values_and_toggles_mark(self):
        self.vm.execute('''O=P.Ref.GetObject();O.Description="changed";O.SetDeletionMark(True);
Message(P.Ref.Description);Message(P.Ref.DeletionMark);O.УстановитьПометкуУдаления(Ложь);
Message(P.Ref.DeletionMark);''')
        self.assertEqual(self.out, ['changed', 'Да', 'Нет'])

    def test_new_object_and_repeated_mark(self):
        self.vm.execute('''N=Catalogs.Products.CreateItem();N.Code="20";N.УстановитьПометкуУдаления(Истина);
Message(N.IsNew());Message(N.Ref.DeletionMark);N.SetDeletionMark(True);Message(N.Ref.DeletionMark);''')
        self.assertEqual(self.out, ['Нет', 'Да', 'Да'])

    def test_query_and_selection_observe_mark_without_filtering(self):
        self.vm.execute('''P.SetDeletionMark(True);S=Catalogs.Products.Select();S.Next();Message(S.DeletionMark);
Q=New Query("SELECT Code FROM Catalog.Products WHERE DeletionMark=TRUE");R=Q.Execute().Select();
Message(R.Next());Message(R.Code);Message(R.Next());''')
        self.assertEqual(self.out, ['Да', 'Да', '10', 'Нет'])

    def test_non_boolean_rejected_without_mutation(self):
        obj = self.vm.execute('P.Ref.GetObject()')
        for value in (None, 1, 'true'):
            with self.subTest(value=value):
                with self.assertRaises(TypeError): obj.set_member('DeletionMark', value)
                with self.assertRaises(TypeError): obj.set_deletion_mark(value)
                self.assertFalse(obj.get_member('DeletionMark'))
        self.assertFalse(self.vm.execute('P.Ref.DeletionMark'))

    def test_stale_mark_conflict_preserves_detached_buffer(self):
        stale = self.vm.execute('P.Ref.GetObject()')
        self.vm.execute('O=P.Ref.GetObject();O.Description="newer";O.Write();')
        with self.assertRaises(BackendError) as raised:
            stale.set_deletion_mark(True)
        self.assertEqual(raised.exception.code, 'conflict')
        self.assertTrue(stale.get_member('DeletionMark'))
        self.assertFalse(self.vm.execute('P.Ref.DeletionMark'))
        self.assertEqual(self.vm.execute('P.Ref.Description'), 'newer')

    def test_new_import_preserves_colliding_attribute_names(self):
        for name in ('SetDeletionMark', 'УстановитьПометкуУдаления'):
            files = configuration_files()
            files['Catalogs/Products.xml'] = files['Catalogs/Products.xml'].replace(
                b'<Name>Text</Name>', ('<Name>'+name+'</Name>').encode())
            with self.subTest(name=name):
                config = import_configuration(files)
                self.assertTrue(any(f.name == name for c in config.catalogs for f in c.fields))

    def test_legacy_colliding_attributes_remain_readable(self):
        files = configuration_files()
        xml = files['Catalogs/Products.xml'].replace(b'<Name>Text</Name>', b'<Name>SetDeletionMark</Name>')
        xml = xml.replace(b'<Name>Amount</Name>', '<Name>УстановитьПометкуУдаления</Name>'.encode())
        files['Catalogs/Products.xml'] = xml
        imported = import_configuration(files)
        legacy_path = Path(self.temp.name) / 'legacy.sqlite'
        legacy = SQLiteDBContext.create(legacy_path, imported)
        try:
            vm = Interpreter(database_context=legacy)
            vm.execute('P=Catalogs.Products.CreateItem();P.Code="1";P.SetDeletionMark="preserved";P.УстановитьПометкуУдаления=42;P.Write();')
            legacy.close(); legacy = SQLiteDBContext(legacy_path)
            vm = Interpreter(database_context=legacy)
            self.assertEqual(vm.execute('Catalogs.Products.FindByCode("1").GetObject().setdeletionmark'), 'preserved')
            self.assertEqual(str(vm.execute('Catalogs.Products.FindByCode("1").GetObject().УСТАНОВИТЬПОМЕТКУУДАЛЕНИЯ')), '42.00')
            with self.assertRaises(Exception):
                vm.execute('Catalogs.Products.FindByCode("1").GetObject().SetDeletionMark(True);')
            self.assertFalse(vm.execute('Catalogs.Products.FindByCode("1").DeletionMark'))
        finally:
            legacy.close()

    def test_lost_commit_response_resolves_exact_mark_without_duplicate_write(self):
        obj = self.vm.execute('P.Ref.GetObject()')
        commit = _View.commit
        def lost_response(tx):
            commit(tx)
            raise BackendError('uncertain_commit')
        with patch.object(_View, 'commit', lost_response), self.assertRaises(BackendError):
            obj.set_deletion_mark(True)
        with self.assertRaises(BackendError): obj.set_member('DeletionMark', False)
        with self.assertRaises(BackendError): obj.set_deletion_mark(False)
        with patch.object(_View, 'commit', side_effect=AssertionError('must not commit twice')):
            obj.write()
        self.assertTrue(self.vm.execute('P.Ref.DeletionMark'))
        obj.set_deletion_mark(False)
        self.assertFalse(self.vm.execute('P.Ref.DeletionMark'))


if __name__ == '__main__':
    unittest.main()
