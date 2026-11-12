"""Unified dispatch and immutable, rechecked database-source handoff."""
from contextlib import redirect_stderr
from dataclasses import dataclass, replace
from hashlib import sha256
from io import BytesIO, StringIO
from pathlib import Path
import json
import sys
import unittest
from unittest import mock
from uuid import UUID

from yadinassi import launcher
from yadinassi.ui import database_launch as ui, configuration_app, editor_stdio, local_app

ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class File:
    path: str
    content: bytes
    kind: str = 'xml'
    digest: str = ''


@dataclass(frozen=True)
class Snapshot:
    route: str = 'catalog'
    profile: str = 'owned-test-profile'
    database_id: UUID = UUID('00000000-0000-0000-0000-000000000001')
    configuration_generation: int = 1
    source_digest: str = 'a' * 64
    files: tuple = (File('Configuration.xml', b'owned'),)


class UnifiedDispatchTests(unittest.TestCase):
    def test_ui_first_argument(self):
        with mock.patch.object(ui, 'main', return_value=7) as launch:
            self.assertEqual(launcher.main(['--ui', '--f', 'owned']), 7)
            launch.assert_called_once_with(['--f', 'owned'])

    def test_no_old_public_alias(self):
        with mock.patch.object(launcher, 'cli_main', return_value=2) as cli, mock.patch.object(ui, 'main') as launch:
            self.assertEqual(launcher.main(['--catalog-ui', '--f', 'owned']), 2)
            cli.assert_called_once(); launch.assert_not_called()

    def test_bsl_strings_do_not_dispatch(self):
        with mock.patch.object(launcher, 'cli_main', return_value=4) as cli, mock.patch.object(ui, 'main') as launch:
            for args in ([], ['-c', '--ui'], ['script.bsl', '--ui'], ['--', '--ui']):
                self.assertEqual(launcher.main(args), 4); cli.assert_called_with(args)
            launch.assert_not_called()

    def test_all_installation_routes_use_same_dispatcher(self):
        self.assertIn('from yadinassi.launcher import main', (ROOT/'scripts/entrypoint.py').read_text())
        self.assertIn('from yadinassi.launcher import main', (ROOT/'yadinassi/__main__.py').read_text())
        project = (ROOT/'pyproject.toml').read_text()
        self.assertIn('yadinassi = "yadinassi.launcher:main"', project)
        self.assertNotIn('yadinassi-catalog =', project)

    def test_database_required_before_backend(self):
        with mock.patch.object(ui, 'SQLiteCatalogBackend') as backend, redirect_stderr(StringIO()), self.assertRaises(SystemExit):
            ui.main([])
        backend.assert_not_called()

    def test_profile_switch_is_not_public(self):
        with mock.patch.object(ui, 'SQLiteCatalogBackend') as backend, redirect_stderr(StringIO()), self.assertRaises(SystemExit):
            ui.main(['--f', 'owned', '--posting-application'])
        backend.assert_not_called()

    def test_options_are_not_abbreviated(self):
        with mock.patch.object(ui, 'SQLiteCatalogBackend') as backend, redirect_stderr(StringIO()), self.assertRaises(SystemExit):
            ui.main(['--f', 'owned', '--open-b'])
        backend.assert_not_called()


