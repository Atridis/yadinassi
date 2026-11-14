"""Explicit false main flags retain scalar input without granting persistence."""
import unittest
import xml.etree.ElementTree as ET
from hashlib import sha256
import test_source_form_projection as projection_tests
from test_source_forms import FORM, files, request
from yadinassi.source_form_projection import project_source_form
from yadinassi.configuration_forms import L


class SourceNonMainAttributeTests(unittest.TestCase):
    controller = projection_tests.SourceFormProjectionTests.controller
    def source(self, flag=b'<MainAttribute>false</MainAttribute>'):
        return FORM.replace(b'<Attribute name="Greeting" id="1">',b'<Attribute name="Greeting" id="1">'+flag)

    def test_false_scalar_retains_field_and_repeated_command_behavior(self):
        raw=self.source();c=self.controller(raw);c.exchange(request())
        for _ in range(2):
            result=c.exchange(request('event',event='command',revision=c.client.session.revision,control='GoButton'))
            self.assertIsNone(result['result']['error'])
            self.assertEqual(dict(c.client.session.snapshot().attributes)['Greeting'],'updated')
        self.assertEqual(c.definition.source_sha256,sha256(raw+b'\0'+files()['CommonForms/Main/Ext/Form/Module.bsl']).hexdigest())
        projected=ET.fromstring(project_source_form(raw).xml)
        self.assertIsNone(projected.find('.//'+L+'MainAttribute'))
        self.assertIsNotNone(projected.find('.//'+L+'Attribute'))
        self.assertTrue(any('non-main scalar' in d['reason'] for d in c.diagnostics))

    def test_false_input_roundtrip_and_stale_revision_still_rejected(self):
        raw=self.source().replace(b'LabelField',b'InputField')
        c=self.controller(raw);c.exchange(request());old=c.client.session.revision
        result=c.exchange(request('event',event='change',revision=old,control='GreetingLabel',value={'type':'String','value':'draft'}))
        self.assertIsNone(result['result']['error'])
        self.assertEqual(dict(c.client.session.snapshot().attributes)['Greeting'],'draft')
        c.exchange(request('event',event='change',revision=old,control='GreetingLabel',value={'type':'String','value':'stale'}))
        self.assertEqual(dict(c.client.session.snapshot().attributes)['Greeting'],'draft')

    def test_true_or_malformed_flags_remain_unavailable_with_bound_controls(self):
        for flag in (b'<MainAttribute>false</MainAttribute>unexpected mixed text',b'<MainAttribute>true</MainAttribute>',b'<MainAttribute/>',b'<MainAttribute>False</MainAttribute>',b'<MainAttribute>0</MainAttribute>',b'<MainAttribute x="1">false</MainAttribute>',b'<MainAttribute><Value>false</Value></MainAttribute>'):
            with self.subTest(flag=flag):
                p=project_source_form(self.source(flag));root=ET.fromstring(p.xml)
                self.assertFalse(any(n.get('name')=='Greeting' for n in root.iter(L+'Attribute')))
                self.assertFalse(any((n.text or '')=='Greeting' for n in root.iter(L+'DataPath')))
                self.assertTrue(any('Attribute unavailable' in d['reason'] for d in p.diagnostics))

    def test_whitespace_false_is_boolean_text_not_object_authority(self):
        c=self.controller(self.source(b'<MainAttribute> false </MainAttribute>'))
        self.assertIn('greeting',c.server.session.form._attributes)
        self.assertIsNone(c.application.constant_store)

    def test_false_does_not_admit_unknown_object_type(self):
        raw=self.source().replace(b'xs:string',b'xs:base64Binary')
        p=project_source_form(raw);root=ET.fromstring(p.xml)
        self.assertFalse(list(root.iter(L+'Attribute')))
        self.assertTrue(any('Attribute unavailable' in d['reason'] for d in p.diagnostics))

    def test_duplicate_flag_is_not_sanitized(self):
        with self.assertRaisesRegex(ValueError,'duplicate'):
            project_source_form(self.source(b'<MainAttribute>false</MainAttribute>'*2))

    def test_strict_loader_remains_unchanged(self):
        with self.assertRaises(ValueError):self.controller(self.source(),False)
