"""Real exported Form.Command paths bind only to declared local commands."""
import unittest
from pathlib import Path
from hashlib import sha256
import xml.etree.ElementTree as ET
import test_source_form_projection as projection_tests
from test_source_forms import FORM, files, request
from yadinassi.source_form_projection import project_source_form
from yadinassi.configuration_forms import L

class SourceQualifiedFormCommandTests(unittest.TestCase):
    controller=projection_tests.SourceFormProjectionTests.controller
    def qualified(self,value='Form.Command.Go'):
        return FORM.replace(b'<CommandName>Go</CommandName>',('<CommandName>'+value+'</CommandName>').encode())

    def test_qualified_exported_button_executes_declared_handler_repeatedly(self):
        raw=self.qualified();c=self.controller(raw);c.exchange(request())
        for _ in range(2):
            reply=c.exchange(request('event',event='command',revision=c.client.session.revision,control='GoButton'))
            self.assertIsNone(reply['result']['error']);self.assertEqual(dict(c.client.session.snapshot().attributes)['Greeting'],'updated')
        self.assertEqual(c.definition.source_sha256,sha256(raw+b'\0'+files()['CommonForms/Main/Ext/Form/Module.bsl']).hexdigest())
        self.assertEqual(c.definition.commands[0][0],'Go')

    def test_casefold_path_returns_original_canonical_command_name(self):
        p=project_source_form(self.qualified('fOrM.cOmMaNd.gO'))
        self.assertEqual(ET.fromstring(p.xml).find('.//'+L+'CommandName').text,'Go')
        self.assertTrue(any('Bound declared Form.Command: Go'==d['reason'] for d in p.diagnostics))

    def test_unknown_standard_foreign_and_partial_paths_do_not_create_buttons(self):
        for value in ('Form.Command.Missing','Form.StandardCommand.Go','Global.Command.Go','Other.Form.Command.Go','Form.Command.Go.Extra','Form.Command.','Form..Go'):
            with self.subTest(value=value):
                c=self.controller(self.qualified(value));c.exchange(request());self.assertNotIn('gobutton',c.server.session.form.items._values)
                self.assertTrue(any('unbound' in d['reason'] for d in c.diagnostics))

    def test_disabled_qualified_button_does_not_gain_dispatch(self):
        raw=self.qualified().replace(b'<Button name="GoButton" id="2">',b'<Button name="GoButton" id="2"><Enabled>false</Enabled>')
        c=self.controller(raw);c.exchange(request());before=dict(c.client.session.snapshot().attributes)
        reply=c.exchange(request('event',event='command',revision=c.client.session.revision,control='GoButton'))
        self.assertIsNotNone(reply['result']['error']);self.assertEqual(dict(c.client.session.snapshot().attributes),before)

    def test_real_demo_xml_retains_qualified_declared_buttons_without_module_activation(self):
        base=Path(__file__).resolve().parents[1]/'examples/demo'
        for path,command in (('CommonForms/DemoWelcome/Ext/Form.xml','Details'),('Catalogs/Номенклатура/Forms/ФормаСписка/Ext/Form.xml','ПроверитьКарточку')):
            raw=(base/path).read_bytes();self.assertIn(('Form.Command.'+command).encode(),raw)
            projected=project_source_form(raw);root=ET.fromstring(projected.xml)
            self.assertIn(command,[n.text for n in root.iter(L+'CommandName')]);self.assertEqual(projected.source_sha256,sha256(raw).hexdigest())

    def test_strict_loader_is_unchanged_and_malformed_target_not_sanitized(self):
        with self.assertRaises(ValueError):self.controller(self.qualified(),False)
        for suffix in (b' extra="bad"',):
            raw=self.qualified().replace(b'<CommandName>',b'<CommandName'+suffix+b'>')
            projected=project_source_form(raw);self.assertFalse(list(ET.fromstring(projected.xml).iter(L+'Button')))

    def test_command_without_supported_action_does_not_gain_button(self):
        raw=self.qualified().replace(b'<Action>Go</Action>',b'')
        p=project_source_form(raw);root=ET.fromstring(p.xml)
        self.assertFalse(list(root.iter(L+'Button')));self.assertFalse(list(root.iter(L+'Command')))
        self.assertTrue(any('no supported action' in d['reason'] for d in p.diagnostics))
