"""Closed renderer-inventory inverse; historical native hashes are unchanged."""
import hashlib
import json
from pathlib import Path
import unittest
from unittest import mock
import test_native_async_fixture as history

ROOT = Path(__file__).resolve().parents[1]


class CatalogAssetsInverseTests(unittest.TestCase):
    def test_exact_inventory_layer_restores_unchanged_sqlite_source(self):
        source = (ROOT / 'scripts/native_1c_full_host.py').read_text(encoding='utf-8')
        restored = history.without_catalog_assets_provenance(source)
        self.assertEqual(hashlib.sha256(restored.encode()).hexdigest(),
                         '3eed042a41e51efebf4d9d4a184ffd8cf23226ace99970864648ac4779200b69')
        self.assertEqual(history.without_catalog_assets_provenance(restored), restored)
        self.assertEqual(history.without_sqlite_host_context(source), history.without_sqlite_host_context(restored))
        self.assertEqual(history.without_collections_measurement_budget(source),
                         history.without_collections_measurement_budget(restored))

    def test_unknown_source_drift_and_missing_or_duplicate_hunk_reject(self):
        source = (ROOT / 'scripts/native_1c_full_host.py').read_text(encoding='utf-8')
        source = history.without_form_assets_provenance(source)
        contract = json.loads((ROOT / 'tests/catalog_assets_source_inverse.json').read_text())
        new = contract['edits'][0]['new']
        for changed in (source + '# drift\n', source.replace(new, '', 1), source + new,
                        source.replace('CASE_SECONDS = 10', 'CASE_SECONDS = 11', 1)):
            with self.assertRaises(AssertionError): history.without_catalog_assets_provenance(changed)

    def test_weakened_contract_or_hunk_cannot_rewrite_historical_source(self):
        source = (ROOT / 'scripts/native_1c_full_host.py').read_text(encoding='utf-8')
        path = ROOT / 'tests/catalog_assets_source_inverse.json'
        for field in ('base_sha256', 'candidate_sha256', 'old', 'new'):
            contract = json.loads(path.read_text())
            if field in ('old', 'new'): contract['edits'][0][field] += '# tamper\n'
            else: contract[field] = '0' * 64
            with mock.patch.object(history.json, 'loads', return_value=contract):
                with self.assertRaises(AssertionError): history.without_catalog_assets_provenance(source)


class FormAssetsInverseTests(unittest.TestCase):
    def test_new_inventory_restores_exact_catalog_layer(self):
        source = (ROOT / 'scripts/native_1c_full_host.py').read_text(encoding='utf-8')
        restored = history.without_form_assets_provenance(source)
        self.assertEqual(hashlib.sha256(restored.encode()).hexdigest(),
                         'e83119e314deae20d6e0288cdbdaf00ad7d92c88236aed227c5c982ca4ee2db4')
        self.assertEqual(history.without_form_assets_provenance(restored), restored)
        self.assertEqual(history.without_catalog_assets_provenance(source),
                         history.without_catalog_assets_provenance(restored))

    def test_new_layer_rejects_unknown_source_and_inventory_drift(self):
        source = (ROOT / 'scripts/native_1c_full_host.py').read_text(encoding='utf-8')
        for changed in (source + '# drift\n', source.replace('("catalog", "form")', '("catalog", "other")'),
                        source.replace('CASE_SECONDS = 10', 'CASE_SECONDS = 11', 1)):
            with self.subTest(changed=changed[-20:]), self.assertRaises(AssertionError):
                history.without_form_assets_provenance(changed)
