"""Closed official catalog profile tests; no native-file-format access."""
from pathlib import Path
import sys
import tempfile
import unittest
from uuid import uuid4
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from yadinassi import Interpreter
from yadinassi.configuration_xml import import_configuration
from yadinassi.database_context import SQLiteDBContext

CATALOG = ROOT / 'scripts/catalog_object_behavior/generated/Catalog.xml'
OLD_NAME = 'OwnedCatalog4f4ccaa9'
MD = 'http://v8.1c.ru/8.3/MDClasses'
XR = 'http://v8.1c.ru/8.3/xcf/readable'


def files(catalog=None, name=OLD_NAME, config_id=None):
    config_id = config_id or str(uuid4())
    config = ('<MetaDataObject xmlns="'+MD+'" version="2.20"><Configuration uuid="'+config_id+'">'
              '<Properties><Name>OwnedApplication</Name></Properties><ChildObjects><Catalog>'+name+
              '</Catalog></ChildObjects></Configuration></MetaDataObject>').encode()
    return {'Configuration.xml':config, 'Catalogs/'+name+'.xml':CATALOG.read_bytes() if catalog is None else catalog}


class OfficialCatalogXMLProfileTests(unittest.TestCase):
    def assert_processing_instruction_rejected(self, source, path, content):
        source[path] = content
        with self.assertRaisesRegex(ValueError, 'processing instructions forbidden'):
            import_configuration(source)

    def test_configuration_prologue_processing_instruction_rejected(self):
        source = files(); path = 'Configuration.xml'
        self.assert_processing_instruction_rejected(source, path, b'<?unknown x?>' + source[path])

    def test_configuration_root_processing_instruction_rejected(self):
        source = files(); path = 'Configuration.xml'
        self.assert_processing_instruction_rejected(source, path, source[path].replace(
            b'<Configuration ', b'<?unknown x?><Configuration ', 1))

    def test_configuration_object_processing_instruction_rejected(self):
        source = files(); path = 'Configuration.xml'
        self.assert_processing_instruction_rejected(source, path, source[path].replace(
            b'<Properties>', b'<?unknown x?><Properties>', 1))

    def test_configuration_epilogue_processing_instruction_rejected(self):
        source = files(); path = 'Configuration.xml'
        self.assert_processing_instruction_rejected(source, path, source[path] + b'<?unknown x?>')

    def test_catalog_prologue_processing_instruction_rejected(self):
        source = files(); path = 'Catalogs/' + OLD_NAME + '.xml'
        self.assert_processing_instruction_rejected(source, path, source[path].replace(
            b'?>', b'?>\n<?unknown x?>', 1))

    def test_catalog_root_processing_instruction_rejected(self):
        source = files(); path = 'Catalogs/' + OLD_NAME + '.xml'
        self.assert_processing_instruction_rejected(source, path, source[path].replace(
            b'<Catalog uuid=', b'<?unknown x?><Catalog uuid=', 1))

    def test_catalog_object_processing_instruction_rejected(self):
        source = files(); path = 'Catalogs/' + OLD_NAME + '.xml'
        self.assert_processing_instruction_rejected(source, path, source[path].replace(
            b'<InternalInfo>', b'<?unknown x?><InternalInfo>', 1))

    def test_catalog_epilogue_processing_instruction_rejected(self):
        source = files(); path = 'Catalogs/' + OLD_NAME + '.xml'
        self.assert_processing_instruction_rejected(source, path, source[path] + b'<?unknown x?>')

    def test_xml_declarations_remain_supported(self):
        source = files(); path = 'Configuration.xml'
        source[path] = b'<?xml version="1.0" encoding="UTF-8"?>\n' + source[path]
        self.assertEqual(import_configuration(source).activation_issues, ())

    def test_bom_and_xml_declaration_remain_supported(self):
        source = files(); path = 'Configuration.xml'
        source[path] = b'\xef\xbb\xbf<?xml version="1.0" encoding="UTF-8"?>\n' + source[path]
        self.assertEqual(import_configuration(source).activation_issues, ())

    def test_auxiliary_xml_processing_instructions_rejected(self):
        for content in (b'<?unknown x?><ExportInfo/>',
                        b'<ExportInfo><?unknown x?></ExportInfo>',
                        b'<ExportInfo/><?unknown x?>'):
            with self.subTest(content=content):
                self.assert_processing_instruction_rejected(files(), 'ConfigDumpInfo.xml', content)

    def test_uppercase_auxiliary_xml_processing_instruction_rejected(self):
        self.assert_processing_instruction_rejected(
            files(), 'Other.XML', b'<Extra><?unknown x?></Extra>')

    def test_bom_declaration_and_processing_instruction_rejected(self):
        source = files(); path = 'Configuration.xml'
        source[path] = (b'\xef\xbb\xbf<?xml version="1.0" encoding="UTF-8"?>\n'
                        b'<?unknown x?>' + source[path])
        self.assert_processing_instruction_rejected(source, path, source[path])

    def test_processing_instruction_text_in_comment_is_not_an_instruction(self):
        source = files(); path = 'Configuration.xml'
        source[path] = source[path].replace(b'<Properties>', b'<!-- <?unknown x?> --><Properties>', 1)
        self.assertEqual(import_configuration(source).activation_issues, ())

    def test_processing_instruction_text_in_cdata_is_not_an_instruction(self):
        source = files()
        source['Other.xml'] = b'<Extra><![CDATA[<?unknown x?>]]></Extra>'
        self.assertEqual(import_configuration(source).activation_issues,
                         ('unsupported configuration file:Other.xml',))

    def test_native_redump_verified_catalog_activates_without_normalizing_source(self):
        sources = files()
        config = import_configuration(sources)
        self.assertEqual(config.activation_issues, ())
        self.assertEqual({f.path:f.content for f in config.files}, sources)
        self.assertEqual((config.catalogs[0].name, config.catalogs[0].code_length,
                          config.catalogs[0].description_length), (OLD_NAME, 8, 64))

    def test_end_to_end_sqlite_write_reopen_and_query(self):
        original = files()
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp)/'owned.sqlite'
            context = SQLiteDBContext.create(path, import_configuration(original))
            try:
                runtime = Interpreter(database_context=context)
                runtime.execute('P=Catalogs.'+OLD_NAME+'.CreateItem();P.Code="42";P.Description="owned";P.Write();')
            finally: context.close()
            context = SQLiteDBContext(path)
            try:
                runtime = Interpreter(database_context=context)
                self.assertEqual(runtime.execute('Catalogs.'+OLD_NAME+'.FindByCode("42").Description'), 'owned')
                self.assertEqual(context.backend.export_configuration(), original)
                self.assertEqual(runtime.execute('Q=New Query("SELECT Description AS Name FROM Catalog.'+OLD_NAME+' WHERE Code=&Key");Q.SetParameter("Key","42");S=Q.Execute().Select();S.Next();S.Name;'), 'owned')
            finally: context.close()

    def test_supported_name_identity_and_lengths_can_change(self):
        raw = CATALOG.read_bytes().replace(OLD_NAME.encode(), 'Товары'.encode()).replace(
            b'<CodeLength>8</CodeLength>', b'<CodeLength>12</CodeLength>').replace(
            b'<DescriptionLength>64</DescriptionLength>', b'<DescriptionLength>80</DescriptionLength>')
        tree = ET.fromstring(raw)
        for node in tree.iter():
            for key in ('uuid',):
                if key in node.attrib: node.set(key,str(uuid4()))
            if node.tag in ('{'+XR+'}TypeId','{'+XR+'}ValueId'): node.text = str(uuid4())
        # ElementTree may choose another legal namespace prefix; QName-valued
        # xsi:type attributes are rewritten explicitly in this generated fixture.
        raw = ET.tostring(tree, encoding='utf-8').replace(b'xs:string', b'xs:string')
        # ElementTree does not preserve unused QName namespace declarations.
        raw = raw.replace(b'<ns0:MetaDataObject ', b'<ns0:MetaDataObject xmlns:xs="http://www.w3.org/2001/XMLSchema" ', 1)
        config = import_configuration(files(raw,'Товары'))
        self.assertEqual(config.activation_issues, ())
        self.assertEqual((config.catalogs[0].code_length,config.catalogs[0].description_length), (12,80))

    def test_unknown_or_behavioral_changes_never_activate(self):
        raw = CATALOG.read_bytes()
        mutations = [
            (b'<CodeAllowedLength>Variable</CodeAllowedLength>',b'<CodeAllowedLength>Fixed</CodeAllowedLength>'),
            (b'<Autonumbering>false</Autonumbering>',b'<Autonumbering>true</Autonumbering>'),
            (b'<xr:FillChecking>DontCheck</xr:FillChecking>',b'<xr:FillChecking>ShowError</xr:FillChecking>'),
            (b'<DataHistory>DontUse</DataHistory>',b'<DataHistory>Use</DataHistory>'),
            (b'<Owners/>',b'<Owners><Item>Catalog.Other</Item></Owners>'),
            (b'</Properties>',b'<UnexpectedBehavior>true</UnexpectedBehavior></Properties>'),
        ]
        for old,new in mutations:
            self.assertIn(old,raw)
            with self.subTest(old=old):
                try: result = import_configuration(files(raw.replace(old,new,1)))
                except ValueError: continue
                self.assertTrue(result.activation_issues)

    def test_duplicate_or_cross_object_generated_identity_is_rejected(self):
        raw = CATALOG.read_bytes()
        root = ET.fromstring(raw)
        type_ids = [node.text for node in root.iter() if node.tag == '{'+XR+'}TypeId']
        self.assertGreater(len(type_ids),1)
        with self.assertRaises(ValueError):
            import_configuration(files(raw,config_id=type_ids[0]))
        altered = raw.replace(type_ids[1].encode(), type_ids[0].encode(),1)
        result = import_configuration(files(altered))
        self.assertTrue(result.activation_issues)

    def test_meaningful_string_whitespace_is_not_normalized_away(self):
        raw = CATALOG.read_bytes()
        old = b'<xr:FillValue xsi:type="xs:string"/>'
        self.assertIn(old, raw)
        changed = raw.replace(old, b'<xr:FillValue xsi:type="xs:string"> </xr:FillValue>', 1)
        self.assertTrue(import_configuration(files(changed)).activation_issues)

    def test_qname_namespace_rebinding_does_not_match(self):
        raw = CATALOG.read_bytes().replace(b'xmlns:xs="http://www.w3.org/2001/XMLSchema"', b'xmlns:xs="urn:foreign"')
        self.assertTrue(import_configuration(files(raw)).activation_issues)

    def test_unknown_document_envelope_never_activates_profile(self):
        raw = CATALOG.read_bytes()
        mutations = [(b'version="2.20"',b'version="2.99"'),
                     (b'version="2.20"',b'version="2.20" unexpected="true"')]
        for old, new in mutations:
            with self.subTest(new=new):
                result = import_configuration(files(raw.replace(old, new, 1)))
                self.assertTrue(result.activation_issues)

    def test_existing_minimal_profile_rejects_unchecked_metadata(self):
        mutations = [
            (b'<Properties>', b'<InternalInfo><Unexpected/></InternalInfo><Properties>'),
            (b'<Name>OwnedApplication</Name>', b'<Name behavior="true">OwnedApplication</Name>'),
            (b'version="2.20"', b'version="2.99"'),
            (b'<Catalog>OwnedCatalog', b'<Catalog behavior="true">OwnedCatalog'),
        ]
        for old,new in mutations:
            source = files()
            self.assertIn(old, source['Configuration.xml'])
            source['Configuration.xml'] = source['Configuration.xml'].replace(old,new,1)
            with self.subTest(old=old):
                try: result = import_configuration(source)
                except ValueError: continue
                self.assertTrue(result.activation_issues)
        source = files(); source['ConfigDumpInfo.xml'] = b'<Unexpected>arbitrary</Unexpected>'
        self.assertTrue(import_configuration(source).activation_issues)
        from sqlite_catalog_fixture import configuration_files
        source = configuration_files()
        source['Catalogs/Products.xml'] = source['Catalogs/Products.xml'].replace(
            b'<Attribute uuid=', b'<Attribute behavior="true" uuid=', 1)
        self.assertTrue(import_configuration(source).activation_issues)

    def test_type_and_qualifier_unknown_attributes_are_refused(self):
        from sqlite_catalog_fixture import configuration_files
        mutations = [
            (b'<Type>', b'<Type behavior="true">'),
            (b'<v8:Type>xs:boolean</v8:Type>', b'<v8:Type behavior="true">xs:boolean</v8:Type>'),
            (b'<v8:StringQualifiers>', b'<v8:StringQualifiers behavior="true">'),
            (b'<v8:Length>32</v8:Length>', b'<v8:Length behavior="true">32</v8:Length>'),
        ]
        for old, new in mutations:
            source = configuration_files()
            self.assertIn(old, source['Catalogs/Products.xml'])
            source['Catalogs/Products.xml'] = source['Catalogs/Products.xml'].replace(old,new,1)
            with self.subTest(old=old), self.assertRaises(ValueError):
                import_configuration(source)

    def test_attribute_nested_objects_are_not_ignored(self):
        from sqlite_catalog_fixture import configuration_files
        source = configuration_files()
        old = b'<Name>Text</Name></Properties></Attribute>'
        # Build the mutation at the Attribute start, retaining its valid UUID.
        raw = source['Catalogs/Products.xml']
        marker = b'<Attribute uuid="'
        pos = raw.index(marker); end = raw.index(b'>', pos)+1
        raw = raw[:end] + b'<ChildObjects><Unexpected/></ChildObjects>' + raw[end:]
        source['Catalogs/Products.xml'] = raw
        self.assertTrue(import_configuration(source).activation_issues)

    def test_mixed_sibling_text_is_not_ignored(self):
        for old,new in ((b'</Properties><ChildObjects>',b'</Properties>unexpected<ChildObjects>'),
                        (b'</Name></Properties>',b'</Name>unexpected</Properties>')):
            source = files()
            self.assertIn(old,source['Configuration.xml'])
            source['Configuration.xml'] = source['Configuration.xml'].replace(old,new,1)
            with self.subTest(old=old):
                try: result = import_configuration(source)
                except ValueError: continue
                self.assertTrue(result.activation_issues)

    def test_unknown_metadata_never_bypasses_profile(self):
        raw = CATALOG.read_bytes().replace(b'<ChildObjects/>',b'<ChildObjects><Unexpected/></ChildObjects>')
        try: result = import_configuration(files(raw))
        except ValueError: return
        self.assertTrue(result.activation_issues)


if __name__ == '__main__': unittest.main()
