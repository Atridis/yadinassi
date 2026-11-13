"""Closed read-only Constants SELECT from an owned scratch snapshot."""
from pathlib import Path
from decimal import Decimal
import tempfile
import unittest
from unittest.mock import patch
from test_source_constant_store import configuration
from yadinassi.configuration_source import import_source
from yadinassi.configuration_source_runtime import SourceApplication
from yadinassi.source_constant_queries import SourceConstantQuery
from yadinassi.errors import BSLError


def package(body=''):
    files={f.path:f.content for f in configuration().files}
    files['Ext/SessionModule.bsl']=('Procedure SessionParametersSetting(Names) '+body+' EndProcedure').encode()
    return import_source(files)


class SourceConstantQueryTests(unittest.TestCase):
    def setUp(self):
        d=tempfile.TemporaryDirectory();self.addCleanup(d.cleanup);self.path=Path(d.name)/'scratch.sqlite'

    def run_body(self,body):
        out=[];app=SourceApplication(package('Constants.Text.Set(""); '+body),scratch_database=self.path,output=out.append);self.addCleanup(app.close);app.start();return app,out

    def test_bsl_projection(self):
        app,out=self.run_body('Constants.Text.Set("hello"); Q=New Query("SELECT C.Text AS Label FROM Constants AS C"); S=Q.Execute().Select(); S.Next(); Message(S.Label);')
        self.assertEqual(out,['hello'])

    def test_russian_and_parameter(self):
        app,out=self.run_body('Константы.Text.Установить("hello"); З=Новый Запрос("ВЫБРАТЬ К.Text КАК Имя ИЗ Константы КАК К ГДЕ К.Text = &Текст"); З.УстановитьПараметр("Текст","hello"); Р=З.Выполнить().Выбрать(); Сообщить(Р.Следующий()); Сообщить(Р.Имя);')
        self.assertEqual(out,['Да','hello'])

    def test_filter_empty_result(self):
        _,out=self.run_body('Q=New Query("SELECT Text AS X FROM Constants WHERE Text = &Value"); Q.SetParameter("Value","absent"); Message(Q.Execute().IsEmpty());')
        self.assertEqual(out,['Да'])

    def test_aggregate_count(self):
        _,out=self.run_body('Q=New Query("SELECT COUNT(*) AS N FROM Constants"); S=Q.Execute().Select(); S.Next(); Message(S.N);')
        self.assertEqual(out,['1'])

    def test_numeric_expression(self):
        _,out=self.run_body('Constants.Amount.Set(2); Q=New Query("SELECT Amount + 3 AS Total FROM Constants ORDER BY Total"); S=Q.Execute().Select(); S.Next(); Message(S.Total);')
        self.assertEqual(out,['5'])

    def test_unload(self):
        _,out=self.run_body('Q=New Query("SELECT Text AS Name FROM Constants"); T=Q.Execute().Unload(); Message(T.Count()); Message(T[0].Name);')
        self.assertEqual(out,['1',''])

    def test_read_sees_uncommitted_then_rollback(self):
        app,out=self.run_body('BeginTransaction(); Constants.Text.Set("pending"); Q=New Query("SELECT Text AS Name FROM Constants"); S=Q.Execute().Select(); S.Next(); Message(S.Name); RollbackTransaction(); Message(Constants.Text.Get());')
        self.assertEqual(out,['pending','']);self.assertFalse(app.constant_store.transaction_active)

    def test_repeated_execute_reads_current_snapshot(self):
        _,out=self.run_body('Q=New Query("SELECT Text AS Name FROM Constants"); A=Q.Execute(); Constants.Text.Set("new"); B=Q.Execute(); S=A.Select(); S.Next(); Message(S.Name); S=B.Select(); S.Next(); Message(S.Name);')
        self.assertEqual(out,['','new'])

    def test_unselected_unsupported_not_read(self):
        _,out=self.run_body('Q=New Query("SELECT Text AS Name FROM Constants"); Message(Q.Execute().IsEmpty());')
        self.assertEqual(out,['Нет'])

    def test_selected_uninitialized_refused(self):
        with self.assertRaisesRegex(BSLError,'uninitialized'):self.run_body('Q=New Query("SELECT Flag AS F FROM Constants"); Q.Execute();')

    def test_selected_unsupported_refused(self):
        with self.assertRaises(BSLError):self.run_body('Q=New Query("SELECT Unsupported AS U FROM Constants"); Q.Execute();')

    def test_no_arbitrary_tables(self):
        with self.assertRaises(BSLError):self.run_body('Q=New Query("SELECT Ref FROM Catalog.Items"); Q.Execute();')

    def test_packages_refused(self):
        with self.assertRaises(BSLError):self.run_body('Q=New Query("SELECT Text FROM Constants; SELECT Text FROM Constants"); Q.Execute();')

    def test_join_refused(self):
        with self.assertRaises(BSLError):self.run_body('Q=New Query("SELECT A.Text FROM Constants AS A INNER JOIN Catalog.Items AS B ON A.Text = B.Description"); Q.Execute();')

    def test_query_text_never_sql(self):
        with self.assertRaises(BSLError):self.run_body('Q=New Query("DROP TABLE constant_value"); Q.Execute();')

    def test_safe_mode_denied(self):
        with self.assertRaises(BSLError):self.run_body('SetSafeMode(True); Q=New Query("SELECT Text FROM Constants"); Q.Execute();')

    def test_direct_execute_denied(self):
        app=SourceApplication(package(),scratch_database=self.path);self.addCleanup(app.close)
        app.start()
        query=SourceConstantQuery(app.interpreter,app,'SELECT Text FROM Constants')
        with self.assertRaisesRegex(ValueError,'actual interpreter'):query.execute()

    def test_client_execution_denied(self):
        app=SourceApplication(package(),scratch_database=self.path);self.addCleanup(app.close)
        app.start()
        query=SourceConstantQuery(app.interpreter,app,'SELECT Text FROM Constants')
        with self.assertRaises(ValueError):query.read(app.interpreter)

    def test_foreign_application_denied(self):
        app=SourceApplication(package(),scratch_database=self.path);other=SourceApplication(package());self.addCleanup(app.close);self.addCleanup(other.close)
        app.start()
        query=SourceConstantQuery(app.interpreter,app,'SELECT Text FROM Constants')
        other.start()
        other.interpreter._context_stack.append('server');self.addCleanup(other.interpreter._context_stack.pop)
        with self.assertRaises(ValueError):query.read(other.interpreter)

    def test_sql_snapshot_once(self):
        from yadinassi.source_constant_store import SourceConstantStore
        original=SourceConstantStore.get_many;calls=[]
        def read(store,names):calls.append(names);return original(store,names)
        with patch.object(SourceConstantStore,'get_many',read):
            self.run_body('Constants.Flag.Set(True); Q=New Query("SELECT Text AS T, Flag AS F FROM Constants"); Q.Execute();')
        self.assertEqual(calls,[('Text','Flag')])

    def test_count_validates_tampered_binding_even_without_fields(self):
        from contextlib import closing
        import sqlite3
        app=SourceApplication(package(),scratch_database=self.path);self.addCleanup(app.close)
        app.start()
        query=SourceConstantQuery(app.interpreter,app,'SELECT COUNT(*) AS N FROM Constants')
        app.interpreter._context_stack.append('server');self.addCleanup(app.interpreter._context_stack.pop)
        with closing(sqlite3.connect(self.path)) as db,db:
            db.execute("UPDATE source_binding SET source_sha256=?",('0'*64,))
        with self.assertRaisesRegex(ValueError,'binding'):query.read(app.interpreter)

    def test_existing_external_query_without_scratch_preserved(self):
        out=[]
        body='T=New ValueTable; T.Columns.Add("Name",New TypeDescription("String")); R=T.Add(); R.Name="external"; Q=New Query("SELECT Name AS N FROM &Data AS D"); Q.SetParameter("Data",T); S=Q.Execute().Select(); S.Next(); Message(S.N);'
        app=SourceApplication(package(body),output=out.append);self.addCleanup(app.close);app.start()
        self.assertEqual(out,['external'])

    def test_existing_external_batch_without_scratch_preserved(self):
        out=[]
        body='T=New ValueTable; T.Columns.Add("Name",New TypeDescription("String")); R=T.Add(); R.Name="external"; Q=New Query("SELECT Name AS N FROM &Data AS D"); Q.SetParameter("Data",T); Results=Q.ExecuteBatch(); Message(Results.Count());'
        app=SourceApplication(package(body),output=out.append);self.addCleanup(app.close);app.start()
        self.assertEqual(out,['1'])
