"""Immutable Linux file-family33 acquisition, not generated expected answers."""
import hashlib
import json
import os
from pathlib import Path
import unittest
from test_native_file_io_family_measurement import emit
from native_1c_file_io_family_contract import require_available

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / 'tests/fixtures/file_io_family'
H = lambda data: hashlib.sha256(data).hexdigest()


class NativeFileIOTests(unittest.TestCase):
    def test_exact_source_capture_and_provenance(self):
        raw = (FIXTURE/'native33.out').read_bytes()
        source = (ROOT/'integrational_tests/measurements/file_io_family.bsl').read_bytes()
        self.assertEqual(H(raw), '5a5096c2c9c4f2ef1c2190580be2679858a2b513e691c09b7f1f6933cd69b2a4')
        self.assertEqual(H(source), '338249c25f36779b6c3f8869c96a7dac7c1ac6e2a3bca9767c7b7e180f81939b')
        self.assertEqual(len(require_available(raw)), 33)
        provenance = json.loads((FIXTURE/'native33-provenance.json').read_text(encoding='utf-8'))
        self.assertEqual(provenance['repository']['github_run_id'], '41215463048')
        self.assertEqual(provenance['repository']['tree'], '70ff16047d1a48538555a962684a1e2930c806aa')
        self.assertIs(provenance['runtime_parity_accepted'], True)
        self.assertIs(provenance['native_measurement_accepted'], True)
        stage = provenance['native_report']['stage3']
        for value in (stage['client_tree'], stage['cases'][0]):
            self.assertEqual(value['source_sha256'], H(source))
            self.assertEqual(value['output_sha256'], H(raw))
            self.assertEqual(value['output_size'], len(raw))
        self.assertIs(provenance['container_cleanup_verified'], True)
        self.assertIs(provenance['private_payloads_removed'], True)

    @unittest.skipUnless(os.name == 'posix', 'Exact Linux capture includes POSIX File.Path separator relations')
    def test_linux_capture_replays_without_exclusions(self):
        # Portable ordinary workflows and child replay run on every OS in the
        # other tests; this exact immutable acquisition used Linux path syntax.
        self.assertEqual(emit(), (FIXTURE/'native33.out').read_bytes())

if __name__ == '__main__': unittest.main()
