"""Native owned Items bytes through synthetic transport; not actual .1CD parity."""
from dataclasses import replace
from decimal import Decimal
import hashlib,json,unittest
from pathlib import Path
from types import SimpleNamespace
import test_document_records as previous
f=previous.f;r=previous.r;c=previous.c;P=previous.P;u32=previous.u32;Source=previous.Source
b=__import__(f.PACKAGE+'.config_document_lines_binding',fromlist=['*'])
d=__import__(f.PACKAGE+'.config_document_lines_records',fromlist=['*'])
PATH=Path(__file__).with_name('fixtures')/'document_lines_records.json'
SHA='8065f69a4c424f480843011b7c669ca6a3ca2d9d142ca6547243aa451c326598'
def cases():
 raw=PATH.read_bytes()
 if hashlib.sha256(raw).hexdigest()!=SHA:raise ValueError('fixture hash')
 return json.loads(raw)['cases']
def inputs(case):
 attrs=tuple(f.attrs.CatalogAttribute(a['metadata_uuid'],a['name'],a['type_token'],tuple(a['qualifiers']),reference_type_uuid=a['reference_type_uuid'],reference_catalog_uuid=a['reference_catalog_uuid']) for a in case['attributes'])
 # Explicit synthetic selected subset reindex; original ordinals stay in fixture.
 index=f.index(tuple((e['uuid'],e['kind'],e['id']) for e in case['dbnames']))
 doc=case['document'];section=case['section']
 return previous.m.DocumentIdentityPrefix(doc['metadata_uuid'],doc['name']),section['metadata_uuid'],section['name'],f.attrs.CatalogAttributes(attrs),index