class LaunchBindingTests(unittest.TestCase):
    def test_binding_is_closed_and_exact(self):
        value = json.loads(ui.binding(Snapshot()))
        self.assertEqual(set(value), {'protocol','database','generation','profile','route','source'})
        self.assertEqual(value['protocol'], ui.BINDING_PROTOCOL)

    def test_exact_binding_and_files_pass(self):
        backend=mock.Mock(); snapshot=Snapshot(); backend.launch_snapshot.return_value=snapshot
        self.assertIs(ui.verify_binding(backend,ui.binding(snapshot),{'Configuration.xml':b'owned'},route='catalog'),snapshot)
        backend.launch_snapshot.assert_called_once_with()

    def test_replaced_database_refused(self):
        backend=mock.Mock(); backend.launch_snapshot.return_value=replace(Snapshot(),database_id=UUID(int=2))
        with self.assertRaises(ValueError):ui.verify_binding(backend,ui.binding(Snapshot()))

    def test_changed_generation_refused(self):
        backend=mock.Mock(); backend.launch_snapshot.return_value=replace(Snapshot(),configuration_generation=2)
        with self.assertRaises(ValueError):ui.verify_binding(backend,ui.binding(Snapshot()))

    def test_same_generation_changed_digest_refused(self):
        backend=mock.Mock(); backend.launch_snapshot.return_value=replace(Snapshot(),source_digest='b'*64)
        with self.assertRaises(ValueError):ui.verify_binding(backend,ui.binding(Snapshot()))

    def test_changed_profile_refused(self):
        backend=mock.Mock(); backend.launch_snapshot.return_value=replace(Snapshot(),profile='other')
        with self.assertRaises(ValueError):ui.verify_binding(backend,ui.binding(Snapshot()))

    def test_materialized_source_mismatch_refused(self):
        backend=mock.Mock(); backend.launch_snapshot.return_value=Snapshot()
        with self.assertRaises(ValueError):ui.verify_binding(backend,ui.binding(Snapshot()),{'Configuration.xml':b'other'})

    def test_noncanonical_json_refused(self):
        backend=mock.Mock(); backend.launch_snapshot.return_value=Snapshot()
        with self.assertRaises(ValueError):ui.verify_binding(backend,json.dumps(json.loads(ui.binding(Snapshot())),indent=1))

    def test_binding_bound_before_backend(self):
        backend=mock.Mock()
        for invalid in (None,{},'', 'x'*1025):
            with self.assertRaises(ValueError):ui.verify_binding(backend,invalid)
        backend.launch_snapshot.assert_not_called()

    def test_wrong_route_refused(self):
        backend=mock.Mock(); backend.launch_snapshot.return_value=Snapshot()
        with self.assertRaises(ValueError):ui.verify_binding(backend,ui.binding(Snapshot()),route='posting')

    def test_configuration_profile_selection_is_exact(self):
        self.assertEqual(ui.configuration_route(posting_application=True),'posting')
        self.assertEqual(ui.configuration_route(reference_application=True),'references')
        with self.assertRaises(ValueError):ui.configuration_route()
        with self.assertRaises(ValueError):ui.configuration_route(application_host=True,posting_application=True)


class MaterializationTests(unittest.TestCase):
    def test_original_bytes_and_cleanup(self):
        snapshot=replace(Snapshot(), files=(File('Configuration.xml',b'\xef\xbb\xbf<owned/>'),File('Forms/Main/Module.bsl',b'\r\n// owned\r\n','module')))
        with ui.materialize(snapshot) as root:
            self.assertEqual((root/'Configuration.xml').read_bytes(),snapshot.files[0].content)
            self.assertEqual((root/'Forms/Main/Module.bsl').read_bytes(),snapshot.files[1].content)
        self.assertFalse(root.exists())

    def test_exception_cleanup(self):
        root=None
        with self.assertRaises(RuntimeError):
            with ui.materialize(Snapshot()) as root:raise RuntimeError('owned')
        self.assertFalse(root.exists())

    def test_unsafe_paths_refused(self):
        for path in ('../outside','/absolute','a/../b','a\\b','C:file','a//b','a/./b'):
            with self.subTest(path=path), self.assertRaises(ValueError), ui.materialize(replace(Snapshot(),files=(File(path,b'x'),))):pass

    def test_duplicate_paths_refused(self):
        with self.assertRaises(FileExistsError), ui.materialize(replace(Snapshot(),files=Snapshot().files*2)):pass


