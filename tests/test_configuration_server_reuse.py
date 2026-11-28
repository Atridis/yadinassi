"""Closed measured file-mode reuse admission and ownership regressions."""
import json
import unittest
from unittest.mock import patch
from yadinassi.configuration.configuration_runtime import ConfigurationApplication
from yadinassi.configuration.configuration_source import import_source
from yadinassi.configuration.configuration_source_runtime import SourceApplication
from yadinassi.types.errors import BSLError
from configuration_runtime_fixture import module_files
from test_server_module_reuse_native_replay import application, application_files, NATIVE, replay_observations

FLAGS={'ClientManagedApplication':'false','Server':'true','ServerCall':'true','ReturnValuesReuse':'DuringSession'}
SOURCE='Function Token(Val Key) Export Return String(New UUID); EndFunction'
class ServerReuseTests(unittest.TestCase):
    def app(self):
        app=application();self.addCleanup(app.close,force=True);return app
    def source_interpreter(self):
        # Qualified file-mode calls use the same source owner as native replay.
        # Keep ConfigurationApplication for its independent admission tests.
        app = SourceApplication(import_source(application_files()))
        self.addCleanup(app.close)
        self.assertTrue(app.start())
        return app.interpreter

    def from_source(self,source=SOURCE,flags=None):
        app=ConfigurationApplication.from_files(module_files([('Tools',source,{**FLAGS,**(flags or {})})]));self.addCleanup(app.close,force=True);app.start();return app
    def test_split_client_closed(self):
        with self.assertRaises(ValueError):ConfigurationApplication.from_files(application_files(),side='client',server_exchange=lambda raw:raw)
    def test_split_server_closed(self):
        with self.assertRaises(ValueError):ConfigurationApplication.from_files(application_files(),side='server')
    def test_global_closed(self):
        with self.assertRaises(ValueError):self.from_source(flags={'Global':'true'})
    def test_dual_side_closed(self):
        with self.assertRaises(ValueError):self.from_source(flags={'ClientManagedApplication':'true'})
    def test_privileged_closed(self):
        with self.assertRaises(ValueError):self.from_source(flags={'Privileged':'true'})
    def test_by_reference_closed(self):
        with self.assertRaises(ValueError):self.from_source(SOURCE.replace('Val Key','Key'))
    def test_default_parameter_closed(self):
        with self.assertRaises(ValueError):self.from_source(SOURCE.replace('Val Key','Val Key="x"'))
    def test_procedure_closed(self):
        with self.assertRaises(ValueError):self.from_source('Procedure Touch(Val Key) Export EndProcedure')
    def test_async_closed(self):
        with self.assertRaises(ValueError):self.from_source('Async '+SOURCE)
    def test_array_argument_closed(self):
        with self.assertRaises(BSLError):self.source_interpreter().execute('CachedServerCall.Token(New Array)')
    def test_structure_argument_closed(self):
        with self.assertRaises(BSLError):self.source_interpreter().execute('CachedServerCall.Token(New Structure("Key",1))')
    def test_array_result_closed(self):
        with self.assertRaises(BSLError):self.from_source(SOURCE.replace('String(New UUID)','New Array')).execute('Tools.Token("x")')
    def test_same_side_array_argument_closed(self):
        source=SOURCE+'\nFunction Inner(Val Key) Export Return Token(New Array); EndFunction'
        with self.assertRaises(BSLError):self.from_source(source).execute('Tools.Inner("x")')
    def test_foreign_family_closed(self):
        a,b=self.app(),self.app()
        with self.assertRaises(ValueError):a.reusable_values.cache(b.interpreter,'DuringSession')
    def test_closed_application(self):
        app=self.app();app.close(force=True)
        with self.assertRaises(ValueError):app.reusable_values.cache(app.interpreter,'DuringSession')
    def test_app_session_separation(self):
        a,b=self.source_interpreter(),self.source_interpreter()
        self.assertNotEqual(a.execute('CachedServerCall.Token("same")'),b.execute('CachedServerCall.Token("same")'))
    def test_warm_cache_cannot_skip_transfer_guard(self):
        vm=self.source_interpreter();vm.execute('CachedServerCall.Token("warm")')
        with patch('yadinassi.db.database_transactions.forbid_transfer',side_effect=ValueError('denied')) as guard:
            with self.assertRaises(BSLError):vm.execute('CachedServerCall.Token("warm")')
            guard.assert_called_once()
    def test_request_cleanup_after_failure(self):
        app=self.app()
        with self.assertRaises(BSLError):app.execute('ServerInspector.RequestToken("x");Raise "stop"')
        self.assertIsNone(app.interpreter._scheduler.active_context.request_cache)
    def test_native_full_event_sequence(self):
        expected=json.loads(NATIVE.read_bytes())['observations']
        self.assertEqual(replay_observations(),expected)
    def test_bad_arity_has_no_argument_effect(self):
        vm=self.source_interpreter()
        self.assertEqual(vm.execute('Calls=0;Try CachedServerCall.Token(ArgumentValue(),ArgumentValue());Except EndTry;Calls'),0)
