"""Default source form navigation never infers object/storage capabilities."""
import unittest
from unittest.mock import patch
from test_source_workspace_navigation import mapping
from test_source_metadata import xml
from test_source_workspace import request
from yadinassi.configuration_source import import_source
from yadinassi.configuration_source_runtime import SourceApplication
from yadinassi.ui.source_workspace import SourceWorkspace

class SourceDefaultFormTests(unittest.TestCase):
    def workspace(self, props=''):
        source=mapping();source['Catalogs/Products.xml']=xml('Catalog','Products',properties=props,children='<Form>Card</Form>')
        app=SourceApplication(import_source(source));self.addCleanup(app.close);app.start()
        w=SourceWorkspace(app);w.exchange(request('inspect',name='Catalog.Products'));return w

    def test_declared_default_targets_and_labels_without_execution(self):
        w=self.workspace('<DefaultObjectForm>Catalog.Products.Form.Card</DefaultObjectForm><DefaultListForm>CommonForm.Main</DefaultListForm>')
        with patch.object(w,'_new_form',side_effect=AssertionError('inspect must not execute')):
            d=w.object_detail();self.assertEqual(d['default_forms'],[{'property':'DefaultObjectForm','name':'Catalog.Products.Form.Card'},{'property':'DefaultListForm','name':'CommonForm.Main'}]);self.assertEqual(d['form_labels']['CommonForm.Main'],'Главная форма')
            self.assertFalse(d['storage_granted']);self.assertFalse(w.open_forms)

    def test_no_default_is_not_inferred_from_existing_card(self):
        for props in ['', '<DefaultObjectForm/>']:
            with self.subTest(props=props):
                d=self.workspace(props).object_detail();self.assertEqual(d['default_forms'],[]);self.assertEqual(d['forms'],['Catalog.Products.Form.Card'])

    def test_malformed_unknown_cross_owner_and_oversize_are_unavailable(self):
        bad=['<DefaultObjectForm>x</DefaultObjectForm>','<DefaultObjectForm>Document.Receipt.Form.Card</DefaultObjectForm>','<DefaultObjectForm a="1">Catalog.Products.Form.Card</DefaultObjectForm>','<DefaultObjectForm><Name>Catalog.Products.Form.Card</Name></DefaultObjectForm>','<DefaultObjectForm/>'*2,'<DefaultObjectForm>'+('x'*1025)+'</DefaultObjectForm>']
        for props in bad:
            with self.subTest(props=props[:60]):
                d=self.workspace(props).object_detail();self.assertEqual(d['default_forms'],[]);self.assertTrue(d['default_form_diagnostics']);self.assertLess(len(str(d['default_form_diagnostics'])),512)

    def test_valid_property_survives_independent_malformed_property(self):
        d=self.workspace('<DefaultObjectForm>Missing</DefaultObjectForm><DefaultListForm>CommonForm.Main</DefaultListForm>').object_detail()
        self.assertEqual(d['default_forms'],[{'property':'DefaultListForm','name':'CommonForm.Main'}]);self.assertEqual(len(d['default_form_diagnostics']),1)

    def test_unknown_default_property_cannot_add_an_open_target(self):
        w=self.workspace('<DefaultAnything>CommonForm.Main</DefaultAnything>');w.exchange(request('search',query='not-visible'))
        self.assertEqual(w.object_detail()['default_forms'],[])
        with self.assertRaises(ValueError):w.exchange(request('open',name='CommonForm.Main'))

    def test_explicit_default_open_outside_search_reuses_session_and_no_storage(self):
        w=self.workspace('<DefaultListForm>CommonForm.Main</DefaultListForm>');w.exchange(request('search',query='not-visible'))
        first=w.exchange(request('open',name='CommonForm.Main'))['result']['state'];self.assertTrue(first['active'])
        second=w.exchange(request('open',name='CommonForm.Main'))['result']['state'];self.assertEqual(first['generation'],second['generation']);self.assertEqual(len(w.open_forms),1);self.assertIsNone(w.application.constant_store)

    def test_returned_default_metadata_cannot_mutate_cached_authority(self):
        w=self.workspace('<DefaultListForm>CommonForm.Main</DefaultListForm>');d=w.object_detail();d['default_forms'][0]['name']='Document.Receipt.Form.Card';d['default_form_diagnostics'].append('injected')
        self.assertEqual(w.object_detail()['default_forms'][0]['name'],'CommonForm.Main');self.assertEqual(w.object_detail()['default_form_diagnostics'],[])

    def test_default_open_still_requires_current_selected_object(self):
        w=self.workspace('<DefaultListForm>CommonForm.Main</DefaultListForm>');w.exchange(request('search',query='not-visible'));w.exchange(request('inspect',name='Document.Receipt'))
        with self.assertRaises(ValueError):w.exchange(request('open',name='CommonForm.Main'))
