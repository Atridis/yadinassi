"""Synthetic compositions of owned XML subtrees, not new native observations."""
from contextlib import closing
from copy import deepcopy
from datetime import datetime
from decimal import Decimal
from itertools import permutations, product
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest
from uuid import UUID, uuid4
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from yadinassi import Interpreter
from yadinassi.catalog_backend import BackendError
from yadinassi.configuration_xml import (
    MD, V8, XR, XS, XSI, DUMP_INFO, MAX_FILES, MAX_FILE_BYTES, MAX_TOTAL_BYTES, _PROFILE_SHA256,
    _catalog_profile_fingerprint, _object, import_configuration,
)
from yadinassi.database_context import SQLiteDBContext
from yadinassi.sqlite_catalog_layout import quote_identifier
from test_official_catalog_scalar_profile import CATALOG, NAME, files, field_properties

DESCRIPTORS = (('number', (12, 2, 'Any'), None),
               ('boolean', (), None), ('datetime', ('DateTime',), None))


def composed(kinds, change=None):
    """Copy entire owned fields; never repair or synthesize their defaults."""
    root = ET.fromstring(CATALOG.read_bytes())
    children = root[0].find('{'+MD+'}ChildObjects')
    originals = tuple(children)
    children[:] = []
    for index, kind in enumerate(kinds):
        field = deepcopy(originals[kind])
        field.set('uuid', str(uuid4()))
        field.find('{'+MD+'}Properties/{'+MD+'}Name').text = 'Field'+str(index)
        children.append(field)
    if change is not None:
        change(root)
    # ElementTree does not retain declarations used only by QName values.
    root.set('xmlns:xs', XS)
    return ET.tostring(root, encoding='utf-8', xml_declaration=True)


def inventory(source):
    """Build bookkeeping from the input XML, independently of the importer."""
    source = dict(source)
    root = ET.Element('{'+DUMP_INFO+'}ConfigDumpInfo', format='Hierarchical', version='2.20')
    versions = ET.SubElement(root, '{'+DUMP_INFO+'}ConfigVersions')
    for path, raw in source.items():
        if path != 'Configuration.xml' and not path.startswith('Catalogs/'):
            continue
        obj = ET.fromstring(raw)[0]
        name = obj.find('{'+MD+'}Properties/{'+MD+'}Name').text
        full_name = obj.tag.rsplit('}', 1)[1]+'.'+name
        record = ET.SubElement(versions, '{'+DUMP_INFO+'}Metadata',
                               name=full_name, id=obj.get('uuid'), configVersion='0'*40)
        for field in obj.findall('{'+MD+'}ChildObjects/{'+MD+'}Attribute'):
            name = field.find('{'+MD+'}Properties/{'+MD+'}Name').text
            ET.SubElement(record, '{'+DUMP_INFO+'}Metadata',
                          name=full_name+'.Attribute.'+name, id=field.get('uuid'))
    source['ConfigDumpInfo.xml'] = ET.tostring(root, encoding='utf-8', xml_declaration=True)
    return source


