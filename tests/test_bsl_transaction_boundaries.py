"""Additional transaction publication, buffer and read boundaries."""
from unittest.mock import patch
from yadinassi.catalog_backend import BackendError
from yadinassi.database_transactions import execution, begin, commit, rollback, current
from yadinassi.sqlite_catalog import SQLiteCatalogBackend
import test_bsl_transactions as fixtures
import unittest


class TransactionBoundariesTests(unittest.TestCase):
    setUp = fixtures.BSLTransactionsTests.setUp
    catalog = fixtures.BSLTransactionsTests.catalog

    def test_owner_publication_memoryerror_releases_connection(self):
        original = SQLiteCatalogBackend.__setattr__
        def faulty(backend, name, value):
            if name == '_bsl_transaction' and value is not None: raise MemoryError()
            return original(backend,name,value)
        with execution(self.backend):
            with patch.object(SQLiteCatalogBackend,'__setattr__',faulty):
                with self.assertRaises(MemoryError): begin(self.backend)
            self.assertIsNone(self.backend._active)
            self.assertIsNone(getattr(self.backend,'_bsl_transaction',None))

    def test_query_wrapper_memoryerror_releases_lease(self):
        with execution(self.backend):
            begin(self.backend)
            with patch('yadinassi.sqlite_catalog.DocumentView', side_effect=MemoryError):
                with self.assertRaises(MemoryError): self.backend.begin_query_read()
            self.assertEqual(current(self.backend).leases,0)
            rollback(self.backend)

    def test_document_query_sees_staged_row(self):
        self.vm.execute('''D=Documents.Orders.CreateDocument();D.Number="A";D.Date=Date(2026,1,1);
BeginTransaction();D.Write();Q=New Query("SELECT Number FROM Document.Orders");
T=Q.Execute().Unload();Message(T.Count());CommitTransaction();''')
        self.assertEqual(self.output,['1'])

    def test_register_query_sees_staged_row(self):
        self.vm.execute('''R=InformationRegisters.Prices.CreateRecordManager();R.Period=Date(2026,1,1);R.Item="A";R.Price=2;
BeginTransaction();R.Write();Q=New Query("SELECT Price FROM InformationRegister.Prices");
T=Q.Execute().Unload();Message(T.Count());CommitTransaction();''')
        self.assertEqual(self.output,['1'])

    def test_record_set_commits_in_mixed_batch(self):
        self.vm.execute('''S=InformationRegisters.Prices.CreateRecordSet();R=S.Add();R.Period=Date(2026,1,1);R.Item="A";R.Price=2;
C=Catalogs.Products.CreateItem();C.Code="A";BeginTransaction();S.Write(False);C.Write();CommitTransaction();
Q=New Query("SELECT Price FROM InformationRegister.Prices");Message(Q.Execute().Unload().Count());''')
        self.assertEqual(self.output,['1'])

    def test_two_documents_one_batch(self):
        self.vm.execute('''D=Documents.Orders.CreateDocument();D.Number="A";D.Date=Date(2026,1,1);
E=Documents.Orders.CreateDocument();E.Number="B";E.Date=Date(2026,1,1);
BeginTransaction();D.Write();E.Write();CommitTransaction();Message(D.IsNew());Message(E.IsNew());''')
        self.assertEqual(self.output,['Нет','Нет'])

    def test_section_dirty_only_cleared_after_commit(self):
        obj=self.catalog(); row=obj.get_member('Lines').add();row.set_member('Text','saved')
        section=obj.get_member('Lines')
        with execution(self.backend):
            begin(self.backend);obj.write();self.assertTrue(section._dirty)
            commit(self.backend)
        self.assertFalse(section._dirty)

    def test_rollback_preserves_section_dirty(self):
        obj=self.catalog(); row=obj.get_member('Lines').add();row.set_member('Text','saved')
        section=obj.get_member('Lines')
        with execution(self.backend):
            begin(self.backend);obj.write();rollback(self.backend)
        self.assertTrue(section._dirty)
        self.assertEqual(row.get_member('Text'),'saved')

    def test_update_retains_old_revision_until_commit(self):
        obj=self.catalog();obj.write();revision=obj._revision
        obj.set_member('Description','new')
        with execution(self.backend):
            begin(self.backend);obj.write();self.assertEqual(obj._revision,revision)
            commit(self.backend)
        self.assertNotEqual(obj._revision,revision)

    def test_failed_stage_does_not_accept_prior_participant(self):
        first=self.catalog()
        second=self.vm.execute('D=Catalogs.Products.CreateItem();D.Code="A";D')
        with execution(self.backend):
            begin(self.backend);first.write()
            with self.assertRaises(BackendError): second.write()
            self.assertTrue(first.is_new());self.assertTrue(second.is_new())
            commit(self.backend)
        self.assertFalse(first.is_new());self.assertTrue(second.is_new())

    def test_import_uses_same_synchronous_transaction(self):
        module=self.path.parent/'Writer.bsl'
        module.write_text('Procedure Save(X) Export X.Write(); EndProcedure',encoding='utf-8')
        self.vm.execute('// #Import Writer.bsl\nC=Catalogs.Products.CreateItem();C.Code="A";BeginTransaction();Writer.Save(C);CommitTransaction();',source=str(self.path.parent/'main.bsl'))
        self.assertFalse(self.vm.execute('C.IsNew()'))
