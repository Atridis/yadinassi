"""Fixed reviewed-source route selection; no second native pair per push."""
import hashlib
import itertools
import re
import json
import subprocess
import sys
import tempfile
from pathlib import Path
import textwrap
import unittest

import test_native_1c_db_oracle_ci_policy as old


class CodecWorkflowTests(unittest.TestCase):
    def test_original_measurement_steps_unchanged(self):
        for job, expected in (
            ('native_reference_a', 'f8f3322650e3b9c4a82968457c2ba79886ff019ec7ee453b764c21969f48a860'),
            ('native_oracle', 'bd3599066bb8bbc61e6eff667947a00c629233496d473dfa7a5092162a700ff2'),
        ):
            steps = old.workflow_job(job).split('    steps:\n', 1)[1]
            self.assertEqual(hashlib.sha256(steps.encode()).hexdigest(), expected)

    def test_fixed_selector_disjoint_jobs_and_exact_dependencies(self):
        eligibility = old.workflow_job('eligibility')
        self.assertIn('    outputs:\n      route: ${{ steps.admission.outputs.route }}\n', eligibility)
        self.assertIn('          NATIVE_DB_ROUTE: catalog-reference-rows-v1\n', eligibility)
        for name in ('native_reference_a', 'native_oracle'):
            self.assertIn("needs.eligibility.outputs.route == 'catalog-reference-identity-v1' &&", old.workflow_job(name))
        for name in ('native_codec_a', 'native_codec_b'):
            self.assertIn("(needs.eligibility.outputs.route == 'catalog-reference-codec-v1' || needs.eligibility.outputs.route == 'catalog-reference-rows-v1') &&", old.workflow_job(name))
        self.assertIn('needs: eligibility', old.workflow_job('native_codec_a'))
        self.assertIn('needs: [eligibility, native_codec_a]', old.workflow_job('native_codec_b'))
        self.assertIn("needs.native_codec_a.result == 'success' &&", old.workflow_job('native_codec_b'))
        self.assertIn('needs: [eligibility, native_reference_a, native_oracle, native_codec_a, native_codec_b]', old.workflow_job('verdict'))

    def test_codec_jobs_preserve_all_security_and_change_only_route_outputs(self):
        pairs = (('native_reference_a','native_codec_a'), ('native_oracle','native_codec_b'))
        for old_name, new_name in pairs:
            expected = old.workflow_job(old_name)
            expected = expected.replace('reference identity case', 'reference codec case')
            expected = expected.replace("catalog-reference-identity-v1", "catalog-reference-codec-v1")
            expected = expected.replace('native_reference_a', 'native_codec_a')
            expected = expected.replace('--catalog-reference-identity ', '--catalog-reference-codec ')
            expected = expected.replace('--validate-reference-a', '--validate-codec-a')
            expected = expected.replace('native-1c-reference-', 'native-1c-codec-')
            expected = expected.replace('native-db-oracle/distinct_', 'native-db-oracle/codec_distinct_')
            expected = expected.replace('native-db-oracle/reference-aggregate.json', 'native-db-oracle/codec-aggregate.json')
            actual = old.workflow_job(new_name)
            selector = "${{ needs.eligibility.outputs.route == 'catalog-reference-rows-v1' && 'rows' || 'codec' }}"
            actual = actual.replace(selector, 'codec').replace(
                "(needs.eligibility.outputs.route == 'catalog-reference-codec-v1' || needs.eligibility.outputs.route == 'catalog-reference-rows-v1')",
                "needs.eligibility.outputs.route == 'catalog-reference-codec-v1'")
            self.assertEqual(actual, expected)
        block = old.workflow_job('native_codec_b').replace("${{ needs.eligibility.outputs.route == 'catalog-reference-rows-v1' && 'rows' || 'codec' }}", 'codec')
        self.assertLess(block.index('--validate-codec-a'), block.index('GHCR_TOKEN:'))
        before = block[:block.index('--validate-codec-a')]
        self.assertNotIn('GHCR_TOKEN:', before)
        self.assertIn('artifact-ids: ${{ needs.native_codec_a.outputs.artifact_id }}', before)
        self.assertIn('digest-mismatch: error', before)
        self.assertNotIn('github-token:', block)

    def test_selected_verdict_is_closed_and_requires_unselected_skip(self):
        program = old.inline_program('verdict')
        block = program.split('# BEGIN NATIVE DB ORACLE ROUTE VERDICT\n', 1)[1].split('# END NATIVE DB ORACLE ROUTE VERDICT', 1)[0]
        namespace = {}
        exec(compile(textwrap.dedent(block), '<route-verdict>', 'exec'), namespace)
        select = namespace['selected_native_result']
        states = ('success', 'failure', 'cancelled', 'skipped', 'timed_out', '', None)
        for route, reference_a, reference_b, codec_a, codec_b in itertools.product(
                ('catalog-reference-identity-v1', 'catalog-reference-codec-v1', 'catalog-reference-rows-v1', '', None, 'other'), states, states, states, states):
            expected = ('success' if route == 'catalog-reference-identity-v1' and reference_a == reference_b == 'success' and codec_a == codec_b == 'skipped'
                        or route in ('catalog-reference-codec-v1', 'catalog-reference-rows-v1') and codec_a == codec_b == 'success' and reference_a == reference_b == 'skipped' else 'failure')
            self.assertEqual(select(route, reference_a, reference_b, codec_a, codec_b), expected)

    def test_actual_admission_rejects_unknown_missing_route_without_output(self):
        program = old.inline_program('eligibility')
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            event, context = old.fixtures()
            (root/'event.json').write_text(json.dumps(event), encoding='utf-8')
            context.update(GITHUB_EVENT_PATH=str(root/'event.json'), GITHUB_OUTPUT=str(root/'output'))
            for route in (None, '', 'other', 'catalog-reference-codec-v1', 'catalog-reference-identity-v1', 'catalog-reference-rows-v1'):
                env = dict(context)
                if route is not None: env['NATIVE_DB_ROUTE'] = route
                output = root/'output'
                if output.exists(): output.unlink()
                result = subprocess.run([sys.executable,'-I','-B','-c',program], env=old.subprocess_environment(env), capture_output=True)
                accepted = route in ('catalog-reference-codec-v1', 'catalog-reference-identity-v1', 'catalog-reference-rows-v1')
                self.assertEqual(result.returncode, 0 if accepted else 1)
                self.assertEqual(output.exists(), accepted)
                if accepted: self.assertEqual(output.read_text(), 'route='+route+'\n')
            output.unlink()
            context.update(NATIVE_DB_ROUTE='catalog-reference-codec-v1', GITHUB_ACTOR='foreign')
            result = subprocess.run([sys.executable,'-I','-B','-c',program], env=old.subprocess_environment(context), capture_output=True)
            self.assertEqual(result.returncode, 1)
            self.assertFalse(output.exists())



if __name__ == '__main__':
    unittest.main()
