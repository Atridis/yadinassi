"""Diagnostic transport changes do not rewrite immutable historical evidence."""
import hashlib
from pathlib import Path
import unittest

from test_native_async_fixture import without_accumulation_exit_status, without_tree_access_probe

ROOT = Path(__file__).resolve().parents[1]
BASE = 'f2992733fcb01cdb2a03195dd80c879f44cc487dc5a84e9fff530aa5a5a6e4d1'
CANDIDATE = '174440879c406f8042cf78625c7f9c0bdff507273125b2101cef27bc6cd04b04'


class AccumulationHistoryTests(unittest.TestCase):
    def source(self):
        return (ROOT / 'scripts/native_1c_bootstrap/full_suite.py').read_text(encoding='utf-8')

    def test_diagnostic_inverse_restores_exact_previous_harness(self):
        source = self.source()
        self.assertEqual(hashlib.sha256(source.encode()).hexdigest(), CANDIDATE)
        restored = without_accumulation_exit_status(source)
        self.assertEqual(hashlib.sha256(restored.encode()).hexdigest(), BASE)
        self.assertNotIn('error.exit_code = code', restored)

    def test_original_and_diagnostic_source_use_the_same_historical_chain(self):
        source = self.source()
        previous = without_accumulation_exit_status(source)
        self.assertEqual(without_accumulation_exit_status(previous), previous)
        self.assertEqual(without_tree_access_probe(source), without_tree_access_probe(previous))

    def test_diagnostic_hunk_or_outer_drift_never_enters_history(self):
        source = self.source()
        for changed in (source.replace('error.exit_code = code', 'error.exit_code = 0'),
                        source.replace('        raise error\n', '        raise error\n        raise error\n', 1),
                        source + '\n# unreviewed suffix\n'):
            with self.subTest(changed=changed[-30:]), self.assertRaises(AssertionError):
                without_tree_access_probe(changed)
