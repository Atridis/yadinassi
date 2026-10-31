"""Exact authenticated JSON31 replay; historical rejected gate stays rejected."""
import hashlib
import json
import os
from pathlib import Path
import unittest
from types import SimpleNamespace
from unittest import mock

import yadinassi.json_processing as json_processing

from test_native_json_family_measurement import emit
from native_1c_json_family_contract import require_available

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / 'tests/fixtures/json_family'


class NativeJSONFamilyTests(unittest.TestCase):
    def test_exact_source_and_capture_identity(self):
        source = (FIXTURE/'original31.bsl').read_bytes()
        capture = (FIXTURE/'original31.out').read_bytes()
        self.assertEqual(source, (ROOT/'integrational_tests/measurements/json_family.bsl').read_bytes())
        self.assertEqual(hashlib.sha256(source).hexdigest(), 'ac6acd4a5af2b93c3d6b3b2e7ffdc95f8024e3fbd52482cd4c814b3f2020b00b')
        self.assertEqual(hashlib.sha256(capture).hexdigest(), 'fdc615321ca3711ca47070f1c9c99d3a9889e498d754731824512bad14d0b2d2')
        records = require_available(capture)
        self.assertEqual([r['case'] for r in records if r['status'] == 'action-error'], [11,13,15,16,17,19,28])
        self.assertEqual(len(records), 31)

    def test_all_observations_replay_exactly_without_exclusions(self):
        source = (FIXTURE/'original31.bsl').read_text(encoding='utf-8')
        # The immutable capture was acquired on Linux. Auto uses the host's
        # separator; select that acquisition context before execution, never
        # normalize output (which could corrupt quoted JSON string contents).
        linux_os = SimpleNamespace(**vars(os))
        linux_os.linesep = '\n'
        with mock.patch.object(json_processing, 'os', linux_os):
            self.assertEqual(emit(source=source), (FIXTURE/'original31.out').read_bytes())

    def test_original_mismatch_and_native_attribution_are_preserved(self):
        value = json.loads((FIXTURE/'original31-provenance.json').read_text(encoding='utf-8'))
        self.assertIs(value['acquisition_accepted'], True)
        self.assertIs(value['runtime_parity_accepted'], False)
        report = value['native_report']
        self.assertEqual(report['comparison']['status'], 'mismatched')
        self.assertIs(report['native_measurement_accepted'], True)
        self.assertIs(report['runtime_parity_accepted'], False)
        self.assertEqual(report['repository']['github_run_id'], '41207470266')
        self.assertEqual(report['repository']['tree'], value['tree'])
        stage = report['native_report']['stage3']
        self.assertEqual(stage['cases'][0]['output_sha256'], stage['client_tree']['output_sha256'])
        self.assertEqual(stage['client_tree']['output_sha256'], value['native_capture_sha256'])
        self.assertEqual(stage['client_tree']['module_sha256'], stage['client_tree']['roundtrip_sha256'])
        self.assertIs(report['container_cleanup_verified'], True)
        self.assertIs(report['private_payloads_removed'], True)


if __name__ == '__main__': unittest.main()
