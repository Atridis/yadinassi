"""Local synchronous constant object-module execution, not native parity."""
from contextlib import closing
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch
from test_source_constant_store import configuration
from yadinassi.configuration_source_runtime import SourceApplication
from yadinassi.source_constant_managers import _ValueInterpreter
from yadinassi.errors import BSLError


class SourceConstantModuleLifecycleTests(unittest.TestCase):
    def setUp(self):
        directory=tempfile.TemporaryDirectory();self.addCleanup(directory.cleanup)
        self.path=Path(directory.name)/'scratch.sqlite'

    def app(self,body,module,extra=None):
        files={'Ext/SessionModule.bsl':('Procedure SessionParametersSetting(Names) '+body+' EndProcedure').encode(),'Constants/Text/Ext/ValueManagerModule.bsl':module.encode()}
        files.update(extra or {})
        app=SourceApplication(configuration(files),scratch_database=self.path);self.addCleanup(app.close);return app

    def count(self):
        with closing(sqlite3.connect(self.path)) as db:return db.execute('SELECT COUNT(*) FROM constant_value').fetchone()[0]

    def test_initializer_once_and_exported_function_state(self):
        app=self.app('M=Constants.Text.CreateValueManager();If M.Counter<>1 Then Raise "init";EndIf;If M.Next()<>2 Then Raise "next";EndIf;If M.Next()<>3 Then Raise "repeat";EndIf;', 'Var Counter Export; Function Next() Export Counter=Counter+1;Return Counter;EndFunction Counter=1;')
        app.start();self.assertEqual(self.count(),0)

    def test_exported_procedure_byref_and_defaults(self):
        app=self.app('M=Constants.Text.CreateValueManager();X="old";M.Change(X);If X<>"changed" Then Raise "ref";EndIf;If M.Prefix()<>"default" Then Raise "default";EndIf;', 'Procedure Change(V) Export V="changed";EndProcedure Function Prefix(Val P="default") Export Return P;EndFunction')
        app.start()

    def test_exported_fields_are_live_and_writable(self):
        app=self.app('M=Constants.Text.CreateValueManager();M.Counter=5;If M.GetCounter()<>5 Then Raise "bad";EndIf;', 'Var Counter Export; Function GetCounter() Export Return Counter;EndFunction Counter=1;')
        app.start()

    def test_manager_properties_byref_preserve_typed_value(self):
        body='M=Constants.Text.CreateValueManager();M.Value="initial";Change(M.Value);M.Write();'
        app=self.app(body,'')
        # Shared helper lives in the session module to exercise actual external caller.
        from yadinassi.configuration_source import import_source
        files={item.path:item.content for item in app.source.files};app.close();self.path.unlink()
        files['Ext/SessionModule.bsl']=('Procedure Change(V) V="helper";EndProcedure Procedure SessionParametersSetting(Names) '+body+' EndProcedure').encode()
        app=SourceApplication(import_source(files),scratch_database=self.path);self.addCleanup(app.close)
        app.start();self.assertEqual(app.constant_store.get('Text'),'helper')

    def test_thisobject_calls_own_export_during_initializer(self):
        app=self.app('M=Constants.Text.CreateValueManager();If M.Counter<>7 Then Raise "self";EndIf;', 'Var Counter Export; Procedure Initialize() Export ThisObject.Counter=7;EndProcedure ThisObject.Initialize();')
        app.start()

    def test_export_can_call_standard_write_and_handlers(self):
        app=self.app('M=Constants.Text.CreateValueManager();M.Save("input");', 'Procedure Save(Val V) Export Value=V;ThisObject.Write();EndProcedure Procedure BeforeWrite(Cancel) Value="handler";EndProcedure')
        app.start();self.assertEqual(app.constant_store.get('Text'),'handler')

    def test_private_procedure_not_exported(self):
        app=self.app('M=Constants.Text.CreateValueManager();M.Hidden();','Procedure Hidden() EndProcedure')
        with self.assertRaisesRegex(BSLError,'Метод объекта'):app.start()

    def test_private_field_not_exported(self):
        app=self.app('M=Constants.Text.CreateValueManager();X=M.Hidden;','Var Hidden;Hidden=1;')
        with self.assertRaisesRegex(BSLError,'Поле объекта'):app.start()

    def test_builtin_name_conflict_rejected(self):
        app=self.app('M=Constants.Text.CreateValueManager();','Procedure Write() Export EndProcedure')
        with self.assertRaisesRegex(BSLError,'reserved'):app.start()

    def test_direct_set_includes_initializer_side_writes_in_atomic_unit(self):
        app=self.app('Constants.Text.Set("input");', 'Constants.Flag.Set(True);Procedure BeforeWrite(Cancel) Value="changed";EndProcedure')
        app.start();self.assertTrue(app.constant_store.get('Flag'));self.assertEqual(app.constant_store.get('Text'),'changed')

    def test_set_cancel_rolls_back_initializer_and_primary_write(self):
        app=self.app('Try Constants.Text.Set("input");Except EndTry;', 'Constants.Flag.Set(True);Procedure OnWrite(Cancel) Cancel=True;EndProcedure')
        app.start();self.assertEqual(self.count(),0)

    def test_initializer_exception_rolls_back_side_writes(self):
        app=self.app('Try M=Constants.Text.CreateValueManager();Except EndTry;','Constants.Flag.Set(True);Raise "init failure";')
        app.start();self.assertEqual(self.count(),0)

    def test_public_creation_commits_successful_initializer_only(self):
        app=self.app('M=Constants.Text.CreateValueManager();','Constants.Flag.Set(True);Value="buffer";')
        app.start();self.assertTrue(app.constant_store.get('Flag'))
        with self.assertRaisesRegex(ValueError,'uninitialized'):app.constant_store.get('Text')

    def test_initializer_keeps_external_transaction_uncommitted(self):
        app=self.app('BeginTransaction();M=Constants.Text.CreateValueManager();RollbackTransaction();','Constants.Flag.Set(True);')
        app.start();self.assertEqual(self.count(),0)

    def test_initializer_cannot_commit_owned_transaction(self):
        app=self.app('M=Constants.Text.CreateValueManager();','Constants.Flag.Set(True);CommitTransaction();')
        with self.assertRaises(BSLError):app.start()
        self.assertEqual(self.count(),0)

    def test_caught_initializer_storage_error_cannot_autocommit(self):
        app=self.app('Constants.Text.Set("input");','Try Constants.Date.Get();Except EndTry;Constants.Flag.Set(True);')
        with self.assertRaisesRegex(BSLError,'initialization transaction aborted'):app.start()
        self.assertEqual(self.count(),0)

    def test_recursive_constructor_refused_and_rolled_back(self):
        app=self.app('M=Constants.Text.CreateValueManager();','Constants.Flag.Set(True);M=Constants.Text.CreateValueManager();')
        with self.assertRaisesRegex(BSLError,'recursive'):app.start()
        self.assertEqual(self.count(),0)

    def test_initializer_safe_mode_is_scoped(self):
        app=self.app('M=Constants.Text.CreateValueManager();Constants.Flag.Set(True);','SetSafeMode(True);')
        app.start();self.assertTrue(app.constant_store.get('Flag'))

    def test_initializer_safe_mode_prevents_writes(self):
        app=self.app('M=Constants.Text.CreateValueManager();','SetSafeMode(True);Constants.Flag.Set(True);')
        with self.assertRaisesRegex(BSLError,'safe mode'):app.start()
        self.assertEqual(self.count(),0)

    def test_leaked_failed_manager_is_retired(self):
        leaked=[];original=_ValueInterpreter.__init__
        def init(vm,*args,**kwargs):
            original(vm,*args,**kwargs);vm.register_function('Capture',leaked.append,returns_value=False)
        app=self.app('Try M=Constants.Text.CreateValueManager();Except EndTry;','Capture(ThisObject);Raise "fail";')
        with patch.object(_ValueInterpreter,'__init__',init):app.start()
        self.assertEqual(len(leaked),1);caller=app._session_owner;caller._context_stack.append('server')
        try:
            with self.assertRaisesRegex(ValueError,'failed'):leaked[0].authorize(caller)
        finally:caller._context_stack.pop()

    def test_saved_manager_export_rejects_client(self):
        app=self.app('','Function Answer() Export Return 1;EndFunction');app.start()
        from yadinassi.source_constant_managers import create_manager
        from yadinassi.source_constants_runtime import SourceConstants
        caller=app._session_owner;caller._context_stack.append('server')
        try:
            generator=create_manager(caller,SourceConstants(app),'Text')
            # Construction has no executable module statements and completes inline.
            try:next(generator)
            except StopIteration as result:manager=result.value
        finally:caller._context_stack.pop()
        app.interpreter.variables['saved']=manager
        with self.assertRaisesRegex(BSLError,'owning synchronous server'):app.interpreter.execute('X=Saved.Answer();')

    def test_set_batch_initialization_failure_rolls_back_previous_members(self):
        app=self.app('S=Constants.CreateSet("Flag,Text");S.Flag=True;S.Text="input";Try S.Write();Except EndTry;','Raise "failure";')
        app.start();self.assertEqual(self.count(),0)