def compile_case(case):return b.compile_document_lines_binding(*inputs(case),budget=c._Budget(c.CatalogLimits()))
def source(case,raw=None,declarations=None):
 shape=compile_case(case);data=bytes.fromhex(case['physical']['raw_hex']) if raw is None else raw
 v=Source(page_count=50);v.catalog((2,6,10,14));fields=shape.declarations if declarations is None else declarations
 for block,name,decl,files in ((2,'CONFIG',(),(4,5,0)),(6,'PARAMS',(),(6,7,0)),(10,'_Document'+str(shape.document_id),(),(18,19,0)),(14,shape.table_name,fields,(20,21,0))):
  text=r.serialize((name,0,('Fields',*decl),('Indexes',),('Recordlock','0'),('Files',*files))).encode();v.chain(tuple(range(block,block+(len(text)+249)//250)),text)
 for page in (4,5,6,7,18,19):v.page(page)[:24]=b'\x1c\xfd'+bytes(22)
 v.page(20)[:24]=b'\x1c\xfd'+bytes(14)+len(data).to_bytes(8,'little')
 for i in range((len(data)+P-1)//P):v.page(20)[24+i*4:28+i*4]=u32(22+i);chunk=data[i*P:(i+1)*P];v.page(22+i)[:len(chunk)]=chunk
 return v,shape
def prepare(v,shape):
 reader,catalog,graph=r.prepared(v)
 # Synthetic empty predecessor table exercises shared lifetime. Exact native
 # Document decode and joins are independently exercised by coordinator replay.
 doc=replace(previous.compile_case(previous.cases()[1]),metadata_uuid=shape.owner_metadata_uuid,table_name='_Document'+str(shape.document_id))
 with graph.stage('records',binding=doc) as h:h._open_table_data(h.table)
 return reader,catalog,graph
def read(v,shape,**kw):
 reader,catalog,graph=prepare(v,shape)
 with graph.stage('document_lines',binding=shape) as h:return d.read_bound_document_lines_records(reader,catalog,shape,handle=h,**kw)
class DocumentLinesRecordsTests(unittest.TestCase):
 def test_all_eight_native_captures_order_owner_join_and_values(self):
  for case in cases():
   v,shape=source(case);self.assertEqual(shape.record_size,121);self.assertEqual(shape.declarations,tuple(map(tuple,case['physical']['declarations'])))
   result=read(v,shape);self.assertEqual(len(result.rows),4)
   # Native Document UUID/number standard fields have their independently
   # measured 155-byte layout; use them only to assert the owner raw16 join.
   doc=bytes.fromhex(case['document_raw_hex']);owners={}
   for off in range(155,len(doc),155):
    raw=doc[off:off+155];length=int.from_bytes(raw[41:43],'little');owners[raw[17:33]]=raw[43:43+2*length].decode('utf-16-le')
   groups={n:[] for n in owners.values()}
   for row in result.rows:
    vals={a.name:row.fields[3+i].value for i,a in enumerate(shape.attributes)}
    groups[owners[row.fields[0].value]].append((int(row.fields[2].value),vals))
   self.assertEqual(groups['30'],[])
   self.assertEqual([(n,x['Note']) for n,x in sorted(groups['10'])],[(1,'single')])
   ordered=sorted(groups['20']);self.assertEqual([n for n,_ in ordered],[1,2,3])
   self.assertEqual([x['Note'] for _,x in ordered],['first','second','last'] if case['state']=='initial' else ['last','replacement','first'])
   for _,vals in ordered:self.assertEqual(vals['Quantity']*vals['Price'],vals['Amount']);self.assertEqual(len(vals['Product']),16)
 def test_zero_length_and_reserved_only(self):
  case=cases()[0];raw=bytes.fromhex(case['physical']['raw_hex'])
  for data in (b'',raw[:121]):
   v,shape=source(case,data);self.assertEqual(read(v,shape).rows,())
 def test_liveness_bad_owner_line_key_and_truncation(self):
  case=cases()[0];raw=bytes.fromhex(case['physical']['raw_hex'])
  changes=[(0,b'\0'),(1,b'\1'),(121,b'\1'),(122,bytes(16)),(121+21,b'\x10\x00\x00'),(121+21,b'\x10\x00\x02'),(3*121+17,raw[2*121+17:2*121+21]),(3*121+21,raw[2*121+21:2*121+24])]
  for offset,value in changes:
   data=bytearray(raw);data[offset:offset+len(value)]=value;v,shape=source(case,bytes(data))
   with self.subTest(offset=offset,value=value),self.assertRaises(c.CatalogError):read(v,shape)
  v,shape=source(case,raw[:-1])
  with self.assertRaises(c.InvalidStructure):read(v,shape)
 def test_typed_binding_declarations_and_limits(self):
  case=cases()[0];v,shape=source(case)
  for bad in (replace(shape,record_size=120),replace(shape,document_id=True),replace(shape,line_number_id=68),replace(shape,format_item=False),replace(shape,placements=shape.placements[::-1]),replace(shape,profile_identifier='other')):
   v,_=source(case)
   with self.assertRaises((ValueError,c.CatalogError)):read(v,bad)
  fields=list(shape.declarations);fields[1]=('_KEYFIELD','B',1,4,0,'CS');v,_=source(case,declarations=tuple(fields))
  with self.assertRaises(c.UnsupportedLayout):read(v,shape)
  v,shape=source(case)
  with self.assertRaises(c.ResourceLimit):read(v,shape,limits=r.legacy.RecordLimits(max_slots=4))
  args=inputs(case)
  with self.assertRaises(b.CatalogBindingError):b.compile_document_lines_binding(*args,budget=c._Budget(c.CatalogLimits()),limits=b.CatalogBindingLimits(max_record_bytes=120))
 def test_dbnames_roles_alias_and_missing_fail_closed(self):
  args=list(inputs(cases()[0]));index=args[-1]
  for change in ('missing','kind','alias'):
   entries=list(index.entries)
   if change=='missing':entries=entries[:-1]
   elif change=='kind':entries[-1]=replace(entries[-1],kind='Other')
   else:entries[-1]=replace(entries[-1],id=entries[-2].id)
   args[-1]=replace(index,entries=tuple(entries),declared_count=len(entries))
   with self.assertRaises(b.CatalogBindingError):b.compile_document_lines_binding(*args,budget=c._Budget(c.CatalogLimits()))
 def test_graph_fourth_stage_owner_binding_and_poison(self):
  case=cases()[0];v,shape=source(case);reader,catalog,graph=r.prepared(v)
  with self.assertRaises(ValueError):
   with graph.stage('records',binding=shape):pass
  v,shape=source(case);reader,catalog,graph=prepare(v,shape)
  bad=replace(shape,owner_metadata_uuid=shape.metadata_uuid)
  with self.assertRaises(ValueError):
   with graph.stage('document_lines',binding=bad):pass
  v,shape=source(case);reader,catalog,graph=prepare(v,shape)
  with self.assertRaises(ValueError):
   with graph.stage('document_lines',binding=shape) as h:
    with self.assertRaises(c.UnsupportedLayout):d.read_bound_document_lines_records(reader,catalog,replace(shape,record_size=120),handle=h)
    self.assertTrue(graph.failed);h._check()
 def test_cross_document_data_page_alias_refused(self):
  case=cases()[0];v,shape=source(case)
  v.page(18)[16:24]=(1).to_bytes(8,'little');v.page(18)[24:28]=u32(22)
  with self.assertRaises(c.UnsupportedSharing):read(v,shape)
if __name__=='__main__':unittest.main()
