"""Object-card diagnostics use the same admitted targets, without activation."""
import unittest
from unittest.mock import patch
import test_source_workspace_default_forms as default_tests
from test_source_workspace import request

class SourceObjectFormCheckTests(unittest.TestCase):
    workspace=default_tests.SourceDefaultFormTests.workspace

    def test_default_outside_search_is_inspected_without_opening(self):
        w=self.workspace('<DefaultListForm>CommonForm.Main</DefaultListForm>')
        w.exchange(request('search',query='not-visible'))
        with patch.object(w,'_new_form',side_effect=AssertionError('no form')),patch('yadinassi.runtime.Interpreter.__init__',side_effect=AssertionError('no interpreter')):
            p=w.exchange(request('preview',name='CommonForm.Main'))['result']['state']['form_preview']
            m=w.exchange(request('preflight',name='CommonForm.Main'))['result']['state']['module_preflight']
        self.assertEqual(p['status'],'projected');self.assertEqual(m['status'],'compiled')
        self.assertFalse(w.open_forms);self.assertIsNone(w.application.constant_store)
        self.assertFalse(m['runtime_checked']);self.assertFalse(m['bindings_checked'])

    def test_child_card_missing_source_is_diagnostic_not_a_generated_form(self):
        w=self.workspace();w.exchange(request('search',query='not-visible'))
        p=w.exchange(request('preview',name='Catalog.Products.Form.Card'))['result']['state']['form_preview']
        self.assertEqual(p['status'],'unavailable');self.assertFalse(w.open_forms)

    def test_stale_object_authority_and_unknown_forms_are_rejected(self):
        w=self.workspace('<DefaultListForm>CommonForm.Main</DefaultListForm>');w.exchange(request('search',query='not-visible'))
        w.exchange(request('inspect',name='Document.Receipt'))
        for method in ('preview','preflight'):
            for name in ('CommonForm.Main','Catalog.Products.Form.Card','CommonForm.Unknown'):
                with self.subTest(method=method,name=name),self.assertRaises(ValueError):w.exchange(request(method,name=name))

    def test_checks_preserve_existing_form_generation_and_closed_gates(self):
        w=self.workspace('<DefaultListForm>CommonForm.Main</DefaultListForm>');w.exchange(request('open',name='CommonForm.Main'))
        form,generation=w.form,w.generation
        with patch.object(form,'exchange',side_effect=AssertionError('no dispatch')):
            for method in ('preview','preflight'):w.exchange(request(method,name='CommonForm.Main'))
        self.assertIs(w.form,form);self.assertEqual(w.generation,generation)
        w.close()
        for method in ('preview','preflight'):
            with self.assertRaises(ValueError):w.exchange(request(method,name='CommonForm.Main'))
