"""Synthetic closed ConfigDumpInfo inventory tests, not native 1C evidence."""
from copy import deepcopy
from pathlib import Path
import sys
import unittest
from uuid import uuid4
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from yadinassi.configuration_xml import import_configuration
from sqlite_catalog_fixture import configuration_files

MD = 'http://v8.1c.ru/8.3/MDClasses'
DI = 'http://v8.1c.ru/8.3/xcf/dumpinfo'
PATH = 'ConfigDumpInfo.xml'
BLOCKED = 'unsupported configuration file:'+PATH
TOKEN = '0123456789abcdef0123456789abcdef00000000'


def with_dump_info():
    """Author an inventory from fixture XML, without using importer results."""
    source = configuration_files()
    root = ET.Element('{'+DI+'}ConfigDumpInfo', format='Hierarchical', version='2.20')
    versions = ET.SubElement(root, '{'+DI+'}ConfigVersions')
    for path, raw in source.items():
        if not path.endswith('.xml'):
            continue
        obj = ET.fromstring(raw)[0]
        name = obj.find('{'+MD+'}Properties/{'+MD+'}Name').text
        full_name = obj.tag.rsplit('}', 1)[1]+'.'+name
        record = ET.SubElement(versions, '{'+DI+'}Metadata',
                              name=full_name, id=obj.get('uuid'), configVersion=TOKEN)
        for field in obj.findall('{'+MD+'}ChildObjects/{'+MD+'}Attribute'):
            field_name = field.find('{'+MD+'}Properties/{'+MD+'}Name').text
            ET.SubElement(record, '{'+DI+'}Metadata',
                          name=full_name+'.Attribute.'+field_name, id=field.get('uuid'))
    source[PATH] = ET.tostring(root, encoding='utf-8', xml_declaration=True)
    return source


def changed(change):
    source = with_dump_info()
    root = ET.fromstring(source[PATH])
    change(root)
    source[PATH] = ET.tostring(root, encoding='utf-8', xml_declaration=True)
    return source


