"""Immutable original ZIP acquisition; unavailable cases never imply parity."""
import hashlib
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'scripts'))
from test_native_zip_family_measurement import emit
import native_1c_zip_family_contract as wire

FIXTURE = ROOT/'tests/fixtures/zip_family'

class ZIPAcquisitionTests(unittest.TestCase):
    def test_original_acquisition_hashes_provenance_and_failure_are_immutable(self):
        source = (FIXTURE/'original32.bsl').read_bytes()
        raw = (FIXTURE/'original32.out').read_bytes()
        provenance = (FIXTURE/'original32-provenance.json').read_bytes()
        for data, expected in ((source,'18fb206d8750451f387156cefba5ef6c0deae854b541f3cca279d34c7b4700d0'),
                               (raw,'170a2bc0b1b48939b0f1330a9bf30c2bc9881b741fd8dd71474036f412de15aa'),
                               (provenance,'71c813ebf5c5e87ecfb41e87413801b5ea38ab2da89baa39d96ce0d7631ed20d')):
            self.assertEqual(hashlib.sha256(data).hexdigest(),expected)
        p=json.loads(provenance)
        self.assertEqual(p['repository']['github_run_id'],'41261334010')
        self.assertEqual(p['repository']['tree'],'4c4c3c36567d834e41ca16e20eaf40e9357e786b')
        self.assertEqual(p['comparison']['acceptance_status'],'rejected')
        self.assertFalse(p['comparison']['native_zip_family_available'])
        records=wire.validate_output(raw)
        self.assertEqual([r['case'] for r in records if r['status']!='ok'],[24,28])
        self.assertEqual(''.join(map(chr,records[12]['units'])),'a.bin:a:bin')
        with self.assertRaises(wire.AvailabilityError):wire.require_available(raw)

    def test_measured_supported_original_cases_replay_without_promoting_failures(self):
        import os
        native=wire.validate_output((FIXTURE/'original32.out').read_bytes())
        actual=wire.validate_output(emit(source=(FIXTURE/'original32.bsl').read_text(encoding='utf-8')))
        omitted={24,25,26,28}  # Original unavailability / recursive layout still pending.
        if not (os.open in os.supports_dir_fd and hasattr(os,'O_NOFOLLOW') and hasattr(os,'O_DIRECTORY')):
            omitted.update((6,7,8,9,10,11,12,21,22))  # Explicit Windows extraction gap.
        for expected, observed in zip(native,actual):
            if expected['case'] not in omitted:
                with self.subTest(case=expected['case']):self.assertEqual(expected,observed)

if __name__=='__main__':unittest.main()
