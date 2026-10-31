"""Native byte replay through synthetic transport, not whole-.1CD parity."""
from dataclasses import replace
from datetime import datetime
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import unittest
import test_config_catalog_binding as f
import test_config_catalog_records as r
from test_filedb_catalog import Source,P,u32

PATH=Path(__file__).with_name('fixtures')/'linked_catalog_records.json'
SHA='1c4330d30b2ae021205ef32ef197bfec508273dd191eff40371d85ffa976e4ee'
b=f.binding;c=f.catalog

def cases():
    raw=PATH.read_bytes()
    if hashlib.sha256(raw).hexdigest()!=SHA:raise ValueError('native fixture digest')
    return json.loads(raw)['cases']


def compile_case(case):
    logical=case['logical'];items=[]
    for a in logical['attributes']:
        kind=a['type'];token={'String':'S','Number':'N','Boolean':'B','Date':'D','SingleCatalogRef':'#'}[kind]
        q=(a['length'],1) if token=='S' else (a['digits'],a['fraction_digits'],0) if token=='N' else ()
        kw={} if token!='#' else dict(reference_type_uuid=a['target_requested_ref_type_uuid'],reference_catalog_uuid=a['target_metadata_uuid'])
        items.append(f.attrs.CatalogAttribute(a['metadata_uuid'],a['name'],token,q,**kw))
    identity=f.name.CatalogIdentityPrefix(logical['metadata_uuid'],logical['name'],2,1,8)
    index=f.index(tuple((e['uuid'],e['kind'],e['id']) for e in case['dbnames']['entries']))
    return b.compile_catalog_binding(identity,f.attrs.CatalogAttributes(tuple(items)),index,
        profile=b.CatalogBindingProfile(b.LINKED_PROFILE_IDENTIFIER),budget=c._Budget(c.CatalogLimits()))


