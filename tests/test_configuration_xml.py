from pathlib import Path
import sys,unittest
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from yadinassi.configuration_xml import import_configuration
from sqlite_catalog_fixture import configuration_files

class ConfigurationXMLTests(unittest.TestCase):
    def test_owned_scalar_reference_schema_and_exact_source_retained(self):
        files=configuration_files();value=import_configuration(files)
        self.assertEqual(value.activation_issues,())
        self.assertEqual({x.path:x.content for x in value.files},files)
        category,product=value.catalogs
        self.assertEqual(tuple(x.kind for x in product.fields),('string','number','boolean','datetime','catalog_ref'))
        self.assertEqual(product.fields[-1].target_catalog_id,category.identity)
        self.assertEqual(value.modules[0].owner,product.identity)
    def test_modules_persist_but_activation_is_explicitly_blocked(self):
        files=configuration_files();files['Catalogs/Products/Ext/ObjectModule.bsl']=b'Procedure BeforeWrite(Cancel)\nCancel=True;\nEndProcedure'
        result=import_configuration(files)
        self.assertTrue(any('module execution unsupported' in x for x in result.activation_issues))
        self.assertEqual({x.path:x.content for x in result.files},files)
    def test_paths_entities_boundaries_and_case_collisions_refused(self):
        for path in ('../x.xml','/x.xml','Catalogs/../x.xml','x.cf','a\\b.xml','C:x.xml'):
            files=configuration_files();files[path]=b'<x/>'
            with self.subTest(path=path),self.assertRaises(ValueError):import_configuration(files)
        files=configuration_files();files['configuration.xml']=files['Configuration.xml']
        with self.assertRaises(ValueError):import_configuration(files)
        files=configuration_files();files['Configuration.xml']=b'<!DOCTYPE x [<!ENTITY x "x">]><x/>'
        with self.assertRaises(ValueError):import_configuration(files)
    def test_unknown_targets_composites_hierarchy_and_reserved_fields_refused(self):
        for old,new in [(b'CatalogRef.Categories',b'CatalogRef.Missing'),(b'xs:boolean',b'xs:base64Binary'),
                        (b'<Hierarchical>false',b'<Hierarchical>true'),(b'<Name>Text</Name>',b'<Name>Write</Name>')]:
            files=configuration_files();files['Catalogs/Products.xml']=files['Catalogs/Products.xml'].replace(old,new)
            with self.subTest(new=new),self.assertRaises(ValueError):import_configuration(files)
        files=configuration_files();files['Catalogs/Products.xml']=files['Catalogs/Products.xml'].replace(b'<v8:Type>xs:boolean</v8:Type>',b'<v8:Type>xs:boolean</v8:Type><v8:Type>xs:string</v8:Type>')
        with self.assertRaises(ValueError):import_configuration(files)
    def test_unknown_metadata_family_is_not_silently_activated(self):
        files=configuration_files();files['Configuration.xml']=files['Configuration.xml'].replace(b'</ChildObjects>',b'<Document>Orders</Document></ChildObjects>')
        self.assertTrue(import_configuration(files).activation_issues)

    def test_unknown_behavior_and_inline_modules_block_activation(self):
        for addition in (b'<ObjectModule>Procedure BeforeWrite() EndProcedure</ObjectModule>',
                         b'<CustomAutomaticBehavior>true</CustomAutomaticBehavior>'):
            files=configuration_files();files['Catalogs/Products.xml']=files['Catalogs/Products.xml'].replace(b'<Properties>',b'<Properties>'+addition,1)
            self.assertTrue(import_configuration(files).activation_issues)
        files=configuration_files();files[1]=b'x'
        with self.assertRaises(ValueError):import_configuration(files)
    def test_boolean_extra_qualifiers_cannot_be_silently_dropped(self):
        files=configuration_files();files['Catalogs/Products.xml']=files['Catalogs/Products.xml'].replace(b'<v8:Type>xs:boolean</v8:Type>',b'<v8:Type>xs:boolean</v8:Type><v8:StringQualifiers/>')
        with self.assertRaises(ValueError):import_configuration(files)

    def test_auxiliary_xml_is_parsed_not_an_entity_escape_hatch(self):
        files=configuration_files();files['ConfigDumpInfo.xml']=b'<!DOCTYPE x [<!ENTITY x "x">]><x/>'
        with self.assertRaises(ValueError):import_configuration(files)

    def test_numeric_qualifiers_are_bounded_ascii_before_conversion(self):
        for token in ('9'*10000,'٣٢','00032'):
            files=configuration_files();files['Catalogs/Products.xml']=files['Catalogs/Products.xml'].replace(b'<v8:Length>32</v8:Length>',('<v8:Length>'+token+'</v8:Length>').encode())
            with self.subTest(token=token[:10]),self.assertRaises(ValueError):import_configuration(files)
