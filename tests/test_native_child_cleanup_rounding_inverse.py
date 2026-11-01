"""Whole-source test-only inverse; never a runtime cap fallback."""
import hashlib
import json
from pathlib import Path
import unittest
from unittest import mock
import test_native_async_fixture as history

ROOT = Path(__file__).resolve().parents[1]

class CleanupRoundingInverseTests(unittest.TestCase):
    def source(self):
        return (ROOT / 'scripts/native_1c_full_host.py').read_text(encoding='utf-8')

    def test_exact_source_and_existing_budget_chain(self):
        original = self.source()
        restored = history.without_child_cleanup_rounding(original)
        self.assertEqual(hashlib.sha256(restored.encode()).hexdigest(),
                         '9249cca10b29455d12bb4ab806b33f572a9f462890d2a2940e4e93aac4c9beb9')
        self.assertEqual(history.without_child_cleanup_rounding(restored), restored)
        self.assertEqual(history.without_collections_measurement_budget(original),
                         history.without_collections_measurement_budget(restored))
        self.assertIn('code = process.wait(timeout=max(0.001, deadline - time.monotonic()))', original)
        self.assertEqual(self.source(), original)

    def test_unrelated_or_cap_drift_refused(self):
        source = self.source()
        for mutant in (source + '\n', source.replace('CHILD_CLEANUP_SECONDS = 5',
                       'CHILD_CLEANUP_SECONDS = 6'), source.replace(
                       'min(CHILD_CLEANUP_SECONDS, max(0.001, deadline - time.monotonic()))',
                       'min(6, max(0.001, deadline - time.monotonic()))')):
            with self.subTest(digest=hashlib.sha256(mutant.encode()).hexdigest()):
                self.assertNotEqual(mutant, source)
                with self.assertRaises(AssertionError):
                    history.without_child_cleanup_rounding(mutant)
                with self.assertRaises(AssertionError):
                    history.without_collections_measurement_budget(mutant)

    def test_tampered_contract_and_nonunique_hunk_refused(self):
        raw = (ROOT / 'tests/child_cleanup_rounding_source_inverse.json').read_text(encoding='utf-8')
        for field in ('base_sha256', 'candidate_sha256'):
            changed = json.loads(raw)
            changed[field] = '0' * 64
            with mock.patch.object(history.json, 'loads', return_value=changed):
                with self.assertRaises(AssertionError):
                    history.without_child_cleanup_rounding(self.source())
        changed = json.loads(raw)
        changed['edits'][0]['new'] = 'def '
        with mock.patch.object(history.json, 'loads', return_value=changed):
            with self.assertRaises(AssertionError):
                history.without_child_cleanup_rounding(self.source())
