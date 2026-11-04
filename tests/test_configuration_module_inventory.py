"""Closed Designer module paths; no configured BSL is executed by import."""
from pathlib import Path
import json
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from yadinassi import Interpreter
from yadinassi.catalog_backend import BackendError
from yadinassi.configuration_xml import import_configuration
from yadinassi.database_context import SQLiteDBContext
from sqlite_catalog_fixture import configuration_files


CONFIGURATION_KINDS = ('ManagedApplicationModule', 'OrdinaryApplicationModule',
                       'ExternalConnectionModule', 'SessionModule')
CATALOG_KINDS = ('ObjectModule', 'ManagerModule')
EMPTY_SOURCES = (b'', b' \t\r\n', b'\xef\xbb\xbf// preserved comment\r\n',
                 '// Сохранённый комментарий\n\t// Second line\n'.encode('utf-8'))


def files():
    return {path: raw for path, raw in configuration_files().items()
            if not path.endswith('.bsl')}


def module_bindings(configuration):
    return {module.path: (module.owner, module.kind) for module in configuration.modules}


class ConfigurationModuleInventoryTests(unittest.TestCase):
    def assert_unknown(self, path, raw=b'// no executable code\r\n'):
        source = files()
        source[path] = raw
        result = import_configuration(source)
        self.assertIn('unsupported module path:'+path, result.activation_issues)
        self.assertNotIn(path, module_bindings(result))
        self.assertEqual({entry.path: entry.content for entry in result.files}, source)
        return result

    def test_configuration_without_modules_stays_active(self):
        result = import_configuration(files())
        self.assertEqual(result.activation_issues, ())
        self.assertEqual(result.modules, ())

    def test_known_configuration_modules_accept_only_empty_source_semantics(self):
        for kind in CONFIGURATION_KINDS:
            for raw in EMPTY_SOURCES:
                with self.subTest(kind=kind, raw=raw):
                    source = files(); path = 'Ext/'+kind+'.bsl'; source[path] = raw
                    result = import_configuration(source)
                    self.assertEqual(result.activation_issues, ())
                    self.assertEqual(module_bindings(result), {path: (result.config_uuid, kind)})
                    self.assertEqual({entry.path: entry.content for entry in result.files}, source)

    def test_known_catalog_modules_bind_to_each_exact_metadata_owner(self):
        for name in ('Categories', 'Products'):
            for kind in CATALOG_KINDS:
                for raw in EMPTY_SOURCES:
                    with self.subTest(name=name, kind=kind, raw=raw):
                        source = files(); path = 'Catalogs/'+name+'/Ext/'+kind+'.bsl'; source[path] = raw
                        result = import_configuration(source)
                        identity = next(c.identity for c in result.catalogs if c.name == name)
                        self.assertEqual(result.activation_issues, ())
                        self.assertEqual(module_bindings(result), {path: (identity, kind)})
                        self.assertEqual({entry.path: entry.content for entry in result.files}, source)

    def test_all_known_paths_coexist_without_owner_or_kind_aliasing(self):
        source = files()
        for kind in CONFIGURATION_KINDS:
            source['Ext/'+kind+'.bsl'] = EMPTY_SOURCES[-1]
        for name in ('Categories', 'Products'):
            for kind in CATALOG_KINDS:
                source['Catalogs/'+name+'/Ext/'+kind+'.bsl'] = EMPTY_SOURCES[-1]
        result = import_configuration(source)
        expected = {'Ext/'+kind+'.bsl': (result.config_uuid, kind) for kind in CONFIGURATION_KINDS}
        for catalog in result.catalogs:
            for kind in CATALOG_KINDS:
                expected['Catalogs/'+catalog.name+'/Ext/'+kind+'.bsl'] = (catalog.identity, kind)
        self.assertEqual(result.activation_issues, ())
        self.assertEqual(module_bindings(result), expected)
        self.assertEqual(len(result.modules), 8)

    def test_unknown_root_module_names_do_not_activate(self):
        for name in ('Anything', 'Module', 'ObjectModule', 'ManagerModule',
                     'CommandModule', 'RecordSetModule', 'ValueManagerModule'):
            for raw in EMPTY_SOURCES:
                with self.subTest(name=name, raw=raw): self.assert_unknown('Ext/'+name+'.bsl', raw)

    def test_unknown_or_wrong_kind_catalog_modules_do_not_activate(self):
        for name in (*CONFIGURATION_KINDS, 'Anything', 'Module', 'CommandModule',
                     'RecordSetModule', 'ValueManagerModule'):
            with self.subTest(name=name): self.assert_unknown('Catalogs/Products/Ext/'+name+'.bsl')

    def test_absent_catalog_owner_is_not_relabelled_as_configuration(self):
        for kind in CATALOG_KINDS:
            with self.subTest(kind=kind): self.assert_unknown('Catalogs/Missing/Ext/'+kind+'.bsl')

    def test_catalog_owner_path_requires_exact_declared_name(self):
        for name in ('products', 'PRODUCTS', 'Product', 'CategoriesExtra'):
            with self.subTest(name=name): self.assert_unknown('Catalogs/'+name+'/Ext/ObjectModule.bsl')

    def test_other_metadata_family_paths_stay_unsupported(self):
        for path in ('Documents/Products/Ext/ObjectModule.bsl',
                     'InformationRegisters/Products/Ext/RecordSetModule.bsl',
                     'CommonModules/Products/Ext/Module.bsl',
                     'Reports/Products/Ext/ObjectModule.bsl',
                     'DataProcessors/Products/Ext/ObjectModule.bsl'):
            with self.subTest(path=path): self.assert_unknown(path)

    def test_nested_flat_and_misplaced_paths_stay_unsupported(self):
        for path in ('ObjectModule.bsl', 'Configuration/Ext/SessionModule.bsl',
                     'Ext/Extra/SessionModule.bsl', 'Catalogs/Products/ObjectModule.bsl',
                     'Catalogs/Products/Ext/Nested/ObjectModule.bsl',
                     'Catalogs/Products/Forms/Main/Ext/Form/Module.bsl',
                     'Catalogs/Products/Commands/Run/Ext/CommandModule.bsl'):
            with self.subTest(path=path): self.assert_unknown(path)

    def test_directory_filename_and_suffix_aliases_are_not_admitted(self):
        for path in ('ext/SessionModule.bsl', 'Ext/sessionModule.bsl', 'Ext/SessionModule.BSL',
                     'catalogs/Products/Ext/ObjectModule.bsl',
                     'Catalogs/Products/ext/ObjectModule.bsl',
                     'Catalogs/Products/Ext/objectmodule.bsl',
                     'Catalogs/Products/Ext/ObjectModule.Bsl'):
            with self.subTest(path=path): self.assert_unknown(path)

    def test_duplicate_case_aliases_keep_the_existing_global_rejection(self):
        source = files()
        source['Catalogs/Products/Ext/ObjectModule.bsl'] = b''
        source['Catalogs/products/Ext/ObjectModule.bsl'] = b''
        with self.assertRaisesRegex(ValueError, 'case-colliding paths'):
            import_configuration(source)

    def test_known_executable_modules_keep_execution_activation_issue(self):
        paths = ['Ext/'+kind+'.bsl' for kind in CONFIGURATION_KINDS]
        paths.extend('Catalogs/Products/Ext/'+kind+'.bsl' for kind in CATALOG_KINDS)
        for path in paths:
            with self.subTest(path=path):
                source = files(); source[path] = b'Message("MUST NOT RUN");\n'
                result = import_configuration(source)
                self.assertEqual(result.activation_issues, ('module execution unsupported:'+path,))
                self.assertIn(path, module_bindings(result))
                self.assertEqual({entry.path: entry.content for entry in result.files}, source)

    def test_unknown_executable_module_has_both_independent_issues(self):
        path = 'Ext/Anything.bsl'
        result = self.assert_unknown(path, b'Message("MUST NOT RUN");\n')
        self.assertEqual(result.activation_issues, (
            'module execution unsupported:'+path, 'unsupported module path:'+path))

    def test_unknown_empty_module_blocks_active_database_creation(self):
        source = files(); source['Ext/Anything.bsl'] = b'// preserved\n'
        result = import_configuration(source)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'active.sqlite'
            with self.assertRaises(BackendError): SQLiteDBContext.create(path, result)
            self.assertFalse(path.exists())

    def test_unknown_source_survives_inactive_archive_and_reopen(self):
        source = files(); source['Catalogs/Missing/Ext/ObjectModule.bsl'] = EMPTY_SOURCES[-1]
        result = import_configuration(source)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'archive.sqlite'
            with SQLiteDBContext.create(path, result, activate=False) as context:
                self.assertEqual(context.backend.export_configuration(), source)
                with self.assertRaises(BackendError): Interpreter(database_context=context)
            with SQLiteDBContext(path) as context:
                self.assertEqual(context.backend.export_configuration(), source)
                with self.assertRaises(BackendError): Interpreter(database_context=context)

    def test_known_empty_modules_preserve_active_database_and_reopen(self):
        source = files(); source['Ext/SessionModule.bsl'] = EMPTY_SOURCES[-1]
        source['Catalogs/Products/Ext/ObjectModule.bsl'] = EMPTY_SOURCES[2]
        result = import_configuration(source)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'active.sqlite'
            with SQLiteDBContext.create(path, result) as context:
                Interpreter(database_context=context)
                self.assertEqual(context.backend.export_configuration(), source)
            with SQLiteDBContext(path) as context:
                Interpreter(database_context=context)
                self.assertEqual(context.backend.export_configuration(), source)

    def test_unknown_path_does_not_remove_known_module_binding(self):
        source = files(); known = 'Catalogs/Products/Ext/ManagerModule.bsl'
        unknown = 'Catalogs/Missing/Ext/ManagerModule.bsl'
        source[known] = b''; source[unknown] = b''
        result = import_configuration(source)
        identity = next(c.identity for c in result.catalogs if c.name == 'Products')
        self.assertEqual(result.activation_issues, ('unsupported module path:'+unknown,))
        self.assertEqual(module_bindings(result), {known: (identity, 'ManagerModule')})
        self.assertEqual({entry.path: entry.content for entry in result.files}, source)

    def test_small_unknown_inventory_preserves_each_exact_path_diagnostic(self):
        source = files()
        paths = ('Ext/Anything.bsl', 'Catalogs/Missing/Ext/ObjectModule.bsl',
                 'Catalogs/Products/Ext/SessionModule.bsl')
        source.update((path, EMPTY_SOURCES[-1]) for path in paths)
        result = import_configuration(source)
        self.assertEqual(result.activation_issues, tuple(sorted(
            'unsupported module path:'+path for path in paths)))
        self.assertEqual(result.modules, ())
        self.assertEqual({entry.path: entry.content for entry in result.files}, source)

    def test_detailed_unknown_inventory_boundary_is_32_paths(self):
        for count in (32, 33):
            with self.subTest(count=count):
                source = files()
                paths = ['Ext/Unknown'+str(index)+'.bsl' for index in range(count)]
                source.update((path, b'') for path in paths)
                result = import_configuration(source)
                expected = (tuple(sorted('unsupported module path:'+path for path in paths))
                            if count == 32 else
                            ('unsupported module paths:33 (individual paths retained in configuration files)',))
                self.assertEqual(result.activation_issues, expected)
                self.assertEqual({entry.path: entry.content for entry in result.files}, source)

    def test_300_long_unknown_paths_keep_inactive_archive_and_block_activation(self):
        source = files()
        paths = ['Ext/Unknown'+format(index, '03d')+'x'*230+'.bsl' for index in range(300)]
        self.assertTrue(all(len(path) == 248 for path in paths))
        previous_diagnostics = ['unsupported module path:'+path for path in paths]
        self.assertEqual(len(json.dumps(previous_diagnostics, separators=(',', ':'))), 82501)
        for index, path in enumerate(paths): source[path] = EMPTY_SOURCES[index % len(EMPTY_SOURCES)]
        result = import_configuration(source)
        self.assertEqual(result.activation_issues, (
            'unsupported module paths:300 (individual paths retained in configuration files)',))
        self.assertEqual(result.modules, ())
        self.assertEqual({entry.path: entry.content for entry in result.files}, source)
        with tempfile.TemporaryDirectory() as directory:
            active = Path(directory)/'active.sqlite'
            with self.assertRaises(BackendError): SQLiteDBContext.create(active, result)
            self.assertFalse(active.exists())
            archive = Path(directory)/'archive.sqlite'
            with SQLiteDBContext.create(archive, result, activate=False) as context:
                self.assertEqual(context.backend.export_configuration(), source)
                with self.assertRaises(BackendError): Interpreter(database_context=context)
            with SQLiteDBContext(archive) as context:
                self.assertEqual(context.backend.export_configuration(), source)
                with self.assertRaises(BackendError): Interpreter(database_context=context)

    def test_summary_preserves_independent_code_and_xml_activation_issues(self):
        for paths in (['Ext/Unknown'+str(index)+'.bsl' for index in range(33)],
                      ['Ext/'+chr(0x1F600+index)+'\U0001f680'*239+'.bsl' for index in range(32)]):
            with self.subTest(count=len(paths)):
                source = files()
                source.update((path, b'') for path in paths)
                source[paths[-1]] = b'Message("MUST NOT RUN");\n'
                source['Other.xml'] = b'<Unknown/>'
                result = import_configuration(source)
                self.assertEqual(result.activation_issues, tuple(sorted((
                    'unsupported module paths:'+str(len(paths))+' (individual paths retained in configuration files)',
                    'module execution unsupported:'+paths[-1],
                    'unsupported configuration file:Other.xml'))))
                self.assertEqual({entry.path: entry.content for entry in result.files}, source)

    def test_32_astral_paths_keep_inactive_archive_with_bounded_diagnostics(self):
        source = files()
        paths = ['Ext/'+chr(0x1F600+index)+'\U0001f680'*239+'.bsl' for index in range(32)]
        self.assertTrue(all(len(path) == 248 for path in paths))
        previous_diagnostics = ['unsupported module path:'+path for path in paths]
        self.assertEqual(len(json.dumps(previous_diagnostics, ensure_ascii=True,
                                       separators=(',', ':'))), 93281)
        for index, path in enumerate(paths): source[path] = EMPTY_SOURCES[index % len(EMPTY_SOURCES)]
        result = import_configuration(source)
        self.assertEqual(result.activation_issues, (
            'unsupported module paths:32 (individual paths retained in configuration files)',))
        self.assertEqual(result.modules, ())
        self.assertEqual({entry.path: entry.content for entry in result.files}, source)
        with tempfile.TemporaryDirectory() as directory:
            active = Path(directory)/'active.sqlite'
            with self.assertRaises(BackendError): SQLiteDBContext.create(active, result)
            self.assertFalse(active.exists())
            archive = Path(directory)/'archive.sqlite'
            with SQLiteDBContext.create(archive, result, activate=False) as context:
                self.assertEqual(context.backend.export_configuration(), source)
                with self.assertRaises(BackendError): Interpreter(database_context=context)
            with SQLiteDBContext(archive) as context:
                self.assertEqual(context.backend.export_configuration(), source)
                with self.assertRaises(BackendError): Interpreter(database_context=context)

    def test_unknown_diagnostic_json_budget_boundaries_are_exact(self):
        for serialized_size, last_path_length in ((8191, 227), (8192, 228), (8193, 229)):
            with self.subTest(serialized_size=serialized_size):
                source = files()
                lengths = [229]*31+[last_path_length]
                paths = ['Ext/Unknown'+format(index, '02d')+'x'*(length-17)+'.bsl'
                         for index, length in enumerate(lengths)]
                diagnostics = tuple(sorted('unsupported module path:'+path for path in paths))
                self.assertEqual(len(json.dumps(diagnostics, ensure_ascii=True,
                                               separators=(',', ':'))), serialized_size)
                source.update((path, b'') for path in paths)
                result = import_configuration(source)
                expected = (diagnostics if serialized_size <= 8192 else
                            ('unsupported module paths:32 (individual paths retained in configuration files)',))
                self.assertEqual(result.activation_issues, expected)
                self.assertEqual({entry.path: entry.content for entry in result.files}, source)


if __name__ == '__main__':
    unittest.main()
