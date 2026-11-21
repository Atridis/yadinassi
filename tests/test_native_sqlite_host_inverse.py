"""Only the exact current SQLite host edits may restore historical oracle source."""
import hashlib
import json
from pathlib import Path
import unittest
from unittest import mock
import test_native_async_fixture as history

ROOT = Path(__file__).resolve().parents[1]


class SQLiteHostInverseTests(unittest.TestCase):
    def test_exact_host_change_restores_unchanged_historical_source(self):
        source = (ROOT / 'scripts/native_1c_full_host.py').read_text(encoding='utf-8')
        contract = json.loads((ROOT / 'tests/sqlite_host_context_source_inverse.json').read_text(encoding='utf-8'))
        restored = history.without_sqlite_host_context(source)
        self.assertEqual(hashlib.sha256(restored.encode()).hexdigest(), contract['base_sha256'])
        self.assertEqual(history.without_sqlite_host_context(restored), restored)
        sqlite_candidate = history.without_catalog_assets_provenance(source)
        self.assertEqual(hashlib.sha256(sqlite_candidate.encode()).hexdigest(),
                         contract['candidate_sha256'])
        for edit in contract['edits']:
            self.assertEqual(sqlite_candidate.count(edit['new']), 1)
        self.assertEqual(history.without_collections_measurement_budget(source),
                         history.without_collections_measurement_budget(restored))

    def test_direct_host_inverse_is_pinned_and_cannot_hide_drift(self):
        source = (ROOT / 'scripts/native_1c_full_host.py').read_text(encoding='utf-8')
        restored = history.without_direct_host_source_history(source)
        self.assertEqual(hashlib.sha256(restored.encode()).hexdigest(),
                         '77555ab592977002bcbb33e3dd1a5fbf9f1d9c0ccca0e4002734d944bc689fd1')
        self.assertEqual(history.without_direct_host_source_history(restored), restored)
        with self.assertRaisesRegex(AssertionError, 'outer source identity'):
            history.without_repository_inventory_budget(source + '# drift\n')
        contracts = json.loads((ROOT / 'tests/native_direct_host_source_inverse.json')
                               .read_text(encoding='utf-8'))
        contracts[1]['edits'][0]['old'] += '# altered\n'
        with mock.patch.object(history.json, 'loads', return_value=contracts):
            with self.assertRaisesRegex(AssertionError, 'direct host inverse inner identity'):
                history.without_direct_host_source_history(source)

    def test_unknown_changes_or_weakened_contract_are_rejected(self):
        source = (ROOT / 'scripts/native_1c_full_host.py').read_text(encoding='utf-8')
        for changed in (source + '# drift\n',
                        source.replace('SQLITE_INFOBASE_CONTEXT_EXPECTED_TOKEN =', 'UNKNOWN_TOKEN =', 1),
                        source.replace('CASE_SECONDS = 10', 'CASE_SECONDS = 11', 1)):
            with self.assertRaises(AssertionError):
                history.without_sqlite_host_context(changed)
        contract = json.loads((ROOT / 'tests/sqlite_host_context_source_inverse.json').read_text(encoding='utf-8'))
        contract['candidate_sha256'] = '0' * 64
        with mock.patch.object(history.json, 'loads', return_value=contract):
            with self.assertRaises(AssertionError):
                history.without_sqlite_host_context(source)


if __name__ == '__main__':
    unittest.main()
