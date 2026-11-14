"""Source navigation is localized metadata, not storage or implicit permissions."""
import json
import unittest
from unittest.mock import patch
from test_source_metadata import xml
from test_source_forms import files, FORM
from test_source_workspace import request
from yadinassi.configuration_source import import_source
from yadinassi.configuration_source_runtime import SourceApplication
from yadinassi.ui.source_workspace import SourceWorkspace

V8='http://v8.1c.ru/8.1/data/core'
XR='http://v8.1c.ru/8.3/xcf/readable'
XSI='http://www.w3.org/2001/XMLSchema-instance'


def synonym(label,lang='ru'):
    return '<Synonym xmlns:v8="'+V8+'"><v8:item><v8:lang>'+lang+'</v8:lang><v8:content>'+label+'</v8:content></v8:item></Synonym>'


def content(*names):
    return '<Content xmlns:xr="'+XR+'" xmlns:xsi="'+XSI+'">'+''.join('<xr:Item xsi:type="xr:MDObjectRef">'+name+'</xr:Item>' for name in names)+'</Content>'


def mapping():
    source=files()
    source['Configuration.xml']=xml('Configuration','Demo',children='<CommonForm>Main</CommonForm><CommonModule>Helpers</CommonModule><Catalog>Products</Catalog><Document>Receipt</Document><Subsystem>Reference</Subsystem><Subsystem>Other</Subsystem>')
    source['CommonForms/Main.xml']=xml('CommonForm','Main',properties='<FormType>Managed</FormType>'+synonym('Главная форма'))
    source['Catalogs/Products.xml']=xml('Catalog','Products',properties=synonym('Номенклатура'),children='<Form>Card</Form>')
    source['Catalogs/Products/Forms/Card.xml']=xml('Form','Card',properties=synonym('Карточка'))
    source['Catalogs/Products/Forms/Card/Ext/Form.xml']=FORM
    source['Documents/Receipt.xml']=xml('Document','Receipt',properties=synonym('Поступление'),children='<Form>Card</Form>')
    # Distinct XML identity even though both forms share the same caption/name.
    source['Documents/Receipt/Forms/Card.xml']=xml('Form','ReceiptCard',properties=synonym('Карточка')).replace(b'<Name>ReceiptCard</Name>',b'<Name>Card</Name>')
    source['Documents/Receipt/Forms/Card/Ext/Form.xml']=FORM
    source['Subsystems/Reference.xml']=xml('Subsystem','Reference',properties=synonym('Нормативная информация')+content('Catalog.Products'),children='<Subsystem>Child</Subsystem>')
    source['Subsystems/Reference/Subsystems/Child.xml']=xml('Subsystem','Child',properties=synonym('Вложенная')+content('Document.Receipt'))
    source['Subsystems/Other.xml']=xml('Subsystem','Other',properties=synonym('Другая')+content('Subsystem.Reference.Subsystem.Child'))
    return source


