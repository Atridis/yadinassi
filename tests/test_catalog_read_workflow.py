"""Existing reviewed-ref admission, one selected-only batch job, no new grants."""
import itertools
import re
import unittest
import test_native_1c_db_oracle_ci_policy as existing
import test_native_params_slot_workflow as routes

ROUTE='catalog-read-batch-v1'


class CatalogReadWorkflowTests(unittest.TestCase):
    def test_closed_route_and_exhaustive_terminal_verdict(self):
        ns={'PolicyError':ValueError}
        exec(routes.marker('eligibility','ROUTE ADMISSION'),ns)
        exec(routes.marker('verdict','ROUTE VERDICT'),ns)
        self.assertEqual(ns['admitted_route'](ROUTE),ROUTE)
        for value in (None,True,'catalog-read-batch-v2',''):
            with self.assertRaises(ValueError):ns['admitted_route'](value)
        for states in itertools.product(('success','failure','cancelled','skipped'),repeat=7):
            expected='success' if states==('skipped',)*6+('success',) else 'failure'
            self.assertEqual(ns['selected_native_result'](ROUTE,*states),expected)
        for route,states in [('metadata-catalog-public-runtime-v1',('skipped',)*5+('success',)),('metadata-catalog-applied-view-v1',('skipped',)*4+('success','skipped'))]:
            self.assertEqual(ns['selected_native_result'](route,*states),'success')
            self.assertEqual(ns['selected_native_result'](route,*states,'success'),'failure')
    def test_exact_same_credential_boundary_and_bounded_artifact(self):
        block=existing.workflow_job('native_catalog_read')
        reference=existing.workflow_job('native_metadata_runtime')
        expected=reference.split('    steps:\n')[0].replace('Native 1C Metadata Catalogs public runtime readback','Native 1C batched Catalog read scenario').replace('metadata-catalog-public-runtime-v1',ROUTE)
        expected=expected.replace("needs.eligibility.outputs.route == 'catalog-read-batch-v1' &&", "(needs.eligibility.outputs.route == 'catalog-read-batch-v1' || needs.eligibility.outputs.route == 'linked-catalog-cards-v1') &&")
        self.assertEqual(block.split('    steps:\n')[0],expected)
        self.assertLess(block.index('scripts/native_1c_db_oracle_ci_policy.py bind'),block.index('GHCR_TOKEN:'))
        self.assertLess(block.index('pip install'),block.index('GHCR_TOKEN:'))
        self.assertEqual(block.count('GHCR_TOKEN:'),1)
        self.assertEqual(block.count('GHCR_USER:'),1)
        self.assertIn('scripts/native_1c_catalog_read_oracle.py --run --ci-report',block)
        self.assertIn("if: always() && steps.native.outputs.report_ready == 'true'",block)
        self.assertEqual(re.findall(r'^          path: (.*)$',block,re.M),["${{ needs.eligibility.outputs.route == 'linked-catalog-cards-v1' && 'native-linked-catalog/linked-card.json' || 'native-catalog-read/catalog-read.json' }}"])
        for forbidden in ('workflow_dispatch','pull_request_target','secrets.','download-artifact','*.json','*.log',': write'):
            self.assertNotIn(forbidden,block)
        self.assertIn('native_catalog_read]',existing.workflow_job('verdict'))
        self.assertIn('CATALOG_READ_RESULT:',existing.workflow_job('verdict'))
