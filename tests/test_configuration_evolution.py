"""Canonical additive deltas; no storage execution or native parity claim."""
from dataclasses import replace
from decimal import Decimal
from datetime import datetime
import unittest
from uuid import uuid4

from sqlite_catalog_fixture import configuration_files
from yadinassi.configuration_xml import import_configuration
from yadinassi.configuration_evolution import additive_delta, default_value
from yadinassi.catalog_backend import BackendError, FieldSchema


def append_field(files, kind='xs:boolean'):
    files = dict(files)
    field = ('<Attribute uuid="' + str(uuid4()) + '"><Properties><Name>Extra</Name>'
             '<Type><v8:Type>' + kind + '</v8:Type></Type></Properties></Attribute>').encode()
    path = 'Catalogs/Categories.xml'
    files[path] = files[path].replace(b'</ChildObjects>', field + b'</ChildObjects>')
    return files


class ConfigurationEvolutionTests(unittest.TestCase):
    def setUp(self):
        self.files = configuration_files()
        self.before = import_configuration(self.files)

    def test_append_boolean_default(self):
        after = import_configuration(append_field(self.files))
        delta = additive_delta(self.before, after)
        self.assertEqual(len(delta.catalogs), 1)
        self.assertEqual(delta.catalogs[0].defaults, (False,))
        self.assertFalse(delta.catalogs[0].new_catalog)

    def test_noop_refused(self):
        with self.assertRaises(BackendError): additive_delta(self.before, self.before)

    def test_schema_not_backed_by_source_refused(self):
        changed = replace(self.before.catalogs[0], description_length=32)
        forged = replace(self.before, catalogs=(changed, *self.before.catalogs[1:]))
        with self.assertRaises(BackendError): additive_delta(self.before, forged)

    def test_configuration_identity_change_refused(self):
        files = append_field(self.files)
        files['Configuration.xml'] = files['Configuration.xml'].replace(
            str(self.before.config_uuid).encode(), str(uuid4()).encode())
        with self.assertRaises(BackendError): additive_delta(self.before, import_configuration(files))

    def test_module_bytes_cannot_hitchhike(self):
        files = append_field(self.files)
        files['Catalogs/Products/Ext/ObjectModule.bsl'] += b'// changed\n'
        with self.assertRaises(BackendError): additive_delta(self.before, import_configuration(files))

    def test_existing_property_change_refused(self):
        files = append_field(self.files)
        files['Catalogs/Categories.xml'] = files['Catalogs/Categories.xml'].replace(
            b'<DescriptionLength>64', b'<DescriptionLength>32')
        with self.assertRaises(BackendError): additive_delta(self.before, import_configuration(files))

    def test_reference_default_refused(self):
        field = FieldSchema(uuid4(), 'Other', 'catalog_ref', (), self.before.catalogs[0].identity)
        with self.assertRaises(BackendError): default_value(field)

    def test_scalar_defaults_are_exact(self):
        for kind, qualifiers, expected in (
            ('string', (12,), ''), ('number', (12, 2, 'Nonnegative'), Decimal(0)),
            ('boolean', (), False), ('datetime', ('DateTime',), datetime(1, 1, 1))):
            with self.subTest(kind=kind):
                value = default_value(FieldSchema(uuid4(), 'Extra', kind, qualifiers))
                self.assertIs(type(value), type(expected)); self.assertEqual(value, expected)

    def test_non_defaultable_metadata_refused(self):
        with self.assertRaises(BackendError):
            default_value(FieldSchema(uuid4(), 'Extra', 'binary'))

    def test_new_scalar_catalog(self):
        files = dict(self.files)
        old = self.before.catalogs[0]
        files['Catalogs/NewCatalog.xml'] = files['Catalogs/Categories.xml'].replace(
            str(old.identity).encode(), str(uuid4()).encode()).replace(b'Categories', b'NewCatalog')
        files['Configuration.xml'] = files['Configuration.xml'].replace(
            b'</ChildObjects>', b'<Catalog>NewCatalog</Catalog></ChildObjects>')
        delta = additive_delta(self.before, import_configuration(files))
        self.assertEqual(len(delta.catalogs), 1)
        self.assertTrue(delta.catalogs[0].new_catalog)
