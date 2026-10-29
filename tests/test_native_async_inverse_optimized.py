"""Run the existing complete inverse drift regression with assertions disabled."""
from pathlib import Path
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]


class OptimizedInverseTests(unittest.TestCase):
    def test_complete_existing_negative_drift_contract_under_optimization(self):
        # Select only the existing test: never discover this subprocess wrapper.
        test = ('test_native_async_fixture.AsyncFixtureSourcesTest.'
                'test_exclude_inverse_restores_exact_immutable_main_and_rejects_drift')
        code = ('import sys, unittest; '
                'sys.path[:0] = [sys.argv[1], sys.argv[2]]; '
                'unittest.main(module=None, argv=["inverse-optimized", sys.argv[3]])')
        result = subprocess.run(
            [sys.executable, '-I', '-B', '-O', '-c', code,
             str(ROOT / 'tests'), str(ROOT), test],
            cwd=ROOT, capture_output=True, text=True, timeout=60)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn('Ran 1 test', result.stderr)
        self.assertIn('OK', result.stderr)


if __name__ == '__main__':
    unittest.main()
