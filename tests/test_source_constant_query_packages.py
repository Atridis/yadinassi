"""Atomic temporary packages over one closed source-constant snapshot."""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from test_source_constant_queries import package
from yadinassi.configuration_source_runtime import SourceApplication
from yadinassi.source_constant_store import SourceConstantStore
from yadinassi.errors import BSLError


class ConstantQueryPackageTests(unittest.TestCase):
    def setUp(self):
        d=tempfile.TemporaryDirectory();self.addCleanup(d.cleanup);self.path=Path(d.name)/'scratch.sqlite'

    def run_body(self,body):
        out=[];app=SourceApplication(package('Constants.Text.Set("hello"); Constants.Amount.Set(2); '+body),scratch_database=self.path,output=out.append);self.addCleanup(app.close);app.start();return app,out

    def test_execute_batch_two_selects(self):
        _,out=self.run_body('Q=New Query("SELECT Text AS X FROM Constants; SELECT Amount AS N FROM Constants"); R=Q.ExecuteBatch(); Message(R.Count()); S=R[0].Select(); S.Next(); Message(S.X); S=R[1].Select(); S.Next(); Message(S.N);')
        self.assertEqual(out,['2','hello','2'])

    def test_execute_returns_last_result(self):
        _,out=self.run_body('Q=New Query("SELECT Text AS X FROM Constants; SELECT Amount AS N FROM Constants"); S=Q.Execute().Select(); S.Next(); Message(S.N);')
        self.assertEqual(out,['2'])

    def test_into_then_read(self):
        _,out=self.run_body('Q=New Query("SELECT Text AS X INTO Saved FROM Constants; SELECT X FROM Saved"); S=Q.Execute().Select(); S.Next(); Message(S.X);')
        self.assertEqual(out,['hello'])

    def test_temp_manager_preserves_across_query_objects(self):
        _,out=self.run_body('M=New TempTablesManager; Q=New Query("SELECT Text AS X INTO Saved FROM Constants"); Q.TempTablesManager=M; Q.Execute(); Constants.Text.Set("new"); Q=New Query("SELECT X FROM Saved"); Q.TempTablesManager=M; S=Q.Execute().Select(); S.Next(); Message(S.X);')
        self.assertEqual(out,['hello'])

    def test_join_constants_and_temp(self):
        _,out=self.run_body('Q=New Query("SELECT Text AS X INTO Saved FROM Constants; SELECT C.Text AS Result FROM Constants AS C INNER JOIN Saved AS S ON C.Text = S.X"); S=Q.Execute().Select(); S.Next(); Message(S.Result);')
        self.assertEqual(out,['hello'])

    def test_external_table_join(self):
        _,out=self.run_body('T=New ValueTable; T.Columns.Add("Name",New TypeDescription("String")); T.Add().Name="hello"; Q=New Query("SELECT C.Text AS X FROM Constants AS C INNER JOIN &Data AS D ON C.Text = D.Name"); Q.SetParameter("Data",T); S=Q.Execute().Select(); S.Next(); Message(S.X);')
        self.assertEqual(out,['hello'])

    def test_count_only_batch(self):
        _,out=self.run_body('Q=New Query("SELECT COUNT(*) AS N FROM Constants"); R=Q.ExecuteBatch(); S=R[0].Select(); S.Next(); Message(S.N);')
        self.assertEqual(out,['1'])

    def test_union_in_batch(self):
        _,out=self.run_body('Q=New Query("SELECT Text AS X FROM Constants UNION ALL SELECT Text AS X FROM Constants"); R=Q.ExecuteBatch(); Message(R[0].Unload().Count());')
        self.assertEqual(out,['2'])

    def test_destroy_temp(self):
        _,out=self.run_body('Q=New Query("SELECT Text AS X INTO Saved FROM Constants; DESTROY Saved; SELECT Amount AS N FROM Constants"); R=Q.ExecuteBatch(); Message(R.Count());')
        self.assertEqual(out,['3'])

    def test_failure_does_not_publish_created_temp(self):
        _,out=self.run_body('M=New TempTablesManager; Q=New Query("SELECT Text AS X INTO Saved FROM Constants; SELECT Missing FROM Constants"); Q.TempTablesManager=M; Try Q.Execute(); Except EndTry; Q=New Query("SELECT X FROM Saved"); Q.TempTablesManager=M; Try Q.Execute(); Except Message("absent"); EndTry;')
        self.assertEqual(out,['absent'])

    def test_failure_retains_prior_temp(self):
        _,out=self.run_body('M=New TempTablesManager; Q=New Query("SELECT Text AS X INTO Saved FROM Constants"); Q.TempTablesManager=M; Q.Execute(); Q.Text="DESTROY Saved; SELECT Missing FROM Constants"; Try Q.Execute(); Except EndTry; Q.Text="SELECT X FROM Saved"; S=Q.Execute().Select(); S.Next(); Message(S.X);')
        self.assertEqual(out,['hello'])

    def test_external_parameter_injection_collision_avoided(self):
        _,out=self.run_body('Q=New Query("SELECT Text AS X FROM Constants WHERE Text = &__source_constants"); Q.SetParameter("__source_constants","hello"); R=Q.ExecuteBatch(); Message(R[0].IsEmpty());')
        self.assertEqual(out,['Нет'])

    def test_missing_parameter_not_filled_by_injected_snapshot(self):
        with self.assertRaises(BSLError):self.run_body('Q=New Query("SELECT Text AS X FROM Constants WHERE Text = &__source_constants"); Q.ExecuteBatch();')

    def test_hidden_count_carrier_not_user_field(self):
        with self.assertRaises(BSLError):self.run_body('Q=New Query("SELECT __source_row FROM Constants"); Q.ExecuteBatch();')

    def test_reserved_constants_temp_target(self):
        with self.assertRaisesRegex(BSLError,'reserved'):self.run_body('Q=New Query("SELECT Text AS X INTO Constants FROM Constants"); Q.ExecuteBatch();')

    def test_reserved_constants_destroy(self):
        with self.assertRaisesRegex(BSLError,'reserved'):self.run_body('Q=New Query("DESTROY Constants; SELECT Text FROM Constants"); Q.ExecuteBatch();')

    def test_other_persistent_source_refused(self):
        with self.assertRaises(BSLError):self.run_body('Q=New Query("SELECT Text FROM Constants; SELECT Ref FROM Catalog.Items"); Q.ExecuteBatch();')

    def test_closed_temp_manager_refused(self):
        with self.assertRaises(BSLError):self.run_body('M=New TempTablesManager; M.Close(); Q=New Query("SELECT Text FROM Constants"); Q.TempTablesManager=M; Q.Execute();')

    def test_snapshot_one_read_for_batch(self):
        original=SourceConstantStore.get_many;calls=[]
        def read(store,names):calls.append(names);return original(store,names)
        with patch.object(SourceConstantStore,'get_many',read):self.run_body('Q=New Query("SELECT Text FROM Constants; SELECT Amount FROM Constants"); Q.ExecuteBatch();')
        self.assertEqual(calls,[('Text','Amount')])

    def test_later_write_cannot_split_batch_snapshot(self):
        original=SourceConstantStore.get_many
        def read(store,names):
            result=original(store,names);store.set('Text','later');return result
        with patch.object(SourceConstantStore,'get_many',read):
            app,out=self.run_body('Q=New Query("SELECT Text AS X FROM Constants; SELECT Text AS X FROM Constants"); R=Q.ExecuteBatch(); For Each Item In R Do S=Item.Select(); S.Next(); Message(S.X); EndDo;')
        self.assertEqual(out,['hello','hello']);self.assertEqual(app.constant_store.get('Text'),'later')

    def test_explicit_transaction_not_committed(self):
        app,out=self.run_body('BeginTransaction(); Constants.Text.Set("pending"); Q=New Query("SELECT Text AS X INTO Saved FROM Constants; SELECT X FROM Saved"); S=Q.Execute().Select(); S.Next(); Message(S.X); RollbackTransaction(); Message(Constants.Text.Get());')
        self.assertEqual(out,['pending','hello']);self.assertFalse(app.constant_store.transaction_active)

    def test_safe_mode_package_denied(self):
        with self.assertRaises(BSLError):self.run_body('SetSafeMode(True); Q=New Query("SELECT Text FROM Constants"); Q.ExecuteBatch();')
