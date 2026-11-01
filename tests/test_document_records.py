"""Hash-pinned native Document bytes through invented transport, not .1CD parity."""
from dataclasses import replace
from datetime import datetime
from decimal import Decimal
import hashlib,json,unittest
from pathlib import Path
from types import SimpleNamespace
import test_config_catalog_binding as f
import test_config_catalog_records as r
from test_filedb_catalog import Source,P,u32
b=__import__(f.PACKAGE+'.config_document_binding',fromlist=['*'])
d=__import__(f.PACKAGE+'.config_document_records',fromlist=['*'])
m=__import__(f.PACKAGE+'.config_document_metadata',fromlist=['*'])
c=f.catalog
PATH=Path(__file__).with_name('fixtures')/'document_records.json'
SHA='10dbf48bfdbc415bfe1f0ba68bbbe290f44a775c366b8eb654cf7189f9d4d439'
def cases():
 raw=PATH.read_bytes()
 if hashlib.sha256(raw).hexdigest()!=SHA:raise ValueError('fixture hash')
 return json.loads(raw)['cases']
def inputs(case):
 logical=case['logical'];attrs=[]
 for a in logical['attributes']:
  t={'String':'S','Number':'N','Boolean':'B','Date':'D','SingleCatalogRef':'#'}[a['type']]
  q=(32,1) if t=='S' else (9,2,0) if t=='N' else ()
  kw={} if t!='#' else dict(reference_type_uuid=a['target_requested_ref_type_uuid'],reference_catalog_uuid=a['target_metadata_uuid'])
  attrs.append(f.attrs.CatalogAttribute(a['metadata_uuid'],a['name'],t,q,**kw))
 return m.DocumentIdentityPrefix(logical['metadata_uuid'],logical['name'],1,8,0),f.attrs.CatalogAttributes(tuple(attrs)),f.index(tuple((e['uuid'],e['kind'],e['id']) for e in case['dbnames']['entries']))
