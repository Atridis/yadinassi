"""Invented register transport only; no native kind/layout/key/ordering facts."""
import copy,json
from pathlib import Path
import sys,unittest
from unittest import mock
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'scripts/native_1c_db_oracle'),str(ROOT/'scripts')]
import information_register_physical as subject
import information_register_fixture as fixture
import test_document_read_physical as previous


def request(repeat=1):
 s,m,files=fixture.load(repeat);p=m['profile']
 return p,fixture.actual_mapping(s,p,{n:v for n,v in files.items() if n.endswith('.xml')})


def image(p,*,kind='InfoRg',table=True,missing=False,extra=(),**baseline_options):
 # Invented catalog-shaped opaque CONFIG is NOT register membership evidence.
 v=previous.image(dict(linked_schema=p['catalog_schema']),table=False,**baseline_options)
 u32=previous.linked.base.u32;P=previous.linked.base.P
 triples=[]
 if not missing:triples.append((p['metadata_uuid'],kind,19))
 cat=p['catalog_schema']['catalogs'][1];triples.append((cat['metadata_uuid'],'Reference',20))
 triples.extend((p['ids'][n],'Fld',100+i) for i,n in enumerate(p['columns']));triples.extend(extra)
 raw=('\ufeff{0,{'+str(len(triples))+','+','.join('{'+uid+',"'+k+'",'+str(n)+'}' for uid,k,n in triples)+'}}').encode()
 packed=b'\x01'+len(raw).to_bytes(2,'little')+(65535-len(raw)).to_bytes(2,'little')+raw
 v.page(32)[301+276:301+287]=bytes.fromhex('1'+str(len(packed)).zfill(20)+'0');v.page(32)[301+287:301+295]=u32(1)+u32(len(packed))
 chunks=[packed[i:i+250] for i in range(0,len(packed),250)]
 v.page(31)[16:24]=((len(chunks)+1)*256).to_bytes(8,'little');v.page(33)[:]=bytes(P)
 for i,chunk in enumerate(chunks,1):
  offset=i*256;v.page(33)[offset:offset+6]=u32(i+1 if i<len(chunks) else 0)+len(chunk).to_bytes(2,'little')
  v.page(33)[offset+6:offset+6+len(chunk)]=chunk
 if table:
  reader=subject.c.CatalogReader(v.read_at,v.size);catalog=reader.read_catalog()
  old=next(t for t in catalog.tables if t.name=='_Reference19')
  raw=old.raw_descriptor.replace(b'_Reference19',b'_InfoRg19')
  v.chain(tuple(range(14,14+(len(raw)+249)//250)),raw)
 v.calls.clear();return v


class InformationRegisterPhysicalTests(unittest.TestCase):
 def test_complete_raw_candidates_and_both_source_orders(self):
  for repeat in (1,2):
   p,m=request(repeat);v=image(p);out=subject.observe(v.read_at,v.size,p,m)
   self.assertEqual(len(out['config']['files']),5);self.assertEqual(out['config']['register_membership'],'unresolved')
   self.assertNotIn('document_membership',out['config']);self.assertEqual(len(out['objects']),2)
   self.assertEqual([o['physical']['candidate'] for o in out['objects']],['_InfoRg19','_Reference20'])
   for obj in out['objects']:
    q=obj['physical'];self.assertEqual(q['status'],'captured');self.assertEqual(q['layout'],'unresolved')
    self.assertEqual(len(bytes.fromhex(q['raw_hex'])),q['logical_length'])
    for key in ('record_size','slots','offsets'):self.assertIsNone(q[key])
   self.assertEqual([e['uuid'] for e in out['dbnames']['groups'][0]['entries']],
                    [p['metadata_uuid'],*[f['metadata_uuid'] for f in m['fields']]])
   self.assertEqual(subject.validate_observation(json.loads(json.dumps(out)),p,m),out)
 def test_unknown_kind_missing_uuid_or_named_table_retains_evidence(self):
  for kw,reason in ((dict(kind='Other'),'dbnames_kind'),(dict(table=False),'table_missing'),(dict(missing=True),'dbnames_missing')):
   p,m=request();v=image(p,**kw);out=subject.observe(v.read_at,v.size,p,m)
   self.assertEqual(out['objects'][0]['physical']['reason'],reason)
   self.assertEqual(len(out['config']['files']),5);self.assertEqual(out['objects'][1]['physical']['status'],'captured')
 def test_all_roles_retained_and_ambiguous_expected_kind_unresolved(self):
  p,m=request();uid=p['metadata_uuid']
  v=image(p,extra=((uid,'Other',71),(p['ids']['Product'],'Other',72)));out=subject.observe(v.read_at,v.size,p,m)
  self.assertEqual([(e['kind'],e['id']) for e in out['dbnames']['groups'][0]['entries'] if e['uuid']==uid],[('InfoRg',19),('Other',71)])
  self.assertEqual(out['objects'][0]['physical']['candidate'],'_InfoRg19')
  v=image(p,extra=((uid,'InfoRg',71),));out=subject.observe(v.read_at,v.size,p,m)
  self.assertEqual(out['objects'][0]['physical']['reason'],'dbnames_ambiguous')
  self.assertIsNone(out['objects'][0]['physical']['candidate']);self.assertEqual(len(out['config']['files']),5)
 def test_global_alias_and_bounded_owned_entries_fail_closed(self):
  p,m=request();uid=p['metadata_uuid']
  for extra,error in ((((uid,'Reference',20),),subject.c.UnsupportedSharing),
      (tuple((uid,'Other',400+i) for i in range(16)),subject.c.ResourceLimit)):
   v=image(p,extra=extra)
   with self.assertRaises(error):subject.observe(v.read_at,v.size,p,m)
  v=image(p)
  with mock.patch.object(subject,'MAX_OWNED_ENTRIES',1),self.assertRaises(subject.c.ResourceLimit):subject.observe(v.read_at,v.size,p,m)
 def test_cross_reader_ownership_precedes_both_target_payloads(self):
  for header,target in ((40,32),(40,33),(40,49),(46,43)):
   p,m=request();v=image(p);v.page(header)[24:28]=previous.linked.base.u32(target)
   with self.subTest(header=header,target=target),self.assertRaises(subject.c.UnsupportedSharing):subject.observe(v.read_at,v.size,p,m)
   if (header,target)==(46,43):self.assertFalse(any(offset==43*previous.linked.base.P for offset,_ in v.calls))
  p,m=request();v=image(p);reader=subject.c.CatalogReader(v.read_at,v.size);catalog=reader.read_catalog()
  t=next(t for t in catalog.tables if t.name=='CONFIG');data=reader._open_table_data(t)
  v.page(40)[24:28]=previous.linked.base.u32(data._pages[0]);v.calls.clear()
  with self.assertRaises(subject.c.UnsupportedSharing):subject.observe(v.read_at,v.size,p,m)
 def test_mapping_and_profile_rejected_before_any_read(self):
  for mutate in (lambda p,m:m['register']['generated_types']['Record'].update(type_uuid=p['ids']['Manager.TypeId']),
       lambda p,m:m['fields'][0].update(kind='Dimension'),lambda p,m:m['fields'].reverse(),
       lambda p,m:m['catalog'].update(ref_type_uuid=p['ids']['Record.TypeId']),lambda p,m:p.update(write_mode='RecorderSubordinate')):
   p,m=request();mutate(p,m);calls=[]
   with self.assertRaises(ValueError):subject.observe(lambda *a:calls.append(a),4096,p,m)
   self.assertEqual(calls,[])
 def test_limits_before_callback_and_raw_payload(self):
  p,m=request();v=image(p)
  with mock.patch.object(subject,'MAX_READ_CALLS',0),self.assertRaises(subject.c.ResourceLimit):subject.observe(v.read_at,v.size,p,m)
  self.assertEqual(v.calls,[])
  v=image(p);v.page(40)[16:24]=(8193).to_bytes(8,'little')
  for i in range(3):v.page(40)[24+i*4:28+i*4]=previous.linked.base.u32(43+i)
  with self.assertRaises(subject.c.ResourceLimit):subject.observe(v.read_at,v.size,p,m)
  self.assertFalse(any(offset==43*previous.linked.base.P for offset,_ in v.calls))
 def test_baseline_verified_per_run_and_unexpected_profile_rejected(self):
  p,m=request()
  for kwargs in (dict(baseline_name='Other'),dict(baseline_code='3'),dict(baseline_missing=True),dict(extra_ref=True)):
   v=image(p,**kwargs)
   with self.assertRaises((ValueError,subject.c.CatalogError)):subject.observe(v.read_at,v.size,p,m)
  uid='66666666-6666-4666-8666-666666666666';v=image(p,baseline_uuid=uid)
  out=subject.observe(v.read_at,v.size,p,m);self.assertEqual(out['config']['baseline']['metadata_uuid'],uid)
 def test_replay_rejects_inferred_layout_and_unbound_evidence(self):
  p,m=request();v=image(p);out=subject.observe(v.read_at,v.size,p,m)
  for mutate in (lambda x:x['config'].update(register_membership='verified'),
      lambda x:x['config']['files'][0].update(sha256='0'*64),lambda x:x['objects'][0]['physical'].update(slots=[]),
      lambda x:x['objects'][0]['physical'].update(candidate='_Reference19'),lambda x:x['source_reads'].update(bytes=1),
      lambda x:x['dbnames']['groups'][0]['entries'].reverse(),
      lambda x:x['dbnames']['groups'][0]['entries'][1].update(ordinal=x['dbnames']['groups'][0]['entries'][0]['ordinal'])):
   bad=copy.deepcopy(out);mutate(bad)
   with self.assertRaises(ValueError):subject.validate_observation(bad,p,m)
if __name__=='__main__':unittest.main()
