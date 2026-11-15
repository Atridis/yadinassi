"""One admitted request pairs source-bound XML and BSL probes, without opening."""
import hashlib
import unittest
from unittest.mock import patch
import test_source_workspace as workspace_tests
from test_source_workspace import request
from test_source_forms import files,FORM,CODE
from yadinassi.ui.source_workspace import SourceWorkspaceHandler

class SourceCombinedCheckTests(unittest.TestCase):
    workspace=workspace_tests.SourceWorkspaceTests.workspace
    def check(self,w,**params):
        return w.exchange(request('check',**(params or {'name':'CommonForm.Main'})))['result']['state']

    def test_one_request_pairs_hashes_without_runtime_or_open(self):
        w=self.workspace()
        with patch.object(w,'_new_form',side_effect=AssertionError('no open')),patch('yadinassi.runtime.Interpreter.__init__',side_effect=AssertionError('no runtime')):
            s=self.check(w)
        p,m=s['form_preview'],s['module_preflight']
        self.assertEqual(p['name'],m['name']);self.assertEqual(p['source_sha256'],m['xml_sha256'])
        self.assertEqual(m['module_sha256'],hashlib.sha256(CODE).hexdigest())
        self.assertEqual(p['status'],'projected');self.assertEqual(m['status'],'compiled')
        for part in (p,m):self.assertFalse(part['runtime_checked']);self.assertFalse(part['native_parity']);self.assertFalse(part['storage_granted'])
        self.assertFalse(w.open_forms)
        self.assertIn('workspace.check',SourceWorkspaceHandler.methods)

    def test_xml_failure_does_not_hide_independent_compilation(self):
        source=files();source['CommonForms/Main/Ext/Form.xml']=b'<Unsupported/>'
        s=self.check(self.workspace(source));self.assertEqual(s['form_preview']['status'],'unavailable');self.assertEqual(s['module_preflight']['status'],'compiled')
        self.assertEqual(s['module_preflight']['handler_names']['status'],'unavailable')

    def test_compile_failure_does_not_hide_projection(self):
        s=self.check(self.workspace(files(b'Procedure Invalid(')))
        self.assertEqual(s['form_preview']['status'],'projected');self.assertEqual(s['module_preflight']['status'],'unavailable')
        self.assertIsNone(s['module_preflight']['handler_names'])

    def test_missing_sources_have_independent_results(self):
        source=files();del source['CommonForms/Main/Ext/Form.xml'];del source['CommonForms/Main/Ext/Form/Module.bsl']
        s=self.check(self.workspace(source))
        for part in ('form_preview','module_preflight'):self.assertEqual(s[part]['status'],'unavailable')
        self.assertIsNone(s['form_preview']['source_sha256']);self.assertIsNone(s['module_preflight']['module_sha256'])

    def test_existing_form_is_not_dispatched_and_repetition_is_read_only(self):
        w=self.workspace();w.exchange(request('open',name='CommonForm.Main'));form,generation=w.form,w.generation
        with patch.object(form,'exchange',side_effect=AssertionError('no dispatch')):
            one=self.check(w);two=self.check(w)
        self.assertEqual(one['form_preview'],two['form_preview']);self.assertEqual(one['module_preflight'],two['module_preflight'])
        self.assertIs(w.form,form);self.assertEqual(w.generation,generation)

    def test_visibility_params_and_closed_authority(self):
        w=self.workspace()
        for params in ({'name':'CommonForm.Main','run':True},{'name':'../Form.xml'},{'name':1}):
            with self.subTest(params=params),self.assertRaises(ValueError):self.check(w,**params)
        w.exchange(request('search',query='absent'))
        with self.assertRaises(ValueError):self.check(w)
        w.close()
        with self.assertRaises(ValueError):self.check(w)
