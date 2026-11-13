"""XML reference membership is metadata, never authorization."""
import unittest
from decimal import Decimal
from test_source_metadata import xml
from yadinassi.configuration_source import import_source
from yadinassi.configuration_source_metadata import SourceMetadataRoot


class SourceMetadataReferenceTests(unittest.TestCase):
    def root(self, references='<xr:Item xsi:type="xr:MDObjectRef">Role.Reader</xr:Item>', *, prop=True):
        properties = ('<DefaultRoles xmlns:xr="http://v8.1c.ru/8.3/xcf/readable" '
                      'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">' + references + '</DefaultRoles>') if prop else ''
        return SourceMetadataRoot(import_source({
            'Configuration.xml': xml('Configuration','Demo', properties=properties,
                children='<Role>Reader</Role><Role>Writer</Role>'),
            'Roles/Reader.xml': xml('Role','Reader'),
            'Roles/Writer.xml': xml('Role','Writer'),
        }))

    def test_identity_membership_and_order(self):
        root=self.root(); roles=root.get_member('DefaultRoles')
        self.assertEqual(roles.count(), Decimal(1))
        self.assertIs(roles.get(Decimal(0)), root.find_by_full_name('Role.Reader'))
        self.assertTrue(roles.contains(root.find_by_full_name('Role.Reader')))
        self.assertFalse(roles.contains(root.find_by_full_name('Role.Writer')))
        self.assertIs(roles,root.get_member('ОсновныеРоли'))

    def test_empty_is_only_explicit_empty(self):
        self.assertEqual(self.root('').get_member('DefaultRoles').count(), Decimal(0))
        with self.assertRaisesRegex(ValueError,'absent'):
            self.root(prop=False).get_member('DefaultRoles')

    def test_foreign_root_identity_is_not_membership(self):
        self.assertFalse(self.root().get_member('DefaultRoles').contains(self.root().find_by_full_name('Role.Reader')))

    def test_missing_target_rejected(self):
        with self.assertRaisesRegex(ValueError,'not declared'):
            self.root('<xr:Item xsi:type="xr:MDObjectRef">Role.Missing</xr:Item>').get_member('DefaultRoles')

    def test_wrong_family_and_type_rejected(self):
        for ref in ('<xr:Item xsi:type="xr:MDObjectRef">Catalog.Reader</xr:Item>',
                    '<xr:Item xsi:type="xs:string">Role.Reader</xr:Item>',
                    '<Other>Role.Reader</Other>'):
            with self.subTest(ref=ref), self.assertRaises(ValueError):
                self.root(ref).get_member('DefaultRoles')

    def test_duplicate_reference_rejected(self):
        ref='<xr:Item xsi:type="xr:MDObjectRef">Role.Reader</xr:Item>'
        with self.assertRaisesRegex(ValueError,'ambiguous'):
            self.root(ref+ref).get_member('DefaultRoles')

    def test_collection_read_only(self):
        with self.assertRaises(ValueError):
            self.root().get_member('DefaultRoles').set_index(Decimal(0),None)

    def test_qname_namespace_binding(self):
        good='<r:Item xmlns:r="http://v8.1c.ru/8.3/xcf/readable" xsi:type="r:MDObjectRef">Role.Reader</r:Item>'
        self.assertEqual(self.root(good).get_member('DefaultRoles').count(), Decimal(1))
        bad='<r:Item xmlns:r="http://v8.1c.ru/8.3/xcf/readable" xmlns:xr="urn:wrong" xsi:type="xr:MDObjectRef">Role.Reader</r:Item>'
        with self.assertRaises(ValueError):
            self.root(bad).get_member('DefaultRoles')