class ConfigurationDumpInfoTests(unittest.TestCase):
    def assert_blocked(self, source):
        result = import_configuration(source)
        self.assertIn(BLOCKED, result.activation_issues)
        self.assertEqual({entry.path: entry.content for entry in result.files}, source)

    def test_matching_catalog_and_attribute_inventory_preserves_source(self):
        source = with_dump_info()
        result = import_configuration(source)
        self.assertEqual(result.activation_issues, ())
        self.assertEqual({entry.path: entry.content for entry in result.files}, source)
        self.assertEqual(len(result.catalogs[1].fields), 5)

    def test_dump_info_remains_optional(self):
        self.assertEqual(import_configuration(configuration_files()).activation_issues, ())

    def test_bom_crlf_and_declaration_preserved(self):
        source = with_dump_info()
        source[PATH] = b'\xef\xbb\xbf'+source[PATH].replace(b'\n', b'\r\n')
        result = import_configuration(source)
        self.assertEqual(result.activation_issues, ())
        self.assertEqual({entry.path: entry.content for entry in result.files}, source)

    def test_declaration_may_be_absent_or_omit_encoding(self):
        for declaration in (b'', b'<?xml version="1.0"?>',
                            b'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'):
            source = with_dump_info()
            source[PATH] = declaration+source[PATH].split(b'?>', 1)[1]
            with self.subTest(declaration=declaration):
                self.assertEqual(import_configuration(source).activation_issues, ())

    def test_double_bom_cannot_hide_nonstandard_declaration(self):
        source = with_dump_info()
        source[PATH] = (b'\xef\xbb\xbf\xef\xbb\xbf<?xml version="1.1" encoding="UTF-8"?>'
                        + source[PATH].split(b'?>', 1)[1])
        try:
            result = import_configuration(source)
        except ValueError:
            return  # A strict XML parser may reject the duplicate BOM first.
        self.assertIn(BLOCKED, result.activation_issues)

    def test_contradictory_encoding_or_xml_version_blocks_activation(self):
        for declaration in (b'<?xml version="1.0" encoding="UTF-16"?>',
                            b'<?xml version="1.0" encoding="windows-1251"?>',
                            b'<?xml version="1.1" encoding="UTF-8"?>'):
            source = with_dump_info()
            source[PATH] = declaration+source[PATH].split(b'?>', 1)[1]
            with self.subTest(declaration=declaration):
                self.assert_blocked(source)

    def test_record_and_attribute_order_is_not_semantic(self):
        def reverse(root):
            root[0][:] = reversed(root[0][:])
            for record in root[0]:
                record[:] = reversed(record[:])
        self.assertEqual(import_configuration(changed(reverse)).activation_issues, ())

    def test_uuid_case_is_accepted_without_rewriting_source(self):
        def upper(root):
            for record in root.iter('{'+DI+'}Metadata'):
                record.set('id', record.get('id').upper())
        source = changed(upper)
        self.assertEqual(import_configuration(source).activation_issues, ())
        self.assertEqual({entry.path: entry.content for entry in import_configuration(source).files}, source)

    def test_namespace_prefix_alias_and_unused_declaration_are_harmless(self):
        source = with_dump_info()
        source[PATH] = source[PATH].replace(b'ns0', b'info').replace(
            b'xmlns:info=', b'xmlns:unused="urn:unused" xmlns:info=', 1)
        self.assertEqual(import_configuration(source).activation_issues, ())

    def test_unknown_root_or_namespace_blocks_activation(self):
        for tag in ('ConfigDumpInfo', '{urn:foreign}ConfigDumpInfo', '{'+DI+'}Unexpected'):
            with self.subTest(tag=tag):
                self.assert_blocked(changed(lambda root: setattr(root, 'tag', tag)))

    def test_only_hierarchical_version_220_is_admitted(self):
        for key, value in (('format', 'Plain'), ('format', 'hierarchical'),
                           ('version', '2.7'), ('version', '2.21'), ('version', '2.20 ')):
            with self.subTest(key=key, value=value):
                self.assert_blocked(changed(lambda root: root.set(key, value)))

    def test_configuration_and_catalog_document_versions_must_agree(self):
        for path in ('Configuration.xml', 'Catalogs/Categories.xml', 'Catalogs/Products.xml'):
            source = with_dump_info()
            source[path] = source[path].replace(b'version="2.20"', b'version="2.19"')
            with self.subTest(path=path):
                self.assert_blocked(source)

    def test_root_attributes_are_closed(self):
        for key in ('unexpected', '{urn:foreign}version'):
            with self.subTest(key=key):
                self.assert_blocked(changed(lambda root: root.set(key, '2.20')))
        for key in ('format', 'version'):
            with self.subTest(missing=key):
                self.assert_blocked(changed(lambda root: root.attrib.pop(key)))

    def test_exactly_one_versions_container_is_required(self):
        self.assert_blocked(changed(lambda root: root.remove(root[0])))
        self.assert_blocked(changed(lambda root: root.append(deepcopy(root[0]))))

    def test_versions_container_has_no_attributes_or_foreign_name(self):
        self.assert_blocked(changed(lambda root: root[0].set('unexpected', 'true')))
        self.assert_blocked(changed(lambda root: setattr(root[0], 'tag', '{urn:foreign}ConfigVersions')))

    def test_top_level_record_attributes_are_exact(self):
        for key in ('name', 'id', 'configVersion'):
            with self.subTest(missing=key):
                self.assert_blocked(changed(lambda root: root[0][0].attrib.pop(key)))
        self.assert_blocked(changed(lambda root: root[0][0].set('unexpected', 'true')))
        self.assert_blocked(changed(lambda root: root[0][0].set('{urn:foreign}id', str(uuid4()))))

    def test_configuration_name_and_uuid_must_match(self):
        for key, value in (('name', 'Configuration.Other'), ('name', 'Configuration.ownedapplication'),
                           ('id', str(uuid4()))):
            with self.subTest(key=key, value=value):
                self.assert_blocked(changed(lambda root: root[0][0].set(key, value)))

    def test_catalog_name_and_uuid_must_match(self):
        for key, value in (('name', 'Catalog.Other'), ('name', 'Catalog.categories'),
                           ('id', str(uuid4()))):
            with self.subTest(key=key, value=value):
                self.assert_blocked(changed(lambda root: root[0][1].set(key, value)))

    def test_missing_or_duplicate_top_level_record_blocks_activation(self):
        for index in (0, 1, 2):
            with self.subTest(index=index):
                self.assert_blocked(changed(lambda root: root[0].remove(root[0][index])))
                self.assert_blocked(changed(lambda root: root[0].append(deepcopy(root[0][index]))))

    def test_reused_uuid_cannot_impersonate_another_object(self):
        self.assert_blocked(changed(lambda root: root[0][1].set('id', root[0][0].get('id'))))

    def test_noncanonical_zero_and_suffixed_ids_are_out_of_profile(self):
        for value in ('00000000-0000-0000-0000-000000000000', 'not-a-uuid',
                      uuid4().hex, '{'+str(uuid4())+'}', str(uuid4())+'.0'):
            with self.subTest(value=value):
                self.assert_blocked(changed(lambda root: root[0][0].set('id', value)))

    def test_version_tokens_are_opaque_bounded_hex_not_content_hashes(self):
        for value in ('f'*40, 'A'*40, '0'*40):
            with self.subTest(value=value):
                source = changed(lambda root: root[0][0].set('configVersion', value))
                self.assertEqual(import_configuration(source).activation_issues, ())
        for value in ('', 'a'*39, 'a'*41, 'g'*40, ' '*40, 'a'*39+'\n'):
            with self.subTest(invalid=value):
                self.assert_blocked(changed(lambda root: root[0][0].set('configVersion', value)))

    def test_attribute_name_uuid_and_parent_must_match(self):
        for key, value in (('name', 'Catalog.Products.Attribute.Unknown'),
                           ('name', 'Catalog.Categories.Attribute.Text'), ('id', str(uuid4()))):
            with self.subTest(key=key, value=value):
                self.assert_blocked(changed(lambda root: root[0][2][0].set(key, value)))
        def move(root):
            field = root[0][2][0]
            root[0][2].remove(field)
            root[0][1].append(field)
        self.assert_blocked(changed(move))

    def test_attribute_records_are_leaf_nodes_with_exact_attributes(self):
        for key in ('name', 'id'):
            with self.subTest(missing=key):
                self.assert_blocked(changed(lambda root: root[0][2][0].attrib.pop(key)))
        for key in ('configVersion', 'unexpected'):
            with self.subTest(extra=key):
                self.assert_blocked(changed(lambda root: root[0][2][0].set(key, TOKEN)))
        self.assert_blocked(changed(lambda root: root[0][2][0].append(deepcopy(root[0][2][1]))))

    def test_missing_duplicate_or_top_level_attribute_blocks_activation(self):
        self.assert_blocked(changed(lambda root: root[0][2].remove(root[0][2][0])))
        self.assert_blocked(changed(lambda root: root[0][2].append(deepcopy(root[0][2][0]))))
        def move(root):
            field = root[0][2][0]
            root[0][2].remove(field)
            field.set('configVersion', TOKEN)
            root[0].append(field)
        self.assert_blocked(changed(move))

    def test_unknown_families_and_external_components_remain_unsupported(self):
        for name in ('Language.English', 'Document.Orders', 'Configuration.OwnedApplication.SessionModule',
                     'Catalog.Products.ObjectModule', 'Catalog.Products.Form.Item'):
            def extra(root):
                ET.SubElement(root[0], '{'+DI+'}Metadata', name=name, id=str(uuid4()), configVersion=TOKEN)
            with self.subTest(name=name):
                self.assert_blocked(changed(extra))

    def test_unknown_elements_and_namespace_rebinding_block_activation(self):
        for select in (lambda root: root[0][0], lambda root: root[0][2][0]):
            for tag in ('{'+DI+'}Unexpected', '{urn:foreign}Metadata', 'Metadata'):
                with self.subTest(tag=tag, select=select):
                    self.assert_blocked(changed(lambda root: setattr(select(root), 'tag', tag)))

    def test_text_and_tails_cannot_hide_in_inventory(self):
        for index, select in enumerate((lambda root: root, lambda root: root[0],
                                        lambda root: root[0][0], lambda root: root[0][2][0])):
            for attribute in ('text', 'tail'):
                if attribute == 'tail' and index == 0:
                    continue  # Root tail would make the XML document malformed.
                for text in ('unexpected', '\u00a0'):
                    source = changed(lambda root: setattr(select(root), attribute, text))
                    with self.subTest(attribute=attribute, text=text):
                        self.assert_blocked(source)

    def test_comments_and_xml_formatting_whitespace_are_inert(self):
        source = with_dump_info()
        source[PATH] = source[PATH].replace(b'<ns0:ConfigVersions>',
            b'<ns0:ConfigVersions>\r\n\t<!-- <?not-an-instruction?> -->\n')
        self.assertEqual(import_configuration(source).activation_issues, ())

    def test_processing_instructions_dtd_entities_and_invalid_utf8_are_rejected(self):
        for content in (b'<?unknown x?><x/>', b'<!DOCTYPE x><x/>',
                        b'<!DOCTYPE x [<!ENTITY a "x">]><x>&a;</x>', b'<x>\xff</x>'):
            source = with_dump_info()
            source[PATH] = content
            with self.subTest(content=content), self.assertRaises(ValueError):
                import_configuration(source)

    def test_structure_and_file_byte_limits_remain_in_force(self):
        for content in (b'<x>'*33+b'</x>'*33,
                        b'<x>'+b'<y/>'*20000+b'</x>', b' '*((1024*1024)+1)):
            source = with_dump_info()
            source[PATH] = content
            with self.subTest(length=len(content)), self.assertRaises(ValueError):
                import_configuration(source)

    def test_matching_inventory_does_not_clear_module_execution_guard(self):
        source = with_dump_info()
        source['Catalogs/Products/Ext/ObjectModule.bsl'] = b'Procedure BeforeWrite(Cancel)\nCancel=True;\nEndProcedure'
        issues = import_configuration(source).activation_issues
        self.assertNotIn(BLOCKED, issues)
        self.assertIn('module execution unsupported:Catalogs/Products/Ext/ObjectModule.bsl', issues)

    def test_matching_inventory_does_not_clear_unknown_file_guard(self):
        source = with_dump_info()
        source['Other.xml'] = b'<Unknown/>'
        self.assertEqual(import_configuration(source).activation_issues,
                         ('unsupported configuration file:Other.xml',))

    def test_matching_inventory_does_not_clear_unknown_metadata_guard(self):
        source = with_dump_info()
        source['Configuration.xml'] = source['Configuration.xml'].replace(
            b'</ChildObjects>', b'<Language>English</Language></ChildObjects>')
        issues = import_configuration(source).activation_issues
        self.assertNotIn(BLOCKED, issues)
        self.assertIn('unsupported metadata family:Language', issues)

    def test_only_exact_root_filename_is_admitted(self):
        for path in ('configdumpinfo.xml', 'ConfigDumpInfo.XML', 'Ext/ConfigDumpInfo.xml'):
            source = with_dump_info()
            source[path] = source.pop(PATH)
            with self.subTest(path=path):
                self.assertEqual(import_configuration(source).activation_issues,
                                 ('unsupported configuration file:'+path,))


if __name__ == '__main__':
    unittest.main()
