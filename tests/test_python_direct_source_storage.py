"""Storage source lowering never delegates execution to the legacy evaluator."""
from contextlib import contextmanager
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from test_source_catalog_records import package as catalogs
from test_source_constants_runtime import package as constants
from yadinassi.configuration.configuration_source_runtime import SourceApplication
from yadinassi.runtime import Interpreter
from yadinassi.execution.codegen.experimental_naked_boundaries import BoundaryViolation
from yadinassi.types.errors import BSLError


class DirectSourceStorageTests(unittest.TestCase):
    def app(self,source,*,catalog=False):
        tmp=TemporaryDirectory();self.addCleanup(tmp.cleanup)
        output=[]
        app=SourceApplication(source,scratch_database=Path(tmp.name)/'db.sqlite',
            source_catalog_records=catalog,output=output.append)
        self.addCleanup(app.close)
        return app,output

    @contextmanager
    def no_vm(self):
        with patch.object(Interpreter,'_execute_program',side_effect=AssertionError('legacy program')), \
             patch.object(Interpreter,'call_routine',side_effect=AssertionError('legacy routine')):
            yield

    def test_constant_set_value_manager_and_index_iteration_without_vm(self):
        app,out=self.app(constants('Constants["Flag"].Set(True); S=Constants.CreateSet("Flag"); S.Read(); Message(S.Flag); S.Flag=False; S.Write(); V=Constants.Flag.CreateValueManager(); V.Read(); Message(V.Value); V.Value=True; V.Write(); For Each C In Constants Do Message(C.Get()); EndDo;'))
        with self.no_vm():app.start()
        self.assertEqual(out,['Да','Нет','Да'])

    def test_catalog_write_reference_selection_and_saved_method_without_vm(self):
        app,out=self.app(catalogs('F=Catalogs.Items.CreateItem; O=F(); O.Code="A"; O.Description="First"; O.Write(); P=O.Ref.GetObject(); P.Description="Second"; P.Write(); S=Catalogs.Items.Select(); Message(S.Next()); Message(S.Description);'),catalog=True)
        with self.no_vm():app.start()
        self.assertEqual(out,['Да','Second'])

    def test_unexpected_suspension_closes_operation(self):
        from yadinassi.execution.direct.source.python_direct_source_storage import finish
        cleaned=[]
        def operation():
            try:yield object()
            finally:cleaned.append(True)
        with self.assertRaisesRegex(BoundaryViolation,'suspension'):finish(operation())
        self.assertEqual(cleaned,[True])

    def test_outer_transaction_rollback_without_vm(self):
        app,out=self.app(constants('Constants.Flag.Set(False); BeginTransaction(); Constants.Flag.Set(True); RollbackTransaction(); Message(Constants.Flag.Get());'))
        with self.no_vm():app.start()
        self.assertEqual(out,['Нет']);self.assertFalse(app.constant_store.transaction_active)

    def test_procedure_as_value_rejected_before_argument_effect(self):
        app,out=self.app(constants('X=Constants.Flag.Set(SideEffect());'))
        app.interpreter.register_function('SideEffect',lambda:out.append('effect'))
        with self.no_vm(),self.assertRaisesRegex(BSLError,'Процедура'):app.start()
        self.assertEqual(out,[])

    def test_wrong_arity_rejected_before_argument_effect(self):
        app,out=self.app(constants('Constants.Flag.Get(SideEffect());'))
        app.interpreter.register_function('SideEffect',lambda:out.append('effect'))
        with self.no_vm(),self.assertRaisesRegex(BSLError,'argument count'):app.start()
        self.assertEqual(out,[])

    def test_safe_mode_change_in_argument_prevents_write(self):
        from yadinassi.configuration.configuration_source import import_source
        source=constants('Constants.Flag.Set(ChangeMode());')
        files={entry.path:entry.content for entry in source.files}
        files['Ext/SessionModule.bsl']+=b' Function ChangeMode() SetSafeMode(True); Return True; EndFunction'
        # Mode set in a child routine intentionally does not leak to the caller.
        # Change it using a registered host callback on the actual session owner.
        app,out=self.app(import_source(files));app.start()
        owner=app._session_owner;owner._context_stack.append('server')
        self.addCleanup(owner._context_stack.pop)
        def change():
            owner.functions['setsafemode'](True)
            return False
        owner.register_function('ChangeModeHost',change)
        with self.no_vm(),self.assertRaisesRegex(BSLError,'safe mode'):
            owner.execute('&AtServer\nProcedure Run() Constants.Flag.Set(ChangeModeHost()); EndProcedure Run();')
        self.assertTrue(app.constant_store.get('Flag'))
        import sqlite3
        from contextlib import closing
        with closing(sqlite3.connect(app.constant_store.path)) as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM constant_value').fetchone()[0],1)


if __name__=='__main__':unittest.main()
