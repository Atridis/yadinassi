"""Bounded authored XML tabular metadata contract, not native format parity."""
from pathlib import Path
import re
import sys
import unittest
from uuid import UUID, uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from yadinassi.configuration_xml import import_configuration
from catalog_sections_fixture import configuration_files_with_sections

PATH = 'Catalogs/Products.xml'


def edit_section(files, change):
    source = files[PATH].decode()
    section = re.search(r'<TabularSection .*?</TabularSection>', source).group()
    files[PATH] = source.replace(section, change(section), 1).encode()


def empty_section(name):
    return (f'<TabularSection uuid="{uuid4()}"><Properties><Name>{name}</Name>'
            '</Properties><ChildObjects/></TabularSection>')


class ConfigurationTabularSectionsTests(unittest.TestCase):
    def test_import_schema_qualifiers_and_reference_target(self):
        value = import_configuration(configuration_files_with_sections())
        categories, products = value.catalogs
        self.assertEqual(value.activation_issues, ())
        self.assertEqual(categories.tabular_sections, ())
        lines, notes = products.tabular_sections
        self.assertEqual((lines.name, notes.name), ('Lines', 'Notes'))
        self.assertEqual([f.kind for f in lines.fields],
                         ['string', 'number', 'boolean', 'datetime', 'catalog_ref'])
        self.assertEqual([f.qualifiers for f in lines.fields],
                         [(32,), (12, 2, 'Any'), (), ('DateTime',), ()])
        self.assertEqual(lines.fields[-1].target_catalog_id, categories.identity)
        self.assertEqual(notes.fields[0].qualifiers, (128,))
        self.assertEqual(len(products.fields), 5)

    def test_plain_source_roundtrip(self):
        files = configuration_files_with_sections()
        files[PATH] = b'\xef\xbb\xbf' + files[PATH]
        imported = import_configuration(files)
        self.assertEqual({f.path: f.content for f in imported.files}, files)

    def test_metadata_identities_retained(self):
        files = configuration_files_with_sections()
        identities = {UUID(x) for x in re.findall(rb'uuid="([^"]+)"', files[PATH])
                      for x in [x.decode()]}
        product = import_configuration(files).catalogs[1]
        actual = {product.identity, *(f.identity for f in product.fields)}
        for section in product.tabular_sections:
            actual.add(section.identity)
            actual.update(f.identity for f in section.fields)
        self.assertEqual(identities, actual)

    def test_owner_attribute_section_name_collisions(self):
        for name in ('Text', 'tExT', 'Notes', 'nOtEs', 'Write', 'Записать'):
            files = configuration_files_with_sections()
            edit_section(files, lambda s: s.replace('<Name>Lines</Name>', f'<Name>{name}</Name>'))
            with self.subTest(name=name), self.assertRaises(ValueError):
                import_configuration(files)

    def test_row_names_casefold_unique_and_reserved(self):
        for name in ('Text', 'tExT', 'Code', 'Ссылка', 'LineNumber', 'НомерСтроки'):
            files = configuration_files_with_sections()
            edit_section(files, lambda s: s.replace('<Name>Amount</Name>', f'<Name>{name}</Name>'))
            with self.subTest(name=name), self.assertRaises(ValueError):
                import_configuration(files)

    def test_duplicate_uuid_global_inventory(self):
        for kind in ('Configuration', 'Catalog', 'Attribute', 'TabularSection'):
            files = configuration_files_with_sections()
            source = files['Configuration.xml'] if kind == 'Configuration' else files[PATH]
            identity = re.search(('<' + kind + ' uuid="([^"]+)"').encode(), source)[1].decode()
            edit_section(files, lambda s: re.sub(r'(<Attribute uuid=")[^"]+', r'\g<1>' + identity, s, count=1))
            with self.subTest(kind=kind), self.assertRaises(ValueError):
                import_configuration(files)

    def test_duplicate_section_uuid(self):
        files = configuration_files_with_sections()
        identity = re.search(rb'<Catalog uuid="([^"]+)"', files[PATH])[1].decode()
        edit_section(files, lambda s: re.sub(r'uuid="[^"]+"', f'uuid="{identity}"', s, count=1))
        with self.assertRaises(ValueError): import_configuration(files)

    def test_invalid_section_identity_and_name(self):
        for old, new in [('<Name>Lines</Name>', '<Name>bad name</Name>'),
                         ('<Name>Lines</Name>', '<Name/>')]:
            files = configuration_files_with_sections()
            edit_section(files, lambda s: s.replace(old, new))
            with self.assertRaises(ValueError): import_configuration(files)
        files = configuration_files_with_sections()
        edit_section(files, lambda s: re.sub(r'uuid="[^"]+"', 'uuid="invalid"', s, count=1))
        with self.assertRaises(ValueError): import_configuration(files)

    def test_empty_section_supported(self):
        files = configuration_files_with_sections()
        edit_section(files, lambda s: empty_section('Lines'))
        self.assertEqual(import_configuration(files).catalogs[1].tabular_sections[0].fields, ())

    def test_row_field_limit(self):
        for count in (64, 65):
            files = configuration_files_with_sections()
            def change(s):
                field = re.search(r'<Attribute .*?</Attribute>', s).group()
                fields = ''.join(re.sub(r'uuid="[^"]+"', f'uuid="{uuid4()}"', field)
                                 .replace('<Name>Text</Name>', f'<Name>Field{i}</Name>') for i in range(count))
                return re.sub(r'<ChildObjects>.*</ChildObjects>', '<ChildObjects>' + fields + '</ChildObjects>', s)
            edit_section(files, change)
            if count == 64:
                self.assertEqual(len(import_configuration(files).catalogs[1].tabular_sections[0].fields), 64)
            else:
                with self.assertRaisesRegex(ValueError, 'section field count'): import_configuration(files)

    def test_sections_per_catalog_limit(self):
        for count in (16, 17):
            files = configuration_files_with_sections()
            source = re.sub(r'<TabularSection .*?</TabularSection>', '', files[PATH].decode())
            before, after = source.rsplit('</ChildObjects>', 1)
            files[PATH] = (before + ''.join(empty_section(f'Part{i}') for i in range(count)) + '</ChildObjects>' + after).encode()
            if count == 16:
                self.assertEqual(len(import_configuration(files).catalogs[1].tabular_sections), count)
            else:
                with self.assertRaisesRegex(ValueError, 'tabular section count'): import_configuration(files)

    def test_sections_per_database_limit(self):
        for count in (512, 513):
            files = configuration_files_with_sections()
            template = files['Catalogs/Categories.xml'].decode()
            names = []
            for i, start in enumerate(range(0, count, 16)):
                name = f'Owner{i}'
                names.append('<Catalog>' + name + '</Catalog>')
                source = re.sub(r'uuid="[^"]+"', f'uuid="{uuid4()}"', template)
                source = source.replace('<Name>Categories</Name>', f'<Name>{name}</Name>')
                source = source.replace('</ChildObjects>', ''.join(empty_section(f'Part{j}') for j in range(min(16, count-start))) + '</ChildObjects>')
                files[f'Catalogs/{name}.xml'] = source.encode()
            files['Configuration.xml'] = re.sub(rb'<ChildObjects>.*</ChildObjects>', ('<ChildObjects>' + ''.join(names) + '</ChildObjects>').encode(), files['Configuration.xml'])
            del files[PATH], files['Catalogs/Categories.xml'], files['Catalogs/Products/Ext/ObjectModule.bsl']
            if count == 512:
                self.assertEqual(sum(len(c.tabular_sections) for c in import_configuration(files).catalogs), count)
            else:
                with self.assertRaisesRegex(ValueError, 'tabular section count'): import_configuration(files)

    def test_unknown_child_objects_rejected(self):
        for addition in ('<TabularSection/>', '<Command/>', '<Form/>'):
            files = configuration_files_with_sections()
            edit_section(files, lambda s: s.replace('<ChildObjects>', '<ChildObjects>' + addition, 1))
            with self.subTest(addition=addition), self.assertRaises(ValueError): import_configuration(files)

    def test_nested_attribute_children_rejected(self):
        files = configuration_files_with_sections()
        edit_section(files, lambda s: s.replace('</Attribute>', '<ChildObjects><Attribute/></ChildObjects></Attribute>', 1))
        with self.assertRaises(ValueError): import_configuration(files)

    def test_embedded_executable_components_rejected(self):
        for addition in ('<ObjectModule>Procedure X() EndProcedure</ObjectModule>', '<Script>x</Script>', '<Code>x</Code>'):
            files = configuration_files_with_sections()
            edit_section(files, lambda s: s.replace('<Properties>', '<Properties>' + addition, 1))
            with self.subTest(addition=addition), self.assertRaises(ValueError): import_configuration(files)

    def test_unknown_behavior_blocks_activation(self):
        for target in ('section', 'row'):
            files = configuration_files_with_sections()
            def change(s):
                marker = '<Properties>' if target == 'section' else '<Name>Amount</Name>'
                return s.replace(marker, marker + '<CustomAutomaticBehavior>true</CustomAutomaticBehavior>', 1)
            edit_section(files, change)
            self.assertTrue(any('unsupported metadata property' in issue for issue in import_configuration(files).activation_issues))

    def test_module_guard_preserved(self):
        files = configuration_files_with_sections()
        files['Catalogs/Products/Ext/ObjectModule.bsl'] = b'Procedure BeforeWrite(Cancel)\nEndProcedure'
        self.assertTrue(any('module execution unsupported' in x for x in import_configuration(files).activation_issues))

    def test_reference_targets_and_type_qualifiers_rejected(self):
        for old, new in [('CatalogRef.Categories', 'CatalogRef.Missing'),
                         ('<v8:Length>32</v8:Length>', '<v8:Length>0</v8:Length>'),
                         ('<v8:FractionDigits>2</v8:FractionDigits>', '<v8:FractionDigits>13</v8:FractionDigits>'),
                         ('<v8:DateFractions>DateTime</v8:DateFractions>', '<v8:DateFractions>Date</v8:DateFractions>'),
                         ('<v8:Type>xs:boolean</v8:Type>', '<v8:Type>xs:boolean</v8:Type><v8:Type>xs:string</v8:Type>')]:
            files = configuration_files_with_sections()
            edit_section(files, lambda s: s.replace(old, new))
            with self.subTest(new=new), self.assertRaises(ValueError): import_configuration(files)

    def test_xml_safety_preserved(self):
        files = configuration_files_with_sections()
        files[PATH] = b'<!DOCTYPE x [<!ENTITY x "unsafe">]>' + files[PATH]
        with self.assertRaises(ValueError): import_configuration(files)

    def test_duplicate_properties_rejected(self):
        files = configuration_files_with_sections()
        edit_section(files, lambda s: s.replace('<Name>Lines</Name>', '<Name>Lines</Name><Name>Other</Name>'))
        with self.assertRaises(ValueError): import_configuration(files)


    def test_section_envelope_keeps_strict_pr201_guards(self):
        variants = (
            ('<Properties>', '<Properties unexpected="true">'),
            ('<Comment/>', '<Comment>not an admitted presentation</Comment>'),
            ('<ChildObjects>', '<ChildObjects unexpected="true">'),
        )
        for old, new in variants:
            files = configuration_files_with_sections()
            edit_section(files, lambda section: section.replace(old, new, 1))
            with self.subTest(new=new):
                self.assertTrue(import_configuration(files).activation_issues)

    def test_section_processing_instruction_keeps_pr201_rejection(self):
        files = configuration_files_with_sections()
        edit_section(files, lambda section: section.replace('<Properties>', '<?hidden payload?><Properties>', 1))
        with self.assertRaisesRegex(ValueError, 'processing instructions forbidden'):
            import_configuration(files)

    def test_owner_only_dump_inventory_cannot_hide_sections(self):
        import xml.etree.ElementTree as ET
        files = configuration_files_with_sections()
        md = 'http://v8.1c.ru/8.3/MDClasses'
        di = 'http://v8.1c.ru/8.3/xcf/dumpinfo'
        root = ET.Element('{'+di+'}ConfigDumpInfo', format='Hierarchical', version='2.20')
        versions = ET.SubElement(root, '{'+di+'}ConfigVersions')
        for path, raw in tuple(files.items()):
            if not path.endswith('.xml'): continue
            obj = ET.fromstring(raw)[0]
            name = obj.find('{'+md+'}Properties/{'+md+'}Name').text
            full_name = obj.tag.rsplit('}', 1)[1]+'.'+name
            record = ET.SubElement(versions, '{'+di+'}Metadata', name=full_name,
                                   id=obj.get('uuid'), configVersion='0'*40)
            for field in obj.findall('{'+md+'}ChildObjects/{'+md+'}Attribute'):
                field_name = field.find('{'+md+'}Properties/{'+md+'}Name').text
                ET.SubElement(record, '{'+di+'}Metadata', name=full_name+'.Attribute.'+field_name,
                              id=field.get('uuid'))
        files['ConfigDumpInfo.xml'] = ET.tostring(root, encoding='utf-8')
        result = import_configuration(files)
        self.assertIn('unsupported configuration file:ConfigDumpInfo.xml', result.activation_issues)

    def test_full_native_catalog_profile_is_not_extended_by_guessing(self):
        from test_official_catalog_xml_profile import files as official_files
        source = official_files()
        path = next(path for path in source if path.startswith('Catalogs/'))
        old = source[path]
        section = ('<ChildObjects><TabularSection uuid="'+str(uuid4())+'">'
                   '<Properties><Name>Lines</Name></Properties><ChildObjects/>'
                   '</TabularSection></ChildObjects>').encode()
        source[path] = old.replace(b'<ChildObjects/>', section, 1)
        self.assertNotEqual(source[path], old)
        result = import_configuration(source)
        self.assertTrue(result.activation_issues)
        self.assertEqual({entry.path:entry.content for entry in result.files}, source)


if __name__ == '__main__':
    unittest.main()
