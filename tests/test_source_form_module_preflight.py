"""Explicit compiler probe is not runtime/handler validation."""
import hashlib
import unittest
from unittest.mock import patch
import test_source_workspace as workspace_tests
from test_source_workspace import request
from test_source_forms import files, FORM, CODE

class SourceFormModulePreflightTests(unittest.TestCase):
    workspace=workspace_tests.SourceWorkspaceTests.workspace
    def check(self,w,name='CommonForm.Main'):
        return w.exchange(request('preflight',name=name))['result']['state']['module_preflight']

    def test_compile_does_not_create_server_or_execute_lifecycle(self):
        source=files(CODE.replace(b'Greeting = Metadata.Name;',b'Raise "must not run";'))
        w=self.workspace(source)
        with patch('yadinassi.ui.source_workspace.SourceFormController',side_effect=AssertionError('no controller')), patch('yadinassi.configuration_forms.FormDefinition.create_server',side_effect=AssertionError('no server')), patch('yadinassi.runtime.Interpreter.__init__',side_effect=AssertionError('no interpreter')):
            p=self.check(w)
        self.assertEqual(p['status'],'compiled');self.assertEqual(p['module_sha256'],hashlib.sha256(source['CommonForms/Main/Ext/Form/Module.bsl']).hexdigest());self.assertEqual(p['xml_sha256'],hashlib.sha256(FORM).hexdigest());self.assertEqual(p['compilation_profile'],w.application.compilation_profile)
        for flag in ('bindings_checked','runtime_checked','storage_granted','native_parity'):self.assertIs(p[flag],False)
        self.assertFalse(w.open_forms)

    def test_syntax_invalid_encoding_and_absent_module_report_failure(self):
        cases=[b'Procedure Broken(',b'\xff',None]
        for code in cases:
            source=files(code or b'')
            if code is None:del source['CommonForms/Main/Ext/Form/Module.bsl']
            with self.subTest(code=code):
                p=self.check(self.workspace(source));self.assertEqual(p['status'],'unavailable');self.assertTrue(p['error']);self.assertLessEqual(len(p['error']),1024)

    def test_top_level_side_effect_not_run_and_empty_module_is_distinguished(self):
        p=self.check(self.workspace(files(b'Raise "never";')));self.assertEqual(p['status'],'unavailable')
        p=self.check(self.workspace(files(b'')));self.assertEqual(p['status'],'compiled');self.assertEqual(p['module_sha256'],hashlib.sha256(b'').hexdigest())

    def test_missing_xml_binding_or_unresolved_call_not_misreported_as_runtime_check(self):
        source=files(b'&AtClient\nProcedure Other()\nMissingService();\nEndProcedure')
        w=self.workspace(source);p=self.check(w)
        self.assertEqual(p['status'],'compiled');self.assertFalse(p['bindings_checked']);self.assertFalse(p['runtime_checked'])
        del source['CommonForms/Main/Ext/Form.xml']
        p=self.check(self.workspace(source));self.assertIsNone(p['xml_sha256']);self.assertEqual(p['status'],'compiled')

    def test_repeated_probe_preserves_existing_form_and_snapshot_is_copy(self):
        w=self.workspace();w.exchange(request('open',name='CommonForm.Main'));form=w.form;generation=w.generation
        with patch.object(form,'exchange',side_effect=AssertionError('no dispatch')):
            p=self.check(w);self.assertEqual(p,self.check(w))
        self.assertIs(w.form,form);self.assertEqual(w.generation,generation)
        p['status']='fake';self.assertEqual(w.snapshot()['state']['module_preflight']['status'],'compiled')

    def test_exact_visibility_and_closed_gates_apply(self):
        w=self.workspace();w.exchange(request('search',query='nothing'))
        for name in ('CommonForm.Main','CommonForm.Missing','ОбщаяФорма.Main','../Module.bsl'):
            with self.subTest(name=name),self.assertRaises(ValueError):self.check(w,name)
        w.close()
        with self.assertRaises(ValueError):self.check(w)

    def test_preflight_passes_exact_application_profile_to_real_compiler(self):
        from yadinassi.configuration_source import import_source
        from yadinassi.configuration_source_runtime import SourceApplication
        from yadinassi.ui.source_workspace import SourceWorkspace
        from yadinassi.form_program import compile_form_module
        app=SourceApplication(import_source(files()),compilation_profile='managed-thick-file')
        self.addCleanup(app.close);app.start();w=SourceWorkspace(app)
        with patch('yadinassi.form_program.compile_form_module',wraps=compile_form_module) as compile:
            p=self.check(w)
        self.assertEqual(p['status'],'compiled');self.assertEqual(p['compilation_profile'],'managed-thick-file')
        compile.assert_called_once_with(CODE.decode(),compilation_profile='managed-thick-file')
