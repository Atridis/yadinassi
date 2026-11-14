"""Explicit exported command bars keep only already-declared commands."""
import unittest
import xml.etree.ElementTree as ET
from hashlib import sha256
import test_source_form_projection as projection_tests
from test_source_forms import FORM, files, request
from yadinassi.source_form_projection import project_source_form
from yadinassi.configuration_forms import L


class SourceCommandBarTests(unittest.TestCase):
    controller = projection_tests.SourceFormProjectionTests.controller

    def bar(self, extra=b'', properties=b''):
        root=ET.fromstring(FORM)
        root.set("xmlns:xs", "http://www.w3.org/2001/XMLSchema")
        children=root.find(L+'ChildItems')
        button=children.find(L+'Button');children.remove(button)
        button.find(L+'CommandName').text='Form.Command.Go'
        bar=ET.SubElement(children,L+'CommandBar',{'name':'Actions','id':'90'})
        if properties:
            for node in ET.fromstring(b'<Root xmlns="http://v8.1c.ru/8.3/xcf/logform">'+properties+b'</Root>'):bar.append(node)
        items=ET.SubElement(bar,L+'ChildItems');items.append(button)
        if extra:items.append(ET.fromstring(extra))
        return ET.tostring(root)

    def test_explicit_command_executes_repeatedly_and_preserves_original_hash(self):
        raw=self.bar();c=self.controller(raw);c.exchange(request())
        for _ in range(2):
            reply=c.exchange(request('event',event='command',revision=c.client.session.revision,control='GoButton'))
            self.assertIsNone(reply['result']['error'])
            self.assertEqual(dict(c.client.session.snapshot().attributes)['Greeting'],'updated')
        self.assertEqual(c.definition.source_sha256,sha256(raw+b'\0'+files()['CommonForms/Main/Ext/Form/Module.bsl']).hexdigest())
        root=ET.fromstring(project_source_form(raw).xml)
        group=root.find('.//'+L+'UsualGroup')
        self.assertEqual(group.find(L+'Group').text,'Horizontal')
        self.assertEqual(group.get('name'),'Actions')
        self.assertTrue(any('no automatic commands' in d['reason'] for d in c.diagnostics))

    def test_auto_fill_and_unknown_standard_commands_never_grant_buttons(self):
        extra=b'<Button xmlns="http://v8.1c.ru/8.3/xcf/logform" name="Save" id="91"><CommandName>Form.StandardCommand.Write</CommandName></Button>'
        c=self.controller(self.bar(extra, b'<Autofill>true</Autofill>'));c.exchange(request())
        self.assertNotIn('save',c.server.session.form.items._values)
        self.assertTrue(any('Autofill' in d['reason'] for d in c.diagnostics))
        self.assertTrue(any('unbound Form.StandardCommand.Write' in d['reason'] for d in c.diagnostics))

    def test_disabled_bar_cannot_dispatch_child(self):
        c=self.controller(self.bar(properties=b'<Enabled>false</Enabled>'));c.exchange(request())
        before=dict(c.client.session.snapshot().attributes)
        reply=c.exchange(request('event',event='command',revision=c.client.session.revision,control='GoButton'))
        self.assertIsNotNone(reply['result']['error'])
        self.assertEqual(dict(c.client.session.snapshot().attributes),before)

    def test_strict_loader_still_refuses_command_bar(self):
        with self.assertRaises(ValueError):self.controller(self.bar(),False)

    def test_duplicate_nested_identity_is_rejected_before_projection(self):
        raw=self.bar().replace(b'id="90"',b'id="2"')
        with self.assertRaisesRegex(ValueError,'duplicate'):project_source_form(raw)

    def test_malformed_visibility_not_sanitized(self):
        with self.assertRaises(ValueError):self.controller(self.bar(properties=b'<Visible>maybe</Visible>'))
