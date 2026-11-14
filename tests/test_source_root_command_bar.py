"""Root exported toolbar preserves explicit commands, not auto CRUD grants."""
import unittest
import xml.etree.ElementTree as ET
from hashlib import sha256
from pathlib import Path
import test_source_form_projection as projection_tests
from test_source_forms import FORM, files, request
from yadinassi.source_form_projection import project_source_form
from yadinassi.configuration_forms import L


class SourceRootCommandBarTests(unittest.TestCase):
    controller=projection_tests.SourceFormProjectionTests.controller
    def source(self,identity='-1',props=b''):
        root=ET.fromstring(FORM);root.set('xmlns:xs','http://www.w3.org/2001/XMLSchema')
        items=root.find(L+'ChildItems');button=items.find(L+'Button');items.remove(button)
        button.find(L+'CommandName').text='Form.Command.Go'
        bar=ET.SubElement(root,L+'AutoCommandBar',{'name':'RootActions','id':identity})
        if props:
            for n in ET.fromstring(b'<Root xmlns="http://v8.1c.ru/8.3/xcf/logform">'+props+b'</Root>'):bar.append(n)
        ET.SubElement(bar,L+'ChildItems').append(button)
        return ET.tostring(root)

    def test_exported_root_toolbar_retains_explicit_command_and_original_hash(self):
        raw=self.source();c=self.controller(raw);c.exchange(request())
        for _ in range(2):
            reply=c.exchange(request('event',event='command',revision=c.client.session.revision,control='GoButton'))
            self.assertIsNone(reply['result']['error'])
            self.assertEqual(dict(c.client.session.snapshot().attributes)['Greeting'],'updated')
        self.assertEqual(c.definition.source_sha256,sha256(raw+b'\0'+files()['CommonForms/Main/Ext/Form/Module.bsl']).hexdigest())
        projected=ET.fromstring(project_source_form(raw).xml)
        group=projected.find('.//'+L+'UsualGroup');self.assertEqual(group.get('name'),'RootActions')
        self.assertEqual(group.get('id'),'3')
        self.assertTrue(any('presentation ID 3' in d['reason'] for d in c.diagnostics))

    def test_positive_toolbar_id_is_preserved(self):
        p=project_source_form(self.source('44'))
        self.assertEqual(ET.fromstring(p.xml).find('.//'+L+'UsualGroup').get('id'),'44')

    def test_invalid_ids_and_duplicate_name_or_id_are_not_remapped(self):
        for identity in ('-2','0','1','2','x','1000001'):
            with self.subTest(identity=identity),self.assertRaises(ValueError):project_source_form(self.source(identity))
        with self.assertRaises(ValueError):project_source_form(self.source().replace(b'RootActions',b'GoButton'))

    def test_disabled_and_invisible_root_toolbar_block_child_dispatch(self):
        for props in (b'<Enabled>false</Enabled>',b'<Visible>false</Visible>',b'<ReadOnly>true</ReadOnly>'):
            with self.subTest(props=props):
                c=self.controller(self.source(props=props));c.exchange(request());before=dict(c.client.session.snapshot().attributes)
                reply=c.exchange(request('event',event='command',revision=c.client.session.revision,control='GoButton'))
                self.assertIsNotNone(reply['result']['error']);self.assertEqual(dict(c.client.session.snapshot().attributes),before)

    def test_no_auto_standard_command_is_created(self):
        raw=self.source(props=b'<Autofill>true</Autofill>').replace(b'Form.Command.Go',b'Form.StandardCommand.Write')
        c=self.controller(raw);c.exchange(request())
        self.assertNotIn('gobutton',c.server.session.form.items._values)
        self.assertTrue(any('Autofill' in d['reason'] for d in c.diagnostics))

    def test_duplicate_root_or_child_inventory_and_malformed_envelope_rejected(self):
        raw=self.source()
        cases=(raw.replace(b'</ns0:Form>',b'<ns0:AutoCommandBar name="Second" id="80"/></ns0:Form>'),raw.replace(b'<ns0:AutoCommandBar ',b'<ns0:AutoCommandBar extra="bad" '),raw.replace(b'<ns0:ChildItems><ns0:Button',b'<ns0:ChildItems/><ns0:ChildItems><ns0:Button'))
        for candidate in cases:
            self.assertNotEqual(candidate,raw)
            with self.assertRaises(ValueError):project_source_form(candidate)

    def test_real_exported_demo_root_toolbar_projects_without_execution(self):
        raw=(Path(__file__).resolve().parents[1]/'examples/demo/Catalogs/Номенклатура/Forms/ФормаСписка/Ext/Form.xml').read_bytes()
        original=ET.fromstring(raw).find(L+'AutoCommandBar')
        self.assertEqual(original.get('id'),'-1')
        p=project_source_form(raw);root=ET.fromstring(p.xml)
        groups=[g for g in root.iter(L+'UsualGroup') if g.get('name')==original.get('name')]
        self.assertEqual(len(groups),1);self.assertEqual(p.source_sha256,sha256(raw).hexdigest())

    def test_strict_loader_unchanged(self):
        with self.assertRaises(ValueError):self.controller(self.source(),False)
