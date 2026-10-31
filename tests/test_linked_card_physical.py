"""Invented linked CONFIG/PARAMS/tables and hostile replay; no native evidence."""
import copy
import hashlib
import json
from pathlib import Path
import sys
import unittest
from unittest import mock
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'scripts/native_1c_db_oracle'),str(ROOT/'scripts'),str(ROOT/'yadinassi/storage')]
import linked_card_physical as subject
import linked_card_fixture as packet
import test_catalog_binding_integration as base
from test_filedb_records import serialize


def request():
    s,m,files=packet.load(1)
    r=m['schema']
    mapping=packet.actual_mapping(s,r,{n:v for n,v in files.items() if n.endswith('.xml')})
    return r,mapping


def image(r):
    cf=base.config_fixture; payloads=[]
    for spec in r['catalogs']:
        prefix=cf.matrix.names.document(name='"'+spec['name']+'"',code='2',kind='1',description='8',metadata_uuid=spec['metadata_uuid'])
        attrs=[]
        for a in spec['attributes']:
            # Invented descriptor grammar for unknown kinds is retained opaque;
            # this test never asserts it is the native CONFIG representation.
            token={'String':'{"S",32,1}','Number':'{"N",9,2,0}','Boolean':'{"B"}',
                   'Date':'{"D"}','SingleCatalogRef':'{"'+r['generated_ids'][r['catalogs'][1]['name']]['REF_TYPE_UUID']+'"}'}[a['type']]
            attrs.append(cf.constructed.attribute(a['metadata_uuid'],'"'+a['name']+'"','{"Pattern",'+token+'}'))
        coll=cf.constructed.node('cf4abea7-37b2-11d4-940f-008048da11f9',str(len(attrs)),*attrs)
        payloads.append(cf.stored_literal(prefix[:-1]+b',0,0,0,0,'+coll.encode()+b'}'))
    ids=[s['metadata_uuid'] for s in r['catalogs']]
    entries=cf.entries(refs=ids,payload=payloads[0],tail=((ids[1],payloads[1],0),))
    entries[0]=(ids[0],payloads[0],0)
    value=cf.content_source(entries)
    P=base.P;u32=base.u32
    value.page_count=64;value.size=64*P;value.page(0)[12:16]=u32(64)
    triples=[]
    for index,s in enumerate(r['catalogs']):
        triples.append('{'+s['metadata_uuid']+',"Reference",'+str(19+index)+'}')
        triples.extend('{'+a['metadata_uuid']+',"Fld",'+str(100+i)+'}' for i,a in enumerate(s['attributes']))
    db=('\ufeff{0,{'+str(len(triples))+','+','.join(triples)+'}}').encode()
    params=base.params_fixture.source()
    packed=b'\x01'+len(db).to_bytes(2,'little')+(65535-len(db)).to_bytes(2,'little')+db
    params.page(10)[301+276:301+287]=bytes.fromhex('1'+str(len(packed)).zfill(20)+'0')
    params.page(10)[301+287:301+295]=u32(1)+u32(len(packed))
    chunks=[packed[i:i+250] for i in range(0,len(packed),250)]
    params.page(8)[16:24]=((len(chunks)+1)*256).to_bytes(8,'little')
    params.page(11)[:]=bytes(P)
    for i,chunk in enumerate(chunks,1):
        offset=i*256;next_id=i+1 if i<len(chunks) else 0
        params.page(11)[offset:offset+6]=u32(next_id)+len(chunk).to_bytes(2,'little')
        params.page(11)[offset+6:offset+6+len(chunk)]=chunk
    for old,new in ((5,30),(8,31),(9,34),(10,32),(11,33)):value.page(new)[:]=params.page(old)
    value.page(30)[24:28]=u32(32);value.page(31)[24:28]=u32(33);value.page(32)[1:5]=u32(0)
    standard=[('_IDRREF','B',0,16,0,'CS'),('_VERSION','RV',0,0,0,'CS'),
              ('_MARKED','L',0,0,0,'CS'),('_PREDEFINEDID','B',0,16,0,'CS'),
              ('_CODE','NVC',0,2,0,'CI'),('_DESCRIPTION','NVC',0,8,0,'CI')]
    descs=[(10,('PARAMS',0,('Fields',*base.params_fixture.policy.DECLARATIONS),('Indexes',),('Recordlock','0'),('Files',30,31,34)))]
    for index,s in enumerate(r['catalogs']):
        ds=list(standard)
        for i,a in enumerate(s['attributes']):
            kind,n,p,case={'String':('NVC',32,0,'CI'),'Number':('N',9,2,'CS'),
                'Boolean':('L',0,0,'CS'),'Date':('DT',0,0,'CS'),'SingleCatalogRef':('B',16,0,'CS')}[a['type']]
            ds.append(('_FLD'+str(100+i),kind,0,n,p,case))
        head,blob,ind,page=(40,41,42,43) if index==0 else (46,47,48,49)
        descs.append((14 if index==0 else 20,('_Reference'+str(19+index),0,('Fields',*ds),('Indexes',),('Recordlock','0'),('Files',head,blob,ind))))
        stride=169 if index==0 else 74
        raw=b'\1'+bytes(stride-1)+bytes(stride)
        value.page(head)[:24]=b'\x1c\xfd'+bytes(14)+len(raw).to_bytes(8,'little')
        value.page(head)[24:28]=u32(page);value.page(page)[:len(raw)]=raw
    value.catalog((2,10,14,20))
    for block,desc in descs:
        raw=serialize(desc).encode();value.chain(tuple(range(block,block+(len(raw)+249)//250)),raw)
    return value


class LinkedCardPhysicalTests(unittest.TestCase):
    def observe(self):
        r,m=request();v=image(r)
        return r,m,v,subject.observe(v.read_at,v.size,r,m)

    def test_complete_raw_mixed_and_zero_attribute_graphs(self):
        r,m,v,out=self.observe()
        self.assertEqual(len(out['catalogs']),2)
        product,category=out['catalogs']
        self.assertEqual(product['physical']['layout'],'unresolved')
        self.assertIsNone(product['physical']['record_size']);self.assertIsNone(product['physical']['slots'])
        self.assertTrue(all(p['offset'] is None for p in product['physical']['placements']))
        self.assertEqual(product['physical']['logical_length'],338)
        self.assertEqual(category['physical']['record_size'],74)
        self.assertEqual(len(category['physical']['slots']),2)
        self.assertEqual(len(product['dbnames']['entries']),6)
        self.assertEqual(len(category['dbnames']['entries']),1)
        self.assertIn(m[1]['ref_type_uuid'].encode(),bytes.fromhex(product['config_hex']))
        self.assertNotIn('active_count',repr(out))
        self.assertEqual(subject.validate_observation(json.loads(json.dumps(out)),r,m),out)

    def test_no_primitive_projector_or_production_decoder_called(self):
        from yadinassi.storage import config_catalog_attributes,config_catalog_records
        r,m=request();v=image(r)
        with mock.patch.object(config_catalog_attributes,'project_catalog_attributes',side_effect=AssertionError('S/N projection')),mock.patch.object(config_catalog_records,'_decode',side_effect=AssertionError('value decoding')):
            subject.observe(v.read_at,v.size,r,m)

    def test_identity_binding_before_table_payload(self):
        r,m=request();v=image(r);bad=copy.deepcopy(r);bad['catalogs'][0]['name']='Cffffffff'
        with self.assertRaises(subject.c.CatalogError):subject._catalog(v.read_at,v.size,bad['catalogs'][0])
        self.assertFalse(any(offset==43*base.P for offset,_ in v.calls))
        mapping=copy.deepcopy(m);mapping[1]['ref_type_uuid']=r['catalogs'][1]['metadata_uuid']
        reader=mock.Mock()
        with self.assertRaises(ValueError):subject.observe(reader,v.size,r,mapping)
        reader.assert_not_called()

    def test_table_span_limit_before_payload(self):
        r,m=request();v=image(r);v.page(40)[16:24]=(8193).to_bytes(8,'little')
        with self.assertRaises(subject.c.CatalogError):subject.observe(v.read_at,v.size,r,m)
        self.assertFalse(any(offset==43*base.P for offset,_ in v.calls))

    def test_shared_byte_and_call_caps_before_forward(self):
        r,m=request()
        def fake(read,*args):read(0,8);read(0,8)
        for key,cap in (('MAX_READ_BYTES',15),('MAX_READ_CALLS',1)):
            reader=mock.Mock(return_value=b'0'*8)
            with mock.patch.object(subject,'_catalog',fake),mock.patch.object(subject,key,cap):
                with self.assertRaises((ValueError,subject.c.ResourceLimit)):subject.observe(reader,8,r,m)
            self.assertEqual(reader.call_count,1)

    def test_invalid_callback_ranges_never_forwarded(self):
        r,m=request()
        for off,n in ((True,1),(-1,1),(0,-1),(8,1),(0,1.0)):
            reader=mock.Mock()
            with mock.patch.object(subject,'_catalog',lambda read,*_:read(off,n)):
                with self.assertRaises(subject.c.InvalidStructure):subject.observe(reader,8,r,m)
            reader.assert_not_called()

    def test_unmeasured_widths_and_nullable_have_no_guessed_offsets(self):
        for declaration in (('_FLD8','DT',0,0,0,'CS'),('_FLD8','NVC',1,32,0,'CI'),('_FLD8','UNKNOWN',0,0,0,'CS')):
            stride,placements=subject._placements([('_VERSION','RV',0,0,0,'CS'),declaration])
            self.assertIsNone(stride);self.assertTrue(all(p['offset'] is None for p in placements))

    def test_known_slot_ceiling(self):
        r,m=request();v=image(r);v.page(46)[16:24]=(17*74).to_bytes(8,'little')
        with self.assertRaisesRegex(subject.c.UnsupportedLayout,'linked_slot_shape'):subject.observe(v.read_at,v.size,r,m)
        self.assertFalse(any(offset==49*base.P for offset,_ in v.calls))

    def test_hostile_report_replay(self):
        r,m,_,out=self.observe()
        for action in ('schema','mapping','config','descriptor','declaration','width','stride','slots','usage','tablealias','headeralias','raw','extra'):
            bad=copy.deepcopy(out);p=bad['catalogs'][0]['physical']
            if action=='schema':bad['schema']=True
            elif action=='mapping':bad['actual_mapping'][0]['ref_type_uuid']=m[1]['ref_type_uuid']
            elif action=='config':bad['catalogs'][0]['config_hex']='00'
            elif action=='descriptor':p['descriptor_hex']='00'
            elif action=='declaration':p['declarations'][0][0]='_OTHER'
            elif action=='width':p['placements'][0]['width']=17
            elif action=='stride':p['record_size']=169
            elif action=='slots':p['slots']=[]
            elif action=='usage':bad['source_reads']['bytes']+=1
            elif action=='tablealias':bad['catalogs'][1]['physical']['table']=p['table']
            elif action=='headeralias':bad['catalogs'][1]['physical']['data_header_page']=p['data_header_page']
            elif action=='raw':p['raw_hex']+='00'
            elif action=='extra':bad['extra']=1
            with self.subTest(action=action),self.assertRaises((ValueError,subject.c.CatalogError)):
                subject.validate_observation(bad,r,m)

if __name__=='__main__':unittest.main()
