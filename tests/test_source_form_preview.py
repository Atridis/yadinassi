"""Form preview describes projection without compiling or activating BSL."""
import hashlib
import unittest
from unittest.mock import patch
import test_source_workspace as workspace_tests
from test_source_workspace import request
from test_source_forms import files,FORM

class SourceFormPreviewTests(unittest.TestCase):
    workspace=workspace_tests.SourceWorkspaceTests.workspace
    def preview(self,w,name='CommonForm.Main'):
        return w.exchange(request('preview',name=name))['result']['state']['form_preview']

    def test_preview_is_hash_bound_without_execution_or_form_creation(self):
        source=files();source['CommonForms/Main/Ext/Form/Module.bsl']=b'not even valid BSL !'
        w=self.workspace(source);before=dict(w.application.files)
        with patch('yadinassi.ui.source_workspace.SourceFormController',side_effect=AssertionError('must not instantiate')):
            p=self.preview(w)
        self.assertEqual(p['status'],'projected');self.assertEqual(p['source_sha256'],hashlib.sha256(FORM).hexdigest());self.assertFalse(p['module_checked']);self.assertFalse(p['runtime_checked']);self.assertFalse(p['storage_granted']);self.assertFalse(p['native_parity']);self.assertFalse(w.open_forms);self.assertEqual(w.application.files,before)
        self.assertGreater(p['counts']['controls'],0)

    def test_unsupported_control_is_visible_diagnostic_not_compatibility_success(self):
        source=files();source['CommonForms/Main/Ext/Form.xml']=FORM.replace(b'</ChildItems>',b'<PictureField name="Logo" id="999"/></ChildItems>')
        p=self.preview(self.workspace(source));self.assertEqual(p['status'],'projected');self.assertTrue(any('PictureField' in x['reason'] for x in p['diagnostics']));self.assertFalse(p['runtime_checked'])

    def test_bad_missing_and_unmanaged_definitions_stay_unavailable(self):
        cases=[]
        source=files();source['CommonForms/Main/Ext/Form.xml']=b'<Unsupported/>';cases.append(source)
        source=files();del source['CommonForms/Main/Ext/Form.xml'];cases.append(source)
        source=files();source['CommonForms/Main.xml']=source['CommonForms/Main.xml'].replace(b'Managed',b'Ordinary');cases.append(source)
        for source in cases:
            with self.subTest(source=source.get('CommonForms/Main/Ext/Form.xml',b'')[:10]):
                w=self.workspace(source);p=self.preview(w);self.assertEqual(p['status'],'unavailable');self.assertTrue(p['diagnostics']);self.assertFalse(w.open_forms)

    def test_preview_repeated_and_snapshot_do_not_dispatch_existing_form(self):
        w=self.workspace();w.exchange(request('open',name='CommonForm.Main'));form=w.form;generation=w.generation
        with patch.object(form,'exchange',side_effect=AssertionError('preview must not dispatch')):
            first=self.preview(w);second=self.preview(w);w.exchange(request())
        self.assertEqual(first,second);self.assertIs(w.form,form);self.assertEqual(w.generation,generation)

    def test_hidden_unknown_alias_and_nonform_targets_are_rejected(self):
        w=self.workspace();w.exchange(request('search',query='nothing'))
        for name in ['CommonForm.Main','CommonForm.Missing','ОбщаяФорма.Main','Configuration.Demo','../Form.xml']:
            with self.subTest(name=name),self.assertRaises(ValueError):self.preview(w,name)

    def test_snapshot_copy_cannot_mutate_preview(self):
        w=self.workspace();p=self.preview(w);p['diagnostics'].append({'path':'injected','reason':'bad'});p['counts']['attributes']=999
        fresh=w.snapshot()['state']['form_preview'];self.assertNotEqual(fresh['counts']['attributes'],999);self.assertFalse(any(x['path']=='injected' for x in fresh['diagnostics']))

    def test_closed_workspace_cannot_preview(self):
        w=self.workspace();w.close()
        with self.assertRaises(ValueError):self.preview(w)

    def test_large_projection_diagnostics_stay_bounded_with_explicit_omission(self):
        import json
        from yadinassi.ui.protocol import encode_line,MAX_LINE_BYTES
        source=files();extra=''.join('<PictureField name="'+('Я'*120)+str(i)+'" id="'+str(1000+i)+'"/>' for i in range(60))
        source['CommonForms/Main/Ext/Form.xml']=FORM.replace(b'<ChildItems>',b'<ChildItems>'+extra.encode())
        w=self.workspace(source);p=self.preview(w)
        self.assertGreater(p['omitted_diagnostics'],0);self.assertLessEqual(len(json.dumps(p['diagnostics'],ensure_ascii=False).encode()),6144)
        self.assertLess(len(encode_line(w.exchange(request()))),MAX_LINE_BYTES)
