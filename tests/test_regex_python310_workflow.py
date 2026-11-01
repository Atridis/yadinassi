"""Exact closed actual-Python3.10 compatibility job, not a native1C gate."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
EXPECTED = '  regex-python310:\n    name: Python 3.10 regex compatibility\n    runs-on: ubuntu-22.04\n    timeout-minutes: 10\n    permissions:\n      contents: read\n    env:\n      PYTHONPATH: tests:scripts\n    steps:\n      - uses: actions/checkout@v7\n        with:\n          persist-credentials: false\n      - uses: actions/setup-python@v7\n        with:\n          python-version: \'3.10\'\n      - name: Install pinned runtime dependencies\n        run: python -m pip install -e . wcwidth==0.8.2\n      - name: Verify actual CPython 3.10\n        run: python -c "import sys; print(sys.version); raise SystemExit(0 if sys.implementation.name == \'cpython\' and sys.version_info[:2] == (3, 10) else 1)"\n      - name: Test bounded regex workflows\n        run: python -m unittest test_regex_family test_native_regex_family_measurement test_native_regex_family_profile -v\n      - name: Test bounded regex workflows optimized\n        run: python -O -m unittest test_regex_family test_native_regex_family_measurement test_native_regex_family_profile -v\n      - name: Test timing runner on actual Python 3.10\n        run: python -m scripts.run_tests test_test_durations -v\n      - name: Test timing runner optimized on actual Python 3.10\n        run: python -O -m scripts.run_tests test_test_durations -v\n\n'

def check_job(case, source):
    block = source.split('jobs:\n', 1)[1].split('  build:\n', 1)[0]
    case.assertEqual(block, EXPECTED)
    release = source.split('  release:\n', 1)[1]
    case.assertIn("    if: startsWith(github.ref, 'refs/tags/v') && github.event_name == 'push'\n    needs: [build, regex-python310]\n", release)

class RegexPython310WorkflowTests(unittest.TestCase):
    def test_exact_closed_actual_interpreter_gate(self):
        source = (ROOT/'.github/workflows/build.yml').read_text()
        check_job(self, source)
        for forbidden in ('secrets.', 'upload-artifact', 'workflow_dispatch', 'native-1c', 'continue-on-error'):
            self.assertNotIn(forbidden, EXPECTED)
        project = (ROOT/'pyproject.toml').read_text()
        for pin in ('prompt-toolkit==3.0.53', 'pyuca==1.2', 'tzdata==2026.5'):
            self.assertIn(pin, project)

    def test_downgraded_version_permissions_timeout_or_release_rejected(self):
        source = (ROOT/'.github/workflows/build.yml').read_text()
        for old, new in (("python-version: '3.10'", "python-version: '3.12'"),
                         ('timeout-minutes: 10', 'timeout-minutes: 60'),
                         ('persist-credentials: false', 'persist-credentials: true'),
                         ('      contents: read', '      contents: write'),
                         ('needs: [build, regex-python310]', 'needs: build'),
                         ('python -O -m unittest test_regex_family', 'python -m unittest test_regex_family')):
            with self.subTest(old=old), self.assertRaises(AssertionError):
                check_job(self, source.replace(old, new, 1))

if __name__ == '__main__': unittest.main()
