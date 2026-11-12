"""Typed fixture lifecycle only: no browser, server, network or BSL."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class StatementFixtureSmokeTests(unittest.TestCase):
    def test_external_mark_preserves_all_other_saved_data(self):
        source = (ROOT / 'tests/browser_ui/inventory_statement_browser_qa.mjs').read_text(encoding='utf-8')
        fixture = source.split('const fixtureCode=String.raw`', 1)[1].split('`;', 1)[0]
        with tempfile.TemporaryDirectory() as owned:
            def run(mode):
                result = subprocess.run([sys.executable, '-c', fixture, mode, owned,
                    str(ROOT / 'examples/configuration-inventory-application')],
                    cwd=ROOT, capture_output=True, text=True, timeout=30, check=True)
                return json.loads(result.stdout)
            self.assertTrue(run('create')['created'])
            before = run('audit')
            marked = run('mark-product')
            after = run('audit-after-mark')
            self.assertEqual(marked['before'], before)
            self.assertEqual(marked['after'], after)
            self.assertEqual(before['invariantFingerprint'], after['invariantFingerprint'])
            self.assertNotEqual(before['p001Revision'], after['p001Revision'])
            self.assertNotEqual(before['fingerprint'], after['fingerprint'])
            self.assertEqual(run('audit-after-mark'), after)
