import unittest
from hashlib import sha256
from test_source_forms import files, FORM, request
from yadinassi.configuration_source import import_source
from yadinassi.configuration_source_runtime import SourceApplication
from yadinassi.source_forms import SourceFormController
from yadinassi.source_form_projection import project_source_form


class SourceFormProjectionTests(unittest.TestCase):
    def controller(self, raw, progressive=True):
        mapping=files();mapping['CommonForms/Main/Ext/Form.xml']=raw
        app=SourceApplication(import_source(mapping));self.addCleanup(app.close);app.start()
        return SourceFormController(app,'CommonForm.Main',progressive=progressive)

    def test_strict_source_form_still_refuses_unknown_control(self):
        raw=FORM.replace(b'<ChildItems>',b'<ChildItems><PictureField name="Logo" id="90"/>')
        with self.assertRaises(ValueError):self.controller(raw,False)

    def test_supported_command_survives_unknown_picture(self):
        raw=FORM.replace(b'<ChildItems>',b'<ChildItems><PictureField name="Logo" id="90"/>')
        c=self.controller(raw);c.exchange(request())
        self.assertTrue(any('PictureField' in x['reason'] for x in c.diagnostics))
        result=c.exchange(request('event',event='command',revision=c.client.session.revision,control='GoButton'))
        self.assertIsNone(result['result']['error'])
        self.assertEqual(dict(c.client.session.snapshot().attributes)['Greeting'],'updated')

    def test_unavailable_attribute_is_not_fabricated_as_string(self):
        raw=FORM.replace(b'</Attributes>',b'<Attribute name="Missing" id="90"><Type><v8:Type>xs:base64Binary</v8:Type></Type></Attribute></Attributes>')
        c=self.controller(raw)
        self.assertNotIn('missing',c.server.session.form._attributes)
        self.assertTrue(any('Attribute unavailable' in x['reason'] for x in c.diagnostics))

    def test_control_bound_to_unavailable_attribute_is_diagnostic(self):
        raw=FORM.replace(b'<ChildItems>',b'<ChildItems><InputField name="AbsentField" id="90"><DataPath>Absent</DataPath></InputField>')
        c=self.controller(raw)
        self.assertNotIn('absentfield',c.server.session.form.items._values)
        self.assertTrue(any('unbound Absent' in x['reason'] for x in c.diagnostics))

    def test_unsupported_event_does_not_activate_handler(self):
        raw=FORM.replace(b'<Events><Event name="OnCreateAtServer">',b'<Events><Event name="UnknownEvent">MissingHandler</Event><Event name="OnCreateAtServer">')
        c=self.controller(raw);self.assertIsNone(c.exchange(request())['result']['error'])
        self.assertTrue(any('Event not executed' in x['reason'] for x in c.diagnostics))

    def test_source_hash_binds_original_not_projection(self):
        raw=FORM.replace(b'<ChildItems>',b'<ChildItems><PictureField name="Logo" id="90"/>')
        c=self.controller(raw)
        self.assertEqual(c.definition.source_sha256,sha256(raw+b'\0'+files()['CommonForms/Main/Ext/Form/Module.bsl']).hexdigest())

    def test_localized_title_keeps_visible_text(self):
        raw=FORM.replace(b'<Title>Counter</Title>',b'<Title><v8:item><v8:lang>en</v8:lang><v8:content>Translated</v8:content></v8:item></Title>')
        self.assertEqual(self.controller(raw).definition.title,'Translated')

    def test_duplicate_even_unsupported_item_refused(self):
        raw=FORM.replace(b'<ChildItems>',b'<ChildItems><PictureField name="Logo" id="90"/><PictureField name="Logo" id="91"/>')
        with self.assertRaisesRegex(ValueError,'duplicate'):self.controller(raw)

    def test_unknown_root_envelope_is_not_sanitized(self):
        with self.assertRaises(ValueError):project_source_form(b'<Unsupported/>')

    def test_unknown_presentation_property_is_explained(self):
        raw=FORM.replace(b'<Title>Counter</Title>',b'<Title>Counter</Title><WindowOpeningMode>LockOwnerWindow</WindowOpeningMode>')
        c=self.controller(raw)
        self.assertTrue(any('WindowOpeningMode' in x['reason'] for x in c.diagnostics))

    def test_more_than_32_losses_have_explicit_summary(self):
        extra=b''.join(('<Unknown'+str(i)+'/>').encode() for i in range(40))
        projection=project_source_form(FORM.replace(b'<Title>Counter</Title>',extra+b'<Title>Counter</Title>'))
        self.assertEqual(len(projection.diagnostics),33)
        self.assertIn('omitted: 8',projection.diagnostics[-1]['reason'])

    def test_numeric_alias_id_is_duplicate_even_when_unsupported(self):
        raw=FORM.replace(b'<ChildItems>',b'<ChildItems><PictureField name="Logo" id="01"/>')
        with self.assertRaisesRegex(ValueError,'duplicate'):project_source_form(raw)

    def test_unknown_subtree_is_checked_before_exclusion(self):
        raw=FORM.replace(b'<ChildItems>',b'<ChildItems><UnknownGroup name="Unknown" id="99"><ChildItems><PictureField name="Logo" id="01"/></ChildItems></UnknownGroup>')
        with self.assertRaisesRegex(ValueError,'duplicate'):project_source_form(raw)
