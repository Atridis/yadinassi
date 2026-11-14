"""Source constant value-manager lifecycle and rollback, not native parity."""
from contextlib import closing
from pathlib import Path
import sqlite3
import tempfile
import unittest
from test_source_constant_store import configuration
from yadinassi.configuration_source_runtime import SourceApplication
from yadinassi.source_constant_store import SourceConstantStore
from yadinassi.source_constant_managers import SourceConstantValueManager, ValueManagerCall
from yadinassi.source_constants_runtime import SourceConstants
from yadinassi.errors import BSLError


class SourceConstantHandlerTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(); self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name)/'scratch.sqlite'

    def app(self, body, module='', extra=None):
        files = {'Ext/SessionModule.bsl': ('Procedure SessionParametersSetting(Names) '+body+' EndProcedure').encode()}
        if module: files['Constants/Text/Ext/ValueManagerModule.bsl'] = module.encode()
        files.update(extra or {})
        app=SourceApplication(configuration(files), scratch_database=self.path)
        self.addCleanup(app.close)
        return app

    def count(self):
        with closing(sqlite3.connect(self.path)) as db:
            return db.execute('SELECT COUNT(*) FROM constant_value').fetchone()[0]

    def test_direct_set_invokes_before_and_after_in_order(self):
        out=[]
        app=self.app('Constants.Text.Set("original");', 'Procedure BeforeWrite(Cancel) Value="changed"; Message("before"); EndProcedure Procedure OnWrite(Cancel) Message(Constants.Text.Get()); EndProcedure')
        app.output=out.append
        app.interpreter.output=out.append
        app.start(); self.assertEqual(app.constant_store.get('Text'),'changed');self.assertEqual(out,['before','changed'])

    def test_value_manager_explicit_value_write_read_metadata(self):
        app=self.app('M=Constants.Text.CreateValueManager(); M.Value="saved"; M.Write(); Constants.Text.Set("next"); M.Read(); If M.Value<>"next" Then Raise "bad"; EndIf; If M.Metadata().Name<>"Text" Then Raise "metadata"; EndIf;')
        app.start();self.assertEqual(app.constant_store.get('Text'),'next')

    def test_russian_aliases_value_and_hooks(self):
        app=self.app('М=Константы.Text.СоздатьМенеджерЗначения(); М.Значение="старое"; М.Записать();', 'Процедура ПередЗаписью(Отказ) Значение="новое"; КонецПроцедуры Процедура ПриЗаписи(Отказ) КонецПроцедуры')
        app.start();self.assertEqual(app.constant_store.get('Text'),'новое')

    def test_before_cancel_rolls_back_all_set_members(self):
        app=self.app('S=Constants.CreateSet("Flag,Text"); S.Flag=True; S.Text="value"; S.Write();','Procedure BeforeWrite(Cancel) Cancel=True; EndProcedure')
        with self.assertRaisesRegex(BSLError,'cancelled'):app.start()
        self.assertEqual(self.count(),0)

    def test_after_cancel_rolls_back_written_value(self):
        app=self.app('Constants.Text.Set("value");','Procedure OnWrite(Cancel) Cancel=True; EndProcedure')
        with self.assertRaisesRegex(BSLError,'cancelled'):app.start()
        self.assertEqual(self.count(),0)

    def test_after_exception_rolls_back_whole_outer_transaction(self):
        app=self.app('BeginTransaction(); Constants.Flag.Set(True); Try Constants.Text.Set("value"); Except EndTry;','Procedure OnWrite(Cancel) Raise "stop"; EndProcedure')
        app.start();self.assertEqual(self.count(),0)

    def test_successful_write_does_not_commit_outer_transaction(self):
        app=self.app('BeginTransaction(); Constants.Text.Set("value"); RollbackTransaction();','Procedure BeforeWrite(Cancel) Value="changed"; EndProcedure')
        app.start();self.assertEqual(self.count(),0)

    def test_handler_cannot_commit_parent_transaction(self):
        app=self.app('Constants.Text.Set("value");','Procedure OnWrite(Cancel) CommitTransaction(); EndProcedure')
        with self.assertRaises(BSLError):app.start()
        self.assertEqual(self.count(),0)

    def test_recursive_handler_write_refused(self):
        app=self.app('Constants.Text.Set("value");','Procedure OnWrite(Cancel) Constants.Flag.Set(True); EndProcedure')
        with self.assertRaisesRegex(BSLError,'recursive'):app.start()
        self.assertEqual(self.count(),0)

    def test_read_and_helper_routines_in_handler(self):
        app=self.app('Constants.Flag.Set(True);Constants.Text.Set("value");','Function Enabled() Return Constants.Flag.Get(); EndFunction Procedure BeforeWrite(Cancel) If Enabled() Then Value="yes"; EndIf; EndProcedure')
        app.start();self.assertEqual(app.constant_store.get('Text'),'yes')

    def test_module_variables_preserved_for_reused_value_manager(self):
        app=self.app('M=Constants.Text.CreateValueManager();M.Value="first";M.Write();M.Value="second";M.Write();','Var Seen; Procedure BeforeWrite(Cancel) If Seen=Undefined Then Seen=True; Else Value="reused"; EndIf; EndProcedure')
        app.start();self.assertEqual(app.constant_store.get('Text'),'reused')

    def test_uninitialized_value_is_not_fake_default(self):
        app=self.app('M=Constants.Text.CreateValueManager(); M.Write();')
        with self.assertRaisesRegex(BSLError,'uninitialized'):app.start()
        self.assertEqual(self.count(),0)

    def test_invalid_handler_value_qualifier_rolls_back(self):
        app=self.app('Constants.Text.Set("value");','Procedure BeforeWrite(Cancel) Value="12345678901234567"; EndProcedure')
        with self.assertRaises(BSLError):app.start()
        self.assertEqual(self.count(),0)

    def test_cancel_must_be_boolean(self):
        app=self.app('Constants.Text.Set("value");','Procedure BeforeWrite(Cancel) Cancel="yes"; EndProcedure')
        with self.assertRaisesRegex(BSLError,'Boolean'):app.start()
        self.assertEqual(self.count(),0)

    def test_handler_signature_byvalue_refused(self):
        app=self.app('Constants.Text.Set("value");','Procedure BeforeWrite(Val Cancel) EndProcedure')
        with self.assertRaisesRegex(BSLError,'signature'):app.start()
        self.assertEqual(self.count(),0)

    def test_dual_alias_ambiguity_refused(self):
        app=self.app('Constants.Text.Set("value");','Procedure BeforeWrite(Cancel) EndProcedure Procedure ПередЗаписью(Отказ) EndProcedure')
        with self.assertRaisesRegex(BSLError,'ambiguous'):app.start()
        self.assertEqual(self.count(),0)

    def test_module_initialization_statements_refused(self):
        app=self.app('Constants.Text.Set("value");','Message("init");')
        with self.assertRaisesRegex(BSLError,'initialization statements'):app.start()
        self.assertEqual(self.count(),0)

    def test_fillcheck_handler_not_silently_skipped(self):
        app=self.app('Constants.Text.Set("value");','Procedure FillCheckProcessing(Cancel, Fields) EndProcedure')
        with self.assertRaisesRegex(BSLError,'FillCheckProcessing'):app.start()
        self.assertEqual(self.count(),0)

    def test_reserved_module_value_variable_refused(self):
        app=self.app('Constants.Text.Set("value");','Var Value;')
        with self.assertRaisesRegex(BSLError,'reserved'):app.start()

    def test_history_blocker_retained(self):
        original=configuration();xml=next(x.content for x in original.files if x.path=='Constants/Text.xml').replace(b'<DataHistory>DontUse</DataHistory>',b'<DataHistory>Use</DataHistory>')
        app=self.app('Constants.Text.Set("value");','Procedure BeforeWrite(Cancel) EndProcedure',{'Constants/Text.xml':xml})
        with self.assertRaisesRegex(BSLError,'history'):app.start()
        self.assertEqual(self.count(),0)

    def test_direct_storage_api_still_refuses_module_bypass(self):
        app=self.app('','Procedure BeforeWrite(Cancel) EndProcedure')
        with self.assertRaisesRegex(ValueError,'module execution'):app.constant_store.set('Text','value')

    def test_client_saved_manager_denied(self):
        app=self.app('');app.start()
        manager=SourceConstantValueManager(SourceConstants(app),'Text');manager.value='value'
        app.interpreter.variables['saved']=manager
        with self.assertRaisesRegex(BSLError,'owning synchronous server'):app.interpreter.execute('Saved.Write();')
        self.assertEqual(self.count(),0)

    def test_safe_mode_changed_in_handler_rolls_back(self):
        app=self.app('Constants.Text.Set("value");','Procedure OnWrite(Cancel) SetSafeMode(True); Value="blocked"; EndProcedure')
        with self.assertRaisesRegex(BSLError,'safe mode'):app.start()
        self.assertEqual(self.count(),0)

    def test_caught_storage_failure_poison_does_not_autocommit(self):
        app=self.app('Constants.Text.Set("value");', 'Procedure BeforeWrite(Cancel) Try Constants.Date.Get(); Except EndTry; EndProcedure Procedure OnWrite(Cancel) Cancel=True; EndProcedure')
        with self.assertRaisesRegex(BSLError,'transaction aborted'):app.start()
        self.assertEqual(self.count(),0)

    def test_pending_tasks_refuse_manager_creation_before_effects(self):
        from unittest.mock import patch, PropertyMock
        from yadinassi.source_constant_managers import create_manager
        app=self.app('','Procedure BeforeWrite(Cancel) EndProcedure');app.start()
        caller=app._session_owner; caller._context_stack.append('server')
        try:
            with patch.object(type(caller._scheduler), 'pending', new_callable=PropertyMock, return_value=True):
                with self.assertRaisesRegex(ValueError,'pending'):
                    next(create_manager(caller, SourceConstants(app), 'Text'))
        finally:caller._context_stack.pop()
        self.assertEqual(self.count(),0)

    def test_pending_tasks_refuse_saved_manager_write_before_commit(self):
        from unittest.mock import patch, PropertyMock
        from yadinassi.source_constant_managers import write_managers
        app=self.app('');app.start()
        caller=app._session_owner;caller._context_stack.append('server')
        owner=SourceConstants(app);manager=SourceConstantValueManager(owner,'Text');manager.value='saved'
        try:
            with patch.object(type(caller._scheduler), 'pending', new_callable=PropertyMock, return_value=True):
                with self.assertRaisesRegex(ValueError,'pending'):
                    next(write_managers(caller,owner,[manager]))
        finally:caller._context_stack.pop()
        self.assertEqual(self.count(),0)

    def test_value_passed_to_helper_by_reference_updates_typed_storage(self):
        app=self.app('Constants.Text.Set("original");', 'Procedure Change(V) V="helper"; EndProcedure Procedure BeforeWrite(Cancel) Change(Value); EndProcedure')
        app.start();self.assertEqual(app.constant_store.get('Text'),'helper')
