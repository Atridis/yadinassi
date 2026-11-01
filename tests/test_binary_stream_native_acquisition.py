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

    def test_explicit_origin_acquisition_is_available_but_originally_mismatched(self):
        source = (FIXTURE/'explicit40.bsl').read_bytes()
        raw = (FIXTURE/'explicit40.out').read_bytes()
        provenance = (FIXTURE/'explicit40-provenance.json').read_bytes()
        digest = lambda data: hashlib.sha256(data).hexdigest()
        self.assertEqual(digest(source), '6f608fb87fe94ad11fd14326e2f3a4795bc46e8286ed540695b7b53cddb1eb1b')
        self.assertEqual(digest(raw), '095b8a975ba50a6ba308247c08f639775896333c6dde0e4863f240a4877e6566')
        self.assertEqual(digest(provenance), '497ef13ab1a815f57addd20f235f51fcc12bf2f6ac0350581a53c39d12184fa4')
        p = json.loads(provenance)
        self.assertEqual(p['repository']['github_run_id'], '41255849371')
        self.assertEqual(p['comparison']['acceptance_status'], 'rejected')
        self.assertTrue(p['comparison']['native_binary_stream_family_available'])
        self.assertEqual(p['trusted_input_sha256']['integrational_tests/measurements/binary_stream_family.bsl'], digest(source))
        records = wire.require_available(raw)
        self.assertEqual(''.join(map(chr, records[16]['units'])), 'omitted-error')
        self.assertEqual(''.join(map(chr, records[25]['units'])), '0:Да')

    def test_explicit_origin_40_measured_cases_replay_after_calibration(self):
        native = wire.require_available((FIXTURE/'explicit40.out').read_bytes())
        actual = wire.require_available(emit(source=(FIXTURE/'explicit40.bsl').read_text(encoding='utf-8')))
        self.assertEqual(native, actual)

    def test_view_acquisition_is_immutable_and_all_40_cases_replay(self):
        source = (FIXTURE/'view40.bsl').read_bytes()
        raw = (FIXTURE/'view40.out').read_bytes()
        provenance = (FIXTURE/'view40-provenance.json').read_bytes()
        for data, expected in ((source, '0a3e3614d6b43534faddf4c911b203233fd76e75770642d96190ed4802138059'),
                               (raw, '37ea62dd423b4b88c188e2d818782d5edb0dd8f55531cea7778f18293b4b4778'),
                               (provenance, 'af2ddfd2305158c13f37280880c60cee1e2be125a5dfb4f29e42a6d81fd83469')):
            self.assertEqual(hashlib.sha256(data).hexdigest(), expected)
        p = json.loads(provenance)
        self.assertEqual(p['repository']['github_run_id'], '41256517386')
        self.assertEqual(p['comparison']['acceptance_status'], 'rejected')
        self.assertTrue(p['comparison']['native_binary_stream_family_available'])
        self.assertEqual(wire.require_available(raw), wire.require_available(emit(source=source.decode('utf-8'))))

    def test_revised_batch_has_one_isolated_omitted_origin_probe(self):
        self.assertEqual(SOURCE.count('S.Seek(2)'), 1)
        self.assertIn('Try R="omitted:"+String(S.Seek(2));Except R="omitted-error";', SOURCE)
        self.assertEqual(SOURCE.count('P=PositionInStream.Begin;'), 2)
        self.assertIn('S.Seek(5,P);Try R="omitted:', SOURCE)


if __name__ == '__main__': unittest.main()
