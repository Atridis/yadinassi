"""Synthetic PR202/PR208 composition checks, never native compatibility evidence."""
from copy import deepcopy
from pathlib import Path
import tempfile
import unittest
from uuid import UUID, uuid4
import xml.etree.ElementTree as ET

from catalog_sections_fixture import configuration_files_with_sections
from test_configuration_tabular_sections import edit_section
from test_official_catalog_scalar_composition import composed, inventory
from test_official_catalog_scalar_profile import NAME
from yadinassi import Interpreter
from yadinassi.catalog_backend import BackendError
from yadinassi.configuration_xml import CFG, MD, V8, XR, XS, import_configuration
from yadinassi.database_context import SQLiteDBContext

PRODUCTS = 'Catalogs/Products.xml'
SCALAR = 'Catalogs/'+NAME+'.xml'


def mixed_source(kinds=(1, 0, 2), *, scalar_first=False):
    source = {path: raw for path, raw in configuration_files_with_sections().items()
              if not path.endswith('.bsl')}
    source[SCALAR] = composed(kinds)
    entry = ('<Catalog>'+NAME+'</Catalog>').encode()
    if scalar_first:
        source['Configuration.xml'] = source['Configuration.xml'].replace(
            b'<ChildObjects>', b'<ChildObjects>'+entry, 1)
    else:
        source['Configuration.xml'] = source['Configuration.xml'].replace(
            b'</ChildObjects>', entry+b'</ChildObjects>', 1)
    return source


def serialized(root):
    # ElementTree discards declarations used only by QName-valued text.
    root.set('xmlns:xs', XS)
    root.set('xmlns:cfg', CFG)
    return ET.tostring(root, encoding='utf-8', xml_declaration=True)


