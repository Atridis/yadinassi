"""Offline QA-contract tests only: never launches a browser or installs tools."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock
from datetime import datetime
from decimal import Decimal
from uuid import uuid4

from ui_catalog_fixture import CATEGORY, PRODUCT
from yadinassi.catalog_backend import CatalogDraft, CatalogKey, CatalogSelection
from yadinassi.sqlite_catalog import SQLiteCatalogBackend

ROOT = Path(__file__).resolve().parents[1]
QA = ROOT / 'tests' / 'browser_ui'
spec = importlib.util.spec_from_file_location('owned_browser_fixture', QA / 'fixture.py')
fixture = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fixture)


class BrowserQAContractTests(unittest.TestCase):
    def test_workflow_is_explicit_opt_in_not_default_or_native(self):
        source = (ROOT / '.github/workflows/ui-browser-qa.yml').read_text(encoding='utf-8')
        self.assertIn('branches: [codex/ui-browser-reviewed, codex/form-browser-reviewed, codex/reference-browser-reviewed, codex/configuration-browser-reviewed]', source)
        for forbidden in ('pull_request:', 'workflow_dispatch:', 'schedule:', 'sudo ', 'sysctl ', 'container:', 'secrets.'):
            self.assertNotIn(forbidden, source)
        self.assertIn('runs-on: ubuntu-22.04', source)
        self.assertIn('persist-credentials: false', source)
        self.assertIn('contents: read', source)
        self.assertNotIn('write', source)

    def test_dependency_lock_exact_official_packages_only(self):
        manifest = json.loads((QA / 'package.json').read_text(encoding='utf-8'))
        lock = json.loads((QA / 'package-lock.json').read_text(encoding='utf-8'))
        self.assertEqual(manifest['devDependencies'], {'playwright': '1.64.1'})
        self.assertEqual(set(lock['packages']), {'', 'node_modules/playwright', 'node_modules/playwright-core'})
        for name in ('playwright', 'playwright-core'):
            package = lock['packages']['node_modules/' + name]
            self.assertEqual(package['version'], '1.64.1')
            self.assertEqual(package['resolved'], f'https://registry.npmjs.org/{name}/-/{name}-1.64.1.tgz')
            self.assertTrue(package['integrity'].startswith('sha512-'))
        self.assertIn('ignore-scripts=true', (QA / '.npmrc').read_text(encoding='utf-8'))

    def test_browser_launch_is_one_explicit_sandbox_enabled_acquisition(self):
        source = (QA / 'catalog_browser_qa.mjs').read_text(encoding='utf-8')
        self.assertEqual(source.count('chromium.launch('), 1)
        self.assertIn('chromiumSandbox:true', source)
        self.assertIn("channel:'chromium'", source)
        self.assertNotIn('args:', source)
        self.assertNotIn('ignoreDefaultArgs:', source)
        self.assertIn('process.getuid()===0', source)
        self.assertIn("cdp.send('SystemInfo.getProcessInfo')", source)
        self.assertIn("lstat(processRoot)).uid,process.getuid()", source)
        self.assertIn("readlink(processRoot+'/exe'),chromium.executablePath()", source)
        self.assertIn('Buffer.alloc(16385)', source)
        self.assertNotIn('Browser.getBrowserCommandLine', source)
        self.assertIn("sandboxStatus(await probe.locator('body').innerText())", source)
        self.assertNotIn('tracing.start', source)
        self.assertNotIn('recordHar', source)

    def test_artifacts_explicit_no_database_profile_or_trace(self):
        source = (ROOT / '.github/workflows/ui-browser-qa.yml').read_text(encoding='utf-8')
        paths = [line.strip() for line in source.splitlines() if 'yadinassi-browser-artifacts/' in line]
        self.assertEqual([path.rsplit('/', 1)[1] for path in paths],
                         ['result.json', 'manifest.json', 'list.png', 'editor.png', 'narrow.png'])
        self.assertIn('retention-days: 14', source)
        self.assertIn('if-no-files-found: error', source)

    def test_harness_binds_checkout_assets_fixture_and_never_rebuilds_renderer(self):
        source = (QA / 'catalog_browser_qa.mjs').read_text(encoding='utf-8')
        self.assertIn('process.env.QA_SOURCE_SHA', source)
        self.assertIn("'tests/ui_catalog_fixture.py'", source)
        self.assertIn("git('ls-files','-z','yadinassi'", source)
        self.assertIn('source_changed', source)
        self.assertNotIn('build.mjs', source)

    def test_harness_checks_ignore_windows_default_text_encoding(self):
        original = Path.read_text
        def windows_default(path, *args, **kwargs):
            # Model a Windows default only when the caller omitted its encoding.
            kwargs.setdefault('encoding', 'cp1252')
            return original(path, *args, **kwargs)
        with mock.patch.object(Path, 'read_text', windows_default):
            self.test_browser_launch_is_one_explicit_sandbox_enabled_acquisition()
            self.test_harness_binds_checkout_assets_fixture_and_never_rebuilds_renderer()

    def test_fixture_is_owned_and_initial_database_is_not_a_durability_pass(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.assertEqual(fixture.seed(root), {'seeded': True})
            self.assertTrue((root / 'owned.sqlite').is_file())
            with self.assertRaisesRegex(ValueError, 'category_durability_mismatch'):
                fixture.audit(root)

    def test_reopened_fixture_audit_requires_exact_final_scalars_and_references(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            fixture.seed(root)
            backend = SQLiteCatalogBackend(root / 'owned.sqlite')
            try:
                tx = backend.begin_write(uuid4())
                category = tx.select_catalog(CATEGORY, CatalogSelection(limit=10))[0]
                row = tx.select_catalog(PRODUCT, CatalogSelection(limit=10))[0]
                tx.create(CatalogDraft(CatalogKey(backend.database_id, CATEGORY, uuid4()),
                    '40', 'Browser persisted edit', False, ()))
                tx.update(CatalogDraft(row.key, row.code, row.description, False,
                    ('Browser scalar', Decimal('123.40'), False, datetime(2025, 6, 7, 8, 9, 10), category.key)), row.revision)
                tx.commit()
            finally:
                backend.close()
            self.assertEqual(fixture.audit(root), {'durable': True, 'categories': 2,
                'products': 3, 'exactScalars': True, 'referencePreserved': True})

    def test_fixture_rejects_existing_database_without_overwriting(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            fixture.seed(root)
            before = (root / 'owned.sqlite').read_bytes()
            with self.assertRaises(Exception):
                fixture.seed(root)
            self.assertEqual((root / 'owned.sqlite').read_bytes(), before)


if __name__ == '__main__':
    unittest.main()
