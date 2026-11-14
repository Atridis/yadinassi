"""Source-owned scalar set buffers; no inferred native defaults or handlers."""
from contextlib import closing
from pathlib import Path
import tempfile
import sqlite3
import unittest
from test_source_constant_store import configuration
from test_source_constants_runtime import package
from yadinassi.configuration_source_runtime import SourceApplication
from yadinassi.source_constant_store import SourceConstantStore
from yadinassi.source_constants_runtime import SourceConstants, SourceConstantSet, ConstantSetCall
from yadinassi.errors import BSLError


class SourceConstantSetTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.path = Path(directory.name) / 'scratch.sqlite'

    def app(self, body, extra=None, simple=False):
        source = package(body) if simple else configuration({
            'Ext/SessionModule.bsl': ('Procedure SessionParametersSetting(Names) ' + body + ' EndProcedure').encode(),
            **(extra or {})})
        app = SourceApplication(source, scratch_database=self.path)
        self.addCleanup(app.close)
        return app

    def count(self):
        with closing(sqlite3.connect(self.path)) as db:
            return db.execute('SELECT COUNT(*) FROM constant_value').fetchone()[0]

    def test_explicit_set_write_persists_together(self):
        app = self.app('S = Constants.CreateSet("Flag, Text"); S.Flag = True; S.Text = "saved"; S.Write();')
        app.start()
        self.assertTrue(app.constant_store.get('Flag'))
        self.assertEqual(app.constant_store.get('Text'), 'saved')

    def test_russian_aliases_and_read_refresh(self):
        app = self.app('Константы.Flag.Установить(Истина); Н = Константы.СоздатьНабор("Flag"); Н.Прочитать(); Если Не Н.Flag Тогда ВызватьИсключение "bad"; КонецЕсли; Н.Flag = Ложь; Н.Записать();')
        app.start(); self.assertFalse(app.constant_store.get('Flag'))

    def test_no_argument_selects_all_declared_constants(self):
        app = self.app('S = Constants.CreateSet(); S.Flag = True; S.Write();', simple=True)
        app.start(); self.assertTrue(app.constant_store.get('Flag'))

    def test_external_transaction_not_committed_by_set(self):
        app = self.app('BeginTransaction(); S = Constants.CreateSet("Flag, Text"); S.Flag = True; S.Text = "pending"; S.Write(); If Not TransactionActive() Then Raise "bad"; EndIf; RollbackTransaction();')
        app.start(); self.assertEqual(self.count(), 0)

    def test_read_sees_pending_transaction_values(self):
        app = self.app('BeginTransaction(); Constants.Flag.Set(True); S = Constants.CreateSet("Flag"); S.Read(); If Not S.Flag Then Raise "bad"; EndIf; RollbackTransaction();')
        app.start(); self.assertEqual(self.count(), 0)

    def test_fields_must_all_be_initialized(self):
        app = self.app('S = Constants.CreateSet("Flag,Text"); S.Flag=True; S.Write();')
        with self.assertRaisesRegex(BSLError, 'all selected'): app.start()
        self.assertEqual(self.count(), 0)

    def test_uninitialized_field_read_not_fake_undefined(self):
        app = self.app('S=Constants.CreateSet("Flag"); X=S.Flag;')
        with self.assertRaisesRegex(BSLError, 'uninitialized'): app.start()

    def test_undefined_is_not_coerced(self):
        app = self.app('S=Constants.CreateSet("Flag"); S.Flag=Undefined;')
        with self.assertRaisesRegex(BSLError, 'Boolean'): app.start()
        self.assertEqual(self.count(), 0)

    def test_qualifiers_checked_before_buffer_assignment(self):
        app = self.app('S=Constants.CreateSet("Text"); S.Text="original"; Try S.Text="12345678901234567"; Except EndTry; S.Write();')
        app.start(); self.assertEqual(app.constant_store.get('Text'), 'original')

    def test_read_failure_keeps_previous_buffer(self):
        app = self.app('Constants.Flag.Set(True); S=Constants.CreateSet("Flag,Text"); S.Flag=False; S.Text="buffer"; Try S.Read(); Except EndTry; S.Write();')
        app.start(); self.assertFalse(app.constant_store.get('Flag'))
        self.assertEqual(app.constant_store.get('Text'), 'buffer')

    def test_late_write_blocker_rolls_back_earlier_value(self):
        app = self.app('S=Constants.CreateSet("Flag,Text"); S.Flag=True; S.Text="value"; S.Write();',
                       {'Constants/Text/Ext/ValueManagerModule.bsl': b'Procedure FillCheckProcessing(Cancel, Fields) EndProcedure'})
        with self.assertRaisesRegex(BSLError, 'FillCheckProcessing'): app.start()
        self.assertEqual(self.count(), 0)

    def test_failed_set_inside_transaction_aborts_whole_transaction(self):
        app = self.app('BeginTransaction(); Constants.Flag.Set(False); S=Constants.CreateSet("Flag,Text"); S.Flag=True; S.Text="value"; Try S.Write(); Except EndTry;',
                       {'Constants/Text/Ext/ValueManagerModule.bsl': b'Procedure FillCheckProcessing(Cancel, Fields) EndProcedure'})
        app.start(); self.assertEqual(self.count(), 0)

    def test_index_and_iteration_manager_calls(self):
        app = self.app('Constants["Flag"].Set(True); For Each C In Constants Do C.Set(False); EndDo;', simple=True)
        app.start(); self.assertFalse(app.constant_store.get('Flag'))

    def test_invalid_selections_refused(self):
        for text in ('Flag,flag', 'Flag,', '', 'Unknown', 'Unsupported'):
            with self.subTest(text=text):
                app = SourceApplication(configuration(), scratch_database=self.path.with_name('case'+str(len(text))+text.replace(',', '_')+'.sqlite'))
                try:
                    app.start()
                    # A missing SessionModule has no server owner: use root with explicit context for host-only validation.
                    caller=app.interpreter; caller._context_stack.append('server')
                    with self.assertRaises((ValueError,TypeError)):
                        ConstantSetCall(SourceConstants(app), 'create').invoke(caller, [text])
                finally: app.close()

    def test_closed_and_client_captured_set_methods_denied(self):
        app = self.app(''); app.start()
        receiver = SourceConstantSet(SourceConstants(app), ('Flag',))
        marker = ConstantSetCall(receiver, 'read')
        app.interpreter.register_function('CapturedRead', marker.descriptor(), returns_value=False)
        with self.assertRaisesRegex(BSLError, 'owning synchronous server'): app.interpreter.execute('CapturedRead();')
        app.close()
        with self.assertRaises(ValueError): marker.invoke(app.interpreter, [])

    def test_foreign_captured_set_denied(self):
        app = self.app(''); app.start()
        other = SourceApplication(package('')); self.addCleanup(other.close); other.start()
        other._session_owner._context_stack.append('server')
        try:
            with self.assertRaisesRegex(ValueError, 'owning synchronous server'):
                ConstantSetCall(SourceConstantSet(SourceConstants(app), ('Flag',)), 'read').invoke(other._session_owner, [])
        finally: other._session_owner._context_stack.pop()

    def test_safe_mode_denies_create_and_access(self):
        app = self.app('S=Constants.CreateSet("Flag"); SetSafeMode(True); S.Flag=True;')
        with self.assertRaisesRegex(BSLError, 'safe mode'): app.start()
        self.assertEqual(self.count(), 0)

    def test_no_implicit_database(self):
        app = SourceApplication(package('S=Constants.CreateSet("Flag");')); self.addCleanup(app.close)
        with self.assertRaisesRegex(BSLError, 'scratch database'): app.start()

    def test_saved_set_can_be_written_repeatedly(self):
        app = self.app('S=Constants.CreateSet("Flag"); S.Flag=True; S.Write(); S.Flag=False; S.Write();')
        app.start(); self.assertFalse(app.constant_store.get('Flag'))

    def test_store_batch_failure_rolls_back_prior_updates(self):
        store = SourceConstantStore.create(self.path, configuration()); self.addCleanup(store.close)
        store.set('Flag', False)
        with self.assertRaises(TypeError): store.set_many({'Flag': True, 'Text': 42})
        self.assertFalse(store.get('Flag')); self.assertEqual(self.count(), 1)

    def test_client_property_access_denied(self):
        app=self.app(''); app.start()
        receiver=SourceConstantSet(SourceConstants(app), ('Flag',)); receiver.values['flag']=True
        app.interpreter.set_variable('SavedSet', receiver)
        with self.assertRaisesRegex(BSLError, 'owning synchronous server'): app.interpreter.execute('X=SavedSet.Flag;')

    def test_createset_name_conflict_refused_for_direct_call(self):
        from yadinassi.configuration_source import import_source
        original = package('S=Constants.CreateSet("CreateSet");')
        files = {item.path.replace('Flag', 'CreateSet'): item.content.replace(b'Flag', b'CreateSet') for item in original.files}
        app = SourceApplication(import_source(files), scratch_database=self.path)
        self.addCleanup(app.close)
        with self.assertRaisesRegex(BSLError, 'conflicts with CreateSet'): app.start()
