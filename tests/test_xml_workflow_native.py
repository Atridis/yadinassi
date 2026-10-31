"""Immutable XML33 native evidence; failed original runtime is not relabeled."""
import hashlib
import json
from pathlib import Path
import unittest

from test_native_xml_workflow_family_measurement import emit
import native_1c_xml_workflow_family_contract as contract

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / 'tests/fixtures/xml_workflow_family'
CAPTURE = '07c4ee0a14ce53f0929bb2c41caf9d9c5dc5fdcc2fec68d5bb28f21874759f0c'
PROVENANCE = '351a270111cac9fc8bb2ee144ae1d260b30b69a16b7c28af9536449bb61be8fc'


class XMLNativeTests(unittest.TestCase):
    def test_immutable_native_acquisition(self):
        raw=(FIXTURE/'native33.out').read_bytes()
        metadata=(FIXTURE/'native33-provenance.json').read_bytes()
        self.assertEqual(hashlib.sha256(raw).hexdigest(),CAPTURE)
        self.assertEqual(hashlib.sha256(metadata).hexdigest(),PROVENANCE)
        p=json.loads(metadata)
        self.assertEqual(p['repository'],{'commit':'e2d02cc66f98de7aefa3c6eccd3633fad59df017',
            'tree':'a4132279a2fdb0344d6be7525524c4c030cdad24',
            'github_run_id':'41227374058','github_run_attempt':'1'})
        self.assertTrue(p['native_measurement_accepted'])
        # Preserve that the originally measured runtime had five mismatches.
        self.assertFalse(p['runtime_parity_accepted'])
        self.assertEqual(p['comparison']['status'],'mismatched')
        self.assertEqual(p['comparison']['interpreter_sha256'],'4b74122d721ff976fdea6004b725c61bea40ed977353ae4c5ee19e997af70654')
        stage=p['native_report']['stage3']
        self.assertEqual(stage['cases'][0]['output_sha256'],CAPTURE)
        self.assertEqual(stage['client_tree']['output_sha256'],CAPTURE)
        self.assertEqual(stage['cases'][0]['output_size'],2497)
        self.assertTrue(p['container_cleanup_verified']);self.assertTrue(p['private_payloads_removed'])
        self.assertEqual(len(contract.require_available(raw)),33)
        source=ROOT/'integrational_tests/measurements/xml_workflow_family.bsl'
        self.assertEqual(hashlib.sha256(source.read_bytes()).hexdigest(),stage['cases'][0]['source_sha256'])

    def test_corrected_runtime_matches_all_33_captured_observations(self):
        self.assertEqual(emit(),(FIXTURE/'native33.out').read_bytes())

if __name__=='__main__':unittest.main()
