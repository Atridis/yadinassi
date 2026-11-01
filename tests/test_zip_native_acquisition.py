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
        source=(FIXTURE/'original32.bsl').read_text(encoding='utf-8')
        raw=(FIXTURE/'original32.out').read_bytes()
        omitted={24,28}  # Old24 cleanup did not handle the now-measured empty out/.
        if not (os.open in os.supports_dir_fd and hasattr(os,'O_NOFOLLOW') and hasattr(os,'O_DIRECTORY')):
            omitted.update((6,7,8,9,10,11,12,21,22,25,26))  # Explicit Windows extraction gap.
        selected=[n for n in range(1,33) if n not in omitted]
        loop='For N=1 To 32 Do ZFObserve(N);EndDo;'
        self.assertEqual(source.count(loop),1)
        # Execute only available ordinary observations, with no fabricated rows.
        # Immutable original capture/source and failed provenance remain unchanged.
        actual=emit(source=source.replace(loop,''.join(f'ZFObserve({n});' for n in selected)))
        lines=raw.splitlines(keepends=True)
        self.assertEqual(actual,b''.join(lines[:2]+[lines[n+1] for n in selected]))

    def test_layout_acquisition_is_immutable_and_supported_cases_replay(self):
        import os
        source=(FIXTURE/'layout32.bsl').read_bytes()
        raw=(FIXTURE/'layout32.out').read_bytes()
        provenance=(FIXTURE/'layout32-provenance.json').read_bytes()
        for data,expected in ((source,'87da2769c9d1f32b021211793d8dae6a0058556440c950edd877eb393a2f7b8e'),
                              (raw,'1fd77f7d971b4e7a13b8ff6d79cd0c098fe4296298a11689b60987e1b7734651'),
                              (provenance,'4391d885febda85fd4a3ed006f943094a7ad4897d32449fc70115538b8cfa56a')):
            self.assertEqual(hashlib.sha256(data).hexdigest(),expected)
        p=json.loads(provenance)
        self.assertEqual(p['repository']['github_run_id'],'41262403464')
        self.assertTrue(p['comparison']['native_zip_family_available'])
        self.assertEqual(p['comparison']['acceptance_status'],'rejected')
        expected=wire.require_available(raw)
        self.assertEqual(''.join(map(chr,expected[23]['units'])),'3|a.bin|out/~|sub/b.bin|X')
        self.assertEqual(''.join(map(chr,expected[27]['units'])),'close-error:items-error')
        actual=wire.validate_output(emit(source=source.decode('utf-8')))
        if os.open in os.supports_dir_fd and hasattr(os,'O_NOFOLLOW') and hasattr(os,'O_DIRECTORY'):
            self.assertEqual(expected,actual)  # All32 on the implemented anchored backend.
        else:
            for a,b in zip(expected,actual):
                if a['case'] not in (6,7,8,9,10,11,12,21,22,24,25,26):self.assertEqual(a,b)
            self.assertTrue(''.join(map(chr,actual[23]['units'])).endswith('|E'))

if __name__=='__main__':unittest.main()
