"""Minimal immutable ordinary capture; source-bound acquisition audited separately."""
import hashlib
import json
from pathlib import Path
import sys
import unittest
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT/'scripts'))
from test_native_xdto_family_measurement import emit
import native_1c_xdto_family_contract as wire
FIXTURE=ROOT/'tests/fixtures/xdto_family/native-initial'

class XDTOAcquisitionTests(unittest.TestCase):
    def test_minimal_capture_exact_bytes_and_closed_receipt(self):
        source=(FIXTURE/'source.bsl').read_bytes();raw=(FIXTURE/'native.out').read_bytes()
        self.assertEqual(hashlib.sha256(source).hexdigest(),'c317011c5fb651fe313eed07cf9587ab14e3f474857ef54d3646a9ae52e5376a')
        self.assertEqual(hashlib.sha256(raw).hexdigest(),'6646c0e7d22b770b580fb19a037b2612c54e2364224b078cbe4a767ef8697a16')
        receipt=json.loads((FIXTURE/'receipt.json').read_text(encoding='utf-8'))
        self.assertEqual(set(receipt),{'schema','source_sha256','output_sha256','cases','context','platform','native_actions_available','initial_mismatches','limits'})
        self.assertEqual(receipt['source_sha256'],wire.SOURCE_SHA256)
        self.assertEqual(receipt['output_sha256'],hashlib.sha256(raw).hexdigest())
        self.assertEqual(len(wire.require_available(raw)),40)
    def test_current_runtime_exact_historical_ordinary40(self):
        self.assertEqual(emit(source=(FIXTURE/'source.bsl').read_text(encoding='utf-8')),(FIXTURE/'native.out').read_bytes())
    def test_measured_metadata_order_and_empty_list_presence(self):
        from test_xdto_family import factory
        f=factory();kind=f.type('urn:test','Box');obj=f.create(kind)
        self.assertEqual(kind._properties.get(0)._name,'id')
        values=obj.get_list('tags');self.assertFalse(obj.is_set('tags'))
        values.add('a');self.assertTrue(obj.is_set('tags'))
        values.clear();self.assertFalse(obj.is_set('tags'))
        values.add('b');obj.unset('tags');self.assertFalse(obj.is_set('tags'))

if __name__=='__main__':unittest.main()
