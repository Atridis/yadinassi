import sys
import unittest
from scripts.benchmark_call_counts import capture
from scripts.benchmark_recovery import scaffold, render, load_manifest


class RecoveryTests(unittest.TestCase):
    def test_evidence_manifest_and_full_grid(self):
        m = load_manifest()
        self.assertEqual((len(m['core']), len(m['method'])), (11, 41))
        report = scaffold('a' * 40)
        self.assertFalse(report['complete'])
        self.assertFalse(report['historical_measurements_reused'])
        rows = report['rows']
        self.assertEqual(len(rows), 312)
        self.assertEqual(len({(r['case'], r['n'], r['layer']) for r in rows}), 312)
        self.assertEqual(sum(r['status'] == 'skipped' for r in rows), 3)
        for r in rows:
            self.assertEqual(r['status'] == 'skipped', r['case'] == 'method.valuetable.find' and r['n'] == 4096)
            for field in ('wall_seconds', 'cpu_seconds', 'python_calls', 'c_calls', 'source_sha256'):
                self.assertIsNone(r[field])

    def test_both_api_tables_do_not_claim_measurement(self):
        text = render(scaffold('b' * 40))
        self.assertEqual(text.count('### N='), 4)
        self.assertIn('не новый замер', text)
        self.assertEqual(text.count('| method.valuetable.find | пропуск:'), 2)
        self.assertIn('не восстановлен', text)

    def test_reject_malformed_source_and_measured_input(self):
        for commit in ('HEAD', '', 'g' * 40):
            with self.assertRaises(ValueError):
                scaffold(commit)
        report = scaffold('a' * 40)
        report['rows'][0]['status'] = 'measured'
        with self.assertRaises(ValueError):
            render(report)

    def test_python_and_c_counts_separate(self):
        def inner():
            return len([])
        def run():
            return inner()
        value, counts = capture(run)
        self.assertEqual(value, 0)
        self.assertEqual(counts, {'python_calls': 2, 'c_calls': 1})
        self.assertIsNone(sys.getprofile())

    def test_c_exception_not_double_counted(self):
        def run():
            try:
                [].index(1)
            except ValueError:
                return 7
        self.assertEqual(capture(run), (7, {'python_calls': 1, 'c_calls': 1}))

    def test_profile_restored_after_failure(self):
        def run():
            raise LookupError('failure')
        with self.assertRaises(LookupError):
            capture(run)
        self.assertIsNone(sys.getprofile())

    def test_existing_profile_not_overwritten(self):
        def profile(*args):
            pass
        sys.setprofile(profile)
        try:
            with self.assertRaises(RuntimeError):
                capture(lambda: None)
            self.assertIs(sys.getprofile(), profile)
        finally:
            sys.setprofile(None)
