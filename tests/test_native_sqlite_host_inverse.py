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
        source = (ROOT / 'scripts/native_1c_full_host.py').read_text()
        contract = json.loads((ROOT / 'tests/sqlite_host_context_source_inverse.json').read_text())
        restored = history.without_sqlite_host_context(source)
        self.assertEqual(hashlib.sha256(restored.encode()).hexdigest(), contract['base_sha256'])
        self.assertEqual(history.without_sqlite_host_context(restored), restored)
        for edit in contract['edits']:
            self.assertEqual(source.count(edit['new']), 1)
        self.assertEqual(history.without_collections_measurement_budget(source),
                         history.without_collections_measurement_budget(restored))

    def test_unknown_changes_or_weakened_contract_are_rejected(self):
        source = (ROOT / 'scripts/native_1c_full_host.py').read_text()
        for changed in (source + '# drift\n',
                        source.replace('SQLITE_INFOBASE_CONTEXT_EXPECTED_TOKEN =', 'UNKNOWN_TOKEN =', 1),
                        source.replace('CASE_SECONDS = 10', 'CASE_SECONDS = 11', 1)):
            with self.assertRaises(AssertionError):
                history.without_sqlite_host_context(changed)
        contract = json.loads((ROOT / 'tests/sqlite_host_context_source_inverse.json').read_text())
        contract['candidate_sha256'] = '0' * 64
        with mock.patch.object(history.json, 'loads', return_value=contract):
            with self.assertRaises(AssertionError):
                history.without_sqlite_host_context(source)


if __name__ == '__main__':
    unittest.main()