def compile_case(case):return b.compile_document_binding(*inputs(case),budget=c._Budget(c.CatalogLimits()))
def source(case,raw=None,declarations=None):
 shape=compile_case(case);data=bytes.fromhex(case['physical']['raw_hex']) if raw is None else raw
 v=Source(page_count=40);v.catalog((2,6,10));fields=shape.declarations if declarations is None else declarations
 for block,name,decl,files in ((2,'CONFIG',(),(4,5,0)),(6,'PARAMS',(),(6,7,0)),(10,shape.table_name,fields,(20,21,0))):
  text=r.serialize((name,0,('Fields',*decl),('Indexes',),('Recordlock','0'),('Files',*files))).encode();v.chain(tuple(range(block,block+(len(text)+249)//250)),text)
 for page in (4,5,6,7):v.page(page)[:24]=b'\x1c\xfd'+bytes(22)
 v.page(20)[:24]=b'\x1c\xfd'+bytes(14)+len(data).to_bytes(8,'little')
 for i in range((len(data)+P-1)//P):v.page(20)[24+i*4:28+i*4]=u32(22+i);chunk=data[i*P:(i+1)*P];v.page(22+i)[:len(chunk)]=chunk
 return v,shape
def read(v,shape,**kwargs):
 reader,catalog,graph=r.prepared(v)
 with graph.stage('records',binding=shape) as handle:return d.read_bound_document_records(reader,catalog,shape,handle=handle,**kwargs)
class DocumentRecordsTests(unittest.TestCase):
 def test_native_both_orders_empty_filled(self):
  for case in cases():
   v,shape=source(case);self.assertEqual(shape.record_size,155);self.assertEqual(shape.declarations,tuple(map(tuple,case['physical']['declarations'])))
   result=read(v,shape);self.assertEqual(len(result.rows),0 if case['state']=='empty' else 3)
   if not result.rows:continue
   rows={row.fields[4].value:row for row in result.rows};self.assertEqual(set(rows),{'10','20','30'})
   self.assertEqual(rows['30'].fields[3].value,datetime(2024,2,29,12,34,56));self.assertTrue(rows['30'].fields[5].value)
   self.assertFalse(rows['10'].fields[5].value)
   vals={a.type_token:rows['30'].fields[6+i].value for i,a in enumerate(shape.attributes)}
   self.assertEqual(vals['S'],'third');self.assertEqual(vals['N'],Decimal('12.50'));self.assertTrue(vals['B']);self.assertEqual(vals['D'],datetime(2024,2,29,12,34,56));self.assertEqual(vals['#'],rows['30'].fields[0].value)
 def test_free_and_logical_mark_refused(self):
  case=cases()[1];raw=bytes.fromhex(case['physical']['raw_hex'])
  for offset,value in ((0,0),(1,1),(155,1),(155+33,1)):
   data=bytearray(raw);data[offset]=value;v,shape=source(case,bytes(data))
   with self.assertRaises(c.CatalogError):read(v,shape)
 def test_bad_field_encodings_and_truncation(self):
  case=cases()[1];raw=bytes.fromhex(case['physical']['raw_hex'])
  for offset,value in ((155+34,0xfa),(155+59,2),(155+41,9)):
   data=bytearray(raw);data[offset]=value;v,shape=source(case,bytes(data))
   with self.assertRaises(c.CatalogError):read(v,shape)
  v,shape=source(case,raw[:-1])
  with self.assertRaises(c.InvalidStructure):read(v,shape)
 def test_forged_binding_and_declarations(self):
  case=cases()[1];v,shape=source(case)
  for bad in (replace(shape,record_size=154),replace(shape,number_length=7),replace(shape,format_item=False),replace(shape,placements=shape.placements[::-1]),replace(shape,profile_identifier='other')):
   v,_=source(case)
   with self.assertRaises((c.CatalogError,ValueError)):read(v,bad)
  fields=list(shape.declarations);fields[5]=('_POSTED','L',1,0,0,'CS');v,_=source(case,declarations=tuple(fields))
  with self.assertRaises(c.UnsupportedLayout):read(v,shape)
 def test_exact_profile_and_dbnames_rejected(self):
  identity,attrs,index=inputs(cases()[1])
  for bad in (replace(identity,number_type=0),replace(identity,number_length=9),replace(identity,number_periodicity=1)):
   with self.assertRaises(b.CatalogBindingError):b.compile_document_binding(bad,attrs,index,budget=c._Budget(c.CatalogLimits()))
  entries=list(index.entries);entries[0]=replace(entries[0],kind='Reference');bad=replace(index,entries=tuple(entries))
  with self.assertRaises(b.CatalogBindingError):b.compile_document_binding(identity,attrs,bad,budget=c._Budget(c.CatalogLimits()))
 def test_graph_rejects_structural_duck_and_limits(self):
  v,shape=source(cases()[1]);reader,catalog,graph=r.prepared(v)
  with self.assertRaises(ValueError):
   with graph.stage('records',binding=SimpleNamespace(table_name=shape.table_name,profile_identifier=b.PROFILE_IDENTIFIER)):pass
  v,shape=source(cases()[1])
  with self.assertRaises(c.ResourceLimit):read(v,shape,limits=r.legacy.RecordLimits(max_slots=3))
 def test_lowered_limits_and_forged_typed_fields(self):
  identity,attrs,index=inputs(cases()[1])
  shape=b.compile_document_binding(identity,attrs,index,budget=c._Budget(c.CatalogLimits()),limits=b.CatalogBindingLimits(max_record_bytes=155))
  self.assertEqual(shape.record_size,155)
  with self.assertRaises(b.CatalogBindingError):b.compile_document_binding(identity,attrs,index,budget=c._Budget(c.CatalogLimits()),limits=b.CatalogBindingLimits(max_record_bytes=154))
  v,shape=source(cases()[1]);places=list(shape.placements);places[1]=replace(places[1],offset=True)
  with self.assertRaises(c.UnsupportedLayout):read(v,replace(shape,placements=tuple(places)))
  v,shape=source(cases()[1]);limits=r.legacy.RecordLimits();object.__setattr__(limits,'max_slots',True)
  with self.assertRaises(ValueError):read(v,shape,limits=limits)
 def test_data_integrity_failure_poisons_graph(self):
  case=cases()[1];raw=bytearray.fromhex(case['physical']['raw_hex']);raw[155]=1
  v,shape=source(case,bytes(raw));reader,catalog,graph=r.prepared(v)
  with self.assertRaises(ValueError):
   with graph.stage('records',binding=shape) as handle:
    with self.assertRaises(c.UnsupportedLayout):d.read_bound_document_records(reader,catalog,shape,handle=handle)
    self.assertTrue(graph.failed)
    with self.assertRaises(ValueError):handle._check()
if __name__=='__main__':unittest.main()
