"""Immutable first acquisition: 28 available cases, 12 errors, never parity acceptance."""
import hashlib
import json
from pathlib import Path
import unittest

from test_native_binary_stream_family_measurement import emit, wire, SOURCE

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / 'tests/fixtures/binary_stream_family'
ERRORS = [16, 17, 18, 19, 21, 22, 23, 24, 26, 30, 33, 39]


class BinaryStreamAcquisitionTests(unittest.TestCase):
    def test_original_source_capture_and_failed_provenance_are_immutable(self):
        source = (FIXTURE/'original40.bsl').read_bytes()
        raw = (FIXTURE/'original40.out').read_bytes()
        provenance = (FIXTURE/'original40-provenance.json').read_bytes()
        digest = lambda data: hashlib.sha256(data).hexdigest()
        self.assertEqual(digest(source), 'ad3cd0f8ded26e1aa142cfad09c0854ae3214aaf837fdf07dbef5e774d2aff82')
        self.assertEqual(digest(raw), '05b6753fb5625ac273e048fddcd84b276d16cbf8a1afea18168f8f8a9d15747b')
        self.assertEqual(digest(provenance), 'e82d97f2649fb656a244347a6cba55d08626bae3819d613428498298b50d711a')
        p = json.loads(provenance)
        self.assertEqual(p['repository']['github_run_id'], '41254621539')
        self.assertEqual(p['repository']['tree'], '852ca6c22214b4ee7b469ac8e91e648ccb3b68b3')
        self.assertEqual(p['trusted_input_sha256']['integrational_tests/measurements/binary_stream_family.bsl'], digest(source))
        self.assertEqual(p['comparison']['native_sha256'], digest(raw))
        self.assertEqual(p['comparison']['acceptance_status'], 'rejected')
        self.assertFalse(p['comparison']['native_binary_stream_family_available'])
        self.assertTrue(p['container_cleanup_verified'])

    def test_original_unavailable_records_still_prevent_acceptance(self):
        raw = (FIXTURE/'original40.out').read_bytes()
        records = wire.validate_output(raw)
        self.assertEqual([r['case'] for r in records if r['status'] != 'ok'], ERRORS)
        with self.assertRaises(wire.AvailabilityError): wire.require_available(raw)

    def test_original_28_available_cases_replay_without_relabeling_12_errors(self):
        native = wire.validate_output((FIXTURE/'original40.out').read_bytes())
        actual = wire.validate_output(emit(source=(FIXTURE/'original40.bsl').read_text(encoding='utf-8')))
        for expected, observed in zip(native, actual):
            if expected['case'] not in ERRORS:
                with self.subTest(case=expected['case']): self.assertEqual(observed, expected)
        # No assertion promotes the unavailable original cases to native parity.

    def test_revised_batch_has_one_isolated_omitted_origin_probe(self):
        self.assertEqual(SOURCE.count('S.Seek(2)'), 1)
        self.assertIn('Try R="omitted:"+String(S.Seek(2)); Except R="omitted-error";', SOURCE)
        self.assertEqual(SOURCE.count('P=PositionInStream.Begin;'), 2)
        self.assertIn('S.Seek(5,P); Try R="omitted:', SOURCE)


if __name__ == '__main__': unittest.main()
