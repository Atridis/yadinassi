"""Owned authored document profile, not native Designer export evidence."""
from pathlib import Path
import sys
import unittest
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from yadinassi.configuration_xml import ConfigurationImport, import_configuration
from sqlite_catalog_fixture import configuration_files


def document_files(*, catalogs=True, auto='true', fields=True):
    files = configuration_files()
    config = files['Configuration.xml']
    if not catalogs:
        config = config.replace(b'<Catalog>Categories</Catalog><Catalog>Products</Catalog>', b'')
        files = {}
    files['Configuration.xml'] = config.replace(b'</ChildObjects>', b'<Document>Orders</Document></ChildObjects>')
    prefix = config.split(b'<Configuration ')[0].decode()
    attrs = ''
    if fields:
        # Reuse all existing scalar qualifier profiles, including catalog refs.
        product = configuration_files()['Catalogs/Products.xml'].decode()
        attrs = product.split('<ChildObjects>')[1].split('</ChildObjects>')[0]
    rows = f'<Attribute uuid="{uuid4()}"><Properties><Name>Flag</Name><Type><v8:Type>xs:boolean</v8:Type></Type></Properties></Attribute>'
    section = f'<TabularSection uuid="{uuid4()}"><Properties><Name>Lines</Name></Properties><ChildObjects>{rows}</ChildObjects></TabularSection>'
    files['Documents/Orders.xml'] = (prefix + f'<Document uuid="{uuid4()}"><Properties><Name>Orders</Name><NumberType>String</NumberType><NumberLength>9</NumberLength><NumberPeriodicity>Nonperiodical</NumberPeriodicity><CheckUnique>true</CheckUnique><Autonumbering>{auto}</Autonumbering><Posting>Deny</Posting></Properties><ChildObjects>{attrs}{section}</ChildObjects></Document></MetaDataObject>').encode()
    return files


