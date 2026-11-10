"""Closed packaged renderer inventory and deterministic source/output provenance."""
import hashlib
from importlib.resources import files
import json
from pathlib import Path
import unittest
from unittest import mock

from test_native_preprocessor_budget import full, ROOT, source_provenance
from test_native_1c_full_host import SyntheticFilesystemCase
import test_native_1c_full_host as filesystem_fixture

ASSETS = ('app.js', 'index.html', 'style.css', 'LICENSE.txt', 'build-manifest.json')


class UIAssetProvenanceTests(SyntheticFilesystemCase):
    # Trusted repository source hashing, not native-container filesystem evidence.
    # Reuse the existing Windows offline adapter; Linux secure reader is unchanged.

    def test_actual_inventory_includes_all_assets_and_modules(self):
        result = source_provenance()
        self.assertEqual(result['source_file_count'], 168)
        # All added runtime modules are hashed, as well as packaged renderer assets.
        original = full.read_regular
        for changed_name in ('app.js', 'http_security.py', 'relational_queries.py', 'form_replication.py', 'callbacks.py', 'form_app.py', 'form_package.py', 'json_dates.py', 'query_packages.py', 'form_tables.py', 'form_table_replication.py', 'order_workbench.py', 'query_sources.py', 'text_streams.py', 'orders_workspace.py', 'configuration_forms.py', 'form_program.py', 'configuration_app.py'):
            def changed(path, *args, **kwargs):
                data = original(path, *args, **kwargs)
                return data + b'\n' if path.name == changed_name else data
            with self.subTest(path=changed_name), mock.patch.object(full, 'read_regular', changed):
                other = source_provenance()
            self.assertNotEqual(result['source_sha256'], other['source_sha256'])

    def test_no_unlisted_asset_extension_is_admitted(self):
        original = Path.rglob
        for name in ('extra.js', 'extra.txt', 'extra.py'):
            def extra(path, pattern):
                return iter(list(original(path, pattern)) + [ROOT / 'yadinassi/ui/assets/catalog' / name])
            with mock.patch.object(Path, 'rglob', extra):
                with self.assertRaisesRegex(full.FullError, 'unexpected_interpreter_source'): source_provenance()

    def test_missing_asset_is_not_silently_excluded(self):
        original = Path.rglob
        def missing(path, pattern):
            return (item for item in original(path, pattern) if item.name != 'style.css')
        with mock.patch.object(Path, 'rglob', missing):
            with self.assertRaisesRegex(full.FullError, 'unexpected_interpreter_source'): source_provenance()

    def test_unrelated_javascript_is_still_rejected(self):
        original = Path.rglob
        def extra(path, pattern):
            return iter(list(original(path, pattern)) + [ROOT / 'yadinassi/unexpected.js'])
        with mock.patch.object(Path, 'rglob', extra):
            with self.assertRaisesRegex(full.FullError, 'unexpected_interpreter_source'): source_provenance()

    def test_every_closed_renderer_pins_checkout_newlines(self):
        attributes = (ROOT / '.gitattributes').read_text().splitlines()
        for renderer in ('catalog', 'form', 'workspace', 'configuration'):
            with self.subTest(renderer=renderer):
                self.assertIn(f'frontend/{renderer}/** text eol=lf', attributes)
                self.assertIn(f'yadinassi/ui/assets/{renderer}/* text eol=lf', attributes)

    def test_build_manifest_matches_sources_and_generated_output(self):
        for renderer in ('catalog', 'form', 'workspace', 'configuration'):
            directory = ROOT / 'yadinassi/ui/assets' / renderer
            manifest = json.loads((directory / 'build-manifest.json').read_text())
            self.assertEqual(manifest['schema'], 'yadinassi-' + renderer + '-assets/0')
            self.assertEqual(set(manifest['outputs']), set(ASSETS) - {'build-manifest.json'})
            for name, digest in manifest['outputs'].items():
                self.assertEqual(hashlib.sha256((directory / name).read_bytes()).hexdigest(), digest, name)
            for name, digest in manifest['sources'].items():
                self.assertEqual(hashlib.sha256((ROOT / 'frontend' / renderer / name).read_bytes()).hexdigest(), digest, name)

    def test_runtime_resource_loader_finds_nonempty_exact_assets(self):
        for renderer in ('catalog', 'form', 'workspace', 'configuration'):
            for name in ASSETS:
                self.assertTrue(files('yadinassi.ui').joinpath('assets', renderer, name).read_bytes())

    def test_windows_offline_adapter_keeps_exact_inventory_and_byte_drift_checks(self):
        with mock.patch.object(filesystem_fixture, '_USE_SYNTHETIC_FILE_READER', True):
            case = UIAssetProvenanceTests('test_actual_inventory_includes_all_assets_and_modules')
            result = unittest.TestResult()
            case.run(result)
        self.assertEqual(result.testsRun, 1)
        self.assertEqual(result.errors, [])
        self.assertEqual(result.failures, [])
