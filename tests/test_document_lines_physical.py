"""Invented Items transport only: no native layout/join/order admission."""
import copy,json,hashlib
from pathlib import Path
import sys,unittest
from unittest import mock
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'scripts/native_1c_db_oracle'),str(ROOT/'scripts')]
import document_lines_physical as subject
import document_lines_fixture as fixture
import test_document_read_physical as previous
from test_filedb_records import serialize


def request(repeat=1):
 s,manifest,files=fixture.load(repeat);p=manifest['profile']
 return p,fixture.actual_mapping(s,p,{n:v for n,v in files.items() if n.endswith('.xml')})


def image(p,*,kind='VT',table=True,missing=False):
 v=previous.image(p['base']);P=previous.linked.base.P;u32=previous.linked.base.u32
 specs=p['base']['linked_schema']['catalogs'];triples=[]
 for i,s in enumerate(specs):
  triples.append('{'+s['metadata_uuid']+',"'+('Document' if i==0 else 'Reference')+'",'+str(19+i)+'}')
  triples.extend('{'+a['metadata_uuid']+',"Fld",'+str(100+j)+'}' for j,a in enumerate(s['attributes']))
 if not missing:triples.append('{'+p['ids']['section']+',"'+kind+'",70}')
 triples.extend('{'+p['ids'][name]+',"Fld",'+str(200+i)+'}' for i,name in enumerate(p['columns']))
 raw=('\ufeff{0,{'+str(len(triples))+','+','.join(triples)+'}}').encode()
 packed=b'\x01'+len(raw).to_bytes(2,'little')+(65535-len(raw)).to_bytes(2,'little')+raw
 v.page(32)[301+276:301+287]=bytes.fromhex('1'+str(len(packed)).zfill(20)+'0');v.page(32)[301+287:301+295]=u32(1)+u32(len(packed))
 chunks=[packed[i:i+250] for i in range(0,len(packed),250)];v.page(31)[16:24]=((len(chunks)+1)*256).to_bytes(8,'little');v.page(33)[:]=bytes(P)
 for i,chunk in enumerate(chunks,1):
  offset=i*256;v.page(33)[offset:offset+6]=u32(i+1 if i<len(chunks) else 0)+len(chunk).to_bytes(2,'little');v.page(33)[offset+6:offset+6+len(chunk)]=chunk
 if table:
  text=serialize(('_Document19_VT70',0,('Fields',('_OWNER','B',0,16,0,'CS'),('_ORDER','N',0,5,0,'CS')),('Indexes',),('Recordlock','0'),('Files',52,53,54))).encode()
  v.chain(tuple(range(24,24+(len(text)+249)//250)),text);v.catalog((2,10,14,20,24))
  data=b'invented opaque section data';v.page(52)[:24]=b'\x1c\xfd'+bytes(14)+len(data).to_bytes(8,'little');v.page(52)[24:28]=u32(55);v.page(55)[:len(data)]=data
 v.calls.clear();return v

class DocumentLinesPhysicalTests(unittest.TestCase):
 def test_complete_three_raw_candidates_and_both_column_orders(self):
  for repeat in (1,2):
   p,m=request(repeat);v=image(p);out=subject.observe(v.read_at,v.size,p,m)
   self.assertEqual(len(out['config']['files']),5);self.assertEqual(len(out['objects']),3)
   q=out['objects'][2]['physical'];self.assertEqual(q['candidate'],'_Document19_VT70');self.assertEqual(bytes.fromhex(q['raw_hex']),b'invented opaque section data')
   self.assertEqual(q['layout'],'unresolved');self.assertIsNone(q['record_size']);self.assertIsNone(q['slots']);self.assertIsNone(q['offsets'])
   self.assertEqual([e['uuid'] for e in out['dbnames']['groups'][2]['entries']],[p['ids']['section'],*[p['ids'][n] for n in p['columns']]])
   self.assertEqual(subject.validate_observation(json.loads(json.dumps(out)),p,m),out)
 def test_unresolved_kind_missing_uuid_and_table_keep_evidence(self):
  for kw,reason in ((dict(kind='Other'),'dbnames_kind'),(dict(table=False),'table_missing'),(dict(missing=True),'dbnames_missing')):
   p,m=request();v=image(p,**kw);out=subject.observe(v.read_at,v.size,p,m)
   self.assertEqual(out['objects'][2]['physical']['reason'],reason);self.assertEqual(len(out['config']['files']),5)
   self.assertTrue(all(o['physical']['status']=='captured' for o in out['objects'][:2]))
 def test_cross_reader_aliases_before_any_target_payload(self):
  for header,target in ((52,32),(52,33),(52,43),(40,55)):
   p,m=request();v=image(p);v.page(header)[24:28]=previous.linked.base.u32(target)
   with self.subTest(header=header,target=target),self.assertRaises(subject.c.UnsupportedSharing):subject.observe(v.read_at,v.size,p,m)
   self.assertFalse(any(offset==55*previous.linked.base.P for offset,_ in v.calls))
 def test_caps_and_mapping_rejection_before_source_access(self):
  p,m=request();v=image(p);m['section']['row_type_uuid']=m['section']['type_uuid']
  with self.assertRaises(ValueError):subject.observe(v.read_at,v.size,p,m)
  self.assertEqual(v.calls,[])
  p,m=request();v=image(p)
  with mock.patch.object(subject,'MAX_READ_CALLS',0),self.assertRaises(subject.c.ResourceLimit):subject.observe(v.read_at,v.size,p,m)
  self.assertEqual(v.calls,[])
 def test_section_bound_and_hostile_replay(self):
  p,m=request();v=image(p);v.page(52)[16:24]=(8193).to_bytes(8,'little')
  for i in range(3):v.page(52)[24+i*4:28+i*4]=previous.linked.base.u32(55+i)
  with self.assertRaises(subject.c.ResourceLimit):subject.observe(v.read_at,v.size,p,m)
  self.assertFalse(any(offset==55*previous.linked.base.P for offset,_ in v.calls))
  v=image(p);out=subject.observe(v.read_at,v.size,p,m)
  for mutate in (lambda x:x['objects'][2]['physical'].update(candidate='_Document20_VT70'),lambda x:x['objects'][2]['physical'].update(slots=[]),lambda x:x['source_reads'].update(bytes=1),lambda x:x['dbnames']['groups'][2]['entries'][0].update(kind='Fld')):
   bad=copy.deepcopy(out);mutate(bad)
   with self.assertRaises(ValueError):subject.validate_observation(bad,p,m)
if __name__=='__main__':unittest.main()
