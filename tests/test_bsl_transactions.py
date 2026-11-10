"""Owned explicit transaction contract, not native parity evidence."""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from yadinassi import Interpreter, BSLRuntimeError
from yadinassi.catalog_backend import BackendError
from yadinassi.database_context import SQLiteDBContext
from yadinassi.database_transactions import execution, begin, commit, rollback, current
from yadinassi.sqlite_migration_plan import prepare, apply
from test_sqlite_catalog_hierarchy import configuration
from test_catalog_commit_cleanup_recovery import FaultConnection


class BSLTransactionsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name)/'owned.sqlite'
        context = SQLiteDBContext.create(self.path, configuration(mixed=True)); context.close()
        apply(self.path, prepare(self.path, maintenance=True), maintenance=True)
        self.context = SQLiteDBContext(self.path); self.addCleanup(self.context.close)
        self.backend = self.context.backend
        self.output = []
        self.vm = Interpreter(database_context=self.context, output=self.output.append)

    def catalog(self):
        return self.vm.execute('C=Catalogs.Products.CreateItem();C.Code="A";C.Description="edited";C')

    def test_mixed_atomic_commit(self):
        self.vm.execute('''C=Catalogs.Products.CreateItem();C.Code="A";
D=Documents.Orders.CreateDocument();D.Number="A";D.Date=Date(2026,1,1);
R=InformationRegisters.Prices.CreateRecordManager();R.Period=Date(2026,1,1);R.Item="A";R.Price=2;
BeginTransaction();C.Write();D.Write();R.Write();Message(C.IsNew());Message(D.IsNew());
CommitTransaction();Message(C.IsNew());Message(D.IsNew());Message(R.Selected());''')
        self.assertEqual(self.output, ['Да','Да','Нет','Нет','Да'])
        self.assertEqual(self.vm.execute('Catalogs.Products.FindByCode("A").Code'), 'A')

    def test_rollback_keeps_edits_not_revision(self):
        self.vm.execute('C=Catalogs.Products.CreateItem();C.Code="A";BeginTransaction();C.Write();RollbackTransaction();Message(C.IsNew());Message(C.Code);')
        self.assertEqual(self.output, ['Да','A'])
        self.assertTrue(self.vm.execute('Catalogs.Products.FindByCode("A").IsEmpty()'))
        self.vm.execute('C.Write();'); self.assertFalse(self.vm.execute('C.IsNew()'))

    def test_unclosed_transaction_rolls_back(self):
        with self.assertRaises((BackendError, BSLRuntimeError)):
            self.vm.execute('C=Catalogs.Products.CreateItem();C.Code="A";BeginTransaction();C.Write();')
        self.assertTrue(self.vm.execute('C.IsNew()'))
        self.assertIsNone(getattr(self.backend, '_bsl_transaction', None))

    def test_empty_commit(self): self.vm.execute('BeginTransaction();CommitTransaction();')

    def test_nested_refused_and_outer_rollback(self):
        with self.assertRaises((BackendError, BSLRuntimeError)):
            self.vm.execute('BeginTransaction();BeginTransaction();')
        self.assertIsNone(getattr(self.backend, '_bsl_transaction', None))

    def test_commit_without_begin(self):
        with self.assertRaises(BSLRuntimeError): self.vm.execute('CommitTransaction();')

    def test_rollback_without_begin(self):
        with self.assertRaises(BSLRuntimeError): self.vm.execute('RollbackTransaction();')

    def test_staged_mutation_refused(self):
        obj = self.catalog()
        with execution(self.backend):
            begin(self.backend); obj.write()
            with self.assertRaises(BackendError): obj.set_member('Description', 'changed')
            rollback(self.backend)
        self.assertEqual(obj.get_member('Description'), 'edited')

    def test_repeat_write_refused(self):
        obj = self.catalog()
        with execution(self.backend):
            begin(self.backend); obj.write()
            with self.assertRaises(BackendError): obj.write()
            rollback(self.backend)

    def test_section_mutation_refused(self):
        obj = self.catalog()
        with execution(self.backend):
            begin(self.backend); obj.write()
            with self.assertRaises(BackendError): obj.get_member('Lines').add()
            rollback(self.backend)

    def test_read_your_writes_query(self):
        self.vm.execute('''C=Catalogs.Products.CreateItem();C.Code="A";BeginTransaction();C.Write();
Q=New Query("SELECT Code FROM Catalog.Products");T=Q.Execute().Unload();Message(T.Count());
CommitTransaction();''')
        self.assertEqual(self.output, ['1'])

    def test_query_lease_close_does_not_close_owner(self):
        obj = self.catalog()
        with execution(self.backend):
            begin(self.backend); obj.write()
            lease = self.backend.begin_query_read(); lease.close()
            self.assertEqual(current(self.backend).unit.state, 'open')
            commit(self.backend)
        self.assertFalse(obj.is_new())

    def test_open_lease_blocks_commit_and_stage(self):
        obj = self.catalog()
        with execution(self.backend):
            begin(self.backend); lease = self.backend.begin_read()
            with self.assertRaises(BackendError): obj.write()
            with self.assertRaises(BackendError): commit(self.backend)
            lease.close(); rollback(self.backend)

    def test_read_object_inside_transaction_refused(self):
        obj=self.catalog();obj.write()
        with execution(self.backend):
            begin(self.backend)
            with self.assertRaises(BackendError): obj._manager._get_object(obj.get_member('Ref'))
            rollback(self.backend)

    def test_no_partial_acceptance_if_preparation_fails(self):
        first = self.catalog()
        second = self.vm.execute('D=Documents.Orders.CreateDocument();D.Number="A";D.Date=Date(2026,1,1);D')
        with execution(self.backend):
            begin(self.backend); first.write(); second.write()
            with patch.object(type(second), '_accept', side_effect=MemoryError):
                with self.assertRaises(MemoryError): commit(self.backend)
            self.assertTrue(first.is_new()); self.assertTrue(second.is_new())
            rollback(self.backend)
        self.assertTrue(self.vm.execute('Catalogs.Products.FindByCode("A").IsEmpty()'))

    def test_uncertain_after_commit_resolves_whole_batch(self):
        obj = self.catalog()
        with execution(self.backend):
            begin(self.backend);obj.write(); tx=current(self.backend)
            tx.unit._view._connection=FaultConnection(tx.unit._view._connection, commit_fault='after')
            with self.assertRaisesRegex(BackendError, 'uncertain_commit'): commit(self.backend)
            self.assertTrue(obj.is_new())
            commit(self.backend)
        self.assertFalse(obj.is_new())

    def test_uncertain_before_commit_does_not_replay(self):
        obj = self.catalog()
        with execution(self.backend):
            begin(self.backend);obj.write();tx=current(self.backend)
            tx.unit._view._connection=FaultConnection(tx.unit._view._connection, commit_fault='before')
            with self.assertRaises(BackendError): commit(self.backend)
            with self.assertRaisesRegex(BackendError, 'conflict'): commit(self.backend)
        self.assertTrue(obj.is_new())
        self.assertTrue(self.vm.execute('Catalogs.Products.FindByCode("A").IsEmpty()'))

    def test_rollback_uncertain_committed_never_claims_rollback(self):
        obj=self.catalog()
        with execution(self.backend):
            begin(self.backend);obj.write();tx=current(self.backend)
            tx.unit._view._connection=FaultConnection(tx.unit._view._connection, commit_fault='after')
            with self.assertRaises(BackendError): commit(self.backend)
            with self.assertRaisesRegex(BackendError,'conflict'): rollback(self.backend)
        self.assertFalse(obj.is_new())

    def test_standalone_write_unchanged(self):
        obj=self.catalog();obj.write();self.assertFalse(obj.is_new())

    def test_unmigrated_profile_refuses_without_upgrade(self):
        path=Path(self.temp.name)/'old.sqlite'
        with SQLiteDBContext.create(path, configuration(mixed=True)) as context:
            vm=Interpreter(database_context=context)
            with self.assertRaises(BSLRuntimeError): vm.execute('BeginTransaction();')
            self.assertEqual(context.backend.format_version,10)

    def test_no_database_refuses(self):
        with self.assertRaises(BSLRuntimeError): Interpreter().execute('BeginTransaction();')

    def test_async_begin_refused(self):
        with self.assertRaises((BackendError, BSLRuntimeError, ValueError)):
            self.vm.execute('Async Procedure P() BeginTransaction(); EndProcedure P();')
        self.assertIsNone(getattr(self.backend,'_bsl_transaction',None))
