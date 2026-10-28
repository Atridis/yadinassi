"""Exact finite diagnostic host history; no capture changes or native acceptance."""
import copy
import hashlib
import json
from pathlib import Path
import unittest
from unittest import mock

import test_native_async_fixture as history

ROOT = Path(__file__).resolve().parents[1]
HOST = 'scripts/native_1c_full_host.py'
BASE = 'a823b590df9e2d1f678b89a519a3b8c5fd3121d948312b4f6c740783fd83f41e'


class FiniteReasonHistoryTests(unittest.TestCase):
    def test_exact_public_host_restored_before_all_previous_layers(self):
        source = (ROOT / HOST).read_text(encoding='utf-8')
        restored = history.without_tree_load_finite_reason_measurement(source)
        self.assertEqual(hashlib.sha256(restored.encode('utf-8')).hexdigest(), BASE)
        self.assertNotIn('def tree_load_calibration_failure(', restored)
        inventory = json.loads((ROOT / 'tests/tree_load_calibration_source_inverse.json').read_text(encoding='utf-8'))
        self.assertEqual(inventory[HOST]['candidate_sha256'], BASE)
        self.assertEqual(history.without_tree_load_calibration_measurement(source, host=True),
                         history.without_tree_load_calibration_measurement(restored, host=True))
        self.assertEqual(history.without_tree_load_measurement(source, host=True),
                         history.without_tree_load_measurement(restored, host=True))
        self.assertTrue(history.without_child_cleanup(source))

    def test_current_public_and_forged_checksums_do_not_hide_drift(self):
        source = (ROOT / HOST).read_text(encoding='utf-8')
        inventory = json.loads((ROOT / 'tests/tree_load_finite_reason_source_inverse.json').read_text(encoding='utf-8'))
        original = history.without_tree_load_finite_reason_measurement(source)
        with self.assertRaises(AssertionError):
            history.without_tree_load_finite_reason_measurement(original)
        for changed in (source + '\n', source.replace('TREE_LOAD_CALIBRATION_CODES =', 'TREE_LOAD_CALIBRATION_CODEX =', 1),
                        source.replace('\n', '\r\n')):
            with self.subTest(change=hashlib.sha256(changed.encode()).hexdigest()):
                self.assertNotEqual(source, changed)
                with self.assertRaises(AssertionError):
                    history.without_tree_load_finite_reason_measurement(changed)
                forged = copy.deepcopy(inventory)
                forged[HOST]['candidate_sha256'] = hashlib.sha256(changed.encode()).hexdigest()
                with mock.patch.object(history.json, 'loads', return_value=forged), self.assertRaises(AssertionError):
                    history.without_tree_load_finite_reason_measurement(changed)


if __name__ == '__main__':
    unittest.main()