class ConfigurationTabularScalarCompositionTests(unittest.TestCase):
    def assert_source(self, result, source):
        self.assertEqual({entry.path: entry.content for entry in result.files}, source)

    def assert_inactive_archive(self, source):
        result = import_configuration(source)
        self.assertTrue(result.activation_issues)
        self.assert_source(result, source)
        with tempfile.TemporaryDirectory() as directory:
            active = Path(directory)/'active.sqlite'
            with self.assertRaises(BackendError):
                SQLiteDBContext.create(active, result)
            self.assertFalse(active.exists())
            path = Path(directory)/'archive.sqlite'
            with SQLiteDBContext.create(path, result, activate=False) as db:
                self.assertEqual(db.backend.export_configuration(), source)
            with SQLiteDBContext(path) as db:
                self.assertEqual(db.backend.export_configuration(), source)
                with self.assertRaises(BackendError):
                    Interpreter(database_context=db)
        return result

    def test_scalar_boundaries_and_section_sibling_keep_independent_schemas(self):
        for kinds in ((), (0,), (1, 0, 2), (0, 1, 2)*21+(1,)):
            for first in (False, True):
                with self.subTest(count=len(kinds), scalar_first=first):
                    source = mixed_source(kinds, scalar_first=first)
                    result = import_configuration(source)
                    self.assertEqual(result.activation_issues, ())
                    self.assert_source(result, source)
                    schemas = {catalog.name: catalog for catalog in result.catalogs}
                    self.assertEqual(len(schemas[NAME].fields), len(kinds))
                    self.assertEqual(schemas[NAME].tabular_sections, ())
                    self.assertEqual([s.name for s in schemas['Products'].tabular_sections],
                                     ['Lines', 'Notes'])
                    self.assertEqual(schemas['Products'].tabular_sections[0].fields[-1].target_catalog_id,
                                     schemas['Categories'].identity)

    def test_modules_retain_real_configuration_and_catalog_owners(self):
        source = mixed_source()
        source['Ext/SessionModule.bsl'] = b'// inert configuration\n'
        for name in ('Products', NAME):
            source['Catalogs/'+name+'/Ext/ObjectModule.bsl'] = b'// inert object\n'
            source['Catalogs/'+name+'/Ext/ManagerModule.bsl'] = b''
        result = import_configuration(source)
        self.assertEqual(result.activation_issues, ())
        schemas = {catalog.name: catalog for catalog in result.catalogs}
        expected = {'Ext/SessionModule.bsl': result.config_uuid}
        for name in ('Products', NAME):
            for kind in ('ObjectModule', 'ManagerModule'):
                expected['Catalogs/'+name+'/Ext/'+kind+'.bsl'] = schemas[name].identity
        self.assertEqual({module.path: module.owner for module in result.modules}, expected)
        self.assert_source(result, source)

    def test_scalar_and_section_writes_reopen_without_source_rewriting(self):
        source = mixed_source()
        source['Catalogs/Products/Ext/ObjectModule.bsl'] = b'// inert\n'
        config = import_configuration(source)
        self.assertEqual(config.activation_issues, ())
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'active.sqlite'
            with SQLiteDBContext.create(path, config) as db:
                vm = Interpreter(database_context=db)
                vm.execute('S=Catalogs.'+NAME+'.CreateItem(); S.Code="scalar"; '
                           'S.Field0=True; S.Field1=12.50; S.Field2=Date(2024,1,2,3,4,5); S.Write(); '
                           'P=Catalogs.Products.CreateItem(); P.Code="owner"; '
                           'R=P.Lines.Add(); R.Text="kept"; R.Amount=2.25; P.Write();')
                self.assertEqual(db.backend.export_configuration(), source)
            with SQLiteDBContext(path) as db:
                output = []
                vm = Interpreter(output=output.append, database_context=db)
                vm.execute('S=Catalogs.'+NAME+'.FindByCode("scalar").GetObject(); '
                           'Message(S.Field0); Message(S.Field1=12.50); '
                           'Message(S.Field2=Date(2024,1,2,3,4,5)); '
                           'P=Catalogs.Products.FindByCode("owner").GetObject(); '
                           'Message(P.Lines.Count()); Message(P.Lines[0].Text); '
                           'Message(P.Lines[0].Amount=2.25);')
                self.assertEqual(output, ['Да', 'Да', 'Да', '1', 'kept', 'Да'])
                self.assertEqual(db.backend.export_configuration(), source)

    def test_owner_only_dump_inventory_stays_blocked_with_scalar_sibling(self):
        source = inventory(mixed_source())
        source['Ext/SessionModule.bsl'] = b'// inert\n'
        result = self.assert_inactive_archive(source)
        self.assertEqual(result.activation_issues, ('unsupported configuration file:ConfigDumpInfo.xml',))

    def test_even_nested_dump_inventory_has_no_unreviewed_section_profile(self):
        source = inventory(mixed_source())
        root = ET.fromstring(source['ConfigDumpInfo.xml'])
        product = next(record for record in root[0] if record.get('name') == 'Catalog.Products')
        section = ET.fromstring(source[PRODUCTS])[0].find('{'+MD+'}ChildObjects/{'+MD+'}TabularSection')
        ET.SubElement(product, product.tag, name='Catalog.Products.TabularSection.Lines',
                      id=section.get('uuid'))
        source['ConfigDumpInfo.xml'] = ET.tostring(root, encoding='utf-8', xml_declaration=True)
        result = self.assert_inactive_archive(source)
        self.assertIn('unsupported configuration file:ConfigDumpInfo.xml', result.activation_issues)

    def test_module_summary_cannot_clear_execution_or_dump_inventory_blockers(self):
        source = inventory(mixed_source())
        source.update(('Ext/Unknown'+str(index)+'.bsl', b'') for index in range(33))
        known = 'Catalogs/'+NAME+'/Ext/ObjectModule.bsl'
        source[known] = b'Message("MUST NOT RUN");\n'
        result = self.assert_inactive_archive(source)
        self.assertIn('module execution unsupported:'+known, result.activation_issues)
        self.assertIn('unsupported module paths:33 (individual paths retained in configuration files)',
                      result.activation_issues)
        self.assertIn('unsupported configuration file:ConfigDumpInfo.xml', result.activation_issues)
        owner = next(catalog.identity for catalog in result.catalogs if catalog.name == NAME)
        self.assertEqual({module.path: module.owner for module in result.modules}, {known: owner})

    def test_rich_scalar_catalog_does_not_admit_appended_section(self):
        for kinds in ((), (0,), (1, 0, 2)):
            with self.subTest(kinds=kinds):
                source = mixed_source(kinds)
                root = ET.fromstring(source[SCALAR])
                section = ET.SubElement(root[0].find('{'+MD+'}ChildObjects'),
                                        '{'+MD+'}TabularSection', uuid=str(uuid4()))
                props = ET.SubElement(section, '{'+MD+'}Properties')
                ET.SubElement(props, '{'+MD+'}Name').text = 'ExtraLines'
                ET.SubElement(section, '{'+MD+'}ChildObjects')
                source[SCALAR] = serialized(root)
                result = self.assert_inactive_archive(source)
                schema = next(catalog for catalog in result.catalogs if catalog.name == NAME)
                self.assertEqual([section.name for section in schema.tabular_sections], ['ExtraLines'])

    def test_rich_scalar_attribute_profile_does_not_transfer_to_section_row(self):
        source = mixed_source((0,))
        rich = ET.fromstring(source[SCALAR])[0].find('{'+MD+'}ChildObjects/{'+MD+'}Attribute')
        rich = deepcopy(rich); rich.set('uuid', str(uuid4()))
        rich.find('{'+MD+'}Properties/{'+MD+'}Name').text = 'RichRowField'
        root = ET.fromstring(source[PRODUCTS])
        root[0].find('{'+MD+'}ChildObjects/{'+MD+'}TabularSection/{'+MD+'}ChildObjects').append(rich)
        source[PRODUCTS] = serialized(root)
        result = self.assert_inactive_archive(source)
        self.assertTrue(any('unsupported metadata property:Products.Lines:' in issue
                            for issue in result.activation_issues))

    def test_section_structural_unicode_spaces_remain_non_inert(self):
        for whitespace in ('\u00a0', '\u0085', '\u2003', '\u2028'):
            for position in ('text', 'tail'):
                for target in ('section', 'properties', 'row', 'type'):
                    source = mixed_source()
                    root = ET.fromstring(source[PRODUCTS])
                    section = root[0].find('{'+MD+'}ChildObjects/{'+MD+'}TabularSection')
                    row = section.find('{'+MD+'}ChildObjects/{'+MD+'}Attribute')
                    node = {'section': section, 'properties': section.find('{'+MD+'}Properties'),
                            'row': row, 'type': row.find('{'+MD+'}Properties/{'+MD+'}Type')}[target]
                    setattr(node, position, '\n'+whitespace+'\n')
                    source[PRODUCTS] = serialized(root)
                    with self.subTest(whitespace=whitespace, position=position, target=target):
                        try:
                            result = import_configuration(source)
                        except ValueError:
                            continue
                        self.assertTrue(result.activation_issues)
                        self.assert_source(result, source)

    def test_empty_or_unbound_type_qname_prefix_still_refuses_section_rows(self):
        for replacement in ('<v8:Type xmlns="'+XS+'">:boolean</v8:Type>',
                            '<v8:Type>missing:boolean</v8:Type>'):
            source = mixed_source()
            edit_section(source, lambda text: text.replace(
                '<v8:Type>xs:boolean</v8:Type>', replacement))
            with self.subTest(replacement=replacement), self.assertRaisesRegex(ValueError, 'unbound type QName'):
                import_configuration(source)

    def test_legal_row_qname_aliases_and_xml_whitespace_remain_supported(self):
        source = mixed_source()
        source[PRODUCTS] = source[PRODUCTS].replace(b'xmlns:xs=', b'xmlns:scalar=').replace(b'xs:', b'scalar:')
        edit_section(source, lambda text: text.replace('<ChildObjects>', '<ChildObjects>\n\t ')
                     .replace('<v8:Type>scalar:boolean</v8:Type>',
                              '<v8:Type> \nscalar:boolean\t </v8:Type>'))
        result = import_configuration(source)
        self.assertEqual(result.activation_issues, ())
        self.assert_source(result, source)

    def test_section_uuid_cannot_collide_with_scalar_generated_identity_in_either_order(self):
        for first in (False, True):
            source = mixed_source(scalar_first=first)
            generated = ET.fromstring(source[SCALAR]).find('.//{'+XR+'}TypeId').text
            self.assertNotEqual(UUID(generated).int, 0)
            edit_section(source, lambda text: text.replace(
                text.split('uuid="', 1)[1].split('"', 1)[0], generated, 1))
            with self.subTest(scalar_first=first), self.assertRaisesRegex(ValueError, 'collision|duplicate generated metadata UUID'):
                import_configuration(source)


if __name__ == '__main__':
    unittest.main()
