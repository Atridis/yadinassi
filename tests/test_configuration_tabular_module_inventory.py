"""Composition of bounded section metadata and closed, nonexecuting BSL inventory."""
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from yadinassi import Interpreter
from yadinassi.catalog_backend import BackendError
from yadinassi.configuration_xml import import_configuration
from yadinassi.database_context import SQLiteDBContext
from catalog_sections_fixture import configuration_files_with_sections
from test_configuration_module_inventory import (
    CATALOG_KINDS, CONFIGURATION_KINDS, EMPTY_SOURCES, module_bindings,
)


def files():
    return {path: raw for path, raw in configuration_files_with_sections().items()
            if not path.endswith('.bsl')}


class ConfigurationTabularModuleInventoryTests(unittest.TestCase):
    def assert_sections(self, configuration):
        categories, products = configuration.catalogs
        self.assertEqual(categories.tabular_sections, ())
        self.assertEqual([section.name for section in products.tabular_sections],
                         ['Lines', 'Notes'])
        self.assertEqual([field.kind for field in products.tabular_sections[0].fields],
                         ['string', 'number', 'boolean', 'datetime', 'catalog_ref'])
        self.assertEqual(products.tabular_sections[0].fields[-1].target_catalog_id,
                         categories.identity)

    def assert_inactive_archive(self, source, configuration):
        self.assertTrue(configuration.activation_issues)
        self.assert_sections(configuration)
        with tempfile.TemporaryDirectory() as directory:
            active = Path(directory)/'active.sqlite'
            with self.assertRaises(BackendError) as caught:
                SQLiteDBContext.create(active, configuration)
            self.assertEqual(caught.exception.code, 'unsupported')
            self.assertFalse(active.exists())
            archive = Path(directory)/'archive.sqlite'
            with SQLiteDBContext.create(archive, configuration, activate=False) as context:
                self.assert_archived_context(context, source, configuration)
            with SQLiteDBContext(archive) as context:
                self.assert_archived_context(context, source, configuration)

    def assert_archived_context(self, context, source, configuration):
        self.assertFalse(context.backend.activated)
        exported = context.backend.export_configuration()
        self.assertEqual(exported, source)
        self.assertEqual(import_configuration(exported), configuration)
        with self.assertRaises(BackendError) as caught:
            context.backend.begin_read()
        self.assertEqual(caught.exception.code, 'unsupported')
        with self.assertRaises(BackendError) as caught:
            Interpreter(database_context=context)
        self.assertEqual(caught.exception.code, 'unsupported')

    def test_all_canonical_modules_preserve_section_metadata_and_owner_bindings(self):
        source = files()
        for kind in CONFIGURATION_KINDS:
            source['Ext/'+kind+'.bsl'] = EMPTY_SOURCES[-1]
        for name in ('Categories', 'Products'):
            for kind in CATALOG_KINDS:
                source['Catalogs/'+name+'/Ext/'+kind+'.bsl'] = EMPTY_SOURCES[2]
        result = import_configuration(source)
        self.assertEqual(result.activation_issues, ())
        self.assert_sections(result)
        expected = {'Ext/'+kind+'.bsl': (result.config_uuid, kind)
                    for kind in CONFIGURATION_KINDS}
        for catalog in result.catalogs:
            expected.update(('Catalogs/'+catalog.name+'/Ext/'+kind+'.bsl',
                             (catalog.identity, kind)) for kind in CATALOG_KINDS)
        self.assertEqual(module_bindings(result), expected)
        self.assertEqual({entry.path: entry.content for entry in result.files}, source)

    def test_known_empty_modules_allow_section_write_and_reopen(self):
        source = files()
        source['Ext/SessionModule.bsl'] = EMPTY_SOURCES[-1]
        source['Catalogs/Products/Ext/ObjectModule.bsl'] = EMPTY_SOURCES[2]
        result = import_configuration(source)
        self.assertEqual(result.activation_issues, ())
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'active.sqlite'
            with SQLiteDBContext.create(path, result) as context:
                vm = Interpreter(database_context=context)
                vm.execute('O=Catalogs.Products.CreateItem(); O.Code="10"; '
                           'R=O.Lines.Add(); R.Text="kept"; R.Amount=12.50; '
                           'N=O.Notes.Add(); N.Text="also kept"; O.Write();')
                self.assertEqual(context.backend.export_configuration(), source)
                # Empty BSL modules do not opt the unimplemented UI into sections.
                with self.assertRaises(BackendError): context.require_active()
            with SQLiteDBContext(path) as context:
                output = []
                vm = Interpreter(output=output.append, database_context=context)
                vm.execute('O=Catalogs.Products.FindByCode("10").GetObject(); '
                           'Message(O.Lines.Count()); Message(O.Lines[0].Text); '
                           'Message(O.Lines[0].Amount=12.50); Message(O.Notes[0].Text);')
                self.assertEqual(output, ['1', 'kept', 'Да', 'also kept'])
                self.assertEqual(context.backend.export_configuration(), source)

    def test_unknown_empty_modules_do_not_gain_owners_from_sections(self):
        paths = ('Ext/Anything.bsl', 'Catalogs/Missing/Ext/ObjectModule.bsl',
                 'Catalogs/products/Ext/ObjectModule.bsl',
                 'Catalogs/Products/Ext/SessionModule.bsl',
                 'Catalogs/Products/TabularSections/Lines/Ext/ObjectModule.bsl')
        for path in paths:
            with self.subTest(path=path):
                source = files(); source[path] = EMPTY_SOURCES[-1]
                result = import_configuration(source)
                self.assertEqual(result.activation_issues, ('unsupported module path:'+path,))
                self.assertEqual(result.modules, ())
                self.assert_inactive_archive(source, result)

    def test_known_executable_modules_still_block_section_database_activation(self):
        paths = ['Ext/'+kind+'.bsl' for kind in CONFIGURATION_KINDS]
        paths.extend('Catalogs/Products/Ext/'+kind+'.bsl' for kind in CATALOG_KINDS)
        for path in paths:
            with self.subTest(path=path):
                source = files(); source[path] = b'Message("MUST NOT RUN");\n'
                result = import_configuration(source)
                self.assertEqual(result.activation_issues, ('module execution unsupported:'+path,))
                self.assertIn(path, module_bindings(result))
                self.assert_inactive_archive(source, result)

    def test_unknown_executable_module_keeps_both_issues_and_section_archive(self):
        source = files(); path = 'Catalogs/Products/TabularSections/Lines/Ext/ObjectModule.bsl'
        source[path] = b'Message("MUST NOT RUN");\n'
        result = import_configuration(source)
        self.assertEqual(result.activation_issues, (
            'module execution unsupported:'+path, 'unsupported module path:'+path))
        self.assertEqual(result.modules, ())
        self.assert_inactive_archive(source, result)

    def test_unknown_module_preserves_known_binding_and_source_bytes(self):
        source = files(); known = 'Catalogs/Products/Ext/ManagerModule.bsl'
        unknown = 'Catalogs/Products/TabularSections/Lines/Ext/ManagerModule.bsl'
        source[known] = EMPTY_SOURCES[2]; source[unknown] = EMPTY_SOURCES[-1]
        result = import_configuration(source)
        self.assertEqual(module_bindings(result), {known: (result.catalogs[1].identity, 'ManagerModule')})
        self.assertEqual(result.activation_issues, ('unsupported module path:'+unknown,))
        self.assert_inactive_archive(source, result)

    def test_unknown_inventory_count_boundary_preserves_section_archive(self):
        for count in (32, 33):
            with self.subTest(count=count):
                source = files()
                paths = ['Ext/Unknown'+str(index)+'.bsl' for index in range(count)]
                source.update((path, EMPTY_SOURCES[2]) for path in paths)
                result = import_configuration(source)
                expected = (tuple(sorted('unsupported module path:'+path for path in paths))
                            if count == 32 else
                            ('unsupported module paths:33 (individual paths retained in configuration files)',))
                self.assertEqual(result.activation_issues, expected)
                self.assertEqual(result.modules, ())
                self.assert_inactive_archive(source, result)

    def test_astral_unknown_inventory_budget_preserves_section_archive(self):
        source = files()
        paths = ['Ext/'+chr(0x1F600+index)+'\U0001f680'*239+'.bsl' for index in range(32)]
        source.update((path, EMPTY_SOURCES[-1]) for path in paths)
        result = import_configuration(source)
        self.assertEqual(result.activation_issues, (
            'unsupported module paths:32 (individual paths retained in configuration files)',))
        self.assertEqual(result.modules, ())
        self.assert_inactive_archive(source, result)

    def test_summary_does_not_clear_executable_or_section_metadata_issues(self):
        source = files()
        paths = ['Ext/Unknown'+str(index)+'.bsl' for index in range(33)]
        source.update((path, b'') for path in paths)
        source[paths[-1]] = b'Message("MUST NOT RUN");\n'
        source['Catalogs/Products.xml'] = source['Catalogs/Products.xml'].replace(
            b'<Name>Lines</Name>',
            b'<Name>Lines</Name><CustomAutomaticBehavior>true</CustomAutomaticBehavior>')
        result = import_configuration(source)
        self.assertIn('unsupported module paths:33 (individual paths retained in configuration files)',
                      result.activation_issues)
        self.assertIn('module execution unsupported:'+paths[-1], result.activation_issues)
        self.assertTrue(any('CustomAutomaticBehavior' in issue for issue in result.activation_issues))
        self.assert_inactive_archive(source, result)

    def test_known_module_does_not_bypass_embedded_section_code_rejection(self):
        source = files(); source['Ext/SessionModule.bsl'] = b''
        source['Catalogs/Products.xml'] = source['Catalogs/Products.xml'].replace(
            b'<Name>Lines</Name>', b'<Name>Lines</Name><ObjectModule>code</ObjectModule>')
        with self.assertRaisesRegex(ValueError, 'embedded executable component unsupported'):
            import_configuration(source)

    def test_case_colliding_modules_remain_rejected_with_sections(self):
        source = files()
        source['Catalogs/Products/Ext/ObjectModule.bsl'] = b''
        source['Catalogs/products/Ext/ObjectModule.bsl'] = b''
        with self.assertRaisesRegex(ValueError, 'case-colliding paths'):
            import_configuration(source)

    def test_no_modules_leaves_section_profile_active(self):
        source = files(); result = import_configuration(source)
        self.assertEqual(result.activation_issues, ())
        self.assertEqual(result.modules, ())
        self.assert_sections(result)
        self.assertEqual({entry.path: entry.content for entry in result.files}, source)


if __name__ == '__main__':
    unittest.main()
