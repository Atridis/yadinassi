"""Minimal immutable ordinary native observations; no installation/session data."""
import hashlib
import json
from pathlib import Path
import sys
import unittest
ROOT=Path(__file__).resolve().parents[1]
for path in (ROOT,ROOT/'scripts'):
    if str(path) not in sys.path: sys.path.insert(0,str(path))
from test_native_data_hashing_family_measurement import emit
from native_1c_data_hashing_family_contract import require_available,validate_output
FIXTURE=ROOT/'tests/fixtures/data_hashing_family/native-ordinary-v1'
class HashingNativeAcquisitionTests(unittest.TestCase):
    def test_immutable_source_and_native40_identity(self):
        receipt=json.loads((FIXTURE/'receipt.json').read_text(encoding='utf-8'))
        self.assertEqual(receipt['source_sha256'],'7a126ea8f2dc1b94b9926b2a12d25554933c32fd7dbca7534ac84104c1027ab6')
        self.assertEqual(receipt['output_sha256'],'f3460e71937c9d6dc29fce76181350845e66456b77d11c8d13ed11ab3882c8ed')
        for name,key in [('original40.bsl','source_sha256'),('original40.out','output_sha256')]:
            self.assertEqual(hashlib.sha256((FIXTURE/name).read_bytes()).hexdigest(),receipt[key])
        self.assertEqual(len(require_available((FIXTURE/'original40.out').read_bytes())),40)
    def test_original38_matches_and_two_unresolved_representation_cases(self):
        native=validate_output((FIXTURE/'original40.out').read_bytes())
        local=validate_output(emit(source=(FIXTURE/'original40.bsl').read_text(encoding='utf-8')))
        self.assertEqual([a['case'] for a,b in zip(native,local) if a!=b],[5,10])
        for n in (5,10):
            self.assertEqual(native[n-1]['units'],tuple(map(ord,'Нет:64')))
            self.assertEqual(local[n-1]['units'],tuple(map(ord,'Да:64')))
if __name__=='__main__':unittest.main()
