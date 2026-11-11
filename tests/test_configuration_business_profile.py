"""Independent additive grant and canonical full-source admission."""
from dataclasses import replace
import unittest
from xml.etree import ElementTree as ET

from business_configuration_fixture import sources
from yadinassi.configuration_business_profile import (
    BUSINESS_SOURCE_ISSUE, business_configuration, import_business_configuration)
from yadinassi.configuration_runtime import ConfigurationApplication
from yadinassi.configuration_forms import load_configuration_forms


class BusinessProfileTests(unittest.TestCase):
    def test_complete_typed_owners_and_original_sources(self):
        files = sources()
        result, inert = business_configuration(files)
        self.assertEqual({f.path: f.content for f in result.files}, files)
        self.assertEqual((len(result.catalogs), len(result.documents), len(result.common_modules)), (1, 1, 1))
        self.assertEqual(len(inert), 1)
        self.assertTrue(result.activation_issues[0].startswith(BUSINESS_SOURCE_ISSUE + ':'))
        forms = load_configuration_forms(files, catalog_schemas=result.catalogs, document_schemas=result.documents)
        self.assertEqual(len(forms.forms), 4)
        self.assertEqual(sum(d.document_schema is not None for d in forms.forms.values()), 1)
        self.assertEqual({m.kind for m in result.modules}, {'CommonModule', 'ManagedApplicationModule', 'ObjectModule'})

    def test_explicit_runtime_start_and_close(self):
        output = []
        app = ConfigurationApplication.from_business_files(sources(), side='client', output=output.append)
        try:
            self.assertEqual(output, [])
            app.start()
            self.assertEqual(output, ['4'])
        finally:
            app.close()

    def test_old_profiles_remain_closed(self):
        from yadinassi.configuration_application_profile import import_application_configuration
        from yadinassi.configuration_document_profile import import_document_forms_configuration
        from yadinassi.configuration_xml import import_catalog_forms_configuration
        for loader in (import_application_configuration, import_document_forms_configuration, import_catalog_forms_configuration):
            with self.subTest(loader=loader.__name__), self.assertRaises(ValueError): loader(sources())

    def test_unknown_families_and_source_rejected(self):
        for path in ('Ext/SessionModule.bsl', 'Documents/Orders/Ext/ObjectModule.bsl',
                     'Documents/Orders/Ext/ManagerModule.bsl', 'orphan.bsl'):
            files = sources(); files[path] = b'// even comments are not granted'
            with self.subTest(path=path), self.assertRaises(ValueError): import_business_configuration(files)

    def test_posting_and_unknown_properties_rejected(self):
        for old, new in ((b'<Posting>Deny</Posting>', b'<Posting>Allow</Posting>'),
                         (b'<Properties>', b'<Properties><UnknownBehavior>true</UnknownBehavior>')):
            files = sources(); files['Documents/Orders.xml'] = files['Documents/Orders.xml'].replace(old, new, 1)
            with self.subTest(new=new), self.assertRaises(ValueError): import_business_configuration(files)

    def test_catalog_object_module_still_checked(self):
        files = sources(); files['Catalogs/Items/Ext/ObjectModule.bsl'] = b'Procedure Evil() Message("no"); EndProcedure'
        with self.assertRaises(ValueError): import_business_configuration(files)

    def test_cross_owner_uuid_collision_rejected(self):
        files = sources()
        uid = list(ET.fromstring(files['CommonModules/Tools.xml']))[0].get('uuid')
        root = ET.fromstring(files['Documents/Orders.xml'])
        list(root)[0].set('uuid', uid)
        files['Documents/Orders.xml'] = ET.tostring(root)
        with self.assertRaises(ValueError): import_business_configuration(files)

    def test_cross_section_uuid_collision_rejected(self):
        files = sources()
        uid = list(ET.fromstring(files['CommonForms/Welcome.xml']))[0].get('uuid')
        root = ET.fromstring(files['Documents/Orders.xml'])
        next(n for n in root.iter() if n.tag.endswith('TabularSection')).set('uuid', uid)
        files['Documents/Orders.xml'] = ET.tostring(root)
        with self.assertRaises(ValueError): import_business_configuration(files)

    def test_forged_canonical_configuration_rejected(self):
        configuration = import_business_configuration(sources())
        for changed in (replace(configuration, name='Forged'), replace(configuration, documents=()),
                        replace(configuration, activation_issues=(BUSINESS_SOURCE_ISSUE + ':forged',))):
            with self.subTest(changed=changed.name), self.assertRaises(ValueError): ConfigurationApplication(changed, side='client')

    def test_references_not_reinterpreted_as_strings(self):
        files = sources()
        files['Documents/Orders.xml'] = files['Documents/Orders.xml'].replace(b'xs:boolean', b'cfg:CatalogRef.Items')
        with self.assertRaises(ValueError): import_business_configuration(files)

    def test_missing_default_form_rejected(self):
        files = sources()
        files['Documents/Orders.xml'] = files['Documents/Orders.xml'].replace(
            b'Document.Orders.Form.Card', b'Document.Orders.Form.Missing')
        with self.assertRaises(ValueError): import_business_configuration(files)

    def test_rehashed_source_change_does_not_reuse_grant(self):
        files = sources(); first = import_business_configuration(files)
        files['Documents/Orders/Forms/Card/Ext/Form/Module.bsl'] += b'\n// new source'
        second = import_business_configuration(files)
        self.assertNotEqual(first.activation_issues, second.activation_issues)
        with self.assertRaises(ValueError): ConfigurationApplication(replace(first, files=second.files), side='client')

    def test_document_required_catalog_optional(self):
        from test_configuration_application_profile import application_sources
        from document_form_fixture import sources as document_sources
        with self.assertRaises(ValueError): import_business_configuration(application_sources())
        result, inert = business_configuration(document_sources())
        self.assertEqual(inert, ())
        self.assertEqual(result.catalogs, ())
        self.assertEqual(len(result.documents), 1)
