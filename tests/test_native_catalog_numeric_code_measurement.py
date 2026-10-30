"""Standalone transform/private witness checks; no native execution claim."""
from decimal import Decimal, localcontext
import hashlib
import json
from pathlib import Path
import unittest
from unittest import mock
import sys
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts/native_1c_db_oracle'))
import catalog_numeric_code_measurement as m


def data(**kw):
    out=dict(schema=1,nonce='a'*32,token='b'*32,case='number3',operation='observe',
        present=True,actual_number=True,actual_code='123',actual_uuid='11111111-2222-3333-4444-555555555555',
        actual_description='Name  ',code_length=3,description_length=8,payload_length=32,autonumbering=False)
    out.update(kw);return out


def raw(**kw):return json.dumps(data(**kw),ensure_ascii=True,separators=(',',':')).encode()
def read(value=None,**kw):return m.validate_witness(raw() if value is None else value,nonce='a'*32,token='b'*32,case='number3',operation='observe',**kw)


class NumericCodeMeasurementTests(unittest.TestCase):
    def test_exact_two_cases_xml_and_full_inverse(self):
        self.assertEqual(set(m.CASES),{'number3','number6'})
        for case,(length,create,update) in m.CASES.items():
            for name in m.PINS:
                original=(m.ROOT/name).read_bytes();out=m.transform(original,name=name,case=case)
                self.assertEqual(m.inverse(out,name=name,case=case),original)
                if name.endswith('.xml'):
                    self.assertIn(f'<CodeLength>{length}</CodeLength>'.encode(),out)
                    self.assertIn(b'<CodeType>Number</CodeType>',out)
                    self.assertIn(b'<Autonumbering>false</Autonumbering>',out)
                    self.assertIn(b'<DescriptionLength>8</DescriptionLength>',out)
                else:
                    text=out.decode();self.assertIn(f'Объект.Код = {create};',text);self.assertIn(f'Объект.Код = {update};',text)
                    self.assertNotIn('Выборка.Код <> "K1"',text)
                    self.assertIn('Результат.code = "observed_number";',text)
                    self.assertIn('КодXML = XMLСтрока(Выборка.Код);',text)
                    self.assertIn('Каталог.Автонумерация',text)
                    self.assertNotIn(f'Выборка.Код = {create}',text)
                    self.assertIn('NativeNumericCodeObserve(Корень, ТокенЗапуска, Операция);',text)

    def test_raw_hash_pins_crlf_bom_drift_and_inverse_tamper(self):
        for name in m.PINS:
            original=(m.ROOT/name).read_bytes()
            for changed in (original+b'\n',b'\xef\xbb\xbf'+original,original.replace(b'\n',b'\r\n')):
                if changed != original:
                    with self.assertRaises(ValueError):m.transform(changed,name=name,case='number3')
            out=m.transform(original,name=name,case='number3')
            with self.assertRaises(ValueError):m.inverse(out+b'x',name=name,case='number3')
            with self.assertRaises(ValueError):m.inverse(out,name=name,case='number6')
        for case in ('number9','',3,True):
            with self.assertRaises(ValueError):m.transform(b'',name='metadata/Catalog.xml',case=case)

    def test_hook_tamper_and_original_template_unchanged(self):
        original=(m.ROOT/'metadata/Catalog.xml').read_bytes()
        module=(m.ROOT/'modules/NativeOracleServer.bsl').read_bytes()
        with mock.patch.object(m.Path,'read_bytes',return_value=b'drift'):
            with self.assertRaises(ValueError):m.transform(module,name='modules/NativeOracleServer.bsl',case='number3')
        self.assertIn(b'<CodeType>String</CodeType>',original)

    def test_number_private_type_readback_is_not_assignment_expectation(self):
        witness=read();self.assertEqual(witness.actual_code,Decimal('123'))
        self.assertNotIn(123,m.CASES['number3'][1:])
        for text in ('0','-1','12.50','123456789012345678901234567890'):
            with localcontext() as context:
                context.prec=2
                self.assertEqual(read(raw(actual_code=text)).actual_code,Decimal(text))
        # These are transport observations, not assignment acceptance claims.
        self.assertEqual(read(raw(actual_code='-0')).actual_code.as_tuple().sign,1)

    def test_witness_shape_join_replay_types_and_canonical_uuid(self):
        changes=[dict(schema=2),dict(schema=True),dict(nonce='c'*32),dict(token='c'*32),dict(case='number6'),
            dict(operation='update'),dict(present=1),dict(actual_number=False),dict(actual_code=123),dict(code_length=True),
            dict(payload_length=-1),dict(autonumbering=0),dict(actual_uuid='0'*32),dict(actual_uuid='11111111222233334444555555555555'),
            dict(actual_uuid='00000000-0000-0000-0000-000000000000'),dict(extra=1),dict(actual_description='\ud800')]
        for change in changes:
            with self.subTest(change=change),self.assertRaises(ValueError):read(raw(**change))
        for text in ('NaN','Infinity','1e2','+1','01',' 1','1.','1,' , '1'*81):
            with self.subTest(text=text),self.assertRaises(ValueError):read(raw(actual_code=text))
        with self.assertRaises(ValueError):read(raw()[:-1]+b',"schema":1}')
        with self.assertRaises(ValueError):read(b'['*2000+b']'*2000)
        with self.assertRaises(ValueError):read(b' '*2049)
        self.assertEqual(read(b'\xef\xbb\xbf'+raw()).actual_code,Decimal('123'))

    def test_absence_is_explicit_no_fabricated_zero_or_uuid(self):
        witness=read(raw(present=False,actual_number=False,actual_code='',actual_uuid='',actual_description=''))
        self.assertIsNone(witness.actual_code);self.assertIsNone(witness.actual_uuid)
        for change in (dict(actual_number=True),dict(actual_code='0'),dict(actual_uuid=data()['actual_uuid'])):
            d=dict(present=False,actual_number=False,actual_code='',actual_uuid='',actual_description='');d.update(change)
            with self.assertRaises(ValueError):read(raw(**d))

    def test_compare_independent_actual_not_seed_and_controls(self):
        import test_native_catalog_numeric_code_physical as f
        from dataclasses import replace
        actual=f.read(f.source(number=123))
        witness=read(raw(actual_uuid=str(actual.typed_uuid),actual_description=actual.records.rows[0].fields[5].value))
        result=m.compare_readback(actual,witness,case='number3')
        self.assertEqual(result['status'],'readback_matches')
        self.assertEqual(result['runtime_support'],'not_claimed')
        serialized=json.dumps(result)
        self.assertNotIn('actual_code',serialized);self.assertNotIn(str(actual.typed_uuid),serialized)
        for change in (dict(actual_code=Decimal('124')),dict(actual_description='other'),
                       dict(actual_uuid=__import__('uuid').UUID('11111111-2222-3333-4444-555555555555'))):
            with self.subTest(change=change):
                self.assertEqual(m.compare_readback(actual,replace(witness,**change),case='number3')['status'],'readback_differs')
        for change in (dict(code_length=6),dict(payload_length=64),dict(autonumbering=True)):
            self.assertEqual(m.compare_readback(actual,replace(witness,**change),case='number3')['status'],'case_metadata_mismatch')
        def edit(ds):return ds[:4]+[('_CODE','N',0,4,0,'CS')]+ds[5:]
        unknown=f.read(f.source(number=123,edit=edit))
        self.assertEqual(m.compare_readback(unknown,witness,case='number3')['status'],'layout_unresolved')
        with self.assertRaises(ValueError):m.compare_readback(actual,replace(witness,present=False),case='number3')

    def test_private_transport_rectangular_bound(self):
        # Worst permitted escaped128 UTF16 units,80number bytes, fixed UUID,
        # maximal scalar widths + BOM; not a report/capture budget proof.
        value=raw(actual_description='\u0800'*128,actual_code='1'*80,code_length=2047,description_length=2047,payload_length=2047)
        self.assertLessEqual(len(value)+3,m.WITNESS_LIMIT)
        self.assertEqual(len(read(value).actual_description),128)
        with self.assertRaises(ValueError):read(raw(actual_description='x'*129))

if __name__=='__main__':unittest.main()
