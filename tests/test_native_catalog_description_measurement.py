"""Standalone mechanics only; no native acceptance or runner registration."""
import hashlib
import json
from pathlib import Path
import sys
import unittest
from unittest import mock
import xml.etree.ElementTree as ET
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'scripts/native_1c_db_oracle'))
import catalog_description_measurement as m
import inject_metadata

class DescriptionMeasurementTests(unittest.TestCase):
    def test_exact_transforms_inverse_and_originals(self):
        for case in m.CASES:
            for name, digest in m.PINS.items():
                raw=(m.ROOT/name).read_bytes()
                self.assertEqual(hashlib.sha256(raw).hexdigest(),digest)
                transformed=m.transform(raw,name=name,case=case)
                self.assertEqual(m.inverse(transformed,name=name,case=case),raw)
                with self.assertRaises(ValueError):
                    m.transform(raw+b' ',name=name,case=case)
                with self.assertRaises(ValueError):
                    m.inverse(transformed+b' ',name=name,case=case)
            xml=m.transform((m.ROOT/'metadata/Catalog.xml').read_bytes(),name='metadata/Catalog.xml',case=case)
            # Sole metadata change: no new catalog, rights, qualifiers or UUIDs.
            root=ET.fromstring(xml)
            node=root.find('.//{*}DescriptionLength')
            self.assertEqual(node.text,str(m.CASES[case][0]))
            self.assertIn(b'@@PAYLOAD_LENGTH@@',xml)
            server=m.transform((m.ROOT/'modules/NativeOracleServer.bsl').read_bytes(),name='modules/NativeOracleServer.bsl',case=case).decode()
            self.assertIn('(Длина <> 32 И Длина <> 64)',server)
            self.assertEqual(server.count('NativeDescriptionObserve(Корень, ТокенЗапуска, Операция);'),1)
            self.assertNotIn('@@DESCRIPTION_CASE@@',server)
            self.assertIn('Выборка.Наименование',server)

    def test_hook_source_is_pinned(self):
        raw=(m.ROOT/'modules/NativeOracleServer.bsl').read_bytes()
        with mock.patch.object(Path,'read_bytes',return_value=b'arbitrary BSL'):
            with self.assertRaises(ValueError):
                m.transform(raw,name='modules/NativeOracleServer.bsl',case='description8')

    def test_seed_units_are_not_assumed_native_readback(self):
        for case,(capacity,created,updated) in m.CASES.items():
            self.assertEqual(len(created.encode('utf-16-le'))//2,capacity)
            self.assertLess(len(created),capacity)
            self.assertTrue(created.endswith('  '))
            self.assertLess(len(updated.encode('utf-16-le'))//2,capacity)
            self.assertTrue(m.verify_case_metadata(case,capacity))
            self.assertFalse(m.verify_case_metadata(case,True))
            self.assertFalse(m.verify_case_metadata(case,0))

    def witness(self,value='',**overrides):
        return dict(schema=2,present=True,nonce='a'*32,token='b'*32,case='description8',operation='create',actual_description=value,**overrides)

    def decode(self,data):
        return m.validate_witness(json.dumps(data,ensure_ascii=True).encode(),nonce='a'*32,token='b'*32,case='description8',operation='create')

    def test_actual_is_measured_not_prescribed(self):
        for value in ('','unexpected','AБ😀xy  ','  ','x'*128):
            w=self.decode(self.witness(value))
            self.assertEqual(w.actual_description,value)
            self.assertEqual(w.utf16_units,len(value.encode('utf-16-le'))//2)
            self.assertEqual(w.scalar_count,len(value))
        self.assertEqual(self.decode(self.witness('😀 ')).trailing_spaces,1)

    def test_closed_witness(self):
        for key,value in [('schema',True),('nonce','c'*32),('token','c'*32),('case','description17'),('operation','update'),('actual_description',False),('actual_description','\ud800'),('actual_description','x'*129),('extra',1)]:
            data=self.witness();data[key]=value
            with self.subTest(key=key,value=repr(value)),self.assertRaises(ValueError):self.decode(data)
        for key in self.witness():
            data=self.witness();del data[key]
            with self.assertRaises(ValueError):self.decode(data)
        raw=json.dumps(self.witness()).encode()
        for invalid in (raw[:-1]+b',"schema":1}',b'[]',b'\xff',b' '*2049):
            with self.assertRaises(ValueError):m.validate_witness(invalid,nonce='a'*32,token='b'*32,case='description8',operation='create')

    def test_private_transport_bound(self):
        # Maximum JSON escaping: each admitted UTF16 unit <= six ASCII bytes;
        # choose surrogate pairs too, ensuring scalar/unit accounting is distinct.
        for case in m.CASES:
            for op in ('create','update'):
                data=self.witness('\x00'*128);data.update(case=case,operation=op)
                raw=json.dumps(data,ensure_ascii=True,separators=(',',':')).encode()
                maximum=len(raw)+3 # optional BOM
                self.assertLessEqual(maximum,m.WITNESS_LIMIT)
                value=m.validate_witness(b'\xef\xbb\xbf'+raw,nonce='a'*32,token='b'*32,case=case,operation=op)
                self.assertEqual(value.utf16_units,128)
        self.assertEqual((m.CAPTURE_LIMIT,m.REPORT_LIMIT),(8192,32768))

if __name__=='__main__':unittest.main()
