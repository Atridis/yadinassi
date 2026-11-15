"""Static source captions must not manufacture data or clickable actions."""
import unittest
from hashlib import sha256
from test_source_forms import FORM, request
import test_source_form_projection as projection_tests
from yadinassi.source_form_projection import project_source_form
from yadinassi.configuration_forms import L
import xml.etree.ElementTree as ET

class StaticLabelTests(unittest.TestCase):
    controller=projection_tests.SourceFormProjectionTests.controller

    def raw(self, extra=b'', title=b'<Title>Help text</Title>'):
        return FORM.replace(b'<ChildItems>',b'<ChildItems><LabelDecoration name="Help" id="90">'+title+extra+b'</LabelDecoration>')

    def test_caption_retained_without_attribute(self):
        c=self.controller(self.raw());self.assertIsNone(c.exchange(request())['result']['error'])
        self.assertIn('help',c.server.session.form.items._values)
        self.assertEqual(len(c.server.session.form._attributes),1)
        p=project_source_form(self.raw());node=ET.fromstring(p.xml).find('.//'+L+'UsualGroup')
        self.assertEqual(node.findtext(L+'Title'),'Help text')
        self.assertEqual(node.findtext(L+'ShowTitle'),'true')
        self.assertTrue(any('Static label decoration' in d['reason'] for d in p.diagnostics))

    def test_russian_localized_caption_and_original_hash(self):
        raw=self.raw(title='<Title><v8:item><v8:lang>ru</v8:lang><v8:content>Подсказка</v8:content></v8:item></Title>'.encode())
        p=project_source_form(raw)
        self.assertEqual(ET.fromstring(p.xml).find('.//'+L+'UsualGroup').findtext(L+'Title'),'Подсказка')
        self.assertEqual(p.source_sha256,sha256(raw).hexdigest())

    def test_actions_links_children_and_binding_do_not_become_capabilities(self):
        extra=b'<Hyperlink>true</Hyperlink><DataPath>Greeting</DataPath><CommandName>Go</CommandName><Events><Event name="Click">Go</Event></Events><ChildItems><Button name="HiddenAction" id="91"><CommandName>Go</CommandName></Button></ChildItems>'
        c=self.controller(self.raw(extra));c.exchange(request())
        self.assertNotIn('hiddenaction',c.server.session.form.items._values)
        result=c.exchange(request('event',event='command',revision=c.client.session.revision,control='Help'))
        self.assertIsNotNone(result['result']['error'])
        self.assertEqual(dict(c.client.session.snapshot().attributes)['Greeting'],'Demo')
        reasons=' '.join(d['reason'] for d in c.diagnostics)
        for name in ('Hyperlink','DataPath','CommandName','Events','ChildItems'):self.assertIn(name,reasons)

    def test_existing_command_unaffected(self):
        c=self.controller(self.raw());c.exchange(request())
        result=c.exchange(request('event',event='command',revision=c.client.session.revision,control='GoButton'))
        self.assertIsNone(result['result']['error'])
        self.assertEqual(dict(c.client.session.snapshot().attributes)['Greeting'],'updated')

    def test_flags_preserved_in_projection(self):
        p=project_source_form(self.raw(b'<Visible>false</Visible><Enabled>false</Enabled><ReadOnly>true</ReadOnly>'))
        n=ET.fromstring(p.xml).find('.//'+L+'UsualGroup')
        for key,value in [('Visible','false'),('Enabled','false'),('ReadOnly','true')]:self.assertEqual(n.findtext(L+key),value)

    def test_strict_loader_and_duplicate_identity_stay_strict(self):
        with self.assertRaises(ValueError):self.controller(self.raw(),False)
        with self.assertRaises(ValueError):self.controller(self.raw().replace(b'id="90"',b'id="1"'))
        with self.assertRaises(ValueError):self.controller(self.raw(b'<Title>duplicate</Title>'))
