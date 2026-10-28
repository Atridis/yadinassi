"""Exact full-source reconstruction; not a shortened native output comparison."""
import copy
import hashlib
import json
from pathlib import Path
import unittest
from unittest import mock
import test_native_async_fixture as history
import test_native_1c_full_stage as fixtures
from scripts.native_historical_replay import without_tree_load_probes

ROOT=Path(__file__).resolve().parents[1]
PATHS=('scripts/native_1c_bootstrap/full_suite.py','scripts/native_1c_full_host.py')
BASE_SOURCE='5a9a57fc6ef11e895191d9796bda5387c5bda25510dfa4e42591cadfade273b4'
BASE_MODULE='a7bfc4e3361bdb1bfde5794b211f3fd1c0594f5c81b4f5e3dafecac4c3049786'


class LoadHarnessHistoryTests(unittest.TestCase):
    def test_exact976_harness_precedes_existing_history(self):
        inventory=json.loads((ROOT/'tests/tree_load_source_inverse.json').read_text(encoding='utf-8'))
        prior=json.loads((ROOT/'tests/tree_unload_supplement_source_inverse.json').read_text(encoding='utf-8'))
        self.assertEqual(set(inventory),set(PATHS))
        for path in PATHS:
            source=(ROOT/path).read_text(encoding='utf-8')
            restored=history.without_tree_load_measurement(source,host=path.endswith('full_host.py'))
            self.assertEqual(hashlib.sha256(restored.encode()).hexdigest(),prior[path]['candidate_sha256'])
            self.assertEqual(inventory[path]['base_sha256'],prior[path]['candidate_sha256'])
            self.assertNotEqual(source,restored)
            self.assertTrue(history.without_tree_unload_supplement_measurement(source,host=path.endswith('full_host.py')))

    def test_entire_prior_source_and_generated_module_are_restored(self):
        source=(ROOT/'integrational_tests/tests/collections.bsl').read_bytes().replace(b'\r\n',b'\n')
        prior=without_tree_load_probes(source.decode('utf-8-sig')).encode('utf-8-sig')
        self.assertEqual(hashlib.sha256(prior).hexdigest(),BASE_SOURCE)
        template=(ROOT/fixtures.suite.CLIENT_SOURCE).read_bytes().replace(b'\r\n',b'\n')
        self.assertEqual(hashlib.sha256(history.historical_tree_load_collections_module(source,template)).hexdigest(),BASE_MODULE)
        with self.assertRaises(fixtures.suite.FullError): fixtures.suite.client_collections_module(prior,template)
        current=fixtures.suite.client_collections_module(source,template)
        self.assertIn(b'TreeLoadProbe',current)
        self.assertEqual(fixtures.suite.CLIENT_COLLECTIONS_MESSAGE_COUNT,1021)

    def test_source_and_harness_drift_rejected_even_with_rebased_outer_hash(self):
        inventory=json.loads((ROOT/'tests/tree_load_source_inverse.json').read_text(encoding='utf-8'))
        for path in PATHS:
            source=(ROOT/path).read_text(encoding='utf-8')
            for altered in (source+'\n',source.replace('\n','\r\n'),source.replace('1021','1022',1)):
                self.assertNotEqual(altered,source)
                with self.assertRaises(AssertionError): history.without_tree_load_measurement(altered,host=path.endswith('full_host.py'))
                forged=copy.deepcopy(inventory)
                forged[path]['candidate_sha256']=hashlib.sha256(altered.encode()).hexdigest()
                with mock.patch.object(history.json,'loads',return_value=forged),self.assertRaises(AssertionError):
                    history.without_tree_load_measurement(altered,host=path.endswith('full_host.py'))
        source=(ROOT/'integrational_tests/tests/collections.bsl').read_bytes().replace(b'\r\n',b'\n').decode('utf-8-sig')
        for altered in (source+'\n',source.replace('TreeLoadProbe(45)','TreeLoadProbe(44)'),source.replace('\n','\r\n')):
            self.assertNotEqual(altered,source)
            with self.assertRaises(ValueError): without_tree_load_probes(altered)


if __name__=='__main__':unittest.main()
