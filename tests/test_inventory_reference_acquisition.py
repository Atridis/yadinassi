"""Immutable native12 evidence; host replay lives in the scenario suite."""
import hashlib
import json
from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parents[1]
FIXTURE=ROOT/'tests/fixtures/native_inventory_reference'


class InventoryAcquisitionTests(unittest.TestCase):
    def evidence(self):
        return json.loads((FIXTURE/'provenance.json').read_text(encoding='utf-8'))

    def test_original_capture_and_source_binding_are_immutable(self):
        raw=(FIXTURE/'observations12.out').read_bytes()
        provenance=(FIXTURE/'provenance.json').read_bytes()
        self.assertEqual(hashlib.sha256(raw).hexdigest(),'494ddd6068ba13cad0c291d9a4ed89bdbf441070482db28c23da31dae6f7e09a')
        self.assertEqual(hashlib.sha256(provenance).hexdigest(),'e8270696c8a12fdfed930c1c495856a1b3484e779b674c6a778e60e712da0599')
        evidence=self.evidence()
        self.assertEqual(evidence['repository'],{'commit':'b52465db5dd71407eceb2f3af85f6f5e84263d6f','tree':'5dbb273f6e7bf8b61bdf5d2e83ac4833d1c30fbf','github_run_id':'43030189023','github_run_attempt':'1'})
        self.assertEqual(evidence['interpreter']['source_file_count'],228)
        self.assertEqual(evidence['interpreter']['source_sha256'],'23ab585dda08e974b9202d6265ff6fbc61bab55a3307cfd3c010c736fc54d9ca')
        self.assertTrue(evidence['native_measurement_accepted'])
        # The original acquisition intentionally did not run the host replay.
        self.assertFalse(evidence['runtime_parity_accepted'])
        self.assertIsNone(evidence['comparison'])
        stage=evidence['native_report']['stage3']
        self.assertEqual(stage['output_sha256'],hashlib.sha256(raw).hexdigest())
        self.assertEqual(stage['partial_observations'],list(map(list,enumerate(json.loads(raw),1))))
        self.assertEqual(len(json.loads(raw)),12)

    def test_acquired_inputs_remain_byte_exact(self):
        evidence=self.evidence()
        for group in ('trusted_input_sha256','host_source_sha256'):
            for path,digest in evidence[group].items():
                with self.subTest(path=path):self.assertEqual(hashlib.sha256((ROOT/path).read_bytes()).hexdigest(),digest)
        self.assertEqual(evidence['native_report']['stage3']['input_sha256'],evidence['trusted_input_sha256'])

    def test_native_material_acceptance_and_cleanup_are_verified(self):
        evidence=self.evidence();native=evidence['native_report'];stage=native['stage3']
        self.assertEqual(native['runtime_version'],'8.3.27.1508')
        self.assertEqual(stage['configuration_validation'],'owned-inventory-reference-material-projection-v1')
        for key in ('completed','config_verified','entered','process_exited','quiet','witness_verified'):
            self.assertIs(stage[key],True,key)
        self.assertEqual(stage['record_count'],12)
        self.assertEqual(stage['failure_kind'],'none')
        self.assertEqual(stage['case_diagnostics'],[])
        self.assertEqual(stage['install_diagnostics'],[])
        self.assertEqual(stage['redump_diagnostic'],[])
        self.assertEqual(stage['module_sha256'],stage['module_verified_sha256'])
        for key in ('container_cleanup_verified','docker_cli_reap_verified','private_payloads_removed'):
            self.assertIs(evidence[key],True,key)
