"""Explicit exact-demo creation through user-facing CLI, without native 1C/browser."""
from contextlib import closing, redirect_stderr, redirect_stdout
from io import StringIO
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from legacy_demo_fixture import legacy_demo_files
from yadinassi import cli
from yadinassi.catalog_backend import BackendError
from yadinassi.configuration_import import read_configuration_directory
from yadinassi.database_context import SQLiteDBContext
from yadinassi.sqlite_catalog import SQLiteCatalogBackend
from yadinassi.ui.catalog_editor import CatalogEditorApplication
from yadinassi.ui.protocol import CatalogRef

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'examples/demo'


class DemoCreationCLITests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.database = self.root / 'демо база.sqlite'

    def arguments(self, *, source=SOURCE, database=None):
        return ['--create-demo-db', str(self.database if database is None else database),
                '--import-xml', str(source)]

    def run_cli(self, arguments=None):
        out, err = StringIO(), StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = cli.main(self.arguments() if arguments is None else arguments)
        return code, out.getvalue(), err.getvalue()

    def test_create_retains_all_original_bytes_and_three_empty_catalogs(self):
        result = self.run_cli()
        self.assertEqual(result[0], 0, result)
        self.assertIn('Created main demo SQLite database:', result[1])
        self.assertIn('not native 1C', result[1])
        self.assertEqual(result[2], '')
        with closing(SQLiteCatalogBackend(self.database)) as backend:
            self.assertEqual(backend.export_configuration(), read_configuration_directory(SOURCE))
            self.assertEqual(backend.format_version, 16)
        with closing(CatalogEditorApplication(SQLiteDBContext(self.database))) as app:
            inventory = app.snapshot()['state']['catalogs']
            self.assertEqual({entry['name'] for entry in inventory},
                             {'ВидыНоменклатуры', 'Склады', 'Номенклатура'})
            for entry in inventory:
                app.select(entry['id'])
                self.assertEqual(app.snapshot()['state']['list']['total'], 0)

    def test_created_database_runs_original_editor_save_check_and_reopen(self):
        self.assertEqual(self.run_cli()[0], 0)
        app = CatalogEditorApplication(SQLiteDBContext(self.database))
        self.addCleanup(app.close)
        catalogs = {entry['name']: entry['id'] for entry in app.snapshot()['state']['catalogs']}

        def change(name, value):
            field = next(f for f in app.editor.snapshot()['fields'] if f['name'] == name)
            app.event('change', control=field['control'], value=value)

        def save():
            app.event('command', control='SaveButton')
            self.assertEqual(app.editor.save_state, 'saved')
            ref = app.editor.object.get_member('Ref')
            result = CatalogRef(str(ref.value_type.metadata_uuid), str(ref.reference_uuid))
            app.event('closeCard')
            return result

        app.select(catalogs['ВидыНоменклатуры']); app.open()
        change('Description', 'АБ')
        app.event('command', control='SaveButton')
        self.assertEqual(app.editor.error, 'form_validation')
        self.assertTrue(app.editor.object.is_new())
        change('Description', '  Товары  ')
        kind = save()
        app.select(catalogs['Склады']); app.open()
        change('Description', 'Основной склад')
        warehouse = save()
        app.select(catalogs['Номенклатура']); app.open()
        change('Description', '  Кабель USB-C  ')
        change('ВидНоменклатуры', kind)
        app.event('addRow', section='Склады')
        row = app.editor.snapshot()['sections'][0]['rows'][0]['id']
        app.event('changeRow', section='Склады', row=row, value=warehouse)
        product = save()
        app.check_card(product)
        self.assertTrue(app.list_messages)
        self.assertIn('Карточка заполнена корректно', app.list_messages[0].text)
        app.close()
        with closing(CatalogEditorApplication(SQLiteDBContext(self.database))) as reopened:
            reopened.select(product.catalog); reopened.open(product)
            values = {f['name']: f['inputText'] for f in reopened.editor.snapshot()['fields']}
            self.assertEqual(values['Code'], '000000001')
            self.assertEqual(values['Description'], 'Кабель USB-C')
            rows = reopened.editor.snapshot()['sections'][0]['rows']
            self.assertEqual(rows[0]['id'], row)
            self.assertEqual(rows[0]['field']['value']['record'], warehouse.record)

    def test_existing_arbitrary_destination_is_never_overwritten(self):
        self.database.write_bytes(b'owned sentinel')
        result = self.run_cli()
        self.assertEqual(result[0], 1)
        self.assertIn('preserve and inspect', result[2])
        self.assertEqual(self.database.read_bytes(), b'owned sentinel')

    def test_repeated_creation_does_not_reset_existing_demo(self):
        self.assertEqual(self.run_cli()[0], 0)
        before = self.database.read_bytes()
        self.assertEqual(self.run_cli()[0], 1)
        self.assertEqual(self.database.read_bytes(), before)

    def test_older_profile_is_not_upgraded(self):
        SQLiteCatalogBackend.create_demo_kinds(self.database, legacy_demo_files()).close()
        before = self.database.read_bytes()
        self.assertEqual(self.run_cli()[0], 1)
        self.assertEqual(self.database.read_bytes(), before)
        with closing(CatalogEditorApplication(SQLiteDBContext(self.database))) as app:
            self.assertEqual([c['name'] for c in app.snapshot()['state']['catalogs']], ['ВидыНоменклатуры'])

    def test_modified_missing_extra_or_unrelated_source_is_refused_before_creation(self):
        from sqlite_catalog_fixture import configuration_files
        for kind in ('modified', 'missing', 'extra', 'unrelated'):
            with self.subTest(kind=kind):
                source = self.root / kind
                shutil.copytree(SOURCE, source)
                module = source / 'Catalogs/Номенклатура/Ext/ObjectModule.bsl'
                if kind == 'modified': module.write_bytes(module.read_bytes() + b'\n')
                elif kind == 'missing': module.unlink()
                elif kind == 'extra': (source / 'extra.xml').write_bytes(b'<extra/>')
                else:
                    shutil.rmtree(source); source.mkdir()
                    for name, content in configuration_files().items():
                        target = source / name; target.parent.mkdir(parents=True, exist_ok=True)
                        target.write_bytes(content)
                self.assertEqual(self.run_cli(self.arguments(source=source))[0], 1)
                self.assertFalse(self.database.exists())

    def test_unsafe_source_alias_is_refused(self):
        source = self.root / 'linked-source'
        try: source.symlink_to(SOURCE, target_is_directory=True)
        except (OSError, NotImplementedError): self.skipTest('directory symlinks unavailable')
        self.assertEqual(self.run_cli(self.arguments(source=source))[0], 1)
        self.assertFalse(self.database.exists())

    def test_source_reader_refusal_never_reaches_creation(self):
        with patch('yadinassi.configuration_import.read_configuration_directory',
                   side_effect=ValueError('/PRIVATE/source')), \
             patch.object(SQLiteCatalogBackend, 'create_main_demo') as create:
            result = self.run_cli()
        create.assert_not_called()
        self.assertEqual(result, (1, '', 'yadinassi: configuration import refused\n'))
        self.assertFalse(self.database.exists())

    def test_creation_flags_are_explicit_and_exclusive(self):
        base = self.arguments()
        invalid = [base[:2], base[2:], base + ['--create-db', str(self.root / 'other.sqlite')],
                   base + ['--inactive'], base + ['--numbering-policy', 'explicit'],
                   base + ['--numbering-policy', 'decimal_v1'], base + ['--f', 'missing.sqlite'],
                   base + ['-c', 'Message(1);'], base + ['missing.bsl']]
        for arguments in invalid:
            with self.subTest(arguments=arguments), redirect_stderr(StringIO()), \
                 patch('yadinassi.configuration_import.read_configuration_directory') as read, \
                 self.assertRaises(SystemExit) as error:
                cli.main(arguments)
            self.assertEqual(error.exception.code, 2)
            read.assert_not_called()
        self.assertFalse(self.database.exists())

    def test_empty_paths_and_nonexistent_source_do_not_create(self):
        for arguments in (self.arguments(source=''), self.arguments(database=''),
                          self.arguments(source=self.root / 'missing')):
            with self.subTest(arguments=arguments):
                self.assertEqual(self.run_cli(arguments)[0], 1)
                self.assertFalse(self.database.exists())

    def test_demo_creation_does_not_instantiate_interpreter_or_ui(self):
        with patch.object(cli, 'Interpreter', side_effect=AssertionError('BSL execution')), \
             patch('yadinassi.ui.local_app.RuntimeBridge', side_effect=AssertionError('UI launch')):
            self.assertEqual(self.run_cli()[0], 0)

    def test_creation_errors_are_finite_and_private(self):
        for error in (BackendError('storage_error'), ValueError('/PRIVATE/value'),
                      OSError('/PRIVATE/path')):
            with self.subTest(error=type(error).__name__), \
                 patch.object(SQLiteCatalogBackend, 'create_main_demo', side_effect=error) as create:
                result = self.run_cli()
            create.assert_called_once()
            self.assertEqual(result[0], 1)
            self.assertEqual(result[1], '')
            self.assertNotIn('PRIVATE', result[2])
            self.assertIn('preserve and inspect', result[2])

    def test_uncertain_creation_keeps_destination_and_never_retries(self):
        create = SQLiteCatalogBackend.create_main_demo
        def uncertain(*args, **kwargs):
            create(*args, **kwargs).close()
            raise BackendError('uncertain_commit')
        with patch.object(SQLiteCatalogBackend, 'create_main_demo', side_effect=uncertain) as attempted:
            result = self.run_cli()
        attempted.assert_called_once()
        self.assertEqual(result[0], 1)
        self.assertIn('outcome uncertain', result[2])
        self.assertIn('SQLite journal', result[2])
        with closing(SQLiteCatalogBackend(self.database)) as backend:
            self.assertEqual(backend.format_version, 16)

    def test_close_failure_keeps_created_database_and_reports_failure(self):
        close = SQLiteCatalogBackend.close
        def failed(backend):
            close(backend)
            raise OSError('/PRIVATE/close')
        with patch.object(SQLiteCatalogBackend, 'close', failed):
            result = self.run_cli()
        self.assertEqual(result[0], 1)
        self.assertNotIn('PRIVATE', result[2])
        self.assertIn('preserve and inspect', result[2])
        with closing(SQLiteCatalogBackend(self.database)) as backend:
            self.assertEqual(backend.format_version, 16)

    def test_module_and_packaged_entrypoint_create_from_unrelated_working_directory(self):
        environment = dict(os.environ, PYTHONIOENCODING='utf-8')
        environment['PYTHONPATH'] = os.pathsep.join(filter(None,
            [str(ROOT), environment.get('PYTHONPATH')]))
        commands = [[sys.executable, '-m', 'yadinassi'],
                    [sys.executable, str(ROOT / 'scripts/entrypoint.py')]]
        for index, command in enumerate(commands):
            with self.subTest(entrypoint=index):
                database = self.root / ('база %d.sqlite' % index)
                result = subprocess.run(command + self.arguments(database=database),
                    cwd=self.root, env=environment, capture_output=True, timeout=30)
                self.assertEqual(result.returncode, 0, result.stderr.decode('utf-8'))
                with closing(SQLiteCatalogBackend(database)) as backend:
                    self.assertEqual(backend.export_configuration(), read_configuration_directory(SOURCE))

    def test_help_describes_demo_without_creating_or_reading_sources(self):
        with patch('yadinassi.configuration_import.read_configuration_directory') as read, \
             redirect_stdout(StringIO()) as output, self.assertRaises(SystemExit) as error:
            cli.main(['--help'])
        self.assertEqual(error.exception.code, 0)
        self.assertIn('--create-demo-db', output.getvalue())
        read.assert_not_called()
        self.assertFalse(self.database.exists())
