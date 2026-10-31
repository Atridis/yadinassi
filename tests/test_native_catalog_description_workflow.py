"""Existing credential jobs select a closed Description route; no native run."""
import re
import unittest
import test_native_1c_db_oracle_ci_policy as old

class DescriptionWorkflowTests(unittest.TestCase):
    def test_only_existing_job_pair_and_fixed_inputs(self):
        workflow=old.WORKFLOW.read_text() if hasattr(old,'WORKFLOW') else (old.ROOT/'.github/workflows/native-1c-file-db-oracle.yml').read_text()
        self.assertEqual(set(re.findall(r'^  ([a-z_]+):$',workflow,re.M)),{'push','eligibility','native_reference_a','native_oracle','native_codec_a','native_codec_b','native_metadata','native_metadata_runtime','native_catalog_read','verdict'})
        for name,number in (('native_codec_a','8'),('native_codec_b','17')):
            block=old.workflow_job(name)
            self.assertIn("needs.eligibility.outputs.route == 'catalog-description-measurement-v1'",block)
            self.assertIn('--catalog-description description'+number+' --output native-db-oracle/description'+number+'.json',block)
            self.assertIn("&& 'description"+number+".json'",block)
            self.assertEqual(block.count('GHCR_TOKEN:'),1)
            self.assertIn('persist-credentials: false',block)
            self.assertIn('ref: ${{ github.sha }}',block)
            self.assertIn('github.workflow_sha == github.sha',block)
    def test_case8_handoff_auth_before_existing_case17_credentials(self):
        block=old.workflow_job('native_codec_b')
        self.assertLess(block.index('--validate-description8'),block.index('GHCR_TOKEN:'))
        for key in ('DESCRIPTION8_SHA256','DESCRIPTION8_RUN_ID','DESCRIPTION8_RUN_ATTEMPT'):
            self.assertEqual(block.count(key+':'),2)
        self.assertIn('artifact-ids: ${{ needs.native_codec_a.outputs.artifact_id }}',block)
        self.assertIn('digest-mismatch: error',block)
        self.assertNotIn('github-token:',block)
        self.assertIn("&& 'description' ||",block)
        self.assertIn('description_sha256: ${{ steps.native.outputs.description_sha256 }}',old.workflow_job('native_codec_a'))

if __name__=='__main__':unittest.main()
