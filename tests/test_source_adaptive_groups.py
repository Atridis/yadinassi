"""Explicit presentation fallback, not native adaptive layout parity."""
import unittest
from hashlib import sha256
from test_source_forms import FORM, request
import test_source_form_projection as projection_tests
from yadinassi.source_form_projection import project_source_form

class AdaptiveGroupTests(unittest.TestCase):
    controller = projection_tests.SourceFormProjectionTests.controller

    def raw(self, property=b'<Group>HorizontalIfPossible</Group>', flags=b''):
        return FORM.replace(b'<ChildItems>', b'<ChildItems><UsualGroup name="Adaptive" id="90">'+property+flags+b'<ChildItems>').replace(b'</ChildItems>', b'</ChildItems></UsualGroup></ChildItems>')

    def test_children_and_command_retained_without_new_fields(self):
        c=self.controller(self.raw());c.exchange(request())
        self.assertTrue(any('Adaptive HorizontalIfPossible' in d['reason'] for d in c.diagnostics))
        self.assertEqual(len(c.server.session.form._attributes),1)
        result=c.exchange(request('event',event='command',revision=c.client.session.revision,control='GoButton'))
        self.assertIsNone(result['result']['error'])
        self.assertEqual(dict(c.client.session.snapshot().attributes)['Greeting'],'updated')

    def test_projection_uses_vertical_and_keeps_original_hash(self):
        raw=self.raw();p=project_source_form(raw)
        self.assertIn(b'<ns0:Group>Vertical</ns0:Group>',p.xml)
        self.assertEqual(p.source_sha256,sha256(raw).hexdigest())
        self.assertIn(b'HorizontalIfPossible',raw)

    def test_page_adaptive_children_retained(self):
        raw=self.raw().replace(b'<UsualGroup name="Adaptive" id="90">',b'<Pages name="Tabs" id="91"><ChildItems><Page name="Adaptive" id="90">').replace(b'</UsualGroup>',b'</Page></ChildItems></Pages>')
        c=self.controller(raw)
        self.assertIsNone(c.exchange(request())['result']['error'])
        self.assertIn('gobutton',c.server.session.form.items._values)

    def test_strict_loader_still_rejects_adaptive(self):
        with self.assertRaises(ValueError):self.controller(self.raw(),False)

    def test_unknown_and_malformed_orientations_not_sanitized(self):
        for prop in (b'<Group>AutoAnything</Group>', b'<Group x="1">HorizontalIfPossible</Group>', b'<Group>HorizontalIfPossible<Extra/></Group>', b'<Group>HorizontalIfPossible</Group>tail', b'<Group>HorizontalIfPossible</Group><Group>Vertical</Group>'):
            with self.subTest(prop=prop),self.assertRaises(ValueError):self.controller(self.raw(prop))

    def test_disabled_parent_does_not_grant_child_command(self):
        c=self.controller(self.raw(flags=b'<Enabled>false</Enabled>'));c.exchange(request())
        result=c.exchange(request('event',event='command',revision=c.client.session.revision,control='GoButton'))
        self.assertIsNotNone(result['result']['error'])
        self.assertEqual(dict(c.client.session.snapshot().attributes)['Greeting'],'Demo')
