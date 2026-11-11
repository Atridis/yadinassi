"""Explicit source-only enum inventory contracts; no storage/native execution."""
from dataclasses import replace
from copy import deepcopy
from hashlib import sha256
from pathlib import Path
import unittest
from uuid import UUID
import xml.etree.ElementTree as ET

from yadinassi.catalog_backend import FieldSchema
from yadinassi.configuration_accumulation import (PROFILE as SCALAR,
    canonical as scalar_canonical, import_accumulation_configuration)
from yadinassi.configuration_accumulation_references import (PROFILE as REFERENCES,
    canonical as reference_canonical, import_inventory_configuration)
from yadinassi.configuration_inventory_enums import (PROFILE, FORMAT_VERSION, VALUE_PROFILE,
    InventoryEnumConfiguration, canonical, import_inventory_enum_configuration)
from yadinassi import configuration_xml as xml

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / 'scripts/inventory_enum_behavior/runtime_source'
MD = '{' + xml.MD + '}'
REG = 'AccumulationRegisters/Stock.xml'
DOC = 'Documents/Receipt.xml'
PRODUCT = 'Catalogs/Products.xml'
UNIT = 'Enums/Units.xml'
STATE = 'Enums/States.xml'
MODULE = 'Documents/Receipt/Ext/ObjectModule.bsl'


def source():
    return {p.relative_to(FIXTURE).as_posix(): p.read_bytes()
            for p in FIXTURE.rglob('*') if p.is_file()}


def edit(files, path, callback):
    root = ET.fromstring(files[path])
    callback(root)
    for prefix, uri in (('', xml.MD), ('v8', xml.V8), ('xr', xml.XR),
                        ('xsi', 'http://www.w3.org/2001/XMLSchema-instance')):
        ET.register_namespace(prefix, uri)
    root.set('xmlns:cfg', xml.CFG)
    root.set('xmlns:xs', xml.XS)
    files[path] = ET.tostring(root, encoding='utf-8', xml_declaration=True)


def named(parent, category, name):
    return next(n for n in parent.findall(MD + category)
                if n.findtext(MD + 'Properties/' + MD + 'Name') == name)


def children(root):
    return root[0].find(MD + 'ChildObjects')


