"""Future-union tests: explicit BSL ownership across additive maintenance."""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from yadinassi import Interpreter
from yadinassi.catalog_backend import BackendError
from yadinassi.configuration_modules import MODULE_RUNTIME
from yadinassi.configuration_xml import import_configuration
from yadinassi.database_context import SQLiteDBContext
from yadinassi.database_transactions import execution, begin, commit, rollback, current
from yadinassi.sqlite_catalog import SQLiteCatalogBackend
from yadinassi.sqlite_configuration_update import prepare, apply, resolve
from yadinassi.sqlite_migration_plan import prepare as profile_plan, apply as profile_apply
from test_configuration_update_recovery import mixed_files
from test_configuration_evolution import append_field
from test_catalog_commit_cleanup_recovery import FaultConnection


class BSLConfigurationUpdateTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.path=Path(self.temp.name)/'owned.sqlite';files=mixed_files()
        self.source=import_configuration(files,numbering_policy='decimal_v1',module_runtime=MODULE_RUNTIME)
        self.target=import_configuration(append_field(files),numbering_policy='decimal_v1',module_runtime=MODULE_RUNTIME)
        backend=SQLiteCatalogBackend.create(self.path,self.source);backend.close()
        profile_apply(self.path,profile_plan(self.path,maintenance=True),maintenance=True)
        self.context=SQLiteDBContext(self.path);self.addCleanup(lambda:self.context.close())
        self.output=[];self.vm=Interpreter(database_context=self.context,output=self.output.append)

    @property
    def backend(self):return self.context.backend

    def evolve(self):
        self.context.close();plan=prepare(self.path,self.target,maintenance=True)
        apply(self.path,plan,maintenance=True)
        self.context=SQLiteDBContext(self.path)
        self.vm=Interpreter(database_context=self.context,output=self.output.append)
        return plan

    def test_bsl_mixed_commit_after_update_uses_new_schema(self):
        self.evolve()
        self.vm.execute('''C=Catalogs.Categories.CreateItem();C.Code="A";C.Extra=True;
D=Documents.Orders.CreateDocument();D.Number="A";D.Date=Date(2026,1,1);
R=InformationRegisters.Prices.CreateRecordManager();R.Period=Date(2026,1,1);R.Item="A";R.Region="R";R.Price=2;R.Enabled=True;
BeginTransaction();C.Write();D.Write();R.Write();CommitTransaction();Message(C.IsNew());Message(D.IsNew());Message(R.Selected());''')
        self.assertEqual(self.output,['Нет','Нет','Да'])
        self.assertTrue(self.vm.execute('Catalogs.Categories.FindByCode("A").Extra'))

    def test_borrowed_queries_after_update_do_not_reuse_stale_validation(self):
        self.evolve()
        self.vm.execute('''A=Catalogs.Categories.CreateItem();A.Code="A";
B=Catalogs.Categories.CreateItem();B.Code="B";BeginTransaction();A.Write();
Q=New Query("SELECT Code, Extra FROM Catalog.Categories");Message(Q.Execute().Unload().Count());
B.Write();Message(Q.Execute().Unload().Count());RollbackTransaction();''')
        self.assertEqual(self.output,['1','2'])
        self.assertTrue(self.vm.execute('Catalogs.Categories.FindByCode("A").IsEmpty()'))

    def test_old_bsl_batch_receipts_resolve_from_new_context(self):
        obj=self.vm.execute('C=Catalogs.Categories.CreateItem();C.Code="A";C')
        with execution(self.backend):
            begin(self.backend);obj.write();tx=current(self.backend)
            operation,requests=tx.unit.operation_id,tx.unit.requests
            commit(self.backend);outcomes=tx.unit._results
        self.evolve()
        for _ in range(2):self.assertEqual(self.backend.resolve_unit_of_work(operation,requests),outcomes)
        self.assertEqual(outcomes[0].result.revision.configuration_generation,1)
        self.assertFalse(self.vm.execute('Catalogs.Categories.FindByCode("A").Extra'))

    def test_active_bsl_writer_prevents_configuration_apply(self):
        plan=prepare(self.path,self.target,maintenance=True)
        before=self.path.read_bytes()
        obj=self.vm.execute('C=Catalogs.Categories.CreateItem();C.Code="A";C')
        with execution(self.backend):
            begin(self.backend);obj.write()
            with self.assertRaises(BackendError):apply(self.path,plan,maintenance=True)
            self.assertEqual(current(self.backend).unit.state,'open')
            rollback(self.backend)
        self.assertEqual(self.path.read_bytes(),before)
        self.assertEqual(resolve(self.path,plan,maintenance=True),'not_committed')

    def test_uncertain_new_generation_bsl_commit_resolves_whole_batch(self):
        self.evolve()
        obj=self.vm.execute('C=Catalogs.Categories.CreateItem();C.Code="A";C.Extra=True;C')
        with execution(self.backend):
            begin(self.backend);obj.write();tx=current(self.backend)
            tx.unit._view._connection=FaultConnection(tx.unit._view._connection,commit_fault='after')
            with self.assertRaisesRegex(BackendError,'uncertain_commit'):commit(self.backend)
            self.assertTrue(obj.is_new());commit(self.backend)
        self.assertFalse(obj.is_new());self.assertTrue(obj.get_member('Extra'))

    def test_open_query_lease_still_blocks_commit_after_update(self):
        self.evolve()
        with execution(self.backend):
            begin(self.backend);lease=self.backend.begin_query_read()
            with self.assertRaises(BackendError):commit(self.backend)
            lease.close();rollback(self.backend)

    def test_stale_bsl_context_cannot_write_after_maintenance(self):
        obj=self.vm.execute('C=Catalogs.Categories.CreateItem();C.Code="A";C')
        # An idle context is not an active writer, but its schema/generation
        # must fail closed after another maintenance owner updates the file.
        plan=prepare(self.path,self.target,maintenance=True);apply(self.path,plan,maintenance=True)
        with self.assertRaises(BackendError):
            with execution(self.backend):begin(self.backend)
        with self.assertRaises(BackendError):obj.write()
