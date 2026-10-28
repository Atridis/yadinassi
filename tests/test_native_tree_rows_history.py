"""Exact source/harness inverse for fail-only Rows probes; no capture rewriting."""
import copy
import hashlib
import json
from pathlib import Path
import unittest
from unittest import mock

import test_native_async_fixture as history
import test_native_1c_full_stage as fixtures
from scripts import native_historical_replay as replay

ROOT = Path(__file__).resolve().parents[1]
PATHS = ('scripts/native_1c_bootstrap/full_suite.py', 'scripts/native_1c_full_host.py')
PUBLIC_SOURCE = '73ffd118fa061e7ecbdfafc8701de03c887e24020fc2fec7d30a04030a2cf03b'
PUBLIC_HARNESSES = {
    PATHS[0]: '5021ea7b064d86971b4a00496bbf1c7ca09869d1d17efe8af73851b98073079b',
    PATHS[1]: 'c5a79387528ea40863d374363c262ff05f567d87435b55f54de0a2116eaf64d5',
}


class RowsHistoryTests(unittest.TestCase):
    def test_entire_public_source_and_harness_restored_before_older_layers(self):
        source = (ROOT / 'integrational_tests/tests/collections.bsl').read_text(encoding='utf-8-sig')
        restored = replay.without_tree_rows_diagnostic(source)
        self.assertEqual(hashlib.sha256(restored.encode('utf-8-sig')).hexdigest(), PUBLIC_SOURCE)
        self.assertEqual(replay.without_tree_load_probes(source), replay.without_tree_load_probes(restored))
        for path in PATHS:
            current = (ROOT / path).read_text(encoding='utf-8')
            restored = history.without_tree_rows_diagnostic_measurement(current, host=path.endswith('full_host.py'))
            self.assertEqual(hashlib.sha256(restored.encode()).hexdigest(), PUBLIC_HARNESSES[path])
            self.assertEqual(history.without_tree_load_measurement(current, host=path.endswith('full_host.py')),
                             history.without_tree_load_measurement(restored, host=path.endswith('full_host.py')))

    def test_new_helper_and_call_blocks_are_independently_pinned(self):
        source = (ROOT / 'integrational_tests/tests/collections.bsl').read_bytes().replace(b'\r\n', b'\n')
        template = (ROOT / fixtures.suite.CLIENT_SOURCE).read_bytes().replace(b'\r\n', b'\n')
        for before, after in ((b'Added.Marker = 17', b'Added.Marker = 18'),
                              (b'TreeRowsDiagnosticProbe(45, TreeRowsDiagnostic)', b'TreeRowsDiagnosticProbe(44, TreeRowsDiagnostic)')):
            changed = source.replace(before, after, 1)
            self.assertNotEqual(hashlib.sha256(source).digest(), hashlib.sha256(changed).digest())
            with mock.patch.object(fixtures.suite, 'CLIENT_COLLECTIONS_SOURCE_SHA256', hashlib.sha256(changed).hexdigest()), self.assertRaisesRegex(fixtures.suite.FullError, '^invalid_input$'):
                fixtures.suite.client_collections_module(changed, template)

    def test_harness_and_source_drift_reject_even_with_forged_checksums(self):
        inventory = json.loads((ROOT / 'tests/tree_rows_diagnostic_source_inverse.json').read_text(encoding='utf-8'))
        for path in PATHS:
            source = (ROOT / path).read_text(encoding='utf-8')
            changed_values = (source + '\n', source.replace(replay.TREE_ROWS_DIAGNOSTIC_SOURCE_SHA256, '0' * 64, 1), source.replace('\n', '\r\n'))
            for changed in changed_values:
                with self.subTest(path=path, changed=hashlib.sha256(changed.encode()).hexdigest()):
                    self.assertNotEqual(source, changed)
                    with self.assertRaises(AssertionError):
                        history.without_tree_rows_diagnostic_measurement(changed, host=path.endswith('full_host.py'))
                    forged = copy.deepcopy(inventory)
                    forged[path]['candidate_sha256'] = hashlib.sha256(changed.encode()).hexdigest()
                    with mock.patch.object(history.json, 'loads', return_value=forged), self.assertRaises(AssertionError):
                        history.without_tree_rows_diagnostic_measurement(changed, host=path.endswith('full_host.py'))
        source = (ROOT / 'integrational_tests/tests/collections.bsl').read_text(encoding='utf-8-sig')
        for changed in (source + '\n', source.replace('TreeRowsDiagnosticPart(Part)', 'TreeRowsDiagnosticPart(1)', 1)):
            self.assertNotEqual(source, changed)
            with self.assertRaises(ValueError): replay.without_tree_rows_diagnostic(changed)
            with mock.patch.object(replay, 'TREE_ROWS_DIAGNOSTIC_SOURCE_SHA256', hashlib.sha256(changed.encode('utf-8-sig')).hexdigest()), self.assertRaises(ValueError):
                replay.without_tree_rows_diagnostic(changed)


if __name__ == '__main__': unittest.main()
