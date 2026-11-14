"""Presentation-only Russian choice, never metadata/handler renaming."""
import unittest
import xml.etree.ElementTree as ET
from hashlib import sha256
from test_source_forms import FORM, files, request
import test_source_form_projection as projection_tests
from yadinassi.source_form_projection import project_source_form
from yadinassi.configuration_forms import L

V8='http://v8.1c.ru/8.1/data/core'
def title(*pairs):
    return ('<Title>'+''.join('<v8:item><v8:lang>'+lang+'</v8:lang><v8:content>'+text+'</v8:content></v8:item>' for lang,text in pairs)+'</Title>').encode()

class SourceFormRussianTitleTests(unittest.TestCase):
    controller=projection_tests.SourceFormProjectionTests.controller
    def test_russian_after_english_applies_to_form_attribute_command_and_control(self):
        raw=FORM.replace(b'<Title>Counter</Title>',title(('en','Counter'),('ru','Счётчик')))
        raw=raw.replace(b'<Title>Run</Title>',title(('en','Run'),('ru','Выполнить')))
        raw=raw.replace(b'<Attribute name="Greeting" id="1">',b'<Attribute name="Greeting" id="1">'+title(('en','Greeting'),('ru','Приветствие')))
        c=self.controller(raw);self.assertEqual(c.definition.title,'Счётчик')
        self.assertEqual(c.definition.attributes[0].title,'Приветствие');self.assertEqual(c.definition.commands[0][:2],('Go','Выполнить'))
        self.assertEqual(c.definition.source_sha256,sha256(raw+b'\0'+files()['CommonForms/Main/Ext/Form/Module.bsl']).hexdigest())
        c.exchange(request());r=c.exchange(request('event',event='command',revision=c.client.session.revision,control='GoButton'))
        self.assertIsNone(r['result']['error']);self.assertEqual(dict(c.client.session.snapshot().attributes)['Greeting'],'updated')
        root=ET.fromstring(project_source_form(raw).xml);self.assertEqual(root.find('.//'+L+'Button/'+L+'Title').text,'Выполнить')

    def test_group_caption_is_russian_without_changing_layout_identity(self):
        raw=FORM.replace(b'<ChildItems>',b'<ChildItems><UsualGroup name="Panel" id="30">'+title(('en','Panel'),('ru','Панель'))+b'<ChildItems>',1)
        raw=raw.replace(b'</ChildItems>',b'</ChildItems></UsualGroup></ChildItems>',1)
        c=self.controller(raw);self.assertIsNone(c.exchange(request())['result']['error'])
        projected=ET.fromstring(project_source_form(raw).xml)
        group=projected.find('./'+L+'ChildItems/'+L+'UsualGroup')
        self.assertEqual(group.get('name'),'Panel');self.assertEqual(group.find(L+'Title').text,'Панель')

    def test_russian_order_and_case_are_not_semantic(self):
        for pairs in ((('ru','Русский'),('en','English')),(('en','English'),('RU','Русский'))):
            with self.subTest(pairs=pairs):self.assertEqual(self.controller(FORM.replace(b'<Title>Counter</Title>',title(*pairs))).definition.title,'Русский')

    def test_fallback_empty_russian_and_plain_title(self):
        raw=FORM.replace(b'<Title>Counter</Title>',title(('ru',' '),('en','English')))
        p=project_source_form(raw);self.assertEqual(ET.fromstring(p.xml).find(L+'Title').text,'English');self.assertTrue(any('fallback en' in d['reason'] for d in p.diagnostics))
        self.assertEqual(self.controller(FORM).definition.title,'Counter')

    def test_invalid_structured_title_is_not_arbitrary_descendant_text(self):
        cases=[title(('ru','Один'),('RU','Два')),b'<Title><v8:other><v8:content>Bad</v8:content></v8:other></Title>',b'<Title><v8:item><v8:lang>ru</v8:lang><v8:content><b>Nested</b></v8:content></v8:item></Title>',title(*[(str(i),'x') for i in range(65)])]
        for value in cases:
            with self.subTest(value=value[:50]):
                p=project_source_form(FORM.replace(b'<Title>Counter</Title>',value));self.assertIsNone(ET.fromstring(p.xml).find(L+'Title'));self.assertTrue(any('Title unavailable' in d['reason'] for d in p.diagnostics))

    def test_long_and_markup_text_remain_bounded_literal_text(self):
        raw=FORM.replace(b'<Title>Counter</Title>',title(('ru','Я'*1100)))
        p=project_source_form(raw);self.assertEqual(len(ET.fromstring(p.xml).find(L+'Title').text),1024);self.assertTrue(any('truncated' in d['reason'] for d in p.diagnostics))
        raw=FORM.replace(b'<Title>Counter</Title>',title(('ru','&lt;script&gt;literal&lt;/script&gt;')))
        self.assertEqual(self.controller(raw).definition.title,'<script>literal</script>')
