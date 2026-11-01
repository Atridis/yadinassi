"""Closed scheduling/security contracts, not a second YAML workflow interpreter."""
from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parents[1]


def section(source, name):
    block=source.split('\n  '+name+':\n',1)[1]
    import re
    return re.split(r'\n  [a-z][a-z0-9-]*:\n',block,maxsplit=1)[0]


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
        self.assertNotIn('    if:',light)
        self.assertIn('--tier light --report',light)
        self.assertIn('python integrational_tests/check_launcher.py',light)
        self.assertNotIn('scripts/build.py',light)
        for name in ('heavy','build'):
            self.assertIn("    if: needs.admission.outputs.heavy == 'true'",section(self.source,name))
        self.assertIn('--tier heavy --shard-count ${{ matrix.shard_count }}',section(self.source,'heavy'))
        self.assertIn('python scripts/build.py --target',section(self.source,'build'))

    def test_two_separate_intel_jobs_and_one_other_platform_each(self):
        heavy=section(self.source,'heavy')
        self.assertEqual(heavy.count('          - target: mac-x86\n'),2)
        self.assertEqual(heavy.count('            shard_count: 2\n'),2)
        self.assertEqual(heavy.count('            shard_index: 1\n'),1)
        for name in ('linux','windows','mac-arm'):
            self.assertEqual(heavy.count('          - target: '+name+'\n'),1)
        self.assertIn('fail-fast: false',heavy)

    def test_verdict_requires_both_tiers_build_and_compatibility(self):
        verdict=section(self.source,'verdict')
        self.assertIn('needs: [admission, light, heavy, build, regex-python310]',verdict)
        self.assertIn("if: always() && needs.admission.result == 'success'",verdict)
        for value in ('needs.light.result','needs.heavy.result','needs.build.result','needs.regex-python310.result'):
            self.assertIn(value,verdict)
        self.assertIn('ci_test_gate.py verdict',verdict)
        self.assertIn('partition-${{ github.run_attempt }}-*',verdict)
        self.assertIn('test-verdict-${{ github.run_attempt }}',verdict)
        self.assertIn('needs: [build, regex-python310, verdict]',section(self.source,'release'))

    def test_exact_checkout_binding_and_no_credentials_persisted(self):
        for name in ('light','heavy','build','verdict'):
            block=section(self.source,name)
            self.assertIn('ref: ${{ needs.admission.outputs.source_sha }}',block)
            self.assertIn('persist-credentials: false',block)
            self.assertIn('ci_test_gate.py checkout --binding ci-binding/binding.json',block)
            self.assertIn('name: ci-binding-${{ github.run_attempt }}',block)
        admission=section(self.source,'admission')
        self.assertIn('ref: ${{ github.sha }}',admission)
        self.assertIn('ci_test_gate.py admit',admission)
        self.assertNotIn('git push',self.source)


if __name__=='__main__':unittest.main()
