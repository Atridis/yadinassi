"""Integration of bounded catalog XML and closed module inventory.

The XML combinations are synthetic compositions, not new native observations.
"""
from pathlib import Path
import tempfile
import unittest

from test_official_catalog_scalar_composition import composed, inventory
from test_official_catalog_scalar_profile import CATALOG, NAME, files
from yadinassi import Interpreter
from yadinassi.catalog_backend import BackendError
from yadinassi.configuration_xml import import_configuration
from yadinassi.database_context import SQLiteDBContext


class ComposedModuleInventoryTests(unittest.TestCase):
    def assert_not_active(self, source):
        try:
            config = import_configuration(source)
        except ValueError:
            return
        self.assertTrue(config.activation_issues)

    def test_empty_prefix_with_default_namespace_never_forms_type_qname(self):
        raw = CATALOG.read_bytes()
        old = b'<v8:Type>xs:boolean</v8:Type>'
        new = (b'<v8:Type xmlns="http://www.w3.org/2001/XMLSchema">'
               b':boolean</v8:Type>')
        self.assertIn(old, raw)
        self.assert_not_active(files(raw.replace(old, new, 1)))

    def test_empty_prefix_with_default_namespace_never_forms_xsi_qname(self):
        raw = CATALOG.read_bytes()
        old = b'<xr:FillValue xsi:type="xs:string"/>'
        new = (b'<xr:FillValue xmlns="http://www.w3.org/2001/XMLSchema" '
               b'xsi:type=":string"/>')
        self.assertIn(old, raw)
        self.assert_not_active(files(raw.replace(old, new, 1)))

    def test_composed_catalog_with_known_inert_modules_reopens_and_writes(self):
        source = inventory(files(composed((1, 0, 1))))
        source['Ext/SessionModule.bsl'] = b'// retained\n'
        source['Catalogs/'+NAME+'/Ext/ObjectModule.bsl'] = b'// retained object\n'
        config = import_configuration(source)
        self.assertEqual(config.activation_issues, ())
        self.assertEqual({item.path: item.content for item in config.files}, source)
        owner = config.catalogs[0].identity
        self.assertEqual({m.path: m.owner for m in config.modules}, {
            'Ext/SessionModule.bsl': config.config_uuid,
            'Catalogs/'+NAME+'/Ext/ObjectModule.bsl': owner,
        })
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'test.sqlite'
            with SQLiteDBContext.create(path, config) as db:
                vm = Interpreter(database_context=db)
                vm.execute('P=Catalogs.'+NAME+'.CreateItem();P.Code="one";'
                           'P.Field0=True;P.Field1=1.25;P.Write();')
            with SQLiteDBContext(path) as db:
                self.assertEqual(db.backend.export_configuration(), source)
                vm = Interpreter(database_context=db)
                vm.execute('P=Catalogs.'+NAME+'.FindByCode("one");')
                self.assertTrue(vm.execute('P.Field0'))
                self.assertEqual(str(vm.execute('P.Field1')), '1.25')

    def test_misplaced_empty_module_blocks_even_when_composition_is_valid(self):
        for path in ('Catalogs/'+NAME+'/Ext/SessionModule.bsl',
                     'Catalogs/Missing/Ext/ObjectModule.bsl',
                     'Catalogs/'+NAME.lower()+'/Ext/ObjectModule.bsl'):
            with self.subTest(path=path):
                source = inventory(files(composed((0, 1))))
                source[path] = b'// no executable code\n'
                config = import_configuration(source)
                self.assertIn('unsupported module path:'+path, config.activation_issues)
                self.assertNotIn(path, {m.path for m in config.modules})
                self.assertEqual({item.path: item.content for item in config.files}, source)
                with tempfile.TemporaryDirectory() as directory:
                    with self.assertRaises(BackendError):
                        SQLiteDBContext.create(Path(directory)/'active.sqlite', config)

    def test_inventory_summary_preserves_xml_and_execution_blockers(self):
        source = inventory(files(composed((2, 0, 2))))
        paths = ['Ext/Unknown'+str(i)+'.bsl' for i in range(33)]
        source.update((path, b'') for path in paths)
        source[paths[0]] = b'X=1;\n'
        source['Unknown.xml'] = b'<Unknown/>'
        config = import_configuration(source)
        self.assertIn('unsupported module paths:33 (individual paths retained in configuration files)',
                      config.activation_issues)
        self.assertIn('module execution unsupported:'+paths[0], config.activation_issues)
        self.assertIn('unsupported configuration file:Unknown.xml', config.activation_issues)
        self.assertEqual({item.path: item.content for item in config.files}, source)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'archive.sqlite'
            with SQLiteDBContext.create(path, config, activate=False) as db:
                self.assertEqual(db.backend.export_configuration(), source)
            with SQLiteDBContext(path) as db:
                self.assertEqual(db.backend.export_configuration(), source)
                with self.assertRaises(BackendError): Interpreter(database_context=db)
