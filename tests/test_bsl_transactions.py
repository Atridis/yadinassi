"""Owned explicit transaction contract, not native parity evidence."""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from yadinassi import Interpreter, BSLRuntimeError
from yadinassi.db.catalog.catalog_backend import BackendError
from yadinassi.db.database_context import SQLiteDBContext
from yadinassi.db.database_transactions import active, execution, begin, commit, rollback, current
from yadinassi.db.sqlite.sqlite_migration_plan import prepare, apply
from test_sqlite_catalog_hierarchy import configuration
from test_catalog_commit_cleanup_recovery import FaultConnection


class BSLTransactionsTests(unittest.TestCase):
    def setUp(self, *, allow_extensions=False):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name)/'owned.sqlite'
        context = SQLiteDBContext.create(self.path, configuration(mixed=True)); context.close()
        apply(self.path, prepare(self.path, maintenance=True), maintenance=True)
        self.context = SQLiteDBContext(self.path); self.addCleanup(self.context.close)
        self.backend = self.context.backend
        self.output = []
        self.vm = Interpreter(database_context=self.context, output=self.output.append,
                              allow_extensions=allow_extensions)

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

    def test_unknown_commit_never_resolves_or_replays(self):
        for phase in ('before', 'after'):
            with self.subTest(phase=phase):
                obj = self.catalog()
                with patch.object(type(self.backend), 'resolve_unit_of_work',
                                  side_effect=AssertionError('durable lookup')) as resolve:
                    # Normal execution exit also refuses to swallow a possibly
                    # committed write when the script caught the initial error.
                    with self.assertRaisesRegex(BackendError, '^uncertain_commit$'), execution(self.backend):
                        begin(self.backend); obj.write(); tx = current(self.backend)
                        fault = FaultConnection(tx.unit._view._connection, commit_fault=phase)
                        tx.unit._view._connection = fault
                        for action in (commit, active, commit, rollback):
                            with self.assertRaisesRegex(BackendError, '^uncertain_commit$'):
                                action(self.backend)
                    resolve.assert_not_called()
                self.assertEqual(fault.commit_calls, 1)
                self.assertIsNone(tx.unit._view._connection)
                self.assertIsNone(current(self.backend))
                self.assertTrue(obj.is_new())
                with self.assertRaisesRegex(BackendError, '^uncertain_commit$'):
                    obj.set_member('Description', 'must stay frozen')
                # The current DB record is independent evidence, not a receipt.
                self.assertEqual(self.vm.execute('Catalogs.Products.FindByCode("A").IsEmpty()'),
                                 phase == 'before')

    def test_bsl_catch_cannot_silence_unknown_at_execution_exit(self):
        from yadinassi.db.sqlite.sqlite_transactions import UnitOfWork
        original = UnitOfWork.commit
        faults = []
        def lose_reply(unit):
            fault = FaultConnection(unit._view._connection, commit_fault='after')
            faults.append(fault)
            unit._view._connection = fault
            return original(unit)
        self.catalog()
        with patch.object(UnitOfWork, 'commit', lose_reply), \
             patch.object(type(self.backend), 'resolve_unit_of_work',
                          side_effect=AssertionError('durable lookup')) as resolve:
            with self.assertRaisesRegex(BackendError, '^uncertain_commit$'):
                self.vm.execute('BeginTransaction();C.Write();Try CommitTransaction(); '
                                'Except Caught=True; EndTry;')
            resolve.assert_not_called()
        self.assertTrue(self.vm.variables['caught'])
        self.assertEqual([fault.commit_calls for fault in faults], [1])
        self.assertTrue(self.vm.execute('C.IsNew()'))
        self.assertFalse(self.vm.execute('Catalogs.Products.FindByCode("A").IsEmpty()'))

    def test_uncertain_exception_exit_preserves_error_and_frozen_buffer(self):
        obj = self.catalog()
        with patch.object(type(self.backend), 'resolve_unit_of_work',
                          side_effect=AssertionError('durable lookup')) as resolve:
            with self.assertRaises(KeyboardInterrupt), execution(self.backend):
                begin(self.backend); obj.write(); tx = current(self.backend)
                fault = FaultConnection(tx.unit._view._connection, commit_fault='interrupt')
                tx.unit._view._connection = fault
                commit(self.backend)
            resolve.assert_not_called()
        self.assertEqual(fault.commit_calls, 1)
        self.assertIsNone(self.backend._bsl_transaction)
        self.assertIsNone(tx.unit._view._connection)
        self.assertTrue(obj.is_new())
        self.assertFalse(self.vm.execute('Catalogs.Products.FindByCode("A").IsEmpty()'))

    def test_unknown_owner_is_not_transferred_if_physical_close_fails(self):
        obj = self.catalog()
        with patch.object(type(self.backend), 'resolve_unit_of_work',
                          side_effect=AssertionError('durable lookup')) as resolve:
            with self.assertRaisesRegex(BackendError, '^uncertain_commit$'), execution(self.backend):
                begin(self.backend); obj.write(); tx = current(self.backend)
                fault = FaultConnection(tx.unit._view._connection, commit_fault='after',
                                        close_fault='before', close_count=10)
                tx.unit._view._connection = fault
                commit(self.backend)
            original_owner = tx.owner
            try:
                with self.assertRaisesRegex(BackendError, '^unsupported$'), execution(self.backend):
                    commit(self.backend)
                self.assertIs(tx.owner, original_owner)
                self.assertIs(self.backend._bsl_transaction, tx)
                self.assertIs(tx.unit._view._connection, fault)
                self.assertEqual(fault.commit_calls, 1)
            finally:
                fault.close_count = 0
            resolve.assert_not_called()

    def test_known_commit_publishes_prebuilt_outcome_without_durable_lookup(self):
        obj = self.catalog()
        with patch.object(type(self.backend), 'resolve_unit_of_work',
                          side_effect=AssertionError('durable lookup')) as resolve:
            with self.assertRaisesRegex(RuntimeError, '^after known commit$'), execution(self.backend):
                begin(self.backend); obj.write(); tx = current(self.backend)
                commit_once = tx.unit.commit
                def after_success():
                    commit_once()
                    raise RuntimeError('after known commit')
                with patch.object(tx.unit, 'commit', side_effect=after_success) as low:
                    commit(self.backend)
            low.assert_called_once_with()
            resolve.assert_not_called()
        self.assertIsNone(self.backend._bsl_transaction)
        self.assertFalse(obj.is_new())
        self.assertFalse(self.vm.execute('Catalogs.Products.FindByCode("A").IsEmpty()'))

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
