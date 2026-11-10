"""Explicit composed source ownership; no native application-host claim."""
from contextlib import closing
from dataclasses import replace
from hashlib import sha256
from pathlib import Path
import sqlite3
import tempfile
import unittest

from yadinassi.configuration_application_profile import import_application_configuration, APPLICATION_SOURCE_ISSUE
from yadinassi.configuration_xml import import_catalog_forms_configuration
from yadinassi.configuration_runtime import ConfigurationApplication
from yadinassi.configuration_forms import load_configuration_forms
from yadinassi.sqlite_catalog import SQLiteCatalogBackend
from yadinassi.catalog_backend import BackendError
from yadinassi.database_context import SQLiteDBContext
from configuration_runtime_fixture import module_files, CLIENT
from test_configuration_catalog_profile import catalog_form_sources
from test_configuration_forms import sources


def application_sources(*, catalog=True):
    result = catalog_form_sources() if catalog else sources()
    if catalog:
        common = sources()
        result.update({k:v for k,v in common.items() if k != 'Configuration.xml'})
        result['Configuration.xml'] = result['Configuration.xml'].replace(b'</ChildObjects>',
            b'<CommonForm>Welcome</CommonForm><CommonForm>Details</CommonForm></ChildObjects>')
    result['Configuration.xml'] = result['Configuration.xml'].replace(b'version="2.17"', b'version="2.20"')
    modules = module_files([CLIENT])
    result.update({k:v for k,v in modules.items() if k.startswith('CommonModules/')})
    result['Configuration.xml'] = result['Configuration.xml'].replace(b'</ChildObjects>',
        b'<CommonModule>Tools</CommonModule></ChildObjects>')
    result['Ext/ManagedApplicationModule.bsl'] = b'Procedure OnStart() Message(Tools.Double(2)); EndProcedure'
    return result


class ApplicationProfileTests(unittest.TestCase):
    def test_hierarchical_catalog_not_implicitly_activated(self):
        files = application_sources()
        files['Catalogs/Items.xml'] = files['Catalogs/Items.xml'].replace(
            b'<CodeLength>', b'<Hierarchical>true</Hierarchical><HierarchyType>HierarchyFoldersAndItems</HierarchyType><CodeLength>')
        with self.assertRaisesRegex(ValueError, 'scalar'):
            import_application_configuration(files)

    def test_common_only_profile_and_explicit_start(self):
        files = application_sources(catalog=False)
        configuration = import_application_configuration(files)
        self.assertEqual(configuration.catalogs, ())
        self.assertTrue(configuration.activation_issues[0].startswith(APPLICATION_SOURCE_ISSUE + ':'))
        output = []
        app = ConfigurationApplication(configuration, side='client', output=output.append)
        self.assertEqual(output, [])
        app.start(); self.assertEqual(output, ['4'])

    def test_all_forms_and_original_source_retained(self):
        files = application_sources()
        configuration = import_application_configuration(files)
        self.assertEqual({f.path:f.content for f in configuration.files}, files)
        forms = load_configuration_forms(files, catalog_schemas=configuration.catalogs)
        self.assertEqual(len(forms.forms), 3)
        self.assertEqual(len(configuration.common_modules), 1)
        self.assertEqual({m.kind for m in configuration.modules}, {'CommonModule','ObjectModule','ManagedApplicationModule'})

    def test_old_profile_does_not_acquire_new_authority(self):
        with self.assertRaises(ValueError): import_catalog_forms_configuration(application_sources())

    def test_unknown_module_and_metadata_fail_closed(self):
        for mode in ('session', 'property', 'document', 'orphan'):
            files = application_sources()
            if mode == 'session': files['Ext/SessionModule.bsl'] = b'// forbidden'
            elif mode == 'property': files['CommonModules/Tools.xml'] = files['CommonModules/Tools.xml'].replace(b'<Properties>', b'<Properties><UnknownBehavior>true</UnknownBehavior>')
            elif mode == 'document': files['Configuration.xml'] = files['Configuration.xml'].replace(b'</ChildObjects>', b'<Document>Order</Document></ChildObjects>')
            else: files['CommonForms/Orphan.xml'] = files['CommonForms/Details.xml']
            with self.subTest(mode=mode), self.assertRaises(ValueError): import_application_configuration(files)

    def test_unsupported_object_code_not_hidden_by_composition(self):
        files = application_sources()
        files['Catalogs/Items/Ext/ObjectModule.bsl'] = b'Procedure Evil() Message("no"); EndProcedure'
        with self.assertRaises(ValueError): import_application_configuration(files)

    def test_shared_uuid_collision_rejected(self):
        files = application_sources()
        from xml.etree import ElementTree as ET
        uid = list(ET.fromstring(files['CommonModules/Tools.xml']))[0].get('uuid')
        files['CommonForms/Welcome.xml'] = files['CommonForms/Welcome.xml'].replace(
            b'00000000-0000-0000-0000-000000000065', uid.encode())
        # Use the actual declared form UUID rather than relying on fixture numbering.
        root = ET.fromstring(files['CommonForms/Welcome.xml'])
        list(root)[0].set('uuid', uid)
        files['CommonForms/Welcome.xml'] = ET.tostring(root)
        with self.assertRaises(ValueError): import_application_configuration(files)

    def test_forged_canonical_configuration_rejected(self):
        configuration = import_application_configuration(application_sources())
        with self.assertRaises(ValueError): ConfigurationApplication(replace(configuration, name='Forged'), side='client')

    def test_durable_opt_in_reopen_and_no_legacy_form_grant(self):
        files = application_sources()
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/'owned.sqlite'
            backend = SQLiteCatalogBackend.create_application(path, files)
            self.assertEqual(backend.storage_version, 6)
            self.assertEqual(backend.active_form_catalogs(), ())
            self.assertIsNotNone(backend.catalog_write_preparation(import_application_configuration(files).catalogs[0].identity))
            backend.close()
            backend = SQLiteCatalogBackend(path)
            self.assertEqual(backend.export_configuration(), files)
            backend.close()
            with self.assertRaises(BackendError):
                SQLiteCatalogBackend.create(Path(tmp)/'forged.sqlite', import_application_configuration(files))

    def test_source_replacement_even_with_rehashed_file_rejected(self):
        files = application_sources()
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/'owned.sqlite'
            SQLiteCatalogBackend.create_application(path, files).close()
            changed = files['CommonModules/Tools/Ext/Module.bsl'] + b'\n// changed'
            with closing(sqlite3.connect(path)) as db:
                db.execute('UPDATE configuration_file SET content=?,sha256=? WHERE path=?',
                    (changed, sha256(changed).hexdigest(), 'CommonModules/Tools/Ext/Module.bsl'))
                db.commit()
            with self.assertRaises(BackendError): SQLiteCatalogBackend(path)

    def test_database_source_must_match_application(self):
        files = application_sources()
        with tempfile.TemporaryDirectory() as tmp:
            backend = SQLiteCatalogBackend.create_application(Path(tmp)/'owned.sqlite', files)
            backend.close()
            context = SQLiteDBContext(Path(tmp)/'owned.sqlite')
            try:
                app = ConfigurationApplication(import_application_configuration(files), side='server', database_context=context)
                app.start(); app.close()
                changed = dict(files); changed['Ext/ManagedApplicationModule.bsl'] += b'\n// changed'
                with self.assertRaises(ValueError):
                    ConfigurationApplication(import_application_configuration(changed), side='server', database_context=context)
            finally: context.close()
