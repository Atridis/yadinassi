"""Keep informational timings independent within the ordinary CI workflow."""
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]


class PerformanceWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.build = (ROOT / '.github/workflows/build.yml').read_text(encoding='utf-8')
        from_performance = self.build.split('  performance:\n', 1)[1]
        self.job = re.split(r'(?m)^  [a-zA-Z0-9_-]+:\s*$', from_performance, maxsplit=1)[0]

    def test_no_job_dependencies_in_either_direction(self):
        self.assertNotRegex(self.job, r'(?m)^    (needs|if|continue-on-error):')
        self.assertNotRegex(self.build, r'needs\.performance\b')
        for dependency in re.findall(r'(?m)^    needs: (.*)$', self.build):
            self.assertNotIn('performance', dependency)

    def test_single_workflow_owns_timing_commands(self):
        self.assertFalse((ROOT / '.github/workflows/performance.yml').exists())
        owners = [p.name for p in (ROOT / '.github/workflows').glob('*.yml')
                  if 'scripts/benchmark_execution_layers.py' in p.read_text(encoding='utf-8')]
        self.assertEqual(owners, ['build.yml'])
        self.assertIn("ref: ${{ github.event.pull_request.head.sha || github.sha }}", self.job)

    def test_default_and_prepared_reports_remain_distinct(self):
        for route in ('default', 'prepared'):
            self.assertIn(f'--bsl-route {route} --iterations 100000 --rounds 9', self.job)
        for name in ('execution-layers.json', 'execution-layers-prepared.json',
                     'summary.md', 'summary-prepared.md'):
            self.assertIn('performance-results/' + name, self.job)
        publish = [line for line in self.job.splitlines()
                   if 'scripts/benchmark_report.py' in line and '>> "$GITHUB_STEP_SUMMARY"' in line]
        self.assertEqual(len(publish), 1)
        self.assertIn('summary-paired.md', publish[0])
        self.assertIn('if: always()', self.job)
        self.assertIn('retention-days: 30', self.job)

    def test_no_speed_gate_but_correctness_errors_are_not_hidden(self):
        self.assertIn('no speed gate', self.job)
        self.assertIn('Порогов скорости нет', self.job)
        self.assertNotIn('continue-on-error', self.job)
        self.assertIn('tests.test_benchmark_execution_layers tests.test_benchmark_summary', self.job)

    def test_extended_reports_share_independent_job_and_artifact(self):
        for route in ('default', 'prepared'):
            self.assertIn('--iterations 64 --rounds 5 --bsl-route ' + route, self.job)
            for extension in ('json', 'md'):
                self.assertIn('performance-results/extended-' + route + '.' + extension, self.job)
        self.assertIn('python -m unittest tests.test_benchmark_extended_layers', self.job)
        self.assertIn('path: performance-results/', self.job)

    def test_diagnostics_are_a_separate_process_after_all_timings(self):
        marker = self.job.index('- name: Collect separate untimed execution diagnostics')
        for name in ('- name: Measure Python and BSL',
                     '- name: Measure prepared execution separately',
                     '- name: Measure extended default reference',
                     '- name: Measure extended prepared reference'):
            self.assertLess(self.job.index(name), marker)
        self.assertIn('python scripts/benchmark_diagnostics.py --iterations 8', self.job)
        self.assertIn('performance-results/diagnostics.json', self.job)
        self.assertIn('performance-results/diagnostics.md', self.job)

    def test_paired_summary_runs_after_timings_even_on_partial_failure(self):
        marker = self.job.index('- name: Publish paired performance summary')
        self.assertGreater(marker, self.job.index('- name: Measure extended prepared reference'))
        self.assertLess(marker, self.job.index('- name: Collect separate untimed execution diagnostics'))
        block = self.job[marker:self.job.index('- name: Collect separate untimed execution diagnostics')]
        self.assertIn('if: ${{ !cancelled() }}', block)
        self.assertIn('scripts/benchmark_report.py', block)
        self.assertIn('performance-results/summary-paired.md', block)
        for name in ('summary.md', 'summary-prepared.md', 'extended-default.md', 'extended-prepared.md'):
            self.assertNotIn('cat performance-results/' + name, self.job)
