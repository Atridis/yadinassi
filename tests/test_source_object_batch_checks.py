import unittest
from unittest.mock import patch
import test_source_workspace_default_forms as default_tests
from test_source_workspace import request

class SourceObjectBatchTests(unittest.TestCase):
    workspace=default_tests.SourceDefaultFormTests.workspace
    def check(self,w,name='Catalog.Products'):
        return w.exchange(request('checkObject',name=name))['result']['state']['object_checks']

    def test_declared_and_default_forms_checked_without_activation(self):
        w=self.workspace('<DefaultListForm>CommonForm.Main</DefaultListForm>')
        with patch.object(w,'_new_form',side_effect=AssertionError('no open')),patch('yadinassi.runtime.Interpreter.__init__',side_effect=AssertionError('no runtime')):
            r=self.check(w)
        self.assertEqual([x['name'] for x in r['forms']],['Catalog.Products.Form.Card','CommonForm.Main'])
        self.assertEqual(r['forms'][0]['xml_status'],'unavailable');self.assertEqual(r['forms'][1]['module_status'],'compiled')
        self.assertFalse(r['runtime_checked']);self.assertFalse(r['storage_granted']);self.assertFalse(w.open_forms)

    def test_duplicate_defaults_are_checked_once(self):
        w=self.workspace('<DefaultObjectForm>Catalog.Products.Form.Card</DefaultObjectForm>')
        self.assertEqual(len(self.check(w)['forms']),1)

    def test_individual_panels_and_existing_form_are_preserved(self):
        w=self.workspace('<DefaultListForm>CommonForm.Main</DefaultListForm>');w.exchange(request('check',name='CommonForm.Main'));before=w.snapshot()['state']
        w.exchange(request('open',name='CommonForm.Main'));form,generation=w.form,w.generation
        with patch.object(form,'exchange',side_effect=AssertionError('no dispatch')):self.check(w)
        after=w.snapshot()['state'];self.assertEqual(before['form_preview'],after['form_preview']);self.assertEqual(before['module_preflight'],after['module_preflight']);self.assertIs(w.form,form);self.assertEqual(w.generation,generation)

    def test_authority_requires_current_visible_object_and_open_workspace(self):
        w=self.workspace();w.exchange(request('inspect',name='Document.Receipt'))
        with self.assertRaises(ValueError):self.check(w)
        w.exchange(request('objects',query='absent',family=''))
        with self.assertRaises(ValueError):self.check(w,'Document.Receipt')
        w.close()
        with self.assertRaises(ValueError):self.check(w)

    def test_four_target_cap_and_omissions_are_explicit(self):
        w=self.workspace();detail=w.object_detail();detail['forms']=['CommonForm.Main']+['Catalog.Products.Form.Card']*3+['CommonForm.Main']
        with patch.object(w,'object_detail',return_value=detail):self.assertEqual(len(self.check(w)['forms']),2)
        detail['forms']=['CommonForm.F'+str(i) for i in range(7)]
        def preview(name):w.form_preview={'source_sha256':None,'status':'unavailable','diagnostics':[]}
        def module(name):w.module_preflight={'module_sha256':None,'status':'unavailable','error':'missing','handler_names':None}
        with patch.object(w,'object_detail',return_value=detail),patch.object(w,'_preview_form',side_effect=preview) as p,patch.object(w,'_preflight_module',side_effect=module):
            r=self.check(w)
        self.assertEqual(p.call_count,4);self.assertEqual(len(r['forms']),4);self.assertEqual(r['uninspected_targets'],3)

    def test_snapshot_cannot_mutate_report(self):
        w=self.workspace();r=self.check(w);r['forms'][0]['name']='injected'
        self.assertNotEqual(w.snapshot()['state']['object_checks']['forms'][0]['name'],'injected')

    def test_unexpected_failure_restores_previous_panels_and_report(self):
        w=self.workspace();previous=self.check(w);w.exchange(request('check',name='CommonForm.Main'))
        before=w.snapshot()['state']
        with patch.object(w,'_preflight_module',side_effect=RuntimeError('interrupted')):
            with self.assertRaises(RuntimeError):self.check(w)
        after=w.snapshot()['state'];self.assertEqual(after['form_preview'],before['form_preview']);self.assertEqual(after['module_preflight'],before['module_preflight']);self.assertEqual(after['object_checks'],previous)

    def test_unavailable_handler_audit_is_not_lost_in_batch_summary(self):
        from test_source_forms import files,FORM
        import test_source_workspace as workspace_tests
        source=files();source['CommonForms/Main/Ext/Form.xml']=FORM.replace(b'</Events></Form>','<Event name="ПриСозданииНаСервере">Created</Event></Events></Form>'.encode())
        w=workspace_tests.SourceWorkspaceTests.workspace(self,source);w.exchange(request('inspect',name='CommonForm.Main'))
        row=self.check(w,'CommonForm.Main')['forms'][0]
        self.assertEqual(row['xml_status'],'projected');self.assertEqual(row['module_status'],'compiled')
        self.assertEqual(row['audit_status'],'unavailable');self.assertIn('duplicate',row['audit_error'])
