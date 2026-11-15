"""Source packages use one frozen snapshot and publish temporary state atomically."""
import unittest
from unittest.mock import patch
import test_source_catalog_queries as support
from yadinassi.errors import BSLError
from yadinassi.source_catalog_store import SourceCatalogStore


class SourceCatalogPackageTests(unittest.TestCase):
    setUp=support.SourceCatalogQueryTests.setUp
    run_body=support.SourceCatalogQueryTests.run_body

    def test_batch_two_results(self):
        _,out=self.run_body('Q=New Query("SELECT Code FROM Catalog.Items; SELECT COUNT(*) AS N FROM Catalog.Items"); R=Q.ExecuteBatch(); Message(R.Count()); S=R[1].Select(); S.Next(); Message(S.N);')
        self.assertEqual(out,['2','2'])
    def test_typed_temp_across_queries(self):
        _,out=self.run_body('M=New TempTablesManager; Q=New Query("SELECT Ref AS R INTO Saved FROM Catalog.Items"); Q.TempTablesManager=M; Q.Execute(); Q.Text="SELECT R FROM Saved"; S=Q.Execute().Select(); S.Next(); Message(S.R.IsEmpty());')
        self.assertEqual(out,['Нет'])
    def test_typed_temp_join(self):
        _,out=self.run_body('Q=New Query("SELECT Ref AS R INTO Saved FROM Catalog.Items; SELECT I.Description AS D FROM Saved AS T INNER JOIN Catalog.Items AS I ON T.R=I.Ref ORDER BY I.Code"); S=Q.Execute().Select(); While S.Next() Do Message(S.D); EndDo;')
        self.assertEqual(out,['Alpha','Beta'])
    def test_destroy(self):
        _,out=self.run_body('Q=New Query("SELECT Ref AS R INTO Saved FROM Catalog.Items; DESTROY Saved; SELECT Code FROM Catalog.Items"); Message(Q.ExecuteBatch().Count());')
        self.assertEqual(out,['3'])
    def test_failure_does_not_publish(self):
        _,out=self.run_body('M=New TempTablesManager; Q=New Query("SELECT Ref AS R INTO Saved FROM Catalog.Items; SELECT Missing FROM Catalog.Items"); Q.TempTablesManager=M; Try Q.Execute(); Except EndTry; Q.Text="SELECT R FROM Saved"; Try Q.Execute(); Except Message("absent"); EndTry;')
        self.assertEqual(out,['absent'])
    def test_failure_restores_destroyed_temp(self):
        _,out=self.run_body('M=New TempTablesManager; Q=New Query("SELECT Ref AS R INTO Saved FROM Catalog.Items"); Q.TempTablesManager=M; Q.Execute(); Q.Text="DESTROY Saved; SELECT Missing FROM Catalog.Items"; Try Q.Execute(); Except EndTry; Q.Text="SELECT R FROM Saved"; Message(Q.Execute().Unload().Count());')
        self.assertEqual(out,['2'])
    def test_typed_external_join(self):
        _,out=self.run_body('Q=New Query("SELECT Ref AS R FROM Catalog.Items"); T=Q.Execute().Unload(); Q.Text="SELECT I.Description AS D FROM &Input AS T INNER JOIN Catalog.Items AS I ON T.R=I.Ref ORDER BY I.Code"; Q.SetParameter("Input",T); S=Q.Execute().Select(); While S.Next() Do Message(S.D); EndDo;')
        self.assertEqual(out,['Alpha','Beta'])
    def test_closed_temp_manager(self):
        with self.assertRaises(BSLError):self.run_body('M=New TempTablesManager; M.Close(); Q=New Query("SELECT Ref FROM Catalog.Items"); Q.TempTablesManager=M; Q.Execute();')
    def test_safe_mode_requery(self):
        with self.assertRaises(BSLError):self.run_body('Q=New Query("SELECT Ref AS R FROM Catalog.Items"); T=Q.Execute().Unload(); Q.Text="SELECT R FROM &Input"; Q.SetParameter("Input",T); SetSafeMode(True); Q.Execute();')
    def test_user_parameter_collision(self):
        _,out=self.run_body('Q=New Query("SELECT Code AS C FROM Catalog.Items WHERE Code=&__source_catalog; SELECT Code AS C FROM Catalog.Items WHERE Code=&__source_catalog"); Q.SetParameter("__source_catalog","1"); Message(Q.ExecuteBatch().Count());')
        self.assertEqual(out,['2'])
    def test_missing_parameter_not_injected(self):
        with self.assertRaises(BSLError):self.run_body('Q=New Query("SELECT Code FROM Catalog.Items WHERE Code=&__source_catalog"); Q.ExecuteBatch();')
    def test_reserved_constants_target(self):
        with self.assertRaisesRegex(BSLError,'reserved'):self.run_body('Q=New Query("SELECT Ref INTO Constants FROM Catalog.Items"); Q.Execute();')
    def test_foreign_persistent_source(self):
        with self.assertRaises(BSLError):self.run_body('Q=New Query("SELECT Ref INTO T FROM Catalog.Items; SELECT Ref FROM Document.Unknown"); Q.Execute();')
    def test_single_snapshot_read_per_catalog(self):
        original=SourceCatalogStore.read_records;calls=[]
        def read(store,name,identity=None):calls.append(name);return original(store,name,identity)
        with patch.object(SourceCatalogStore,'read_records',read):
            self.run_body('Q=New Query("SELECT Ref FROM Catalog.Items; SELECT Ref FROM Catalog.Items"); Q.ExecuteBatch();')
        self.assertEqual(calls,['Items'])
    def test_external_empty_reference_report(self):
        _,out=self.run_body('Q=New Query("SELECT Ref AS R FROM Catalog.Items WHERE Code=""absent"""); T=Q.Execute().Unload(); Q.Text="SELECT COUNT(*) AS N FROM &Input"; Q.SetParameter("Input",T); S=Q.Execute().Select(); S.Next(); Message(S.N);')
        self.assertEqual(out,['0'])
    def test_explicit_transaction_not_committed(self):
        _,out=self.run_body('BeginTransaction(); O=Catalogs.Items.CreateItem(); O.Code="3"; O.Write(); Q=New Query("SELECT Ref INTO T FROM Catalog.Items; SELECT COUNT(*) AS N FROM T"); S=Q.Execute().Select(); S.Next(); Message(S.N); RollbackTransaction(); Q.Text="SELECT COUNT(*) AS N FROM Catalog.Items"; S=Q.Execute().Select(); S.Next(); Message(S.N);')
        self.assertEqual(out,['3','2'])
    def test_scalar_temp_retains_source_owner(self):
        from yadinassi.source_constant_queries import SourceConstantQuery
        from yadinassi.source_catalog_queries import has_source_inputs
        from yadinassi.query_packages import BSLTempTablesManager
        app,_=self.run_body('')
        query=SourceConstantQuery(app.interpreter,app,'SELECT Code AS C INTO Saved FROM Catalog.Items')
        query._temp_tables_manager=BSLTempTablesManager()
        app.interpreter._context_stack.append('server');self.addCleanup(app.interpreter._context_stack.pop)
        query.read(app.interpreter)
        self.assertTrue(has_source_inputs(query))
        self.assertIs(query._temp_tables_manager._source_owner(),app)
        query._text='SELECT C FROM Saved';app.close()
        with self.assertRaises(ValueError):query.read(app.interpreter)
    def test_scalar_temp_foreign_application_refused(self):
        from yadinassi.source_constant_queries import SourceConstantQuery
        from yadinassi.query_packages import BSLTempTablesManager
        from yadinassi.configuration_source_runtime import SourceApplication
        app,_=self.run_body('')
        query=SourceConstantQuery(app.interpreter,app,'SELECT Code AS C INTO Saved FROM Catalog.Items')
        manager=BSLTempTablesManager();query._temp_tables_manager=manager
        app.interpreter._context_stack.append('server');self.addCleanup(app.interpreter._context_stack.pop)
        query.read(app.interpreter)
        other=SourceApplication(app.source,existing_scratch_database=self.path,source_catalog_records=True);self.addCleanup(other.close)
        other.start();other.interpreter._context_stack.append('server');self.addCleanup(other.interpreter._context_stack.pop)
        foreign=SourceConstantQuery(other.interpreter,other,'SELECT C FROM Saved');foreign._temp_tables_manager=manager
        with self.assertRaises(TypeError):foreign.read(other.interpreter)
