"""New finite selector shares the existing reviewed job and no new privileges."""
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'tests'),str(ROOT/'scripts')]
import itertools
import unittest
import test_native_1c_db_oracle_ci_policy as existing
import test_native_params_slot_workflow as routes


class InformationRegisterWorkflowTests(unittest.TestCase):
    def test_closed_new_route_and_selected_only_job(self):
        ns={'PolicyError':ValueError}
        exec(routes.marker('eligibility','ROUTE ADMISSION'),ns)
        exec(routes.marker('verdict','ROUTE VERDICT'),ns)
        route='information-register-read-v2'
        self.assertEqual(ns['admitted_route'](route),route)
        for invalid in ('information-register-read-v1','information-register-read',None,True):
            with self.assertRaises(ValueError):ns['admitted_route'](invalid)
        for states in itertools.product(('success','failure','cancelled','skipped'),repeat=7):
            self.assertEqual(ns['selected_native_result'](route,*states),'success' if states==('skipped',)*6+('success',) else 'failure')
        block=existing.workflow_job('native_catalog_read')
        self.assertEqual(block.count('GHCR_TOKEN:'),1);self.assertEqual(block.count('GHCR_USER:'),1)
        self.assertIn('information-register-read-v2) python3 scripts/native_1c_information_register_oracle.py --run --ci-report',block)
        self.assertIn('*) exit 1',block)
        self.assertIn("github.ref == 'refs/heads/codex/native-file-db-oracle-reviewed'",block)
        for forbidden in ('workflow_dispatch','pull_request_target',': write','download-artifact','*.json','*.log'):self.assertNotIn(forbidden,block)
