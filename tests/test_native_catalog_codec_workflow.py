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


def legacy_codec_view(block):
    """Select the unchanged old-route branches; separate tests cover new route."""
    # Exact inverse for the new route: do not erase arbitrary commands/env.
    block = block.replace('      numeric_code_sha256: ${{ steps.native.outputs.numeric_code_sha256 }}\n', '')
    for key,source in (('SHA256','numeric_code_sha256'),('RUN_ID','run_id'),('RUN_ATTEMPT','run_attempt')):
        block = block.replace('          NUMERIC_CODE3_'+key+': ${{ needs.native_codec_a.outputs.'+source+' }}\n', '')
    block = block.replace(" || needs.eligibility.outputs.route == 'catalog-numeric-code-measurement-v1'", '')
    block = block.replace("needs.eligibility.outputs.route == 'catalog-numeric-code-measurement-v1' && 'numeric-code' || ", '')
    numeric_numbers = ('3',) if block.startswith('    name: Native 1C reference codec case A\n') else ('6',) if block.startswith('    name: Native 1C reference codec case B\n') else ()
    for number in numeric_numbers:
        block = block.replace("needs.eligibility.outputs.route == 'catalog-numeric-code-measurement-v1' && 'numeric_code"+number+".json' || ", '')
        command = 'python3 scripts/native_1c_db_oracle.py --execute-approved-image --file-db-oracle --catalog-numeric-code number'+number+' --output native-db-oracle/numeric_code'+number+'.json'
        branch = '          if [ "${{ needs.eligibility.outputs.route }}" = catalog-numeric-code-measurement-v1 ]; then\n            '+command+'\n          elif '
        block = block.replace(branch, '          if ')
    branch = '          if [ "${{ needs.eligibility.outputs.route }}" = catalog-numeric-code-measurement-v1 ]; then\n            python3 scripts/native_1c_db_oracle.py --validate-numeric-code3\n          elif '
    block = block.replace(branch, '          if ')
    # Exact inverse for the new route: do not erase arbitrary commands/env.
    block = block.replace('      params_slots_sha256: ${{ steps.native.outputs.params_slots_sha256 }}\n', '')
    for key,source in (('SHA256','params_slots_sha256'),('RUN_ID','run_id'),('RUN_ATTEMPT','run_attempt')):
        block = block.replace('          PARAMS_SLOTS8_'+key+': ${{ needs.native_codec_a.outputs.'+source+' }}\n', '')
    block = block.replace(" || needs.eligibility.outputs.route == 'catalog-params-slot-measurement-v1'", '')
    block = block.replace("needs.eligibility.outputs.route == 'catalog-params-slot-measurement-v1' && 'params-slots' || ", '')
    for number in ('8','17'):
        block = block.replace("needs.eligibility.outputs.route == 'catalog-params-slot-measurement-v1' && 'params_slots"+number+".json' || ", '')
        command = 'python3 scripts/native_1c_db_oracle.py --execute-approved-image --file-db-oracle --catalog-params-slots description'+number+' --output native-db-oracle/params_slots'+number+'.json'
        branch = '          if [ "${{ needs.eligibility.outputs.route }}" = catalog-params-slot-measurement-v1 ]; then\n            '+command+'\n          elif '
        block = block.replace(branch, '          if ')
    branch = '          if [ "${{ needs.eligibility.outputs.route }}" = catalog-params-slot-measurement-v1 ]; then\n            python3 scripts/native_1c_db_oracle.py --validate-params-slots8\n          elif '
    block = block.replace(branch, '          if ')
    # Exact inverse for the new route: do not erase arbitrary commands/env.
    block = block.replace('      description_rows_sha256: ${{ steps.native.outputs.description_rows_sha256 }}\n', '')
    for key,source in (('SHA256','description_rows_sha256'),('RUN_ID','run_id'),('RUN_ATTEMPT','run_attempt')):
        block = block.replace('          DESCRIPTION_ROWS8_'+key+': ${{ needs.native_codec_a.outputs.'+source+' }}\n', '')
    block = block.replace(" || needs.eligibility.outputs.route == 'catalog-description-rows-v1'", '')
    block = block.replace("needs.eligibility.outputs.route == 'catalog-description-rows-v1' && 'description-rows' || ", '')
    for number in ('8','17'):
        block = block.replace("needs.eligibility.outputs.route == 'catalog-description-rows-v1' && 'description_rows"+number+".json' || ", '')
        command = 'python3 scripts/native_1c_db_oracle.py --execute-approved-image --file-db-oracle --catalog-description-rows description'+number+' --output native-db-oracle/description_rows'+number+'.json'
        branch = '          if [ "${{ needs.eligibility.outputs.route }}" = catalog-description-rows-v1 ]; then\n            '+command+'\n          elif '
        block = block.replace(branch, '          if ')
    branch = '          if [ "${{ needs.eligibility.outputs.route }}" = catalog-description-rows-v1 ]; then\n            python3 scripts/native_1c_db_oracle.py --validate-description-rows8\n          elif '
    block = block.replace(branch, '          if ')
    block = re.sub(r"^      description_sha256:.*\n", "", block, flags=re.M)
    block = re.sub(r"^          DESCRIPTION8_(?:SHA256|RUN_ID|RUN_ATTEMPT):.*\n", "", block, flags=re.M)
    block = block.replace(" || needs.eligibility.outputs.route == 'catalog-description-measurement-v1'", "")
    block = block.replace("needs.eligibility.outputs.route == 'catalog-description-measurement-v1' && 'description' || ", "")
    for case,number in (('a','8'),('b','17')):
        long = "${{ needs.eligibility.outputs.route == 'catalog-description-measurement-v1' && 'description"+number+".json' || format('{0}_distinct_"+case+".json', needs.eligibility.outputs.route == 'catalog-reference-rows-v1' && 'rows' || 'codec') }}"
        short = "${{ needs.eligibility.outputs.route == 'catalog-reference-rows-v1' && 'rows' || 'codec' }}_distinct_"+case+".json"
        block = block.replace(long, short)
    block = re.sub(r'        run: \|\n          if \[ .*? = catalog-description-measurement-v1 \]; then\n            [^\n]+\n          else\n            ([^\n]+)\n          fi', r'        run: \1', block)
    return block


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
        self.assertIn('          NATIVE_DB_ROUTE: catalog-numeric-code-measurement-v1\n', eligibility)
        for name in ('native_reference_a', 'native_oracle'):
            self.assertIn("needs.eligibility.outputs.route == 'catalog-reference-identity-v1' &&", old.workflow_job(name))
        for name in ('native_codec_a', 'native_codec_b'):
            self.assertIn("(needs.eligibility.outputs.route == 'catalog-reference-codec-v1' || needs.eligibility.outputs.route == 'catalog-reference-rows-v1' || needs.eligibility.outputs.route == 'catalog-description-measurement-v1' || needs.eligibility.outputs.route == 'catalog-description-rows-v1' || needs.eligibility.outputs.route == 'catalog-params-slot-measurement-v1' || needs.eligibility.outputs.route == 'catalog-numeric-code-measurement-v1') &&", old.workflow_job(name))
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
            actual = legacy_codec_view(old.workflow_job(new_name))
            selector = "${{ needs.eligibility.outputs.route == 'catalog-reference-rows-v1' && 'rows' || 'codec' }}"
            actual = actual.replace(selector, 'codec').replace(
                "(needs.eligibility.outputs.route == 'catalog-reference-codec-v1' || needs.eligibility.outputs.route == 'catalog-reference-rows-v1')",
                "needs.eligibility.outputs.route == 'catalog-reference-codec-v1'")
            self.assertEqual(actual.strip(), expected.strip())
        block = old.workflow_job('native_codec_b').replace("${{ needs.eligibility.outputs.route == 'catalog-reference-rows-v1' && 'rows' || 'codec' }}", 'codec')
        self.assertLess(block.index('--validate-codec-a'), block.index('GHCR_TOKEN:'))
        before = block[:block.index('--validate-codec-a')]
        self.assertNotIn('GHCR_TOKEN:', before)
        self.assertIn('artifact-ids: ${{ needs.native_codec_a.outputs.artifact_id }}', before)
        self.assertIn('digest-mismatch: error', before)
        self.assertNotIn('github-token:', block)

    def test_new_route_inverse_does_not_hide_command_or_handoff_drift(self):
        for name,old_value,new_value in (
            ('native_codec_a','--catalog-numeric-code number3','--catalog-numeric-code number6'),
            ('native_codec_b','--validate-numeric-code3','--validate-description8'),
            ('native_codec_b','NUMERIC_CODE3_SHA256: ${{ needs.native_codec_a.outputs.numeric_code_sha256 }}','NUMERIC_CODE3_SHA256: foreign'),
            ('native_codec_a','numeric_code_sha256: ${{ steps.native.outputs.numeric_code_sha256 }}','numeric_code_sha256: foreign'),
            ('native_codec_a',"'numeric_code3.json'","'numeric_code6.json'"),
            ('native_codec_a','--catalog-params-slots description8','--catalog-params-slots description17'),
            ('native_codec_b','--validate-params-slots8','--validate-description8'),
            ('native_codec_b','PARAMS_SLOTS8_SHA256: ${{ needs.native_codec_a.outputs.params_slots_sha256 }}','PARAMS_SLOTS8_SHA256: foreign'),
            ('native_codec_a','params_slots_sha256: ${{ steps.native.outputs.params_slots_sha256 }}','params_slots_sha256: foreign'),
            ('native_codec_a','--catalog-description-rows description8','--catalog-description-rows description17'),
            ('native_codec_b','--validate-description-rows8','--validate-description8'),
            ('native_codec_b','DESCRIPTION_ROWS8_SHA256: ${{ needs.native_codec_a.outputs.description_rows_sha256 }}','DESCRIPTION_ROWS8_SHA256: foreign'),
            ('native_codec_a','description_rows_sha256: ${{ steps.native.outputs.description_rows_sha256 }}','description_rows_sha256: foreign'),
        ):
            original=old.workflow_job(name)
            self.assertIn(old_value,original)
            self.assertNotEqual(legacy_codec_view(original),legacy_codec_view(original.replace(old_value,new_value)))

    def test_selected_verdict_is_closed_and_requires_unselected_skip(self):
        program = old.inline_program('verdict')
        block = program.split('# BEGIN NATIVE DB ORACLE ROUTE VERDICT\n', 1)[1].split('# END NATIVE DB ORACLE ROUTE VERDICT', 1)[0]
        namespace = {}
        exec(compile(textwrap.dedent(block), '<route-verdict>', 'exec'), namespace)
        select = namespace['selected_native_result']
        states = ('success', 'failure', 'cancelled', 'skipped', 'timed_out', '', None)
        for route, reference_a, reference_b, codec_a, codec_b in itertools.product(
                ('catalog-reference-identity-v1', 'catalog-reference-codec-v1', 'catalog-reference-rows-v1', 'catalog-description-measurement-v1', 'catalog-description-rows-v1', 'catalog-params-slot-measurement-v1', 'catalog-numeric-code-measurement-v1', '', None, 'other'), states, states, states, states):
            expected = ('success' if route == 'catalog-reference-identity-v1' and reference_a == reference_b == 'success' and codec_a == codec_b == 'skipped'
                        or route in ('catalog-reference-codec-v1', 'catalog-reference-rows-v1', 'catalog-description-measurement-v1', 'catalog-description-rows-v1', 'catalog-params-slot-measurement-v1', 'catalog-numeric-code-measurement-v1') and codec_a == codec_b == 'success' and reference_a == reference_b == 'skipped' else 'failure')
            self.assertEqual(select(route, reference_a, reference_b, codec_a, codec_b), expected)

    def test_actual_admission_rejects_unknown_missing_route_without_output(self):
        program = old.inline_program('eligibility')
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            event, context = old.fixtures()
            (root/'event.json').write_text(json.dumps(event), encoding='utf-8')
            context.update(GITHUB_EVENT_PATH=str(root/'event.json'), GITHUB_OUTPUT=str(root/'output'))
            for route in (None, '', 'other', 'catalog-reference-codec-v1', 'catalog-reference-identity-v1', 'catalog-reference-rows-v1', 'catalog-description-measurement-v1', 'catalog-description-rows-v1', 'catalog-params-slot-measurement-v1', 'catalog-numeric-code-measurement-v1'):
                env = dict(context)
                if route is not None: env['NATIVE_DB_ROUTE'] = route
                output = root/'output'
                if output.exists(): output.unlink()
                result = subprocess.run([sys.executable,'-I','-B','-c',program], env=old.subprocess_environment(env), capture_output=True)
                accepted = route in ('catalog-reference-codec-v1', 'catalog-reference-identity-v1', 'catalog-reference-rows-v1', 'catalog-description-measurement-v1', 'catalog-description-rows-v1', 'catalog-params-slot-measurement-v1', 'catalog-numeric-code-measurement-v1')
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