class DatabaseRouteTests(unittest.TestCase):
    def setUp(self):
        self.patch=mock.patch.object(ui,'SQLiteCatalogBackend');self.factory=self.patch.start();self.addCleanup(self.patch.stop)
        self.backend=self.factory.return_value;self.backend.launch_snapshot.return_value=Snapshot()

    def test_catalog_handoff_with_binding(self):
        with mock.patch.object(local_app,'main',return_value=7) as app:
            self.assertEqual(ui.main(['--f','owned','--open-browser']),7)
        self.factory.assert_called_once_with('owned',read_only=True)
        self.backend.close.assert_called_once()
        self.assertEqual(app.call_args.args[0],['--f','owned','--browser-session','--launch-binding',ui.binding(Snapshot()),'--open-browser'])

    def test_configuration_routes_use_private_stored_source(self):
        for route,flag in ui.ROUTES.items():
            if route=='catalog':continue
            snapshot=replace(Snapshot(),route=route);self.backend.launch_snapshot.return_value=snapshot
            seen=[]
            def app(args):
                root=Path(args[0]);seen.append(root)
                self.assertEqual((root/'Configuration.xml').read_bytes(),b'owned')
                self.assertEqual(args[1],flag);self.assertIn(ui.binding(snapshot),args)
                self.assertEqual(args[-2:],['--form','CommonForm.Main']);return 9
            with mock.patch.object(configuration_app,'main',side_effect=app):
                self.assertEqual(ui.main(['--f','owned','--form','CommonForm.Main']),9)
            self.assertFalse(seen[0].exists())

    def test_catalog_initial_form_refused(self):
        with mock.patch.object(local_app,'main') as app, redirect_stderr(StringIO()),self.assertRaises(SystemExit):
            ui.main(['--f','owned','--form','CommonForm.Main'])
        app.assert_not_called()

    def test_failed_admission_never_falls_back(self):
        self.backend.launch_snapshot.side_effect=ValueError('private source path')
        errors=StringIO()
        with mock.patch.object(local_app,'main') as app,redirect_stderr(errors):self.assertEqual(ui.main(['--f','owned']),1)
        app.assert_not_called();self.backend.close.assert_called_once()
        self.assertNotIn('private source path',errors.getvalue())

    def test_unknown_route_never_falls_back(self):
        self.backend.launch_snapshot.return_value=replace(Snapshot(),route='accumulation15')
        with mock.patch.object(local_app,'main') as app,redirect_stderr(StringIO()):self.assertEqual(ui.main(['--f','owned']),1)
        app.assert_not_called()

    def test_configuration_failure_cleans_materialization(self):
        self.backend.launch_snapshot.return_value=replace(Snapshot(),route='documents');seen=[]
        def fail(args):seen.append(Path(args[0]));raise ValueError('owned failure')
        with mock.patch.object(configuration_app,'main',side_effect=fail),redirect_stderr(StringIO()):self.assertEqual(ui.main(['--f','owned']),1)
        self.assertFalse(seen[0].exists())

    def test_child_checks_binding_before_catalog_app(self):
        context=mock.Mock()
        with mock.patch.object(editor_stdio,'SQLiteDBContext',return_value=context),mock.patch.object(ui,'verify_binding',side_effect=ValueError('changed')) as verify,mock.patch.object(editor_stdio,'CatalogEditorApplication') as app,redirect_stderr(StringIO()):
            self.assertEqual(editor_stdio.main(['owned','--launch-binding','bound'],source=BytesIO(),target=BytesIO()),1)
        verify.assert_called_once_with(context.backend,'bound',route='catalog');app.assert_not_called();context.close.assert_called_once()

    def test_configuration_child_binding_precedes_runtime(self):
        configuration=mock.Mock();configuration.source_files=(('Configuration.xml',b'owned'),)
        context=mock.Mock()
        with mock.patch.object(configuration_app,'_definitions',return_value={}),mock.patch.object(configuration_app,'SQLiteDBContext',return_value=context),mock.patch.object(ui,'verify_binding',side_effect=ValueError('changed')),mock.patch.object(configuration_app,'_runtime') as runtime:
            with self.assertRaises(ValueError):configuration_app.ConfigurationBroker(configuration,'owned',application_host=True,launch_binding='bound',launch_route='application')
        runtime.assert_not_called();context.close.assert_called_once()