def source(case,raw=None,declarations=None):
    shape=compile_case(case);data=bytes.fromhex(case['physical']['raw_hex']) if raw is None else raw
    value=Source(page_count=40);value.catalog((2,6,10))
    fields=shape.declarations if declarations is None else declarations
    for block,table,decl,files in ((2,'CONFIG',(),(4,5,0)),(6,'PARAMS',(),(6,7,0)),(10,shape.table_name,fields,(20,21,0))):
        text=r.serialize((table,0,('Fields',*decl),('Indexes',),('Recordlock','0'),('Files',*files))).encode()
        value.chain(tuple(range(block,block+(len(text)+249)//250)),text)
    for page in (4,5,6,7):value.page(page)[:24]=b'\x1c\xfd'+bytes(22)
    head=value.page(20);head[:24]=b'\x1c\xfd'+bytes(14)+len(data).to_bytes(8,'little')
    for i in range((len(data)+P-1)//P):
        head[24+i*4:28+i*4]=u32(22+i);chunk=data[i*P:(i+1)*P];value.page(22+i)[:len(chunk)]=chunk
    return value,shape


class LinkedCatalogRecordsTests(unittest.TestCase):
    def test_native_both_orders_empty_and_filled(self):
        for case in cases():
            with self.subTest(repeat=case['repeat'],state=case['state'],name=case['logical']['name']):
                value,shape=source(case)
                self.assertEqual(shape.declarations,tuple(tuple(x) for x in case['physical']['declarations']))
                self.assertEqual(shape.record_size,169 if shape.attributes else 74)
                result=r.read(value,shape,slot_policy='closed_free_single_v1')
                self.assertEqual(len(result.rows),0 if case['state']=='empty' else 3 if shape.attributes else 1)
                if result.rows and shape.attributes:
                    by_code={row.fields[4].value:row for row in result.rows}
                    for code,date,number,boolean,text in [('10',datetime(1,1,1),Decimal('0'),False,''),('20',datetime(2001,1,1,0,0,1),Decimal('-7.25'),True,'third'),('30',datetime(2024,2,29,12,34,56),Decimal('12.50'),True,'hello')]:
                        values={a.type_token:field.value for a,field in zip(shape.attributes,by_code[code].fields[6:])}
                        self.assertEqual((values['D'],values['N'],values['B'],values['S']),(date,number,boolean,text))
                        self.assertEqual(len(values['#']),16)
                        if code=='10':self.assertEqual(values['#'],bytes(16))
                        if code=='30':self.assertEqual(values['#'],by_code[code].fields[0].value)

    def test_date_encoding_rejects_nondecimal_and_invalid_calendar(self):
        decl=('_FLD1','DT',0,0,0,'CS')
        for raw in (bytes.fromhex('20240230123456'),bytes.fromhex('20241301123456'),bytes.fromhex('20240229123460'),bytes.fromhex('20240229123a56'),bytes.fromhex('00000101000000'),bytes(6)):
            with self.subTest(raw=raw),self.assertRaises(c.UnsupportedLayout):r.records._decode(raw,decl)
        self.assertEqual(r.records._decode(bytes(7),decl),datetime(1,1,1))

    def test_forged_binding_offsets_and_target_metadata_fail_before_payload(self):
        case=cases()[2];base=compile_case(case)
        ref=next(a for a in base.attributes if a.type_token=='#')
        changes=[replace(base,record_size=170),replace(base,placements=(replace(base.placements[0],offset=1),)+base.placements[1:]),replace(base,attributes=tuple(replace(a,reference_catalog_uuid=None) if a is ref else a for a in base.attributes)),replace(base,attributes=tuple(replace(a,reference_type_uuid=a.reference_catalog_uuid) if a is ref else a for a in base.attributes))]
        for changed in changes:
            value,_=source(case)
            with self.assertRaises(c.UnsupportedLayout):r.read(value,changed)
            self.assertFalse(any(offset==20*P for offset,_ in value.calls))

    def test_nullable_reference_or_date_declaration_is_not_admitted(self):
        case=cases()[2];shape=compile_case(case)
        for index in (next(i for i,d in enumerate(shape.declarations) if d[1]=='DT'),len(shape.declarations)-1):
            declarations=list(shape.declarations);d=declarations[index];declarations[index]=d[:2]+(1,)+d[3:]
            value,_=source(case,declarations=tuple(declarations))
            with self.assertRaises(c.UnsupportedLayout):r.read(value,shape)
            self.assertFalse(any(offset==20*P for offset,_ in value.calls))

    def test_mixed_binding_profile_bounds_and_mapping_fail_closed(self):
        import copy
        original=cases()[2]
        mutations=[]
        bad=copy.deepcopy(original);bad['logical']['attributes'][0]['length']=2048;mutations.append(bad)
        bad=copy.deepcopy(original);bad['logical']['attributes'][1]['fraction_digits']=10;mutations.append(bad)
        bad=copy.deepcopy(original);bad['logical']['attributes'][4]['target_metadata_uuid']='00000000-0000-0000-0000-000000000000';mutations.append(bad)
        bad=copy.deepcopy(original);bad['logical']['attributes'][4]['target_requested_ref_type_uuid']=bad['logical']['attributes'][4]['target_metadata_uuid'];mutations.append(bad)
        bad=copy.deepcopy(original);bad['logical']['attributes']*=3;mutations.append(bad)
        bad=copy.deepcopy(original);bad['dbnames']['entries'].append(dict(bad['dbnames']['entries'][-1]));mutations.append(bad)
        for bad in mutations:
            with self.subTest(bad=bad['logical']['name']),self.assertRaises(b.CatalogBindingError):compile_case(bad)

    def test_lowered_field_and_slot_caps_still_apply(self):
        case=cases()[2]
        for limits in (r.legacy.RecordLimits(max_fields=10),r.legacy.RecordLimits(max_slots=3),r.legacy.RecordLimits(max_active_records=2)):
            value,shape=source(case)
            with self.assertRaises(c.ResourceLimit):r.read(value,shape,limits=limits)

    def test_existing_single_free_chain_policy_remains_closed(self):
        case=cases()[2];shape=compile_case(case);raw=bytearray(bytes.fromhex(case['physical']['raw_hex']))
        raw[1:5]=(2).to_bytes(4,'little');raw[2*169]=1;raw[2*169+1:2*169+5]=(3).to_bytes(4,'little')
        value,_=source(case,bytes(raw))
        with self.assertRaises(c.UnsupportedLayout) as error:r.read(value,shape,slot_policy='closed_free_single_v1')
        self.assertEqual(error.exception.code,'catalog_multiple_free_slots')

if __name__=='__main__':unittest.main()
