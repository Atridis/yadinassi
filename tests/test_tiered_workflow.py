"""Closed scheduling/security contracts, not a second YAML workflow interpreter."""
from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parents[1]


def section(source, name):
    block=source.split('\n  '+name+':\n',1)[1]
    import re
    return re.split(r'\n  [a-z][a-z0-9-]*:\n',block,maxsplit=1)[0]


def assert_phase_dependencies(test, source):
    """Check literal DAG edges, not a simulation of GitHub's scheduler."""
    import re
    for job, needs in (('light', 'admission'),
                       ('heavy', '[admission, light]'),
                       ('build', '[admission, heavy]')):
        block = section(source, job)
        test.assertEqual(re.findall(r'^    needs: (.+)$', block, re.M), [needs])
        conditions = re.findall(r'^    if: (.+)$', block, re.M)
        test.assertEqual(conditions, [] if job == 'light' else
                         ["needs.admission.outputs.heavy == 'true'"])
        test.assertNotIn('always()', block)
        test.assertNotIn('continue-on-error', block)


class TieredWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.source=(ROOT/'.github/workflows/build.yml').read_text(encoding='utf-8')

    def test_real_ready_and_head_update_triggers_no_privileged_pr_event(self):
        self.assertIn('types: [opened, synchronize, reopened, ready_for_review]',self.source)
        self.assertNotIn('pull_request_target',self.source)
        self.assertNotIn('workflow_run:',self.source)
        self.assertNotIn('secrets.',self.source)
        self.assertNotIn('continue-on-error',self.source)
        self.assertNotIn('contents: write',self.source.split('\n  release:\n')[0])
        self.assertIn('branches: [main]',self.source)
        self.assertIn("tags: ['**']",self.source)

    def test_light_every_event_heavy_and_packaging_only_candidate(self):
        light=section(self.source,'light')
        self.assertNotIn('    if:',light.split('    steps:', 1)[0])
        self.assertIn('--tier light --report',light)
        self.assertIn('python integrational_tests/check_launcher.py',light)
        self.assertNotIn('scripts/build.py',light)
        for name in ('heavy','build'):
            self.assertIn("    if: needs.admission.outputs.heavy == 'true'",section(self.source,name))
        self.assertIn('--tier heavy --shard-count ${{ matrix.shard_count }}',section(self.source,'heavy'))
        self.assertIn('python scripts/build.py --target',section(self.source,'build'))

    def test_phases_preserve_draft_skips_and_fail_closed_verdict(self):
        # Draft: light runs, heavy is false and build remains skipped. Ready:
        # success-only needs edges serialize whole matrices; failed/skipped
        # prerequisites cannot produce an accepted partial phase.
        assert_phase_dependencies(self, self.source)
        verdict = section(self.source, 'verdict')
        self.assertIn("if: always() && needs.admission.result == 'success'", verdict)
        self.assertIn('needs: [admission, light, heavy, build, regex-python310, javascript]', verdict)
        self.assertIn("expected='success' if e['PHASE_HEAVY']=='true' else 'skipped'", verdict)
        self.assertIn("e['HEAVY_RESULT']==e['BUILD_RESULT']==expected", verdict)
        for job, output in (('light', 'light_matrix'), ('heavy', 'heavy_matrix'), ('build', 'light_matrix')):
            block = section(self.source, job)
            self.assertIn('matrix: ${{ fromJSON(needs.admission.outputs.' + output + ') }}', block)
            self.assertNotIn('          - target:', block)
        # Ordinary PR/main mac demand is 1 -> 2 -> 1. Tags/manual remain
        # 2 -> 3 -> 2; no runner is allocated just to skip its steps.

    def test_missing_or_bypassed_phase_dependencies_are_rejected(self):
        for changed in (
            self.source.replace('needs: [admission, light]', 'needs: admission'),
            self.source.replace('needs: [admission, heavy]', 'needs: admission'),
            self.source.replace('needs: [admission, heavy]', 'needs: [admission, light]'),
            self.source.replace("if: needs.admission.outputs.heavy == 'true'",
                                "if: always() && needs.admission.outputs.heavy == 'true'"),
        ):
            with self.assertRaises(AssertionError):
                assert_phase_dependencies(self, changed)

    def test_heavy_matrix_and_package_matrix_have_no_independent_scope(self):
        heavy = section(self.source, 'heavy')
        self.assertIn('matrix: ${{ fromJSON(needs.admission.outputs.heavy_matrix) }}', heavy)
        self.assertIn('--shard-count ${{ matrix.shard_count }} --shard-index ${{ matrix.shard_index }}', heavy)
        self.assertIn('fail-fast: false', heavy)
        build = section(self.source, 'build')
        self.assertIn('matrix: ${{ fromJSON(needs.admission.outputs.light_matrix) }}', build)
        self.assertNotIn('github.ref', build.split('    steps:', 1)[0])
        self.assertNotIn('exclude:', self.source)

    def test_verdict_requires_both_tiers_build_and_compatibility(self):
        verdict=section(self.source,'verdict')
        self.assertIn('needs: [admission, light, heavy, build, regex-python310, javascript]',verdict)
        self.assertIn("if: always() && needs.admission.result == 'success'",verdict)
        for value in ('needs.light.result','needs.heavy.result','needs.build.result','needs.regex-python310.result','needs.javascript.result'):
            self.assertIn(value,verdict)
        self.assertIn('ci_test_gate.py verdict',verdict)
        self.assertIn('partition-${{ github.run_attempt }}-*',verdict)
        self.assertIn('test-verdict-${{ github.run_attempt }}',verdict)
        self.assertIn('needs: [build, regex-python310, verdict]',section(self.source,'release'))

    def test_exact_checkout_binding_and_no_credentials_persisted(self):
        for name in ('light','heavy','build','verdict','javascript'):
            block=section(self.source,name)
            self.assertIn('ref: ${{ needs.admission.outputs.source_sha }}',block)
            self.assertIn('persist-credentials: false',block)
            self.assertIn('ci_test_gate.py checkout --binding ci-binding/binding.json',block)
            self.assertIn('name: ci-binding-${{ github.run_attempt }}',block)
        admission=section(self.source,'admission')
        self.assertIn('ref: ${{ github.sha }}',admission)
        self.assertIn('ci_test_gate.py admit',admission)
        self.assertNotIn('git push',self.source)


    def test_failure_diagnostics_run_without_masking_partition_failure(self):
        for job in ('light', 'heavy'):
            block = section(self.source, job)
            self.assertIn("        id: partition\n        run: python -m scripts.test_partition", block)
            self.assertIn("        id: stamp\n        if: ${{ !cancelled() && (steps.partition.outcome == 'success' || steps.partition.outcome == 'failure') && hashFiles('test-results/partition.json') != '' }}\n        run: python scripts/ci_test_gate.py stamp", block)
            self.assertIn("      - uses: actions/upload-artifact@v7\n        if: ${{ !cancelled() && steps.stamp.outcome == 'success' }}", block)
            self.assertIn('          if-no-files-found: error', block)
            self.assertNotIn('continue-on-error', block)
            self.assertNotIn('|| true', block)
        verdict = section(self.source, 'verdict')
        self.assertIn("e['LIGHT_RESULT']==e['COMPAT_RESULT']==e['JAVASCRIPT_RESULT']=='success'", verdict)
        self.assertIn("e['HEAVY_RESULT']==e['BUILD_RESULT']==expected", verdict)

    def test_main_jobs_have_bounded_timeouts_with_measured_headroom(self):
        for job, minutes in (('light', 30), ('heavy', 45), ('build', 40), ('javascript', 5)):
            block = section(self.source, job).split('    steps:', 1)[0]
            self.assertIn(f'    timeout-minutes: {minutes}\n', block)

    def test_existing_javascript_suites_are_required_without_install_or_browser(self):
        block = section(self.source, 'javascript')
        self.assertIn('    needs: admission\n', block)
        self.assertNotIn('    if:', block)
        self.assertIn('actions/setup-node@v7', block)
        self.assertIn("          node-version: '22'", block)
        self.assertIn('          package-manager-cache: false', block)
        self.assertIn('run: node --test frontend/catalog/test/client.test.mjs tests/browser_ui/support.test.mjs', block)
        for forbidden in ('npm ', 'playwright', 'contents: write', 'continue-on-error', 'secrets.'):
            self.assertNotIn(forbidden, block)


if __name__=='__main__':unittest.main()
