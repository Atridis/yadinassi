"""Numeric measurement uses the existing credential pair and closed shell dispatch."""
import itertools
import unittest
import test_native_1c_db_oracle_ci_policy as old
import test_native_params_slot_workflow as shell

ROUTE = 'catalog-numeric-code-rows-v1'
ROUTES = shell.ROUTES + ('catalog-numeric-code-measurement-v1', ROUTE,)

class NumericCodeRowsWorkflowTests(unittest.TestCase):
    def test_admission_and_exhaustive_final_gate(self):
        class PolicyError(ValueError): pass
        namespace = {'PolicyError': PolicyError}
        exec(shell.marker('eligibility', 'ROUTE ADMISSION'), namespace)
        for route in ROUTES:
            self.assertEqual(namespace['admitted_route'](route), route)
        for value in (None, True, '', 'catalog-numeric-code-measurement-v2', 'foreign'):
            with self.assertRaises(PolicyError):
                namespace['admitted_route'](value)
        exec(shell.marker('verdict', 'ROUTE VERDICT'), namespace)
        for states in itertools.product(('success', 'failure', 'cancelled', 'skipped', 'timed_out', None), repeat=4):
            expected = 'success' if states == ('skipped', 'skipped', 'success', 'success') else 'failure'
            self.assertEqual(namespace['selected_native_result'](ROUTE, *states), expected)

    def test_fixed_case_artifacts_and_authenticated_precredential_handoff(self):
        a, b = (old.workflow_job(job) for job in ('native_codec_a', 'native_codec_b'))
        self.assertIn('NATIVE_DB_ROUTE: '+ROUTE, old.workflow_job('eligibility'))
        self.assertIn('numeric_code_rows_sha256: ${{ steps.native.outputs.numeric_code_rows_sha256 }}', a)
        self.assertIn('needs: [eligibility, native_codec_a]', b)
        self.assertLess(b.index('--validate-numeric-code-rows3'), b.index('GHCR_TOKEN:'))
        for key, source in (('SHA256','numeric_code_rows_sha256'), ('RUN_ID','run_id'), ('RUN_ATTEMPT','run_attempt')):
            self.assertEqual(b.count('NUMERIC_CODE_ROWS3_'+key+': ${{ needs.native_codec_a.outputs.'+source+' }}'), 2)
        self.assertIn('artifact-ids: ${{ needs.native_codec_a.outputs.artifact_id }}', b)
        self.assertIn('digest-mismatch: error', b)
        for block, number in ((a,'3'), (b,'6')):
            self.assertIn("&& 'numeric_code_rows"+number+".json'", block)
            self.assertIn("&& 'numeric-code-rows' ||", block)
            self.assertIn("if: always() && steps.native.outputs.report_ready == 'true'", block)
            self.assertEqual(block.count('GHCR_TOKEN:'), 1)
        self.assertIn("if: always() && steps.native.outputs.aggregate_ready == 'true'", b)
        self.assertIn("}}-aggregate.json", b)
        handoff = next(step for step in shell.steps('native_codec_b') if '--validate-numeric-code-rows3' in step)
        self.assertNotIn('GHCR_TOKEN', handoff)
        self.assertNotIn('GHCR_USER', handoff)

    def test_actual_portable_bash_all_seven_pair_routes_and_handoffs(self):
        # No emulation of shell conditionals: execute the exact workflow bodies.
        for route in ROUTES[1:]:
            for job, number, numeric, letter in (
                    ('native_codec_a','8','3','a'), ('native_codec_b','17','6','b')):
                if route == ROUTE:
                    expected = '--catalog-numeric-code-rows number'+numeric+' --output native-db-oracle/numeric_code_rows'+numeric+'.json'
                elif route == 'catalog-numeric-code-measurement-v1':
                    expected = '--catalog-numeric-code number'+numeric+' --output native-db-oracle/numeric_code'+numeric+'.json'
                elif route == shell.ROUTE:
                    expected = '--catalog-params-slots description'+number+' --output native-db-oracle/params_slots'+number+'.json'
                elif route == 'catalog-description-rows-v1':
                    expected = '--catalog-description-rows description'+number+' --output native-db-oracle/description_rows'+number+'.json'
                elif route == 'catalog-description-measurement-v1':
                    expected = '--catalog-description description'+number+' --output native-db-oracle/description'+number+'.json'
                else:
                    kind = 'rows' if route == 'catalog-reference-rows-v1' else 'codec'
                    expected = '--catalog-reference-'+kind+' distinct_'+letter+' --output native-db-oracle/'+kind+'_distinct_'+letter+'.json'
                result = shell.dispatch(shell.rendered(shell.command(job, '--execute-approved-image'), route))
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(result.stdout.strip(), 'scripts/native_1c_db_oracle.py --execute-approved-image --file-db-oracle '+expected)
            expected = {
                ROUTE:'numeric-code-rows3', 'catalog-numeric-code-measurement-v1':'numeric-code3', shell.ROUTE:'params-slots8',
                'catalog-description-rows-v1':'description-rows8',
                'catalog-description-measurement-v1':'description8',
                'catalog-reference-rows-v1':'rows-a', 'catalog-reference-codec-v1':'codec-a',
            }[route]
            result = shell.dispatch(shell.rendered(shell.command('native_codec_b', '--validate-numeric-code-rows3'), route))
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout.strip(), 'scripts/native_1c_db_oracle.py --validate-'+expected)

if __name__ == '__main__':
    unittest.main()
