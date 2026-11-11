"""Offline source derivation contracts only, never native/runtime parity proof."""
import copy
import hashlib
import json
from pathlib import Path
import sys
import unittest
from unittest import mock
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from accumulation_register_behavior import fixture, native_source, route
import native_1c_accumulation_register_profile as host

ASSETS = ROOT / 'scripts/accumulation_register_behavior'
MD = '{http://v8.1c.ru/8.3/MDClasses}'
V8 = '{http://v8.1c.ru/8.1/data/core}'
XR = '{http://v8.1c.ru/8.3/xcf/readable}'
TARGET = 'AccumulationRegisters/OwnedAccumulationRows.xml'


def signature(node):
    return node.tag, tuple(sorted(node.attrib.items())), (node.text or '').strip(), tuple(map(signature, node))


class NativeAccumulationSourceTests(unittest.TestCase):
    def xml(self, path='AccumulationRegister.xml'):
        return ET.fromstring((ASSETS / path).read_bytes())

    def native(self, name):
        return ET.fromstring((native_source.PUBLIC / name).read_bytes())

    def register(self):
        return self.xml().find(MD + 'AccumulationRegister')

    def fields(self):
        return {node.findtext(MD + 'Properties/' + MD + 'Name'): node
                for node in self.register().find(MD + 'ChildObjects')}

    def test_checked_in_derivative_reproduces_exact_bytes(self):
        self.assertEqual(native_source.derive(), (ASSETS / 'AccumulationRegister.xml').read_bytes())

    def test_original_sources_and_license_have_exact_provenance(self):
        manifest = json.loads((native_source.PUBLIC / 'SOURCE.json').read_text(encoding='utf-8'))
        self.assertEqual(manifest['repository'], 'vanessa-opensource/add')
        self.assertEqual(manifest['commit'], '2deeed6636dfbb84f42ae625fd40c8ab662bb64e')
        self.assertEqual(len(manifest['files']), 2)
        self.assertEqual(manifest['license']['spdx'], 'MPL-2.0')
        for record in manifest['files'] + [manifest['license']]:
            raw = (native_source.PUBLIC / Path(record['path']).name).read_bytes()
            self.assertEqual(len(raw), record['bytes'])
            self.assertEqual(hashlib.sha256(raw).hexdigest(), record['sha256'])
            self.assertEqual(hashlib.sha1(b'blob ' + str(len(raw)).encode() + b'\0' + raw).hexdigest(), record['git_blob'])
        for record in manifest['files']:
            self.assertIs(record['modified'], False)
            self.assertEqual(record['schema_version'], '2.4')
        derivative = manifest['derivative']
        raw = (native_source.PUBLIC / derivative['path']).read_bytes()
        self.assertIs(derivative['modified'], True)
        self.assertEqual(derivative['license'], 'MPL-2.0')
        self.assertEqual(len(raw), derivative['bytes'])
        self.assertEqual(hashlib.sha256(raw).hexdigest(), derivative['sha256'])
        self.assertEqual(derivative['sha256'], fixture.ASSET_HASHES['AccumulationRegister.xml'])

    def test_derivative_retains_native_header_bom_and_truthful_schema(self):
        raw = (ASSETS / 'AccumulationRegister.xml').read_bytes()
        native = (native_source.PUBLIC / native_source.BALANCE).read_bytes()
        self.assertTrue(raw.startswith(b'\xef\xbb\xbf<?xml'))
        header = lambda data: next(line for line in data.splitlines() if line.startswith(b'<MetaDataObject '))
        self.assertEqual(header(raw), header(native))
        self.assertEqual(self.xml().get('version'), '2.4')
        self.assertIn(b'SPDX-License-Identifier: MPL-2.0', raw)

    def test_derivation_refuses_changed_source_before_processing(self):
        with mock.patch.object(Path, 'read_bytes', return_value=b'<MetaDataObject/>'):
            with self.assertRaisesRegex(ValueError, 'native source changed'):
                native_source.derive()

    def test_derivation_refuses_source_symlink(self):
        with mock.patch.object(Path, 'is_symlink', return_value=True):
            with self.assertRaisesRegex(ValueError, 'native source symlink'):
                native_source.derive()

    def test_derivation_does_not_expose_an_arbitrary_source_argument(self):
        with self.assertRaises(TypeError):
            native_source.derive(b'<MetaDataObject/>')

    def test_all_five_standard_descriptors_are_native_complete(self):
        expected = self.native(native_source.BALANCE).find('.//' + MD + 'StandardAttributes')
        actual = self.register().find(MD + 'Properties/' + MD + 'StandardAttributes')
        self.assertEqual([node.get('name') for node in actual], ['RecordType', 'Active', 'LineNumber', 'Recorder', 'Period'])
        self.assertEqual(signature(actual), signature(expected))
        self.assertTrue(all(len(node) == 23 for node in actual))

    def test_top_level_properties_preserve_complete_native_wrappers(self):
        expected = self.native(native_source.BALANCE).find('.//' + MD + 'Properties')
        actual = self.register().find(MD + 'Properties')
        self.assertEqual([node.tag for node in actual], [node.tag for node in expected])
        substitutions = {'Name': 'OwnedAccumulationRows', 'UseStandardCommands': 'false', 'EnableTotalsSplitting': 'false'}
        for before, after in zip(expected, actual):
            tag = before.tag.removeprefix(MD)
            if tag in substitutions:
                self.assertEqual(after.text, substitutions[tag])
            elif tag == 'Synonym':
                self.assertEqual(len(after), 0)
                self.assertFalse(after.text)
            else:
                self.assertEqual(signature(after), signature(before))
        self.assertEqual(actual.findtext(MD + 'RegisterType'), 'Balance')
        self.assertEqual(actual.findtext(MD + 'DataLockControlMode'), 'Managed')

    def test_owned_register_and_six_generated_identities_are_unchanged(self):
        register = self.register()
        self.assertEqual(register.get('uuid'), '53f5be52-f6c4-5f55-a904-2315026fbcdb')
        expected = {
            'Record': ('d782356a-9cef-5a95-bcb4-b0a023d9e836', '2304697b-3424-5372-9808-46eb18bb5d4f'),
            'Manager': ('653a8f41-551b-5958-b02f-bd2b92d2b69b', '39ed6dd6-e775-5147-a5cc-b488fae77cdd'),
            'Selection': ('8268781d-8014-5f2d-9641-4c5d18f9e696', '13bd901b-2fa2-5324-be3a-58031a22c05f'),
            'List': ('1ad8a538-cbea-51c0-8e0e-3d6d43a88e1c', '7865a44f-fb94-5fba-b4c8-f854aee4e607'),
            'RecordSet': ('68487e52-a354-58f4-8e5e-3c0585112bfd', 'f0da1f92-37c0-5331-8fa1-21524a4c4a90'),
            'RecordKey': ('81f3bc3b-61e6-5b2b-ba6d-b61324e4dfef', '26da58a6-f818-5ac2-bf22-b16c671a1d21'),
        }
        generated = register.find(MD + 'InternalInfo')
        self.assertEqual(len(generated), 6)
        self.assertEqual({node.get('category'): (node.findtext(XR + 'TypeId'), node.findtext(XR + 'ValueId')) for node in generated}, expected)
        for node in generated:
            self.assertEqual(node.get('name'), 'AccumulationRegister' + node.get('category') + '.OwnedAccumulationRows')

    def test_owned_field_groups_and_identities_are_unchanged(self):
        expected = {
            'Amount': ('Resource', 'bacfca9e-c9bc-5116-aaf9-23373023a45f'),
            'Quantity': ('Resource', '18281200-85cf-5f3e-97c7-034f3eaffd9b'),
            'Note': ('Attribute', '77b1bc03-3518-5dca-b33e-d00a5c9f1943'),
            'Item': ('Dimension', '7669a9dd-957b-5575-b334-a9a893d4ed32'),
            'Warehouse': ('Dimension', 'ce426a7f-dd8d-5df2-bcdd-c177f05bd8cf'),
        }
        self.assertEqual({name: (node.tag.removeprefix(MD), node.get('uuid')) for name, node in self.fields().items()}, expected)

    def test_owned_scalar_qualifiers_are_unchanged_without_external_types(self):
        fields = self.fields()
        for name, digits, fraction in (('Amount', '10', '2'), ('Quantity', '10', '3'), ('Warehouse', '4', '0')):
            node = fields[name].find(MD + 'Properties/' + MD + 'Type')
            self.assertEqual(node.findtext(V8 + 'Type'), 'xs:decimal')
            self.assertEqual([child.text for child in node.find(V8 + 'NumberQualifiers')], [digits, fraction, 'Any'])
            self.assertEqual(len(node), 2)
        for name in ('Note', 'Item'):
            node = fields[name].find(MD + 'Properties/' + MD + 'Type')
            self.assertEqual(node.findtext(V8 + 'Type'), 'xs:string')
            self.assertEqual([child.text for child in node.find(V8 + 'StringQualifiers')], ['32', 'Variable'])
            self.assertEqual(len(node), 2)
        for name in ('Item', 'Warehouse'):
            self.assertEqual(fields[name].findtext(MD + 'Properties/' + MD + 'UseInTotals'), 'true')
        self.assertNotIn(b'cfg:CatalogRef.', (ASSETS / 'AccumulationRegister.xml').read_bytes())

    def test_field_wrappers_change_only_reviewed_names_synonyms_and_types(self):
        native = self.native(native_source.BALANCE)
        templates = {kind: native.find('.//' + MD + kind + '/' + MD + 'Properties') for kind in ('Resource', 'Dimension')}
        templates['Attribute'] = self.native(native_source.ATTRIBUTE).find('.//' + MD + 'Attribute/' + MD + 'Properties')
        for field in self.fields().values():
            before = templates[field.tag.removeprefix(MD)]
            after = field.find(MD + 'Properties')
            self.assertEqual([node.tag for node in after], [node.tag for node in before])
            for source, owned in zip(before, after):
                if source.tag == MD + 'Synonym':
                    self.assertEqual(len(owned), 0)
                    self.assertFalse(owned.text)
                elif source.tag not in (MD + 'Name', MD + 'Type'):
                    self.assertEqual(signature(owned), signature(source))

    def test_original_document_handler_observer_and_route_are_byte_unchanged(self):
        for name, digest in {
            'Document.xml': 'e7a73a70869292aa6034d2b0aa12f8df1d3ef9bbb802403ab9a6063fd2ad29da',
            'ObjectModule.bsl': '9e86fc375520fb8f774ff8ff7db46a3a7343aeccf48d2494116f4a80c9b13133',
            'observe.bsl': '10c0d64ebe8c5a17d7ba161ddc2f73b8e11a24447e91d7d370822eb08bdc34c0',
            'route.py': 'ff2b06a56fae5b61769935d45bd5883e6702d6bd6ec02f4080677beb6cb75ac1',
        }.items():
            self.assertEqual(hashlib.sha256((ASSETS / name).read_bytes()).hexdigest(), digest)
        self.assertEqual(route.COUNT, 16)

    def test_only_owned_derivative_is_staged_not_upstream_sibling_dependencies(self):
        staged = host.staged_files()
        self.assertIn('scripts/accumulation_register_behavior/AccumulationRegister.xml', staged)
        self.assertFalse(any('/public_source/' in path or path.endswith('/native_source.py') for path in staged))
        types = list(self.register().find(MD + 'ChildObjects').iter(V8 + 'Type'))
        self.assertEqual(len(types), 5)
        self.assertEqual({node.text for node in types}, {'xs:decimal', 'xs:string'})

    def test_material_gate_already_allows_native_schema_redump_not_field_drift(self):
        raw = (ASSETS / 'AccumulationRegister.xml').read_bytes()
        actual = raw.replace(b'version="2.4"', b'version="2.20"')
        self.assertNotEqual(raw, actual)
        self.assertTrue(fixture.verify_redump({TARGET: raw}, {TARGET: actual}))
        actual = actual.replace(b'<UseInTotals>true', b'<UseInTotals>false')
        with self.assertRaises(ValueError):
            fixture.verify_redump({TARGET: raw}, {TARGET: actual})

    def test_material_gate_still_rejects_owned_control_and_type_changes(self):
        raw = (ASSETS / 'AccumulationRegister.xml').read_bytes()
        for before, after in (
            (b'<RegisterType>Balance', b'<RegisterType>Turnovers'),
            (b'<DataLockControlMode>Managed', b'<DataLockControlMode>Automatic'),
            (b'<EnableTotalsSplitting>false', b'<EnableTotalsSplitting>true'),
            (b'<v8:AllowedSign>Any', b'<v8:AllowedSign>Nonnegative'),
            (b'<v8:Length>32', b'<v8:Length>64'),
            (b'<v8:AllowedLength>Variable', b'<v8:AllowedLength>Fixed'),
            (b'<v8:FractionDigits>3', b'<v8:FractionDigits>2'),
            (b'<Name>Item</Name>', b'<Name>Other</Name>'),
            (b'7669a9dd-957b-5575-b334-a9a893d4ed32', b'7669a9dd-957b-5575-b334-a9a893d4ed33'),
        ):
            changed = raw.replace(before, after)
            self.assertNotEqual(raw, changed)
            with self.subTest(before=before), self.assertRaises(ValueError):
                fixture.verify_redump({TARGET: raw}, {TARGET: changed})

    def test_missing_or_duplicate_owned_fields_are_still_rejected(self):
        raw = (ASSETS / 'AccumulationRegister.xml').read_bytes()
        for duplicate in (False, True):
            root = self.xml()
            children = root.find(MD + 'AccumulationRegister/' + MD + 'ChildObjects')
            if duplicate:
                children.append(copy.deepcopy(children[0]))
            else:
                children.remove(children[0])
            # ET omits unused namespace declarations, including xs in QName text.
            root.set('xmlns:xs', 'http://www.w3.org/2001/XMLSchema')
            with self.assertRaises(ValueError):
                fixture.verify_redump({TARGET: raw}, {TARGET: ET.tostring(root)})

    def test_preparation_preserves_exact_inventory_and_material_grants(self):
        from test_catalog_object_fixture import baseline
        original = baseline()
        _, prepared = fixture.prepare(original)
        self.assertEqual(set(prepared) - set(original), {
            'Documents/OwnedAccumulationDoc.xml',
            'Documents/OwnedAccumulationDoc/Ext/ObjectModule.bsl', TARGET,
        })
        rights_path = fixture.original.ROLE_FILES[1]
        rights_ns = '{' + fixture.original.RIGHTS + '}'
        before = ET.fromstring(original[rights_path])
        after = ET.fromstring(prepared[rights_path])
        original_objects = before.findall(rights_ns + 'object')
        actual_objects = after.findall(rights_ns + 'object')
        self.assertEqual(len(actual_objects), len(original_objects) + 2)
        self.assertEqual([signature(node) for node in actual_objects[:-2]],
                         [signature(node) for node in original_objects])
        expected = {
            'Document.OwnedAccumulationDoc': ['Read', 'Insert', 'Update', 'Posting', 'UndoPosting'],
            'AccumulationRegister.OwnedAccumulationRows': ['Read', 'Update'],
        }
        for node in actual_objects[-2:]:
            name = node.findtext(rights_ns + 'name')
            rights = node.findall(rights_ns + 'right')
            self.assertEqual([right.findtext(rights_ns + 'name') for right in rights], expected[name])
            self.assertEqual([right.findtext(rights_ns + 'value') for right in rights], ['true'] * len(rights))
        for name in set(original) - {'Configuration.xml', rights_path}:
            self.assertEqual(prepared[name], original[name])
        self.assertTrue(fixture.verify_redump(prepared, dict(prepared)))
