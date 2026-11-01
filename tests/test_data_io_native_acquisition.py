"""Immutable first native observation; only established ordinary fixes are parity claims."""
import hashlib
import json
from pathlib import Path
import sys
import unittest
ROOT=Path(__file__).resolve().parents[1]
for path in (ROOT, ROOT/'scripts'):
    if str(path) not in sys.path: sys.path.insert(0,str(path))
from test_native_data_io_family_measurement import emit
from native_1c_data_io_family_contract import validate_output,require_available,AvailabilityError
FIXTURE=ROOT/'tests/fixtures/data_io_family/native-v1'
class DataIONativeAcquisitionTests(unittest.TestCase):
    def test_original_capture_identities_and_partial_availability(self):
        receipt=json.loads((FIXTURE/'receipt.json').read_text(encoding='utf-8'))
        self.assertEqual(receipt['source_sha256'], 'ce3cc485dec511c85fdb65dbc0acadb2f6fbf1407cba7022c8c04eae79af4198')
        self.assertEqual(receipt['output_sha256'], '8365f67ba7d3b7312aa7d8ba1938ddd4a030104055ad4e1e3ca5fd0dc8e7ce1c')
        for name,key in [('original40.bsl','source_sha256'),('original40.out','output_sha256')]:
            self.assertEqual(hashlib.sha256((FIXTURE/name).read_bytes()).hexdigest(),receipt[key])
        raw=(FIXTURE/'original40.out').read_bytes()
        records=validate_output(raw)
        self.assertEqual([r['case'] for r in records if r['status']!='ok'],[24])
        with self.assertRaises(AvailabilityError): require_available(raw)
    def test_measured_corrections_and_remaining_discriminants(self):
        native=validate_output((FIXTURE/'original40.out').read_bytes())
        local=validate_output(emit(source=(FIXTURE/'original40.bsl').read_text(encoding='utf-8')))
        self.assertEqual([a['case'] for a,b in zip(native,local) if a!=b],[])
        for case in (6,29,36,40): self.assertEqual(native[case-1],local[case-1])
    def test_second_capture_and_measured_skip_unicode_alias_corrections(self):
        fixture=FIXTURE.parent/'native-v2'
        source=(fixture/'original40.bsl').read_bytes();raw=(fixture/'original40.out').read_bytes()
        self.assertEqual(hashlib.sha256(source).hexdigest(), 'e67d1932d1adaa0b53dc79dcc3995a6c906c5c752364a333fbd25675cacb6e2e')
        self.assertEqual(hashlib.sha256(raw).hexdigest(), 'ab449ba7fc1f42ef55039106fec2acb15d16149e0a5913dd0af3edf20cd96552')
        native=validate_output(raw);local=validate_output(emit(source=source.decode('utf-8')))
        self.assertEqual([r['case'] for r in native if r['status']!='ok'],[2])
        self.assertEqual([a['case'] for a,b in zip(native,local) if a!=b],[2])
        for case in (16,18,26):self.assertEqual(native[case-1],local[case-1])
        with self.assertRaises(AvailabilityError):require_available(raw)

    def test_third_capture_retains_unsupported_out_of_band_reposition(self):
        fixture=FIXTURE.parent/'native-v3'
        source=(fixture/'original40.bsl').read_bytes();raw=(fixture/'original40.out').read_bytes()
        self.assertEqual(hashlib.sha256(source).hexdigest(), 'e292172fa74ecf940781093229f49e58c97ca8706ba983676fc20bfea6d4ff06')
        self.assertEqual(hashlib.sha256(raw).hexdigest(), '1a31dfa8a7535ab97ef70009982be3d628600d3fb6a50740681889cff6b43df9')
        native=require_available(raw);local=validate_output(emit(source=source.decode('utf-8')))
        # This old probe moves the external stream after reader consumption.
        # Its captured native exception remains an explicit unsupported boundary,
        # not a reason to invent broad buffer invalidation for all stream users.
        self.assertEqual([a['case'] for a,b in zip(native,local) if a!=b],[2])
        self.assertEqual(native[23],local[23])

    def test_final_closed_40_native_parity_and_current_source(self):
        fixture=FIXTURE.parent/'native-final'
        source=(fixture/'original40.bsl').read_bytes();raw=(fixture/'original40.out').read_bytes()
        self.assertEqual(hashlib.sha256(source).hexdigest(), '18f636ec1cca0fb2839787f6c0764619c6dacae86c96df5dd14e4ab16c97fdd9')
        self.assertEqual(hashlib.sha256(raw).hexdigest(), 'c9f371a2074b07629146d3230710fa6ac7192b0c41af986390c295fdf0eecdfa')
        self.assertEqual(source, (ROOT/'integrational_tests/measurements/data_io_family.bsl').read_text(encoding='utf-8').encode('utf-8'))
        self.assertEqual(len(require_available(raw)),40)
        self.assertEqual(emit(source=source.decode('utf-8')),raw)

if __name__=='__main__':unittest.main()
