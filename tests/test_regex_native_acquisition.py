"""Minimal immutable observations; original private acquisition report is not public."""
import hashlib
import json
from pathlib import Path
import sys
import unittest
ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT/'scripts')]
from test_native_regex_family_measurement import emit, wire
FIXTURE = ROOT/'tests/fixtures/regex_family'

class RegexNativeAcquisitionTests(unittest.TestCase):
    def test_original_capture_and_minimal_projection_are_immutable(self):
        source = (FIXTURE/'original40.bsl').read_bytes()
        raw = (FIXTURE/'original40.out').read_bytes()
        meta = json.loads((FIXTURE/'original40.json').read_text())
        self.assertEqual(set(meta), {'schema','platform_version','source_sha256','output_sha256','cases','status'})
        self.assertEqual(meta['schema'], 'regex-family-observations-v1')
        self.assertEqual(meta['platform_version'], '8.3.27.1508')
        self.assertEqual(meta['source_sha256'], '28deb10f2d1b0f6e072388a92070c360208601bc9082042a853e1367e12fbb6e')
        self.assertEqual(meta['output_sha256'], '9f759fc3a0e5e11edc565e4aa20047bec27791b916154eb7e530881b9c449c05')
        self.assertEqual(hashlib.sha256(source).hexdigest(), meta['source_sha256'])
        self.assertEqual(hashlib.sha256(raw).hexdigest(), meta['output_sha256'])
        self.assertEqual(meta['cases'], 40)
        self.assertEqual(meta['status'], 'native-acquisition-available-not-parity')
        self.assertEqual(len(wire.require_available(raw)), 40)

    def test_original_capture_replays_after_measured_corrections(self):
        native = wire.require_available((FIXTURE/'original40.out').read_bytes())
        local = wire.require_available(emit(source=(FIXTURE/'original40.bsl').read_text()))
        self.assertEqual([a['case'] for a,b in zip(native,local) if a!=b], [])

    def test_reference_discriminant_capture_and_exact_replay(self):
        source = (FIXTURE/'references40.bsl').read_bytes()
        raw = (FIXTURE/'references40.out').read_bytes()
        meta = json.loads((FIXTURE/'references40.json').read_text())
        original = json.loads((FIXTURE/'original40.json').read_text())
        self.assertEqual(set(meta), set(original))
        self.assertEqual(meta['schema'], original['schema'])
        self.assertEqual(meta['platform_version'], original['platform_version'])
        self.assertEqual(meta['cases'], 40)
        self.assertEqual(meta['status'], 'native-acquisition-available-original-runtime-mismatch')
        self.assertEqual(meta['source_sha256'], 'd332ac52d0eb8257bd41abee4494df74bc4969a7c5087c74bbcce8c6ed0309cb')
        self.assertEqual(meta['output_sha256'], 'f29009bf8ade447ab95250e77bf004c7191cdea3fa363d4032a7e5e7d486dd76')
        self.assertEqual(hashlib.sha256(source).hexdigest(), meta['source_sha256'])
        self.assertEqual(hashlib.sha256(raw).hexdigest(), meta['output_sha256'])
        self.assertEqual(wire.require_available(emit(source=source.decode())), wire.require_available(raw))

if __name__ == '__main__': unittest.main()
