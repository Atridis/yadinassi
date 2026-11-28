"""No-handler source admission borrows only the current explicit writer snapshot."""
import unittest
from unittest.mock import patch
from yadinassi import BSLRuntimeError
from yadinassi.db import database_transactions as tx
from yadinassi.db.catalog.catalog_backend import BackendError
from yadinassi.execution.codegen.direct_boundaries import BoundaryViolation
import test_python_direct_database as fixture
from test_catalog_commit_cleanup_recovery import FaultConnection

class DirectSourceTransactionTests(unittest.TestCase):
    setUp=fixture.DirectDatabaseTests.setUp
    def clean(self):
        self.assertIsNone(tx._execution.get());self.assertIsNone(tx._execution_backend.get())
        self.assertIsNone(self.context.backend._active)
        self.assertIsNone(tx._registered(self.context.backend))
    def count(self):
        self.vm.execute('Q=New Query("SELECT COUNT(*) AS N FROM Catalog.Склады");S=Q.Execute().Select();S.Next();N=S.N;')
        return self.vm.variables['n']
    def test_existing_object_update_commit_and_rollback(self):
        self.vm.execute('A=Catalogs.Склады.CreateItem();A.Description="before";A.Write();BeginTransaction();A.Description="after";A.Write();CommitTransaction();R=A.Ref.GetObject().Description;')
        self.assertEqual(self.vm.variables['r'],'after');self.clean()
        self.vm.execute('BeginTransaction();A.Description="discard";A.Write();RollbackTransaction();R=A.Ref.GetObject().Description;')
        self.assertEqual(self.vm.variables['r'],'after');self.clean()
    def test_source_is_checked_on_same_connection_without_new_reader(self):
        self.vm=fixture.DirectDatabaseTests.interpreter(self, allow_extensions=True)
        backend=self.context.backend;read=backend._main_demo_source_snapshot;seen=[]
        def check(connection):
            owner=tx.current(backend);self.assertIs(connection,owner.unit._view._connection)
            self.assertEqual(owner.leases,1);seen.append(connection)
            return read(connection)
        def forbid_new_connection():
            self.patch=patch.object(backend,'_connect',side_effect=AssertionError('separate snapshot'))
            self.patch.start();self.addCleanup(self.patch.stop)
        self.vm.register_function('Check',forbid_new_connection)
        with patch.object(backend,'_main_demo_source_snapshot',side_effect=check):
            self.vm.execute('A=Catalogs.Склады.CreateItem();A.Description="same";BeginTransaction();Check();A.Write();CommitTransaction();')
        self.assertEqual(len(seen),1);self.clean()
    def test_corrupt_source_or_schema_never_means_absent_handler(self):
        self.vm=fixture.DirectDatabaseTests.interpreter(self, allow_extensions=True)
        backend=self.context.backend
        for sql in ("UPDATE configuration_file SET content=x'00' WHERE path LIKE '%ObjectModule.bsl'",'UPDATE database_info SET generation=generation+1', 'DROP TABLE configuration_file'):
            def corrupt():tx.current(backend).unit._view._connection.execute(sql)
            self.vm.register_function('Corrupt',corrupt)
            with self.subTest(sql=sql),self.assertRaises((BackendError,BSLRuntimeError)):
                self.vm.execute('A=Catalogs.Склады.CreateItem();A.Description="bad";BeginTransaction();Corrupt();A.Write();CommitTransaction();')
            self.clean();self.assertEqual(self.count(),0)
    def test_invalid_format16_envelope_is_rejected_before_source_reparse(self):
        self.vm = fixture.DirectDatabaseTests.interpreter(self, allow_extensions=True)
        backend = self.context.backend
        for sql in ('UPDATE database_info SET generation=2',
                    'UPDATE database_info SET activated=0',
                    "UPDATE database_info SET activation_issues='not admitted'"):
            def corrupt():
                tx.current(backend).unit._view._connection.execute(sql)
            self.vm.register_function('Corrupt', corrupt)
            with self.subTest(sql=sql), patch(
                    'yadinassi.configuration.configuration_main_demo.import_main_demo_configuration',
                    side_effect=AssertionError('an invalid envelope cannot reach the source importer')):
                with self.assertRaisesRegex(BSLRuntimeError, 'integrity'):
                    self.vm.execute('A=Catalogs.Склады.CreateItem();BeginTransaction();Corrupt();A.Write();CommitTransaction();')
            self.clean()
            self.assertEqual(self.count(), 0)

    def test_refused_handler_rolls_back_prior_staging(self):
        with self.assertRaises((BackendError,BSLRuntimeError)):
            self.vm.execute('A=Catalogs.Склады.CreateItem();A.Description="staged";B=Catalogs.Номенклатура.CreateItem();B.Description="product";BeginTransaction();A.Write();B.Write();CommitTransaction();')
        self.clean();self.assertEqual(self.count(),0);self.assertTrue(self.vm.variables['a'].is_new())
    def test_foreign_owner_or_nontransaction_writer_not_borrowed(self):
        backend=self.context.backend;catalog=self.vm._catalogs.get_member('Склады')._schema.identity
        from uuid import uuid4
        view=backend.begin_write(uuid4())
        try:
            with self.assertRaisesRegex(BackendError,'busy'):backend.catalog_write_preparation(catalog)
            self.assertIs(backend._active,view)
        finally:view.close()
        with tx.execution(backend):
            tx.begin(backend);owner=tx.current(backend)
            marker=tx._execution.set(object())
            try:
                with self.assertRaises(BackendError):backend.catalog_write_preparation(catalog)
            finally:tx._execution.reset(marker)
            self.assertIs(tx.current(backend),owner);self.assertEqual(owner.leases,0);tx.rollback(backend)
        self.clean()
    def test_owner_recheck_after_source_read_rejects_change(self):
        backend=self.context.backend;read=backend._main_demo_source_snapshot
        def change(connection):
            result=read(connection);tx._execution.set(object());return result
        with patch.object(backend,'_main_demo_source_snapshot',side_effect=change):
            with self.assertRaises(BoundaryViolation):
                self.vm.execute('A=Catalogs.Склады.CreateItem();BeginTransaction();A.Write();CommitTransaction();')
        self.clean();self.assertEqual(self.count(),0)
    def test_interrupted_source_validation_releases_only_its_lease(self):
        class Stop(BaseException):pass
        with patch.object(self.context.backend,'_main_demo_source_snapshot',side_effect=Stop):
            with self.assertRaises(Stop):
                self.vm.execute('A=Catalogs.Склады.CreateItem();BeginTransaction();A.Write();CommitTransaction();')
        self.clean();self.assertEqual(self.count(),0)
    def test_uncertain_commit_neither_recovers_nor_rechecks_source(self):
        self.vm=fixture.DirectDatabaseTests.interpreter(self, allow_extensions=True)
        backend=self.context.backend
        for fault in ('before','after'):
            calls=[];read=backend._main_demo_source_snapshot
            def check(connection):calls.append(1);return read(connection)
            def inject():
                view=tx.current(backend).unit._view
                view._connection=FaultConnection(view._connection,commit_fault=fault)
            self.vm.register_function('Inject',inject)
            with patch.object(backend,'_main_demo_source_snapshot',side_effect=check):
                with self.assertRaises((BackendError,BSLRuntimeError)):
                    self.vm.execute('A=Catalogs.Склады.CreateItem();A.Description="fault";BeginTransaction();A.Write();Inject();CommitTransaction();')
            self.assertEqual(len(calls),1);self.clean()
            self.assertTrue(self.vm.variables['a'].is_new())
            self.assertIsNotNone(self.vm.variables['a']._pending_write)
        self.assertEqual(self.count(),1)
