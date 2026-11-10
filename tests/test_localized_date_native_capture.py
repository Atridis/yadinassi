"""Exact retained native observations, never generated expected Format answers."""
import hashlib
import json
from pathlib import Path
import unittest

from test_native_format_date_acquisition_measurement import COUNTS, SHAS, emit, wire

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / 'tests/fixtures/format_dates'
CAPTURES = {'names': 'b6e3b20750b76369c301b9f4678c83b3da6b585786cb9391f76edaae17436cd1',
            'tokens': '29d45f0720f9ad74cc6383e6be53f25c9d747a82e746d0589d9f9f4e03588d26'}


class LocalizedDateNativeCaptureTests(unittest.TestCase):
    def test_capture_provenance_and_immutable_source_identities(self):
        proof = json.loads((FIXTURE/'localized-provenance.json').read_text(encoding='utf-8'))
        self.assertEqual(proof['run_id'], 42792967665)
        self.assertEqual(proof['commit'], '3ceb0516377c11ab641d42996b5a2a8e3fd6d6e9')
        self.assertEqual(proof['tree'], '0078d689ee5f937bf686eba55d00a0388eb61631')
        self.assertEqual(proof['runtime'], '8.3.27.1508')
        for kind, record in zip(('names','tokens'), proof['records']):
            raw = (FIXTURE/record['capture']).read_bytes()
            self.assertEqual(hashlib.sha256(raw).hexdigest(), CAPTURES[kind])
            self.assertEqual(record['capture_sha256'], CAPTURES[kind])
            self.assertEqual(record['source_sha256'], SHAS[kind])
            self.assertEqual((record['case_count'],record['calibration_count']), (COUNTS[kind],2))
            self.assertTrue(record['native_measurement_accepted'])
            self.assertFalse(record['runtime_parity_accepted_at_acquisition'])
            self.assertTrue(record['client_server_identical'])
            self.assertTrue(record['private_payloads_removed'])
            self.assertTrue(record['container_cleanup_verified'])
            self.assertTrue(all(row['status']=='ok' for row in wire(kind).require_available(raw)))

    def test_all_52_native_month_names_and_contexts_replayed(self):
        self.assertEqual(emit('names'), (FIXTURE/'names52-native.out').read_bytes())

    def test_all_56_native_tokens_styles_and_precedence_replayed(self):
        self.assertEqual(emit('tokens'), (FIXTURE/'tokens56-native.out').read_bytes())
