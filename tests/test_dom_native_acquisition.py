"""Minimal immutable native DOM observations; no installation or session data."""
import hashlib
import json
from pathlib import Path
import sys
import unittest
ROOT=Path(__file__).resolve().parents[1]
for path in (ROOT, ROOT/'scripts'):
    if str(path) not in sys.path: sys.path.insert(0,str(path))
from test_native_dom_family_measurement import emit
from native_1c_dom_family_contract import validate_output, require_available, AvailabilityError
FIXTURE=ROOT/'tests/fixtures/dom_family/native-initial-v1'
class DOMNativeAcquisitionTests(unittest.TestCase):
    def test_immutable_capture_and_exact_original_differences(self):
        receipt=json.loads((FIXTURE/'receipt.json').read_text(encoding='utf-8'))
        self.assertEqual(receipt['source_sha256'],'ca117f2f0cd72a8803c8c2b323aecfdb70e8b471103ed9f77a83859c7a131dfd')
        self.assertEqual(receipt['output_sha256'],'97d4f9a76de58fe5e6aa37c00fc6e3133c90e12fd162e5a85d69504e0a5d25a9')
        for name,key in [('original40.bsl','source_sha256'),('original40.out','output_sha256')]:
            self.assertEqual(hashlib.sha256((FIXTURE/name).read_bytes()).hexdigest(),receipt[key])
        raw=(FIXTURE/'original40.out').read_bytes();native=validate_output(raw)
        local=validate_output(emit(source=(FIXTURE/'original40.bsl').read_text(encoding='utf-8')))
        self.assertEqual([a['case'] for a,b in zip(native,local) if a!=b],[12,29,30,31,36])
        self.assertEqual([a['case'] for a in native if a['status']=='action-error'],[12,29,31])
        with self.assertRaises(AvailabilityError):require_available(raw)
        self.assertEqual(native[29]['units'],tuple(map(ord,'2:2')))
        self.assertEqual(native[35]['units'],tuple(map(ord,'3:a<b:task')))