class OfficialCatalogScalarCompositionTests(unittest.TestCase):
    def assert_active(self, raw=None, *, source=None, kinds=None):
        source = files(raw) if source is None else source
        result = import_configuration(source)
        self.assertEqual(result.activation_issues, ())
        self.assertEqual({entry.path: entry.content for entry in result.files}, source)
        if kinds is not None:
            fields = result.catalogs[0].fields
            self.assertEqual([field.name for field in fields], ['Field'+str(i) for i in range(len(kinds))])
            self.assertEqual([(field.kind, field.qualifiers, field.target_catalog_id) for field in fields],
                             [DESCRIPTORS[kind] for kind in kinds])
        return result

    def assert_refused(self, raw=None, *, source=None):
        source = files(raw) if source is None else source
        try:
            result = import_configuration(source)
        except ValueError:
            return
        self.assertTrue(result.activation_issues, 'out-of-profile composition activated')
        self.assertEqual({entry.path: entry.content for entry in result.files}, source)

    def test_empty_and_each_singleton_preserve_exact_schema_and_source(self):
        for kinds in ((), (0,), (1,), (2,)):
            with self.subTest(kinds=kinds):
                self.assert_active(composed(kinds), kinds=kinds)

    def test_zero_fields_keep_original_newline_and_indentation(self):
        raw = composed(())
        self.assertEqual(ET.fromstring(raw)[0].find('{'+MD+'}ChildObjects').text, '\n')
        self.assert_active(raw, kinds=())
        for whitespace in ('', '\n', '\n  \t\r\n'):
            def change(root): root[0].find('{'+MD+'}ChildObjects').text = whitespace
            with self.subTest(whitespace=whitespace):
                self.assert_active(composed((), change), kinds=())

    def test_unicode_spaces_in_structural_text_and_tails_are_rejected(self):
        for whitespace in ('\u00a0', '\u0085', '\u2003', '\u2028'):
            for target in ('root', 'catalog', 'internal', 'properties', 'children',
                           'field', 'field_properties', 'type', 'qualifiers'):
                for position in ('text', 'tail'):
                    def change(root):
                        props = field_properties(root)
                        nodes = {'root': root, 'catalog': root[0],
                                 'internal': root[0].find('{'+MD+'}InternalInfo'),
                                 'properties': root[0].find('{'+MD+'}Properties'),
                                 'children': root[0].find('{'+MD+'}ChildObjects'),
                                 'field': root[0].find('{'+MD+'}ChildObjects')[0],
                                 'field_properties': props, 'type': props.find('{'+MD+'}Type'),
                                 'qualifiers': props.find('{'+MD+'}Type/{'+V8+'}NumberQualifiers')}
                        setattr(nodes[target], position, ' \n'+whitespace+'\t ')
                    with self.subTest(whitespace=whitespace, target=target, position=position):
                        self.assert_refused(composed((0,), change))

    def test_unicode_spaces_in_empty_child_container_are_rejected(self):
        for whitespace in ('\u00a0', '\u0085', '\u2003', '\u2028'):
            for position in ('text', 'tail'):
                def change(root):
                    setattr(root[0].find('{'+MD+'}ChildObjects'), position, '\n'+whitespace+'\n')
                with self.subTest(whitespace=whitespace, position=position):
                    self.assert_refused(composed((), change))

    def test_unicode_spaces_do_not_normalize_qnames_or_scalar_values(self):
        for kind in range(3):
            for whitespace in ('\u00a0', '\u0085', '\u2003', '\u2028'):
                for target in ('type', 'fill', 'fill_type', 'field_name'):
                    def change(root):
                        props = field_properties(root)
                        if target == 'fill_type':
                            node = props.find('{'+MD+'}FillValue')
                            node.set('{'+XSI+'}type', whitespace+node.get('{'+XSI+'}type')+whitespace)
                        else:
                            path = {'type': '{'+MD+'}Type/{'+V8+'}Type',
                                    'fill': '{'+MD+'}FillValue', 'field_name': '{'+MD+'}Name'}[target]
                            node = props.find(path)
                            node.text = whitespace+node.text+whitespace
                    with self.subTest(kind=kind, whitespace=whitespace, target=target):
                        self.assert_refused(composed((kind,), change))

    def test_xml_formatting_whitespace_does_not_rewrite_leaf_defaults(self):
        for kind in range(3):
            for target in ('FillValue', 'Synonym', 'MinValue'):
                def change(root):
                    node = field_properties(root).find('{'+MD+'}'+target)
                    node.text = ' \n'+(node.text or '')+'\t '
                with self.subTest(kind=kind, target=target):
                    self.assert_refused(composed((kind,), change))

    def test_minimal_xml_branch_rejects_unicode_space_normalization(self):
        from sqlite_catalog_fixture import configuration_files
        substitutions = (
            ('Configuration.xml', '<Properties>', '<Properties>{space}'),
            ('Configuration.xml', '<Name>OwnedApplication</Name>', '<Name>{space}OwnedApplication</Name>'),
            ('Configuration.xml', '<Catalog>Products</Catalog>', '<Catalog>Products{space}</Catalog>'),
            ('Catalogs/Products.xml', '<CodeLength>8</CodeLength>', '<CodeLength>{space}8</CodeLength>'),
            ('Catalogs/Products.xml', '<Type>', '<Type>{space}'),
            ('Catalogs/Products.xml', '<v8:Type>xs:boolean</v8:Type>', '<v8:Type>{space}xs:boolean</v8:Type>'),
            ('Catalogs/Products.xml', '<v8:NumberQualifiers>', '<v8:NumberQualifiers>{space}'),
            ('Catalogs/Products.xml', '<v8:Digits>12</v8:Digits>', '<v8:Digits>12{space}</v8:Digits>'),
            ('Catalogs/Products.xml', '</v8:Digits>', '</v8:Digits>{space}'),
            ('Catalogs/Products.xml', '<Hierarchical>false</Hierarchical>', '<Hierarchical>false{space}</Hierarchical>'),
        )
        for whitespace in ('\u00a0', '\u0085', '\u2003', '\u2028'):
            for path, old, new in substitutions:
                source = configuration_files()
                self.assertIn(old.encode(), source[path])
                source[path] = source[path].replace(old.encode(), new.format(space=whitespace).encode(), 1)
                with self.subTest(whitespace=whitespace, path=path, old=old):
                    self.assert_refused(source=source)
        # The change tightens Unicode handling, not existing XML formatting.
        for path, old, new in substitutions:
            source = configuration_files()
            source[path] = source[path].replace(old.encode(), new.format(space=' \t\r\n ').encode(), 1)
            with self.subTest(xml_whitespace_path=path, old=old):
                self.assert_active(source=source)

    def test_pairs_permutations_and_repeated_profiles_preserve_input_order(self):
        cases = tuple(product(range(3), repeat=2)) + tuple(permutations(range(3)))
        cases += ((2, 0, 2, 1, 0, 1), (1, 1, 1, 1))
        for kinds in cases:
            with self.subTest(kinds=kinds):
                self.assert_active(composed(kinds), kinds=kinds)

    def test_64_fields_are_admitted_for_each_profile_and_mixed_order(self):
        for kinds in ((0,)*64, (1,)*64, (2,)*64, tuple(i % 3 for i in range(64))):
            with self.subTest(first=kinds[:3]):
                self.assert_active(composed(kinds), kinds=kinds)

    def test_65_fields_are_refused_before_profile_admission(self):
        self.assert_refused(composed((1,)*65))

    def test_document_envelope_and_processing_instructions_remain_closed(self):
        for operation in ('version', 'attribute', 'text', 'tail'):
            def change(root):
                if operation == 'version': root.set('version', '2.99')
                elif operation == 'attribute': root.set('unknown', 'true')
                elif operation == 'text': root.text = 'unexpected'
                else: root[0].tail = 'unexpected'
            with self.subTest(operation=operation): self.assert_refused(composed((1,), change))
        raw = composed((1,))
        self.assert_refused(raw.replace(b'?>', b'?><?unknown x?>', 1))

    def test_existing_source_and_xml_resource_bounds_still_apply(self):
        for raw in (b'<Root>'+b'<Leaf/>'*20000+b'</Root>',
                    b'<Root>'*33+b'</Root>'*33,
                    b'<!DOCTYPE Root><Root/>', b'<!ENTITY x "y"><Root/>'):
            source = files(composed((1,)))
            source['Other.xml'] = raw
            with self.subTest(prefix=raw[:40]): self.assert_refused(source=source)
        source = files(composed((1,)))
        source['Other.xml'] = b' '*(MAX_FILE_BYTES+1)
        self.assert_refused(source=source)
        source = files(composed((1,)))
        source.update({str(index)+'.xml': b'<Extra/>' for index in range(MAX_FILES)})
        self.assert_refused(source=source)
        source = files(composed((1,)))
        payload = b'<Extra>'+b' '*(MAX_FILE_BYTES-len(b'<Extra></Extra>'))+b'</Extra>'
        source.update({str(index)+'.xml': payload for index in range(MAX_TOTAL_BYTES//MAX_FILE_BYTES+1)})
        self.assert_refused(source=source)

    def test_every_composition_has_the_same_closed_envelope(self):
        for kinds in ((), (0,), (1, 1), (2, 0, 1), (2,)*64):
            with self.subTest(kinds=kinds):
                obj, namespaces = _object(composed(kinds), 'Catalog')
                before = ET.tostring(obj)
                scopes = deepcopy(namespaces)
                digest, generated = _catalog_profile_fingerprint(
                    obj, namespaces, scalar_attributes=True, envelope_only=True)
                self.assertEqual(digest, _PROFILE_SHA256)
                self.assertEqual(len(generated), 10)
                field_ids = {UUID(field.get('uuid')) for field in obj.find('{'+MD+'}ChildObjects')}
                self.assertFalse(generated & (field_ids | {UUID(obj.get('uuid'))}))
                self.assertEqual(ET.tostring(obj), before)
                self.assertEqual(namespaces, scopes)

    def test_empty_catalog_fixture_still_activates(self):
        from test_official_catalog_xml_profile import files as empty_files
        self.assert_active(source=empty_files())

    def test_one_invalid_last_field_refuses_the_whole_64_field_profile(self):
        for kind in range(3):
            def change(root):
                field_properties(root, 63).find('{'+MD+'}FillValue').text = 'unexpected'
            with self.subTest(kind=kind):
                self.assert_refused(composed((kind,)*64, change))

    def test_unknown_children_cannot_disappear_at_any_inventory_position(self):
        for index in (0, 1, 3):
            for tag in ('Unexpected', 'TabularSection', 'ObjectModule', 'Attribute'):
                def change(root):
                    namespace = 'urn:foreign' if tag == 'Attribute' else MD
                    root[0].find('{'+MD+'}ChildObjects').insert(index, ET.Element('{'+namespace+'}'+tag))
                with self.subTest(index=index, tag=tag):
                    self.assert_refused(composed((1, 0, 1), change))

    def test_child_container_shape_text_and_tail_remain_bound(self):
        for operation in ('missing', 'duplicate', 'attribute', 'text', 'tail', 'namespace'):
            def change(root):
                child = root[0].find('{'+MD+'}ChildObjects')
                if operation == 'missing': root[0].remove(child)
                elif operation == 'duplicate': root[0].append(deepcopy(child))
                elif operation == 'attribute': child.set('unknown', 'true')
                elif operation == 'namespace': child.tag = '{urn:foreign}ChildObjects'
                else: setattr(child, operation, 'unexpected')
            with self.subTest(operation=operation):
                self.assert_refused(composed((1,), change))

    def test_attribute_root_text_tail_attributes_and_nested_objects_are_bound(self):
        for operation in ('text', 'tail', 'attribute', 'child'):
            def change(root):
                field = root[0].find('{'+MD+'}ChildObjects')[-1]
                if operation == 'attribute': field.set('unknown', 'true')
                elif operation == 'child': ET.SubElement(field, '{'+MD+'}ChildObjects')
                else: setattr(field, operation, 'unexpected')
            with self.subTest(operation=operation):
                self.assert_refused(composed((2, 2), change))

    def test_every_singleton_default_property_is_checked(self):
        original = ET.fromstring(CATALOG.read_bytes())
        for kind in range(3):
            for node in field_properties(original, kind):
                if node.tag in ('{'+MD+'}Name', '{'+MD+'}Type'):
                    continue
                def change(root):
                    field_properties(root).find(node.tag).text = 'unexpected'
                with self.subTest(kind=kind, property=node.tag):
                    self.assert_refused(composed((kind,), change))

    def test_missing_duplicate_and_unknown_properties_refuse_each_profile(self):
        for kind in range(3):
            for operation in ('remove', 'duplicate', 'unknown', 'executable'):
                def change(root):
                    props = field_properties(root)
                    fill = props.find('{'+MD+'}FillValue')
                    if operation == 'remove': props.remove(fill)
                    elif operation == 'duplicate': props.append(deepcopy(fill))
                    else: ET.SubElement(props, '{'+MD+'}'+('Script' if operation == 'executable' else 'Unknown')).text = 'Run()'
                with self.subTest(kind=kind, operation=operation):
                    self.assert_refused(composed((kind,), change))

    def test_type_profile_cannot_borrow_another_profiles_default(self):
        originals = ET.fromstring(CATALOG.read_bytes())
        for kind, default_kind in permutations(range(3), 2):
            def change(root):
                props = field_properties(root)
                index = list(props).index(props.find('{'+MD+'}FillValue'))
                props[index] = deepcopy(field_properties(originals, default_kind).find('{'+MD+'}FillValue'))
            with self.subTest(kind=kind, default_kind=default_kind):
                self.assert_refused(composed((kind,), change))

    def test_property_and_catalog_component_order_are_not_generalized(self):
        for target in ('field_properties', 'catalog_properties', 'catalog_components', 'generated_types'):
            def change(root):
                node = {'field_properties': field_properties(root),
                        'catalog_properties': root[0].find('{'+MD+'}Properties'),
                        'catalog_components': root[0],
                        'generated_types': root[0].find('{'+MD+'}InternalInfo')}[target]
                node[0], node[1] = node[1], node[0]
            with self.subTest(target=target):
                self.assert_refused(composed((1,), change))

    def test_full_standard_catalog_defaults_still_guard_composed_fields(self):
        for old, new in ((b'<QuickChoice>false</QuickChoice>', b'<QuickChoice>true</QuickChoice>'),
                         (b'<Owners/>', b'<Owners><Catalog>Other</Catalog></Owners>'),
                         (b'<Autonumbering>false</Autonumbering>', b'<Autonumbering>true</Autonumbering>')):
            # Preserve the original namespace prefix spelling for this mutation.
            raw = CATALOG.read_bytes()
            self.assertIn(old, raw)
            self.assert_refused(raw.replace(old, new, 1))
        def change(root):
            ET.SubElement(root[0].find('{'+MD+'}Properties'), '{'+MD+'}Unexpected').text = '0'
        self.assert_refused(composed((1,), change))

    def test_local_qname_aliases_preserve_source_and_types(self):
        for kind in range(3):
            def change(root):
                props = field_properties(root)
                type_node = props.find('{'+MD+'}Type/{'+V8+'}Type')
                type_node.set('xmlns:localtype', XS)
                type_node.text = type_node.text.replace('xs:', 'localtype:')
                fill = props.find('{'+MD+'}FillValue')
                fill.set('xmlns:localfill', XS)
                fill.set('{'+XSI+'}type', fill.get('{'+XSI+'}type').replace('xs:', 'localfill:'))
            with self.subTest(kind=kind):
                raw = b'\xef\xbb\xbf'+composed((kind,), change).replace(b'\n', b'\r\n')
                self.assert_active(raw, kinds=(kind,))

    def test_local_rebinding_in_one_repeated_profile_refuses_everything(self):
        for target in ('type', 'default'):
            def change(root):
                props = field_properties(root, 1)
                node = props.find('{'+MD+'}Type/{'+V8+'}Type') if target == 'type' else props.find('{'+MD+'}FillValue')
                node.set('xmlns:xs', 'urn:foreign')
            with self.subTest(target=target):
                self.assert_refused(composed((1, 1), change))

    def test_repeated_profiles_still_require_distinct_valid_field_names(self):
        for value in ('Field0', 'field0', 'CODE', 'ПометкаУдаления', 'Field 1', ' Field1 ', ''):
            def change(root): field_properties(root, 1).find('{'+MD+'}Name').text = value
            with self.subTest(value=value):
                self.assert_refused(composed((1, 1), change))
        def rename(root):
            field_properties(root, 0).find('{'+MD+'}Name').text = 'Количество'
            field_properties(root, 1).find('{'+MD+'}Name').text = 'Остаток'
        result = self.assert_active(composed((0, 0), rename))
        self.assertEqual([field.name for field in result.catalogs[0].fields], ['Количество', 'Остаток'])

    def test_field_uuids_cannot_collide_with_catalog_generated_or_sibling(self):
        for target in ('catalog', 'generated', 'sibling'):
            for uppercase in (False, True):
                def change(root):
                    fields = root[0].find('{'+MD+'}ChildObjects')
                    value = {'catalog': root[0].get('uuid'), 'generated': root.find('.//{'+XR+'}ValueId').text,
                             'sibling': fields[0].get('uuid')}[target]
                    fields[-1].set('uuid', value.upper() if uppercase else value)
                with self.subTest(target=target, uppercase=uppercase):
                    self.assert_refused(composed((1,)*64, change))

    def test_composed_field_uuid_cannot_collide_with_configuration(self):
        raw = composed((2,))
        root = ET.fromstring(raw)
        identity = root[0].find('{'+MD+'}ChildObjects')[0].get('uuid')
        self.assert_refused(source=files(raw, config_id=identity))

    def test_cross_catalog_field_generated_collisions_fail_in_both_orders(self):
        first = composed((1,))
        other = ET.fromstring(composed((2, 2)))
        for node in other.iter():
            if 'uuid' in node.attrib: node.set('uuid', str(uuid4()))
            if node.tag in ('{'+XR+'}TypeId', '{'+XR+'}ValueId'): node.text = str(uuid4())
            if node.tag == '{'+XR+'}GeneratedType': node.set('name', node.get('name').replace(NAME, 'Other'))
        other[0].find('{'+MD+'}Properties/{'+MD+'}Name').text = 'Other'
        other.set('xmlns:xs', XS)
        first_obj = ET.fromstring(first)[0]
        first_field = first_obj.find('{'+MD+'}ChildObjects')[0].get('uuid')
        first_generated = first_obj.find('.//{'+XR+'}TypeId').text
        for target, value in (('field', first_generated), ('generated', first_field),
                              ('field', first_field), ('catalog', first_field)):
            mutated = deepcopy(other)
            if target == 'field': mutated[0].find('{'+MD+'}ChildObjects')[-1].set('uuid', value)
            elif target == 'generated': mutated[0].find('.//{'+XR+'}TypeId').text = value
            else: mutated[0].set('uuid', value)
            for order in ((NAME, 'Other'), ('Other', NAME)):
                source = files(first)
                config = ET.fromstring(source['Configuration.xml'])
                children = config[0].find('{'+MD+'}ChildObjects')
                children[:] = []
                for name in order: ET.SubElement(children, '{'+MD+'}Catalog').text = name
                source['Configuration.xml'] = ET.tostring(config, encoding='utf-8')
                source['Catalogs/Other.xml'] = ET.tostring(mutated, encoding='utf-8')
                with self.subTest(target=target, value=value, order=order):
                    self.assert_refused(source=source)

    def test_matching_inventory_accepts_empty_singleton_and_repeated_fields(self):
        for kinds in ((), (2,), (1, 0, 1), (0,)*64):
            with self.subTest(kinds=kinds):
                self.assert_active(source=inventory(files(composed(kinds))), kinds=kinds)

    def test_inventory_cannot_hide_missing_added_or_stale_field_records(self):
        for operation in ('missing', 'extra', 'stale'):
            source = inventory(files(composed((1, 1))))
            root = ET.fromstring(source['ConfigDumpInfo.xml'])
            catalog = next(record for record in root[0] if record.get('name').startswith('Catalog.'))
            if operation == 'missing': catalog.remove(catalog[-1])
            elif operation == 'extra': catalog.append(deepcopy(catalog[-1]))
            else: catalog[-1].set('id', str(uuid4()))
            source['ConfigDumpInfo.xml'] = ET.tostring(root, encoding='utf-8')
            with self.subTest(operation=operation): self.assert_refused(source=source)

    def test_known_empty_modules_preserve_composed_catalog_admission(self):
        source = files(composed((1, 1)))
        source['Ext/SessionModule.bsl'] = b'// inert owned source\n'
        source['Catalogs/'+NAME+'/Ext/ObjectModule.bsl'] = b'\xef\xbb\xbf \r\n'
        self.assert_active(source=source, kinds=(1, 1))

    def test_executable_and_unsupported_module_paths_remain_independent_blockers(self):
        for path, content in (('Ext/SessionModule.bsl', b'X=1;'),
                              ('Catalogs/'+NAME+'/Ext/ObjectModule.bsl', b'X=1;'),
                              ('Other/Ext/Unknown.bsl', b'')):
            source = files(composed((2,)))
            source[path] = content
            with self.subTest(path=path): self.assert_refused(source=source)

    def test_configuration_and_auxiliary_issues_are_not_cleared(self):
        source = files(composed((1,)))
        source['Configuration.xml'] = source['Configuration.xml'].replace(
            b'</Properties>', b'<DefaultLanguage>Language.English</DefaultLanguage></Properties>')
        self.assert_refused(source=source)
        source = files(composed((1,)))
        source['Other.xml'] = b'<Unknown/>'
        result = import_configuration(source)
        self.assertEqual(result.activation_issues, ('unsupported configuration file:Other.xml',))

    def test_invalid_composition_can_archive_but_never_activate(self):
        def change(root): field_properties(root).find('{'+MD+'}FillValue').text = 'true'
        source = files(composed((0,), change))
        config = import_configuration(source)
        self.assertTrue(config.activation_issues)
        with tempfile.TemporaryDirectory() as directory:
            active = Path(directory)/'active.sqlite'
            with self.assertRaises(BackendError): SQLiteDBContext.create(active, config)
            self.assertFalse(active.exists())
            archive = Path(directory)/'archive.sqlite'
            with SQLiteDBContext.create(archive, config, activate=False) as context:
                self.assertEqual(context.backend.export_configuration(), source)
            with SQLiteDBContext(archive) as context:
                self.assertEqual(context.backend.export_configuration(), source)
                with self.assertRaises(BackendError): Interpreter(database_context=context)

    def test_default_and_explicit_writes_reopen_typed_queries_and_physical_order(self):
        for kinds in ((0,), (1,), (2,), (2, 0, 2, 1, 0, 1)):
            with self.subTest(kinds=kinds), tempfile.TemporaryDirectory() as directory:
                source = files(composed(kinds))
                config = import_configuration(source)
                path = Path(directory)/'owned.sqlite'
                expected = []
                expressions = []
                defaults = []
                for index, kind in enumerate(kinds):
                    if kind == 0:
                        value = Decimal(index+1)+Decimal('0.25')
                        expression = str(value); default = Decimal(0)
                    elif kind == 1:
                        value = (index // 2) % 2 == 0
                        expression = 'True' if value else 'False'; default = False
                    else:
                        value = datetime(2024, 2, 29, 12, 34, index)
                        expression = 'Date(2024,2,29,12,34,'+str(index)+')'; default = datetime(1, 1, 1)
                    expected.append(value); expressions.append(expression); defaults.append(default)
                with SQLiteDBContext.create(path, config) as context:
                    vm = Interpreter(database_context=context)
                    vm.execute('P=Catalogs.'+NAME+'.CreateItem();P.Code="default";P.Write();'
                               'P=Catalogs.'+NAME+'.CreateItem();P.Code="typed";')
                    for index, expression in enumerate(expressions): vm.execute('P.Field'+str(index)+'='+expression+';')
                    vm.execute('P.Write();')
                    mapping = context.backend.inspect_storage_mapping()
                    self.assertEqual([field[1] for field in mapping[0][3]], ['Field'+str(i) for i in range(len(kinds))])
                with closing(sqlite3.connect(path)) as connection:
                    columns = [row[1] for row in connection.execute('PRAGMA table_info('+quote_identifier(mapping[0][2])+')')]
                    self.assertEqual(columns[5:], [field[2] for field in mapping[0][3]])
                with SQLiteDBContext(path) as context:
                    vm = Interpreter(database_context=context)
                    self.assertEqual(context.backend.inspect_storage_mapping(), mapping)
                    self.assertEqual(context.backend.export_configuration(), source)
                    vm.execute('D=Catalogs.'+NAME+'.FindByCode("default");R=Catalogs.'+NAME+'.FindByCode("typed");')
                    for index, (value, default) in enumerate(zip(expected, defaults)):
                        for owner, wanted in (('D', default), ('R', value)):
                            actual = vm.execute(owner+'.Field'+str(index))
                            if type(wanted) is datetime:
                                actual = vm.execute('XMLString('+owner+'.Field'+str(index)+')')
                                self.assertEqual(actual, wanted.isoformat(timespec='seconds'))
                            else:
                                self.assertEqual(actual, wanted)
                                self.assertIs(type(actual), type(wanted))
                    projection = ','.join('Field'+str(i) for i in range(len(kinds)))
                    vm.execute('Q=New Query("SELECT '+projection+' FROM Catalog.'+NAME+' WHERE Code=&Code");'
                               'Q.SetParameter("Code","typed");Result=Q.Execute();S=Result.Select();')
                    self.assertIs(vm.execute('S.Next()'), True)
                    for index, wanted in enumerate(expected):
                        field = 'S.Field'+str(index)
                        if type(wanted) is datetime:
                            self.assertEqual(vm.execute('XMLString('+field+')'), wanted.isoformat(timespec='seconds'))
                        else:
                            self.assertEqual(vm.execute(field), wanted)
                            self.assertIs(type(vm.execute(field)), type(wanted))
                    self.assertIs(vm.execute('S.Next()'), False)
                    vm.execute('T=Result.Unload();')
                    for index, kind in enumerate(kinds):
                        self.assertEqual(vm.execute('T.Columns['+str(index)+'].Name'), 'Field'+str(index))
                        if kind == 0:
                            prefix = 'T.Columns['+str(index)+'].ValueType.NumberQualifiers.'
                            self.assertEqual(vm.execute(prefix+'Digits'), Decimal(12))
                            self.assertEqual(vm.execute(prefix+'FractionDigits'), Decimal(2))
                    self.assertEqual(context.backend.export_configuration(), source)


if __name__ == '__main__':
    unittest.main()