class SourceWorkspaceNavigationTests(unittest.TestCase):
    def workspace(self,source=None):
        app=SourceApplication(import_source(mapping() if source is None else source));self.addCleanup(app.close)
        app.start();return SourceWorkspace(app)

    def test_russian_captions_preserve_canonical_keys_and_search(self):
        w=self.workspace();state=w.snapshot()['state']
        self.assertEqual(state['object_labels']['Catalog.Products'],'Номенклатура')
        self.assertEqual(state['form_labels']['CommonForm.Main'],'Главная форма')
        result=w.exchange(request('objects',query='Номенклатура',family='',subsystem=''))['result']['state']
        self.assertEqual(result['objects'],['Catalog.Products'])
        detail=w.exchange(request('inspect',name='Catalog.Products'))['result']['state']['object_detail']
        self.assertEqual(detail['title'],'Номенклатура');self.assertFalse(detail['storage_granted'])
        self.assertEqual(detail['forms'],['Catalog.Products.Form.Card'])
        self.assertEqual(detail['form_labels'],{'Catalog.Products.Form.Card':'Карточка'})
        with self.assertRaises(ValueError):w.exchange(request('inspect',name='Номенклатура'))
        self.assertEqual(w.exchange(request('search',query='Главная'))['result']['state']['forms'],['CommonForm.Main'])

    def test_duplicate_captions_do_not_merge_names_or_grant_label_rpc(self):
        w=self.workspace();labels=w.snapshot()['state']['form_labels']
        self.assertEqual(labels['Catalog.Products.Form.Card'],labels['Document.Receipt.Form.Card'])
        with self.assertRaises(ValueError):w.exchange(request('open',name='Карточка'))
        self.assertFalse(w.open_forms)

    def test_direct_membership_never_inherits_parent_or_child_contents(self):
        w=self.workspace()
        state=w.exchange(request('objects',query='',family='',subsystem='Subsystem.Reference'))['result']['state']
        self.assertEqual(state['objects'],['Catalog.Products'])
        state=w.exchange(request('objects',query='',family='',subsystem='Subsystem.Reference.Subsystem.Child'))['result']['state']
        self.assertEqual(state['objects'],['Document.Receipt'])
        state=w.exchange(request('objects',query='',family='',subsystem='Subsystem.Other'))['result']['state']
        self.assertEqual(state['objects'],['Subsystem.Reference.Subsystem.Child'])
        self.assertTrue(state['memory_only']);self.assertFalse(state['native_parity'])
        self.assertIsNone(w.application.constant_store)

    def test_family_query_and_subsystem_intersect_with_no_synthetic_document_group(self):
        w=self.workspace()
        state=w.exchange(request('objects',query='',family='Document',subsystem='Subsystem.Reference'))['result']['state']
        self.assertEqual(state['objects'],[])
        state=w.exchange(request('objects',query='',family='Document'))['result']['state']
        self.assertEqual(state['object_subsystem'],'');self.assertIn('Document.Receipt',state['objects'])
        with self.assertRaises(ValueError):w.exchange(request('objects',query='',family='',subsystem='Все документы'))

    def test_unknown_or_duplicate_reference_fails_whole_group_closed(self):
        for members in [('Catalog.Products','Document.Missing'),('Catalog.Products','Catalog.Products')]:
            with self.subTest(members=members):
                source=mapping();source['Subsystems/Reference.xml']=xml('Subsystem','Reference',properties=content(*members),children='<Subsystem>Child</Subsystem>')
                w=self.workspace(source);state=w.exchange(request('objects',query='',family='',subsystem='Subsystem.Reference'))['result']['state']
                self.assertEqual(state['objects'],[]);self.assertTrue(state['navigation_diagnostics'])
                self.assertIn('Catalog.Products',w.objects)

    def test_invalid_qname_namespace_and_structured_reference_fail_closed(self):
        for bad in [content('Catalog.Products').replace('xsi:type="xr:MDObjectRef"','xmlns:fake="urn:fake" xsi:type="fake:MDObjectRef"'),
                    content('Catalog.Products').replace('Catalog.Products','<Nested/>'),
                    '<Content/><Content/>']:
            with self.subTest(bad=bad):
                source=mapping();source['Subsystems/Reference.xml']=xml('Subsystem','Reference',properties=bad,children='<Subsystem>Child</Subsystem>')
                w=self.workspace(source)
                self.assertFalse(w.subsystem_members['Subsystem.Reference']);self.assertTrue(w.navigation_diagnostics)

    def test_non_russian_missing_oversize_or_ambiguous_synonyms_fall_back_to_names(self):
        for props in ['',synonym('English','en'),synonym('Я'*257),synonym('Первый')+synonym('Второй')]:
            source=mapping();source['Catalogs/Products.xml']=xml('Catalog','Products',properties=props,children='<Form>Card</Form>')
            w=self.workspace(source);self.assertEqual(w.snapshot()['state']['object_labels']['Catalog.Products'],'Products')

    def test_open_form_caption_survives_hidden_search_and_filter_does_not_close_it(self):
        w=self.workspace();w.exchange(request('open',name='CommonForm.Main'))
        state=w.exchange(request('search',query='не найдено'))['result']['state']
        self.assertEqual(state['forms'],[]);self.assertEqual(state['form_labels']['CommonForm.Main'],'Главная форма')
        w.exchange(request('objects',query='',family='',subsystem='Subsystem.Reference'))
        self.assertEqual(len(w.open_forms),1);self.assertEqual(w.selected,'CommonForm.Main')

    def test_navigation_labels_do_not_execute_or_mutate_source(self):
        w=self.workspace();before=dict(w.application.files)
        with patch.object(w,'_new_form',side_effect=AssertionError('navigation is not execution')):
            w.exchange(request('objects',query='',family='',subsystem='Subsystem.Reference'))
            w.exchange(request('inspect',name='Catalog.Products'));w.snapshot()
        self.assertEqual(w.application.files,before);self.assertFalse(w.open_forms)

    def test_member_bound_and_label_byte_budgets(self):
        source=mapping();source['Subsystems/Reference.xml']=xml('Subsystem','Reference',properties=content(*(['Catalog.Products']*2049)),children='<Subsystem>Child</Subsystem>')
        w=self.workspace(source);self.assertFalse(w.subsystem_members['Subsystem.Reference'])
        self.assertTrue(any('bound' in d for d in w.navigation_diagnostics))
        names=['Object.'+str(i) for i in range(256)]
        w.navigation_labels.update({name:'Ж'*256 for name in names})
        labels=w._labels(names)
        self.assertLessEqual(len(json.dumps(labels,ensure_ascii=False).encode()),8192)
        self.assertLess(len(labels),len(names));self.assertTrue(labels)

    def test_real_demo_import_only_has_actual_catalog_membership_not_documents(self):
        from pathlib import Path
        from types import SimpleNamespace
        from yadinassi.configuration_source_metadata import SourceMetadataRoot
        root=Path(__file__).resolve().parents[1]/'examples/demo'
        source=import_source({path.relative_to(root).as_posix():path.read_bytes()
                              for path in root.rglob('*') if path.is_file()})
        # Presentation-only smoke: no application startup, modules or form events.
        app=SimpleNamespace(require_open=lambda:None,constant_store=None,source=source,
                            metadata=SourceMetadataRoot(source))
        w=SourceWorkspace(app)
        name='Subsystem.НормативнаяИнформация'
        state=w.exchange(request('objects',query='',family='',subsystem=name))['result']['state']
        self.assertEqual(set(state['objects']),{'Catalog.ВидыНоменклатуры','Catalog.Склады','Catalog.Номенклатура'})
        self.assertEqual(state['subsystem_labels'][name],'Нормативная информация')
        self.assertNotIn('Document.Receipt',state['objects']);self.assertNotIn('Document.Issue',state['objects'])
        self.assertFalse(state['navigation_diagnostics'])

    def test_diagnostics_and_subsystem_selection_are_stably_bounded(self):
        source=mapping()
        for i in range(300):
            name='S'+str(i)
            source['Subsystems/'+name+'.xml']=xml('Subsystem',name,properties=content('Catalog.Missing'))
        w=self.workspace(source);before=list(w.subsystems)
        self.assertGreater(w.omitted_subsystems,0)
        self.assertLessEqual(len(w.navigation_diagnostics),16)
        self.assertGreater(w.omitted_navigation_diagnostics,0)
        selected=before[-1]
        state=w.exchange(request('objects',query='nothing',family='',subsystem=selected))['result']['state']
        self.assertEqual(state['subsystems'],before);self.assertEqual(state['object_subsystem'],selected)
        missing=next(name for name in w.objects if name.startswith('Subsystem.S') and name not in before)
        with self.assertRaises(ValueError):w.exchange(request('objects',query='',family='',subsystem=missing))

    def test_large_localized_inventory_snapshot_stays_inside_wire_budget(self):
        from types import SimpleNamespace
        from yadinassi.configuration_source_metadata import SourceMetadataRoot
        from yadinassi.ui.protocol import encode_line, MAX_LINE_BYTES
        source={'Configuration.xml':xml('Configuration','Demo')}
        for i in range(600):
            name='Ф'*120+str(i)
            source['CommonForms/'+name+'.xml']=xml('CommonForm',name,properties=synonym('Я'*256))
        admitted=import_source(source)
        app=SimpleNamespace(require_open=lambda:None,constant_store=None,source=admitted,
                            metadata=SourceMetadataRoot(admitted))
        w=SourceWorkspace(app);state=w.snapshot()['state']
        self.assertGreater(state['omitted_forms'],0);self.assertGreater(state['omitted_objects'],0)
        self.assertLess(len(encode_line(w.exchange(request()))),MAX_LINE_BYTES)
