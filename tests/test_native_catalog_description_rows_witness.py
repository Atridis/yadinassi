"""Private witness versions and source-bound renderer remain closed and separate."""
import json
import unittest
import catalog_description_measurement as m
from test_native_catalog_description_rows_policy import NATIVE_UUID

class RowsWitnessTests(unittest.TestCase):
    def test_schema_versions_are_not_interchangeable(self):
        base=dict(schema=2,nonce='a'*32,token='b'*32,case='description8',operation='observe',present=True,actual_description='Я ')
        args=dict(nonce='a'*32,token='b'*32,case='description8',operation='observe')
        raw=json.dumps(base).encode();self.assertEqual(m.validate_witness(raw,**args).schema,2)
        with self.assertRaises(ValueError):m.validate_witness(raw,rows=True,**args)
        base.update(schema=3,actual_uuid=NATIVE_UUID);raw=json.dumps(base).encode()
        self.assertEqual(m.validate_witness(raw,rows=True,**args).actual_uuid,NATIVE_UUID)
        with self.assertRaises(ValueError):m.validate_witness(raw,**args)
        for value in ('',NATIVE_UUID.upper().replace('52','AB'),'{'+NATIVE_UUID+'}','0'*32,'00000000-0000-0000-0000-000000000000',1,None):
            with self.subTest(value=value),self.assertRaises(ValueError):m.validate_witness(json.dumps({**base,'actual_uuid':value}).encode(),rows=True,**args)
    def test_rows_render_exact_inverse_and_same_selected_read(self):
        for case in m.CASES:
            for name in m.PINS:
                original=(m.ROOT/name).read_bytes()
                rendered=m.transform(original,name=name,case=case,rows=True)
                self.assertEqual(m.inverse(rendered,name=name,case=case,rows=True),original)
                if name.endswith('.bsl'):
                    self.assertIn('UUID = Строка(Выборка.Ссылка.УникальныйИдентификатор());'.encode(),rendered)
                    self.assertEqual(rendered.count(b'actual_uuid'),1)
                    with self.assertRaises(ValueError):m.inverse(rendered,name=name,case=case)
                    old=m.transform(original,name=name,case=case)
                    self.assertNotIn(b'actual_uuid',old)
                    self.assertEqual(m.inverse(old,name=name,case=case),original)
