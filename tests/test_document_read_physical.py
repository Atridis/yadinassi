"""Invented Document raw transport; no native membership/layout assertions."""
import copy
import hashlib
import json
from pathlib import Path
import sys
import unittest
from unittest import mock
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'scripts/native_1c_db_oracle'),str(ROOT/'scripts'),str(ROOT/'yadinassi/storage')]
import document_read_physical as subject
import test_linked_card_physical as linked


def request():
    schema,mapping=linked.request();a,b=schema['catalogs']
    p=dict(source='f1549f9a53fb12d5d6ceca02d3bc78e5d17e2955',status='schema-backed-not-native-applied',
        document_name='D'+a['name'][1:],catalog_name=b['name'],document_uuid=a['metadata_uuid'],catalog_uuid=b['metadata_uuid'],
        posting='Allow',number_type='String',number_length=8,number_periodicity='Nonperiodical',attributes=5,linked_schema=schema)
    mapping[0]=dict(mapping[0],name=p['document_name'])
    return p,mapping


def image(p,kind='Document',table=True,*,baseline_name='NativeOracleItems',baseline_code='2',baseline_missing=False,extra_ref=False,baseline_uuid='77777777-7777-4777-8777-777777777777'):
    # The opaque UUID filename contains an invented catalog-shaped descriptor.
    # Document interpretation MUST NOT use that shape to claim collection membership.
    schema=p['linked_schema'];u32=linked.base.u32;P=linked.base.P
    cf=linked.base.config_fixture;original=cf.content_source
    baseline=baseline_uuid # Invented input, not a routing constant.
    prefix=cf.matrix.names.document(name='"'+baseline_name+'"',code=baseline_code,kind='1',description='0',metadata_uuid=baseline)
    attributes=[cf.constructed.attribute('88888888-8888-4888-8888-888888888888','"Payload"','{"Pattern",{"S",32,1}}'),
                cf.constructed.attribute('99999999-9999-4999-8999-999999999999','"Amount"','{"Pattern",{"N",9,2,0}}')]
    collection=cf.constructed.node('cf4abea7-37b2-11d4-940f-008048da11f9','2',*attributes)
    payload=cf.stored_literal(prefix[:-1]+b',0,0,0,0,'+collection.encode()+b'}')
    def complete(entries):
        refs=[schema['catalogs'][1]['metadata_uuid'],baseline]
        if extra_ref:refs.append('aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa')
        entries=list(entries);entries[2]=cf.entries(refs=refs)[2]
        if not baseline_missing:entries.append((baseline,payload,0))
        return original(entries)
    with mock.patch.object(cf,'content_source',side_effect=complete):value=linked.image(schema)
    triples=[]
    for i,s in enumerate(schema['catalogs']):
        triples.append('{'+s['metadata_uuid']+',"'+(kind if i==0 else 'Reference')+'",'+str(19+i)+'}')
        triples.extend('{'+a['metadata_uuid']+',"Fld",'+str(100+n)+'}' for n,a in enumerate(s['attributes']))
    raw=('\ufeff{0,{'+str(len(triples))+','+','.join(triples)+'}}').encode()
    packed=b'\x01'+len(raw).to_bytes(2,'little')+(65535-len(raw)).to_bytes(2,'little')+raw
    value.page(32)[301+276:301+287]=bytes.fromhex('1'+str(len(packed)).zfill(20)+'0')
    value.page(32)[301+287:301+295]=u32(1)+u32(len(packed))
    chunks=[packed[i:i+250] for i in range(0,len(packed),250)]
    value.page(31)[16:24]=((len(chunks)+1)*256).to_bytes(8,'little');value.page(33)[:]=bytes(P)
    for i,chunk in enumerate(chunks,1):
        offset=i*256;value.page(33)[offset:offset+6]=u32(i+1 if i<len(chunks) else 0)+len(chunk).to_bytes(2,'little')
        value.page(33)[offset+6:offset+6+len(chunk)]=chunk
    if table:
        reader=subject.c.CatalogReader(value.read_at,value.size);catalog=reader.read_catalog()
        old=next(t for t in catalog.tables if t.name=='_Reference19')
        raw=old.raw_descriptor.replace(b'_Reference19',b'_Document19')
        value.chain(tuple(range(14,14+(len(raw)+249)//250)),raw)
    value.calls.clear()
    return value


class DocumentReadPhysicalTests(unittest.TestCase):
    def test_complete_raw_capture_root_target_and_both_uuid_files(self):
        p,m=request();v=image(p)
        result=subject.observe(v.read_at,v.size,p,m)
        self.assertEqual(len(result['config']['files']),5)
        self.assertEqual(result['config']['document_membership'],'unresolved')
        self.assertEqual(result['config']['baseline']['name'],'NativeOracleItems')
        self.assertEqual([x['physical']['candidate'] for x in result['objects']],['_Document19','_Reference20'])
        for obj in result['objects']:
            q=obj['physical'];self.assertEqual(q['status'],'captured');self.assertEqual(q['layout'],'unresolved')
            for key in ('record_size','slots','offsets'):self.assertIsNone(q[key])
        self.assertEqual(subject.validate_observation(json.loads(json.dumps(result)),p,m),result)

    def test_unknown_kind_and_unmatched_name_keep_config_and_dbnames(self):
        for kind,table,reason in [('Other',True,'dbnames_kind'),('Document',False,'table_missing')]:
            p,m=request();v=image(p,kind,table);result=subject.observe(v.read_at,v.size,p,m)
            self.assertEqual(result['objects'][0]['physical']['reason'],reason)
            self.assertEqual(len(result['config']['files']),5)
            self.assertEqual(result['dbnames']['groups'][0]['entries'][0]['kind'],kind)
            self.assertEqual(result['objects'][1]['physical']['status'],'captured')

    def test_config_params_and_other_target_payload_aliases_fail_closed(self):
        for target in (32,33,49):
            p,m=request();v=image(p);v.page(40)[24:28]=linked.base.u32(target)
            with self.subTest(target=target),self.assertRaises(subject.c.UnsupportedSharing):subject.observe(v.read_at,v.size,p,m)
            if target==49:self.assertFalse(any(offset==49*linked.base.P for offset,length in v.calls))
        p,m=request();v=image(p)
        # Determine CONFIG's mapped data page without assuming a descriptor offset.
        reader=subject.c.CatalogReader(v.read_at,v.size);catalog=reader.read_catalog();t=next(t for t in catalog.tables if t.name=='CONFIG')
        data=reader._open_table_data(t);v.page(40)[24:28]=linked.base.u32(data._pages[0])
        with self.assertRaises(subject.c.UnsupportedSharing):subject.observe(v.read_at,v.size,p,m)

    def test_raw_bound_precedes_payload_and_callback_budget_precedes_forward(self):
        p,m=request();v=image(p);v.page(40)[16:24]=(8193).to_bytes(8,'little')
        # Complete independent page mapping, otherwise malformed pointers fail earlier.
        for i in range(3):v.page(40)[24+i*4:28+i*4]=linked.base.u32(43+i)
        with self.assertRaises(subject.c.ResourceLimit):subject.observe(v.read_at,v.size,p,m)
        self.assertFalse(any(offset==43*linked.base.P for offset,length in v.calls))
        v=image(p)
        with mock.patch.object(subject,'MAX_READ_CALLS',0),self.assertRaises(subject.c.ResourceLimit):subject.observe(v.read_at,v.size,p,m)
        self.assertEqual(v.calls,[])

    def test_mapping_request_mismatch_before_any_read(self):
        p,m=request();m[0]['name']=p['catalog_name'];calls=[]
        with self.assertRaises(ValueError):subject.observe(lambda *a:calls.append(a),4096,p,m)
        self.assertEqual(calls,[])

    def test_hostile_replay_rejected_and_membership_not_upgradable(self):
        p,m=request();v=image(p);result=subject.observe(v.read_at,v.size,p,m)
        for mutate in (lambda x:x.update(schema=True),lambda x:x['config'].update(document_membership='verified'),
            lambda x:x['config']['files'][0].update(sha256='0'*64),lambda x:x['objects'][0]['physical'].update(record_size=169),
            lambda x:x['objects'][0]['physical'].update(raw_hex='00'),lambda x:x['objects'][0]['physical'].update(candidate='_Reference19'),
            lambda x:x['dbnames']['groups'][0]['entries'][0].update(id=True),lambda x:x['source_reads'].update(bytes=1)):
            bad=copy.deepcopy(result);mutate(bad)
            with self.assertRaises(ValueError):subject.validate_observation(bad,p,m)

    def test_baseline_membership_identity_and_profile_are_closed(self):
        p,m=request()
        for kwargs in (dict(baseline_name='Other'),dict(baseline_code='3'),dict(baseline_missing=True),dict(extra_ref=True)):
            v=image(p,**kwargs)
            with self.subTest(kwargs=kwargs),self.assertRaises((ValueError,subject.c.CatalogError)):
                subject.observe(v.read_at,v.size,p,m)
        dynamic='66666666-6666-4666-8666-666666666666'
        v=image(p,baseline_uuid=dynamic);out=subject.observe(v.read_at,v.size,p,m)
        self.assertEqual(out['config']['baseline']['metadata_uuid'],dynamic)
        bad=copy.deepcopy(out);item=bad['config']['files'][4]
        raw=bytes.fromhex(item['raw_hex']).replace(b'Amount',b'OtherX')
        item.update(raw_hex=raw.hex(),sha256=hashlib.sha256(raw).hexdigest())
        with self.assertRaises(ValueError):subject.validate_observation(bad,p,m)
        for mutate in (lambda x:x['config']['baseline'].update(code_type=True),
                       lambda x:x['config']['baseline'].update(name='Other'),
                       lambda x:x['config']['baseline'].update(metadata_uuid=p['catalog_uuid']),
                       lambda x:x['config']['files'].pop()):
            bad=copy.deepcopy(out);mutate(bad)
            with self.assertRaises(ValueError):subject.validate_observation(bad,p,m)

if __name__=='__main__':unittest.main()
