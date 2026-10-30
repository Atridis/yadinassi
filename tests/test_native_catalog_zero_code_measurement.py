import hashlib
import json
import unittest
from uuid import UUID
from decimal import Decimal
import test_native_catalog_zero_code_physical as physical
import catalog_zero_code_measurement as subject


def witness(case='zero8',state='unavailable',value='',present=True):
    return dict(schema=1,nonce='a'*32,token='b'*32,case=case,operation='observe',present=present,
        code_type="string",code_state=state,actual_code=value,actual_uuid=str(physical.read().typed_uuid) if present else '',
        actual_description='X' if present and case=='zero8' else '',code_length=0,
        description_length=subject.CASES[case],payload_length=32,autonumbering=False)


def parse(d,raw=None):
    return subject.validate_witness(json.dumps(d).encode() if raw is None else raw,
        nonce='a'*32,token='b'*32,case=d['case'],operation='observe')


class ZeroCodeMeasurementTests(unittest.TestCase):
    def test_exact_transforms_and_inverse_no_code_assignment(self):
        for case in subject.CASES:
            for path in subject.PINS:
                raw=(subject.ROOT/path).read_bytes();changed=subject.transform(raw,name=path,case=case)
                self.assertEqual(subject.inverse(changed,name=path,case=case),raw)
                with self.assertRaises(ValueError):subject.transform(raw+b' ',name=path,case=case)
                with self.assertRaises(ValueError):subject.inverse(changed+b' ',name=path,case=case)
                if path.endswith('.bsl'):
                    self.assertNotIn('Объект.Код =',changed.decode())
                    self.assertNotIn('Выборка.Код <>',changed.decode())
                    self.assertIn('observed_no_code',changed.decode())
                    if case=='zero0':self.assertNotIn('Объект.Наименование =',changed.decode())
    def test_all_availability_outcomes_without_seed_equality(self):
        for state,value,expected in (('unavailable','',None),('other','',None),('string','', ''),('string','unexpected Ж  ','unexpected Ж  '),('number','-12.50',Decimal('-12.50'))):
            d=witness(state=state,value=value);w=parse(d);self.assertEqual(w.actual_code,expected)
            out=subject.compare_readback(physical.read(),w,case='zero8')
            self.assertTrue(out['metadata_matches']);self.assertEqual(out['uuid_verdict'],'matches')
            self.assertEqual(out['description_verdict'],'matches');self.assertEqual(out['code_availability'],state)
            self.assertNotIn(str(w.actual_uuid),json.dumps(out))
            if value:self.assertNotIn(value,json.dumps(out))
    def test_disabled_description_and_absent_baseline(self):
        d=witness('zero0');w=parse(d);out=subject.compare_readback(physical.read(physical.source(0)),w,case='zero0')
        self.assertEqual(out['description_verdict'],'not_applicable')
        self.assertIsNone(parse(witness(state='absent',present=False)).actual_uuid)
    def test_schema_token_and_values_fail_closed(self):
        changes=[{'schema':True},{'token':'c'*32},{'present':1},{'code_state':'arbitrary'},
            {'code_state':'unavailable','actual_code':'leak'},{'code_state':'number','actual_code':'NaN'},
            {'code_state':'number','actual_code':'01'},{'actual_uuid':'0'*36},{'actual_description':'\ud800'},
            {'code_state':'string','actual_code':'x'*129},{'code_length':True},{'extra':1}]
        for change in changes:
            d=witness();d.update(change)
            with self.subTest(change=change),self.assertRaises(ValueError):parse(d)
        d=witness()
        raw=json.dumps(d).replace('"schema": 1','"schema": 1,"schema": 1').encode()
        with self.assertRaises(ValueError):parse(d,raw)
    def test_native_metadata_and_uuid_are_independent_controls(self):
        d=witness();d['code_length']=2
        self.assertFalse(subject.compare_readback(physical.read(),parse(d),case='zero8')['metadata_matches'])
        d=witness();d['actual_uuid']='12345678-1234-1234-1234-123456789abc'
        self.assertEqual(subject.compare_readback(physical.read(),parse(d),case='zero8')['uuid_verdict'],'differs')
    def test_private_bound_rectangular(self):
        d=witness(state='string',value='\u0001'*128);d['actual_description']='\u0001'*128
        raw=json.dumps(d,separators=(',',':'),ensure_ascii=True).encode()
        self.assertLessEqual(len(raw)+3,2048)
        parse(d,b'\xef\xbb\xbf'+raw)
        self.assertEqual(parse(d,b'\xef\xbb\xbf'+raw).raw_sha256,hashlib.sha256(b'\xef\xbb\xbf'+raw).hexdigest())

    def test_native_metadata_type_independent_of_all_code_access_states(self):
        for state,value in (('unavailable',''),('other',''),('string',''),('number','12')):
            for native_type in ('number','other'):
                d=witness(state=state,value=value);d['code_type']=native_type
                self.assertFalse(subject.compare_readback(physical.read(),parse(d),case='zero8')['metadata_matches'])
        for value in (1,True,None,[],{},'String'):
            d=witness();d['code_type']=value
            with self.assertRaises(ValueError):parse(d)
        d=witness();del d['code_type']
        with self.assertRaises(ValueError):parse(d)
        text=subject._hook('zero8')
        self.assertIn('Каталог.ТипКода = ТипКодаСправочника.Строка',text)
        self.assertIn('Каталог.ТипКода = ТипКодаСправочника.Число',text)
