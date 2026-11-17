"""Source forms keep the existing lifecycle with generated event execution."""
from contextlib import contextmanager
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from test_source_forms import files,request,CODE
from yadinassi.configuration_source import import_source
from yadinassi.configuration_source_runtime import SourceApplication
from yadinassi.source_forms import SourceFormController
from yadinassi.runtime import Interpreter


class DirectSourceForms(unittest.TestCase):
    @contextmanager
    def no_vm(self):
        with patch.object(Interpreter,'_execute_program',side_effect=AssertionError('legacy program')), \
             patch.object(Interpreter,'call_routine',side_effect=AssertionError('legacy routine')):
            yield

    def controller(self,code=CODE):
        app=SourceApplication(import_source(files(code)));self.addCleanup(app.close)
        app.start();return app,SourceFormController(app,'CommonForm.Main')

    def command(self,controller):
        return controller.exchange(request('event',event='command',revision=controller.client.session.revision,control='GoButton'))['result']

    def test_client_server_roundtrip_metadata_and_common_module_without_vm(self):
        with self.no_vm():
            app,controller=self.controller()
            self.assertIsNone(controller.exchange(request())['result']['error'])
            self.assertEqual(dict(controller.client.session.snapshot().attributes)['Greeting'],'Demo')
            self.assertIsNone(self.command(controller)['error'])
            self.assertEqual(dict(controller.client.session.snapshot().attributes)['Greeting'],'updated')
            self.assertFalse(controller.client.session._busy)
            self.assertFalse(controller.server.session._busy)
            self.assertIsNone(app.constant_store)

    def test_same_module_nested_routine_safe_mode_frame_is_isolated(self):
        code=CODE.replace(b' UpdateAtServer();',b' Child(); Greeting=String(SafeMode());')+b'\n&AtClient\nProcedure Child() SetSafeMode(True); EndProcedure'
        with self.no_vm():
            _,controller=self.controller(code);controller.exchange(request())
            self.assertIsNone(self.command(controller)['error'])
            self.assertEqual(dict(controller.client.session.snapshot().attributes)['Greeting'],'Нет')

    def test_safe_mode_file_effect_denied_in_actual_event(self):
        with TemporaryDirectory() as directory:
            target=Path(directory)/'denied'
            code=CODE.replace(b' UpdateAtServer();',(' SetSafeMode(True); CreateDirectory("'+str(target)+'");').encode())
            with self.no_vm():
                _,controller=self.controller(code);controller.exchange(request())
                self.assertIsNotNone(self.command(controller)['error'])
            self.assertFalse(target.exists())

    def test_nocontext_rejected_before_specialized_server_creation(self):
        code=CODE+b'\n&AtServerNoContext\nFunction Remote(Val X) Return X; EndFunction'
        with self.no_vm(),patch('yadinassi.source_forms._SourceNoContextServer',side_effect=AssertionError('legacy NoContext server')):
            with self.assertRaisesRegex(ValueError,'NoContext is not integrated'):self.controller(code)

    def test_failed_validation_releases_exact_source_child(self):
        from yadinassi.source_forms import _SourceFormInterpreter,source_form_definition
        app=SourceApplication(import_source(files()));self.addCleanup(app.close);app.start()
        children=[];original=_SourceFormInterpreter.__init__
        def initialize(child,*args,**kwargs):
            original(child,*args,**kwargs);children.append(child)
        with patch.object(_SourceFormInterpreter,'__init__',initialize),patch('yadinassi.python_direct_forms.prepare_form',side_effect=ValueError('failed preparation')):
            with self.assertRaisesRegex(ValueError,'failed preparation'):source_form_definition(app,'CommonForm.Main')
        self.assertEqual(len(children),1)
        self.assertTrue(children[0]._family_released);self.assertFalse(app.interpreter._family_closed)

    def test_explicit_legacy_nocontext_control_remains_available(self):
        from yadinassi.execution_policy import execution_backend_policy
        code=CODE.replace(b' UpdateAtServer();',b' Greeting=Remote("legacy");')+b'\n&AtServerNoContext\nFunction Remote(Val X) Return X; EndFunction'
        with execution_backend_policy('compiled-strict'):
            _,controller=self.controller(code);controller.exchange(request())
            self.assertIsNone(self.command(controller)['error'])
            self.assertEqual(dict(controller.client.session.snapshot().attributes)['Greeting'],'legacy')

    def test_closed_source_owner_cannot_receive_event(self):
        with self.no_vm():
            app,controller=self.controller();controller.exchange(request());app.close()
            with self.assertRaisesRegex(ValueError,'not running'):self.command(controller)


if __name__=='__main__':unittest.main()
