"""Source form spellings resolve only existing, explicitly declared targets."""
import unittest
import test_source_workspace_default_forms as default_tests
import test_source_workspace as workspace_tests
from test_source_workspace import request
from yadinassi.ui.source_workspace import SourceWorkspace

class SourceFormNameResolutionTests(unittest.TestCase):
    workspace=default_tests.SourceDefaultFormTests.workspace
    def test_russian_and_english_explicit_names_are_canonical(self):
        w=self.workspace()
        for name in ['Catalog.Products.Form.Card','Справочник.Products.Форма.Card','справочник.products.форма.card']:
            self.assertEqual(w._resolve_form_name(name),'Catalog.Products.Form.Card')
        self.assertEqual(w._resolve_form_name('ОбщаяФорма.main'),'CommonForm.Main')

    def test_standard_name_uses_declared_default_not_physical_name_guess(self):
        w=self.workspace('<DefaultObjectForm>Catalog.Products.Form.Card</DefaultObjectForm><DefaultListForm>CommonForm.Main</DefaultListForm>')
        for name in ['Catalog.Products.ObjectForm','Справочник.Products.ФормаОбъекта']:
            self.assertEqual(w._resolve_form_name(name),'Catalog.Products.Form.Card')
        self.assertEqual(w._resolve_form_name('Справочник.Products.ФормаСписка'),'CommonForm.Main')
        with self.assertRaises(ValueError):self.workspace()._resolve_form_name('Справочник.Products.ФормаОбъекта')

    def test_invalid_names_and_defaults_do_not_expand_inventory(self):
        w=self.workspace('<DefaultObjectForm>Document.Receipt.Form.Card</DefaultObjectForm>');before=w.forms
        for name in [None,True,'','Catalog.Products','Catalog..Form.Card','Catalog.Products.Form.Card.Extra','Products.Card','Catalog.Products.Unknown','Справочник.Products.ФормаОбъекта','ОбщаяФорма.Missing','x'*1025]:
            with self.subTest(name=str(name)[:60]),self.assertRaises(ValueError):w._resolve_form_name(name)
        self.assertEqual(w.forms,before);self.assertFalse(w.open_forms)

    def test_browser_rpc_remains_canonical_and_filtered(self):
        w=self.workspace();w.exchange(request('search',query='none'))
        with self.assertRaises(ValueError):w.exchange(request('open',name='ОбщаяФорма.Main'))

class SourceRussianRuntimeNavigationTests(unittest.TestCase):
    workspace=workspace_tests.SourceWorkspaceTests.workspace
    many_forms=workspace_tests.SourceWorkspaceTests.many_forms
    navigation_workspace=workspace_tests.SourceWorkspaceTests.navigation_workspace
    invoke_navigation=workspace_tests.SourceWorkspaceTests.invoke_navigation
    def test_bsl_russian_name_queues_canonical_child(self):
        w=self.navigation_workspace('ОткрытьФорму("ОбщаяФорма.Other1", Новый Структура("Greeting", "ru"));');reply=self.invoke_navigation(w)
        self.assertIsNone(reply['result']['result']['error']);self.assertEqual(w.selected,'CommonForm.Other1')
    def test_alias_intent_discarded_when_handler_fails(self):
        w=self.navigation_workspace('ОткрытьФорму("ОбщаяФорма.Other1", Новый Структура("Greeting", "ru")); Raise "stop";');reply=self.invoke_navigation(w)
        self.assertIsNotNone(reply['result']['result']['error']);self.assertEqual(len(w.open_forms),1);self.assertFalse(w.pending_navigation)

class SourceRussianStartupTests(unittest.TestCase):
    app=workspace_tests.SourceStartupNavigationTests.app
    def test_startup_russian_name_opens_only_after_start(self):
        w=SourceWorkspace.start(self.app('OpenForm("ОбщаяФорма.Main");'));self.assertEqual(w.selected,'CommonForm.Main')

    def test_startup_standard_name_uses_validated_source_default(self):
        from test_source_workspace_navigation import mapping
        from test_source_metadata import xml
        from yadinassi.configuration_source import import_source
        from yadinassi.configuration_source_runtime import SourceApplication
        source=mapping();source['Catalogs/Products.xml']=xml('Catalog','Products',properties='<DefaultListForm>CommonForm.Main</DefaultListForm>',children='<Form>Card</Form>')
        source['Ext/ManagedApplicationModule.bsl']='ОткрытьФорму("Справочник.Products.ФормаСписка");'.encode()
        app=SourceApplication(import_source(source));self.addCleanup(app.close)
        w=SourceWorkspace.start(app);self.assertEqual(w.selected,'CommonForm.Main');self.assertIsNone(app.constant_store)