class DocumentConfigurationXMLTests(unittest.TestCase):
    def test_document_schema_fields_sections_and_sources(self):
        files = document_files(); result = import_configuration(files)
        self.assertEqual(result.activation_issues, ())
        document, = result.documents
        self.assertEqual((document.name, document.number_length, document.numbering), ('Orders', 9, 'decimal_v1'))
        self.assertEqual(tuple(f.kind for f in document.fields), ('string', 'number', 'boolean', 'datetime', 'catalog_ref'))
        self.assertEqual(document.fields[-1].target_catalog_id, result.catalogs[0].identity)
        self.assertEqual(document.tabular_sections[0].fields[0].kind, 'boolean')
        self.assertEqual({f.path: f.content for f in result.files}, files)

    def test_document_only_and_explicit_numbering(self):
        result = import_configuration(document_files(catalogs=False, fields=False, auto='false'))
        self.assertEqual(result.catalogs, ())
        self.assertEqual(result.documents[0].numbering, 'explicit')
        self.assertEqual(result.activation_issues, ())

    def test_existing_positional_import_call_and_catalog_profile_unchanged(self):
        result = import_configuration(configuration_files())
        self.assertEqual(result.documents, ())
        self.assertEqual(ConfigurationImport(result.config_uuid, result.name, result.catalogs,
            result.files, result.modules, result.activation_issues), result)

    def test_catalog_numbering_policy_does_not_disable_document_numbering(self):
        for policy in ('explicit', 'decimal_v1'):
            result = import_configuration(document_files(), numbering_policy=policy)
            self.assertEqual(result.documents[0].numbering, 'decimal_v1')
            self.assertEqual(result.catalogs[0].numbering, 'explicit')

    def test_required_semantics_fail_closed(self):
        for tag, value in (('NumberType', 'Number'), ('NumberPeriodicity', 'Year'),
                ('CheckUnique', 'false'), ('Posting', 'Allow'), ('Autonumbering', 'yes'),
                ('NumberLength', '0'), ('NumberLength', '10'), ('NumberLength', '٠١')):
            files = document_files()
            import re
            files['Documents/Orders.xml'] = re.sub(
                f'<{tag}>.*?</{tag}>'.encode(), f'<{tag}>{value}</{tag}>'.encode(), files['Documents/Orders.xml'])
            with self.subTest(tag=tag, value=value), self.assertRaises(ValueError):
                import_configuration(files)

    def test_posting_and_numbering_require_explicit_metadata(self):
        for fragment in (b'<Posting>Deny</Posting>', b'<Autonumbering>true</Autonumbering>',
                         b'<NumberPeriodicity>Nonperiodical</NumberPeriodicity>'):
            files = document_files(); files['Documents/Orders.xml'] = files['Documents/Orders.xml'].replace(fragment, b'')
            with self.subTest(fragment=fragment), self.assertRaises(ValueError): import_configuration(files)

    def test_unknown_behavior_and_generated_types_block_activation(self):
        for fragment in (b'<RegisterRecords/>', b'<CustomBehavior>true</CustomBehavior>',
                         b'<ObjectModule>Procedure Run() EndProcedure</ObjectModule>'):
            files = document_files(); files['Documents/Orders.xml'] = files['Documents/Orders.xml'].replace(b'<Properties>', b'<Properties>'+fragment, 1)
            self.assertTrue(import_configuration(files).activation_issues)
        files = document_files(); files['Documents/Orders.xml'] = files['Documents/Orders.xml'].replace(b'<Properties>', b'<InternalInfo><GeneratedType/></InternalInfo><Properties>', 1)
        self.assertTrue(import_configuration(files).activation_issues)

    def test_envelopes_and_declarations_remain_strict(self):
        for path, old, new in (
            ('Documents/Orders.xml', b'version="2.20"', b'version="2.21"'),
            ('Documents/Orders.xml', b'<NumberType>', b'<NumberType unexpected="yes">'),
            ('Documents/Orders.xml', b'<ChildObjects>', b'<ChildObjects bad="yes">'),
            ('Configuration.xml', b'<Document>Orders</Document>', b'<Document>Orders<Nested/></Document>')):
            files = document_files(); files[path] = files[path].replace(old, new, 1)
            with self.subTest(new=new): self.assertTrue(import_configuration(files).activation_issues)

    def test_document_modules_are_owned_but_only_comments_are_inert(self):
        for kind in ('ObjectModule', 'ManagerModule'):
            files = document_files(); path = f'Documents/Orders/Ext/{kind}.bsl'
            files[path] = '// comment\n// Другой комментарий\n'.encode()
            result = import_configuration(files)
            self.assertEqual(result.activation_issues, ())
            module = next(m for m in result.modules if m.path == path)
            self.assertEqual(module.owner, result.documents[0].identity)
            files[path] += b'Message("not inert");'
            self.assertIn('module execution unsupported:'+path, import_configuration(files).activation_issues)

    def test_unknown_document_module_paths_block_activation(self):
        files = document_files(); files['Documents/Other/Ext/ObjectModule.bsl'] = b'// comment'
        result = import_configuration(files)
        self.assertTrue(any('unsupported module path:' in issue for issue in result.activation_issues))

    def test_names_have_separate_namespaces_but_ids_do_not(self):
        files = document_files()
        files['Documents/Categories.xml'] = files.pop('Documents/Orders.xml').replace(b'<Name>Orders</Name>', b'<Name>Categories</Name>')
        files['Configuration.xml'] = files['Configuration.xml'].replace(b'<Document>Orders</Document>', b'<Document>Categories</Document>')
        result = import_configuration(files)
        self.assertEqual(result.activation_issues, ())
        self.assertEqual(result.documents[0].name, result.catalogs[0].name)
        source = files['Documents/Categories.xml']
        files['Documents/Categories.xml'] = source.replace(str(result.documents[0].identity).encode(), str(result.catalogs[0].identity).encode())
        with self.assertRaises(ValueError): import_configuration(files)

    def test_field_and_section_uuids_are_globally_unique(self):
        for target in ('catalog', 'field', 'section'):
            files = document_files(); result = import_configuration(files); document = result.documents[0]
            identity = {'catalog': result.catalogs[0].identity, 'field': result.catalogs[1].fields[0].identity,
                        'section': document.tabular_sections[0].identity}[target]
            files['Documents/Orders.xml'] = files['Documents/Orders.xml'].replace(str(document.fields[0].identity).encode(), str(identity).encode())
            with self.subTest(target=target), self.assertRaises(ValueError): import_configuration(files)

    def test_reserved_fields_and_document_reference_types_refused(self):
        for old, new in ((b'<Name>Text</Name>', b'<Name>Number</Name>'),
                         (b'cfg:CatalogRef.Categories', b'cfg:DocumentRef.Orders'),
                         (b'<Name>Flag</Name>', b'<Name>LineNumber</Name>')):
            files = document_files(); files['Documents/Orders.xml'] = files['Documents/Orders.xml'].replace(old, new)
            with self.subTest(new=new), self.assertRaises(ValueError): import_configuration(files)

    def test_duplicate_document_declarations_and_unknown_catalog_refs_refused(self):
        files = document_files(); files['Configuration.xml'] = files['Configuration.xml'].replace(b'<Document>Orders</Document>', b'<Document>Orders</Document><Document>orders</Document>')
        with self.assertRaises(ValueError): import_configuration(files)
        files = document_files(); files['Documents/Orders.xml'] = files['Documents/Orders.xml'].replace(b'CatalogRef.Categories', b'CatalogRef.Missing')
        with self.assertRaises(ValueError): import_configuration(files)

    def test_missing_document_source_preserves_inactive_legacy_archive(self):
        files = document_files(); del files['Documents/Orders.xml']
        result = import_configuration(files)
        self.assertEqual(result.documents, ())
        self.assertIn('missing document XML:Orders', result.activation_issues)

    def test_catalog_dump_info_is_not_evidence_of_document_inventory(self):
        files = document_files(); files['ConfigDumpInfo.xml'] = b'<ConfigDumpInfo/>'
        self.assertIn('unsupported configuration file:ConfigDumpInfo.xml', import_configuration(files).activation_issues)


if __name__ == '__main__':
    unittest.main()
