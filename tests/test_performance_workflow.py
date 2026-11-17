"""Keep informational timings independent within the ordinary CI workflow."""
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]


class PerformanceWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.build = (ROOT / '.github/workflows/build.yml').read_text()
        self.job = self.build.split('  performance:\n', 1)[1].split('\n  light:\n', 1)[0]

    def test_no_job_dependencies_in_either_direction(self):
        self.assertNotRegex(self.job, r'(?m)^    (needs|if|continue-on-error):')
        self.assertNotRegex(self.build, r'needs\.performance\b')
        for dependency in re.findall(r'(?m)^    needs: (.*)$', self.build):
            self.assertNotIn('performance', dependency)

    def test_single_workflow_owns_timing_commands(self):
        self.assertFalse((ROOT / '.github/workflows/performance.yml').exists())
        owners = [p.name for p in (ROOT / '.github/workflows').glob('*.yml')
                  if 'scripts/benchmark_execution_layers.py' in p.read_text()]
        self.assertEqual(owners, ['build.yml'])
        self.assertIn("ref: ${{ github.event.pull_request.head.sha || github.sha }}", self.job)

    def test_default_and_prepared_reports_remain_distinct(self):
        for route in ('default', 'prepared'):
            self.assertIn(f'--bsl-route {route} --iterations 100000 --rounds 9', self.job)
        for name in ('execution-layers.json', 'execution-layers-prepared.json',
                     'summary.md', 'summary-prepared.md'):
            self.assertIn('performance-results/' + name, self.job)
        self.assertEqual(self.job.count('>> "$GITHUB_STEP_SUMMARY"'), 3)
        self.assertIn('if: always()', self.job)
        self.assertIn('retention-days: 30', self.job)

    def test_no_speed_gate_but_correctness_errors_are_not_hidden(self):
        self.assertIn('no speed gate', self.job)
        self.assertIn('No speed threshold is enforced', self.job)
        self.assertNotIn('continue-on-error', self.job)
        self.assertIn('tests.test_benchmark_execution_layers tests.test_benchmark_summary', self.job)