class InventoryEnumSourceTests(unittest.TestCase):
    def setUp(self):
        self.files = source()

    def load(self, files=None):
        return import_inventory_enum_configuration(self.files if files is None else files,
                                                   inventory_runtime=PROFILE)

    def refused(self):
        with self.assertRaises(ValueError): self.load()

    def test_explicit_profile_is_required(self):
        for profile in (None, SCALAR, REFERENCES, 'inventory-enum-v2', 16):
            with self.subTest(profile=profile), self.assertRaises(ValueError):
                import_inventory_enum_configuration(self.files, inventory_runtime=profile)

    def test_full_fixture_and_configuration_type(self):
        config = self.load()
        self.assertIs(type(config), InventoryEnumConfiguration)
        self.assertEqual((PROFILE, FORMAT_VERSION), ('inventory-enum-v1', 16))
        self.assertEqual((len(config.catalogs), len(config.documents), len(config.registers),
                          len(config.enumerations)), (2, 2, 1, 2))
        self.assertEqual(dict(config.files), self.files)
        self.assertEqual(len(config.files), 10)

    def test_source_digest_covers_every_original_byte(self):
        config = self.load()
        expected = sha256(b''.join(path.encode('utf-8') + b'\0' + sha256(raw).digest()
                                   for path, raw in sorted(self.files.items()))).hexdigest()
        self.assertEqual(config.source_digest, expected)
        self.files[MODULE] += b'\n// retained authored source\n'
        changed = self.load()
        self.assertNotEqual(changed.source_digest, config.source_digest)
        self.assertEqual(dict(changed.files)[MODULE], self.files[MODULE])

    def test_enum_declarations_keep_names_order_and_declared_uuids(self):
        enums = {e.name: e for e in self.load().enumerations}
        self.assertEqual(tuple(v.name for v in enums['Units'].values), ('Piece', 'Pack'))
        self.assertEqual(tuple(v.name for v in enums['States'].values), ('Draft', 'Approved'))
        root = ET.fromstring(self.files[UNIT])
        self.assertEqual(enums['Units'].identity, UUID(root[0].get('uuid')))
        self.assertEqual(enums['Units'].values[0].identity,
                         UUID(children(root)[0].get('uuid')))

    def test_enum_field_target_is_not_catalog_target(self):
        config = self.load(); enums = {e.name: e.identity for e in config.enumerations}
        products = next(c for c in config.catalogs if c.name == 'Products')
        unit = next(f for f in products.fields if f.name == 'Unit')
        self.assertEqual((unit.kind, unit.qualifiers, unit.target_catalog_id, unit.target_enum_id),
                         ('enum_ref', (), None, enums['Units']))
        for document in config.documents:
            state = next(f for f in document.fields if f.name == 'State')
            line = next(f for f in document.tabular_sections[0].fields if f.name == 'Unit')
            self.assertEqual(state.target_enum_id, enums['States'])
            self.assertEqual(line.target_enum_id, enums['Units'])

    def test_register_dimension_and_attribute_are_enum_typed(self):
        config = self.load(); schema = config.registers[0]
        self.assertEqual(schema.value_profile, VALUE_PROFILE)
        self.assertEqual(VALUE_PROFILE, 'catalog_enum_reference_v1')
        self.assertEqual(next(f for f in schema.dimensions if f.name == 'Unit').kind, 'enum_ref')
        self.assertEqual(next(f for f in schema.attributes if f.name == 'State').kind, 'enum_ref')
        self.assertTrue(all(f.kind == 'number' and f.target_enum_id is None for f in schema.resources))
        self.assertEqual(set(schema.recorder_documents), {d.identity for d in config.documents})

    def test_catalog_reference_fields_keep_separate_target(self):
        config = self.load(); product = next(c for c in config.catalogs if c.name == 'Products')
        field = next(f for f in config.documents[0].tabular_sections[0].fields if f.name == 'Product')
        self.assertEqual((field.kind, field.target_catalog_id, field.target_enum_id),
                         ('catalog_ref', product.identity, None))

    def test_field_schema_legacy_positional_shape_is_preserved(self):
        field = FieldSchema(UUID(int=1), 'N', 'number', (10, 2, 'Any'))
        self.assertIsNone(field.target_enum_id)
        self.assertIsNone(field.target_catalog_id)

    def test_handlers_bind_complete_owned_source_without_execution(self):
        config = self.load()
        for identity, path, digest in config.handlers:
            self.assertIn(identity, {d.identity for d in config.documents})
            self.assertEqual(digest, sha256(self.files[path]).hexdigest())
            self.assertIn(b'Row.Unit = Line.Unit; Row.State = State;', self.files[path])
        self.files[MODULE] = b'Raise "import must not execute this";'
        self.assertEqual(dict(self.load().files)[MODULE], self.files[MODULE])

    def test_canonical_reimports_full_configuration(self):
        config = self.load(); fresh = canonical(config)
        self.assertEqual(fresh, config)
        self.assertIsNot(fresh, config)

    def test_canonical_rejects_core_projection_and_wrong_class(self):
        config = self.load()
        for value in (None, object(), config.catalogs):
            with self.assertRaises(ValueError): canonical(value)
        for old in (scalar_canonical, reference_canonical):
            with self.assertRaises(ValueError): old(config)

    def test_canonical_rejects_profile_digest_and_identity_drift(self):
        config = self.load()
        for changed in (replace(config, profile=REFERENCES), replace(config, source_digest='0'*64),
                        replace(config, identity=UUID(int=999)), replace(config, name='Other')):
            with self.assertRaises(ValueError): canonical(changed)

    def test_canonical_rejects_enum_declaration_drift(self):
        config = self.load()
        changed = replace(config.enumerations[0], values=tuple(reversed(config.enumerations[0].values)))
        with self.assertRaises(ValueError): canonical(replace(config, enumerations=(changed, *config.enumerations[1:])))

    def test_canonical_rejects_catalog_enum_field_target_drift(self):
        config = self.load(); index = next(i for i, c in enumerate(config.catalogs) if c.name == 'Products')
        catalog = config.catalogs[index]
        wrong = replace(catalog, fields=(replace(catalog.fields[0], target_enum_id=UUID(int=999)),))
        catalogs = list(config.catalogs); catalogs[index] = wrong
        with self.assertRaises(ValueError): canonical(replace(config, catalogs=tuple(catalogs)))

    def test_canonical_rejects_register_profile_and_recorder_drift(self):
        config = self.load()
        for schema in (replace(config.registers[0], value_profile='catalog_reference_v1'),
                       replace(config.registers[0], recorder_documents=(UUID(int=999),))):
            with self.assertRaises(ValueError): canonical(replace(config, registers=(schema,)))

    def test_canonical_rejects_duplicate_files_or_mutable_schema(self):
        config = self.load()
        for changed in (replace(config, files=(*config.files, config.files[0])),
                        replace(config, catalogs=list(config.catalogs)), replace(config, handlers=())):
            with self.assertRaises(ValueError): canonical(changed)

    def test_canonical_rejects_hostile_uuid_without_equality_hook(self):
        touched = []
        class Hostile:
            def __eq__(self, other): touched.append('eq'); raise AssertionError('hook')
        config = self.load(); forged = UUID(int=1)
        object.__setattr__(forged, 'int', Hostile())
        with self.assertRaises(ValueError): canonical(replace(config, identity=forged))
        self.assertEqual(touched, [])

    def test_old_explicit_source_grants_still_refuse(self):
        with self.assertRaises(ValueError): import_accumulation_configuration(self.files, accumulation_runtime=SCALAR)
        with self.assertRaises(ValueError): import_inventory_configuration(self.files, inventory_runtime=REFERENCES)

    def test_every_metadata_document_requires_authored_220(self):
        for path in tuple(p for p in self.files if p.endswith('.xml')):
            files = dict(self.files)
            edit(files, path, lambda root: root.set('version', '2.4'))
            with self.subTest(path=path), self.assertRaises(ValueError): self.load(files)

    def test_enum_metadata_unknown_envelope_is_refused(self):
        edit(self.files, UNIT, lambda root: root.set('extra', 'unsupported'))
        self.refused()

    def test_enum_field_requires_declared_enum_target(self):
        self.files[PRODUCT] = self.files[PRODUCT].replace(b'EnumRef.Units', b'EnumRef.Unknown')
        self.refused()

    def test_catalog_name_is_not_an_enum_target(self):
        self.files[PRODUCT] = self.files[PRODUCT].replace(b'EnumRef.Units', b'EnumRef.Products')
        self.refused()

    def test_enum_manager_and_mixed_field_types_are_refused(self):
        for replacement in (b'EnumManager.Units', b'EnumRef.Units</v8:Type><v8:Type>xs:string'):
            files = dict(self.files); files[PRODUCT] = files[PRODUCT].replace(b'EnumRef.Units', replacement)
            with self.subTest(replacement=replacement), self.assertRaises(ValueError): self.load(files)

    def test_enum_type_qualifiers_are_not_admitted(self):
        def change(root):
            props = named(children(root), 'Attribute', 'Unit').find(MD + 'Properties')
            ET.SubElement(props.find(MD+'Type'), '{'+xml.V8+'}StringQualifiers')
        edit(self.files, PRODUCT, change); self.refused()

    def test_enum_type_attributes_or_mixed_content_are_refused(self):
        for mode in ('attribute', 'text', 'tail'):
            files = dict(self.files)
            def change(root):
                node = named(children(root), 'Attribute', 'Unit').find(MD+'Properties/'+MD+'Type')
                if mode == 'attribute': node[0].set('x', '1')
                elif mode == 'text': node.text = 'not whitespace'
                else: node[0].tail = 'not whitespace'
            edit(files, PRODUCT, change)
            with self.subTest(mode=mode), self.assertRaises(ValueError): self.load(files)

    def test_unbound_enum_qname_prefix_is_refused(self):
        self.files[PRODUCT] = self.files[PRODUCT].replace(b'cfg:EnumRef.Units', b'absent:EnumRef.Units')
        self.refused()

    def test_enum_resources_are_not_admitted(self):
        def change(root):
            node = named(children(root), 'Resource', 'Quantity').find(MD+'Properties/'+MD+'Type')
            node.clear(); ET.SubElement(node, '{'+xml.V8+'}Type').text = 'cfg:EnumRef.Units'
        edit(self.files, REG, change); self.refused()

    def test_catalog_tabular_sections_are_not_admitted(self):
        edit(self.files, PRODUCT, lambda root: ET.SubElement(children(root), MD+'TabularSection', uuid=str(UUID(int=999))))
        self.refused()

    def test_catalog_reference_fields_are_not_silently_added(self):
        self.files[PRODUCT] = self.files[PRODUCT].replace(b'EnumRef.Units', b'CatalogRef.Warehouses')
        self.refused()

    def test_unknown_configuration_declaration_is_refused(self):
        edit(self.files, 'Configuration.xml', lambda root: ET.SubElement(children(root), MD+'InformationRegister').__setattr__('text', 'Other'))
        self.refused()

    def test_no_enum_declarations_is_refused(self):
        def change(root):
            nodes = children(root)
            for node in list(nodes):
                if node.tag == MD+'Enum': nodes.remove(node)
        edit(self.files, 'Configuration.xml', change); self.refused()

    def test_duplicate_configuration_declaration_is_refused(self):
        edit(self.files, 'Configuration.xml', lambda root: ET.SubElement(children(root), MD+'Enum').__setattr__('text', 'Units'))
        self.refused()

    def test_missing_declared_enum_file_is_refused(self):
        self.files.pop(UNIT); self.refused()

    def test_enum_filename_and_metadata_name_must_match(self):
        self.files[UNIT] = self.files[UNIT].replace(b'<Name>Units</Name>', b'<Name>Other</Name>', 1)
        self.refused()

    def test_enum_manager_module_and_form_files_are_refused(self):
        for path in ('Enums/Units/Ext/ManagerModule.bsl', 'Enums/Units/Forms/Main.xml',
                     'CommonModules/Helper/Ext/Module.bsl'):
            files = dict(self.files); files[path] = b'<Other/>' if path.endswith('.xml') else b'Procedure F() EndProcedure'
            with self.subTest(path=path), self.assertRaises(ValueError): self.load(files)

    def test_enum_unknown_behavioral_property_is_refused(self):
        edit(self.files, UNIT, lambda root: ET.SubElement(root[0].find(MD+'Properties'), MD+'Unknown').__setattr__('text', 'true'))
        self.refused()

    def test_enum_generated_identity_inventory_cannot_be_incomplete(self):
        def change(root):
            info = root[0].find(MD+'InternalInfo'); info.remove(info[0])
        edit(self.files, UNIT, change); self.refused()

    def test_enum_generated_uuid_collision_with_catalog_is_refused(self):
        enum = ET.fromstring(self.files[UNIT]); identity = enum[0].find(MD+'InternalInfo')[0][0].text
        edit(self.files, PRODUCT, lambda root: root[0].set('uuid', identity))
        self.refused()

    def test_enum_value_uuid_collision_with_field_is_refused(self):
        enum = ET.fromstring(self.files[UNIT]); identity = children(enum)[0].get('uuid')
        edit(self.files, PRODUCT, lambda root: named(children(root), 'Attribute', 'Unit').set('uuid', identity))
        self.refused()

    def test_duplicate_enum_value_uuid_across_enums_is_refused(self):
        enum = ET.fromstring(self.files[UNIT]); identity = children(enum)[0].get('uuid')
        edit(self.files, STATE, lambda root: children(root)[0].set('uuid', identity))
        self.refused()

    def test_enum_metadata_uuid_requires_canonical_spelling(self):
        edit(self.files, UNIT, lambda root: root[0].set('uuid', root[0].get('uuid').upper()))
        self.refused()

    def test_duplicate_enum_value_names_are_refused(self):
        def change(root):
            nodes = children(root)
            nodes[1].find(MD+'Properties/'+MD+'Name').text = nodes[0].findtext(MD+'Properties/'+MD+'Name')
        edit(self.files, UNIT, change); self.refused()

    def test_noncanonical_enum_value_uuid_is_refused(self):
        edit(self.files, UNIT, lambda root: children(root)[0].set('uuid', str(UUID(int=0))))
        self.refused()

    def test_missing_owned_handler_and_extra_source_are_refused(self):
        files = dict(self.files); files.pop(MODULE)
        with self.assertRaises(ValueError): self.load(files)
        self.files['Extra.xml'] = b'<Extra/>'; self.refused()

    def test_dimension_totals_cannot_be_disabled(self):
        def change(root):
            named(children(root), 'Dimension', 'Unit').find(MD+'Properties/'+MD+'UseInTotals').text = 'false'
        edit(self.files, REG, change); self.refused()

    def test_register_requires_numeric_resources(self):
        def change(root):
            nodes = children(root)
            for node in list(nodes):
                if node.tag == MD+'Resource': nodes.remove(node)
        edit(self.files, REG, change); self.refused()

    def test_register_dimension_count_remains_bounded(self):
        def change(root):
            nodes = children(root); original = named(nodes, 'Dimension', 'Unit')
            count = len(nodes.findall(MD+'Dimension'))
            for i in range(17-count):
                item = deepcopy(original); item.set('uuid', str(UUID(int=9000+i)))
                item.find(MD+'Properties/'+MD+'Name').text = 'Extra'+str(i)
                nodes.append(item)
        edit(self.files, REG, change); self.refused()

    def test_register_total_field_count_remains_bounded(self):
        def change(root):
            nodes = children(root); original = named(nodes, 'Attribute', 'State')
            for i in range(65-len(nodes)):
                item = deepcopy(original); item.set('uuid', str(UUID(int=9000+i)))
                item.find(MD+'Properties/'+MD+'Name').text = 'Extra'+str(i)
                nodes.append(item)
        edit(self.files, REG, change); self.refused()

    def test_catalog_enum_field_count_remains_bounded(self):
        def change(root):
            nodes = children(root); original = named(nodes, 'Attribute', 'Unit')
            for i in range(65-len(nodes)):
                item = deepcopy(original); item.set('uuid', str(UUID(int=9000+i)))
                item.find(MD+'Properties/'+MD+'Name').text = 'Extra'+str(i)
                nodes.append(item)
        edit(self.files, PRODUCT, change); self.refused()

    def test_document_section_count_remains_bounded(self):
        def change(root):
            nodes = children(root)
            for i in range(16):
                section = ET.SubElement(nodes, MD+'TabularSection', uuid=str(UUID(int=9000+i)))
                props = ET.SubElement(section, MD+'Properties')
                ET.SubElement(props, MD+'Name').text = 'Extra'+str(i)
                ET.SubElement(section, MD+'ChildObjects')
        edit(self.files, DOC, change); self.refused()

    def test_empty_enum_declaration_keeps_typed_target_without_values(self):
        edit(self.files, UNIT, lambda root: children(root).clear())
        config = self.load()
        self.assertEqual(next(e for e in config.enumerations if e.name == 'Units').values, ())

    def test_register_without_recorder_is_refused(self):
        for path in ('Documents/Receipt.xml', 'Documents/Issue.xml'):
            self.files[path] = self.files[path].replace(b'AccumulationRegister.Stock', b'AccumulationRegister.Missing')
        self.refused()

    def test_unsafe_source_paths_and_nonbytes_are_refused(self):
        for path, raw in (('../Extra.xml', b'<Extra/>'), ('Extra.xml', '<Extra/>')):
            files = dict(self.files); files[path] = raw
            with self.subTest(path=path), self.assertRaises(ValueError): self.load(files)

    def test_dtd_and_processing_instructions_are_refused(self):
        for prefix in (b'<!DOCTYPE Enum []>', b'<?owned not-supported?>'):
            files = dict(self.files); files[UNIT] = prefix + files[UNIT]
            with self.assertRaises(ValueError): self.load(files)
