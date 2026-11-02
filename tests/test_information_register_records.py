"""Owned native InfoRg bytes in synthetic transport, not actual .1CD parity."""
from dataclasses import replace
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
import hashlib,json,unittest
import test_document_records as previous
f=previous.f;r=previous.r;c=previous.c;P=previous.P;u32=previous.u32;Source=previous.Source
b=__import__(f.PACKAGE+'.config_information_register_binding',fromlist=['*'])
d=__import__(f.PACKAGE+'.config_information_register_records',fromlist=['*'])
m=__import__(f.PACKAGE+'.config_information_register_metadata',fromlist=['*'])
PATH=Path(__file__).with_name('fixtures')/'information_register_records.json'
SHA='81c4089b7cd94e14337c147c36731d4e2fc4fc7b09531d2be884fad2bb11d794'
def cases():
 raw=PATH.read_bytes()
 if hashlib.sha256(raw).hexdigest()!=SHA:raise ValueError('fixture hash')
 return json.loads(raw)['cases']
def inputs(case):
 groups=[]
 for role in ('Dimension','Resource','Attribute'):
  attrs=tuple(f.attrs.CatalogAttribute(a['metadata_uuid'],a['name'],a['type_token'],tuple(a['qualifiers']),reference_type_uuid=a['reference_type_uuid'],reference_catalog_uuid=a['reference_catalog_uuid']) for a in case['fields'] if a['kind']==role)
  groups.append(f.attrs.CatalogAttributes(attrs))
 # Synthetic transport carries only selected owned entries; reindex explicitly.
 index=f.index(tuple((e['uuid'],e['kind'],e['id']) for e in case['dbnames']))
 return (m.InformationRegisterIdentityPrefix(**case['identity']),*groups,index)
def compile_case(case,**kw):return b.compile_information_register_binding(*inputs(case),budget=c._Budget(c.CatalogLimits()),**kw)
def source(case,raw=None,declarations=None):
 shape=compile_case(case);data=bytes.fromhex(case['physical']['raw_hex']) if raw is None else raw
 v=Source(page_count=40);v.catalog((2,6,10));fields=shape.declarations if declarations is None else declarations
 for block,name,decl,files in ((2,'CONFIG',(),(4,5,0)),(6,'PARAMS',(),(6,7,0)),(10,shape.table_name,fields,(20,21,0))):
  text=r.serialize((name,0,('Fields',*decl),('Indexes',),('Recordlock','0'),('Files',*files))).encode();v.chain(tuple(range(block,block+(len(text)+249)//250)),text)
 for page in (4,5,6,7):v.page(page)[:24]=b'\x1c\xfd'+bytes(22)
 v.page(20)[:24]=b'\x1c\xfd'+bytes(14)+len(data).to_bytes(8,'little')
 for i in range((len(data)+P-1)//P):v.page(20)[24+i*4:28+i*4]=u32(22+i);chunk=data[i*P:(i+1)*P];v.page(22+i)[:len(chunk)]=chunk
 return v,shape
def read(v,shape,**kw):
 reader,catalog,graph=r.prepared(v)
 with graph.stage('records',binding=shape) as h:return d.read_bound_information_register_records(reader,catalog,shape,handle=h,**kw)
class InformationRegisterRecordsTests(unittest.TestCase):
 def test_eight_native_captures_both_role_orders_and_values(self):
  for case in cases():
   v,shape=source(case);self.assertEqual(shape.record_size,101);self.assertEqual(shape.declarations,tuple(map(tuple,case['physical']['declarations'])))
   result=read(v,shape);self.assertEqual(len(result.rows),0 if case['state']=='empty' else 3)
   if not result.rows:continue
   # Target catalog standard raw16/code layout was independently measured by
   # earlier catalog evidence. Compare exact raw reference, not UUID byte guesses.
   cat=bytes.fromhex(case['catalog_raw_hex']);codes={}
   for off in range(74,len(cat),74):
    row=cat[off:off+74];n=int.from_bytes(row[50:52],'little');codes[row[17:33]]=row[52:52+2*n].decode('utf-16-le')
   values=[]
   for row in result.rows:
    vals={a.name:row.fields[i].value for i,a in enumerate(shape.attributes)}
    self.assertIn(vals['Product'],codes)
    values.append((codes[vals['Product']],int(vals['Variant']),vals['Price'],vals['Available'],vals['ValidUntil'],vals['Note']))
   self.assertEqual(sorted(values),[('10',1,Decimal('12.50'),True,datetime(2024,2,29,12,34,56),'first'),('10',2,Decimal(0),False,datetime(1,1,1),''),('20',1,Decimal('-7.25'),True,datetime(2001,1,1,0,0,1),'second')])
 def test_reserved_only_is_structural_empty(self):
  case=cases()[2];raw=bytes.fromhex(case['physical']['raw_hex']);v,shape=source(case,raw[:101]);self.assertEqual(read(v,shape).rows,())
 def test_free_head_marker_truncation_and_duplicate_dimension_refused(self):
  case=cases()[2];raw=bytes.fromhex(case['physical']['raw_hex'])
  for offset,value in ((0,b'\0'),(1,b'\1'),(101,b'\1'),(202+1,raw[102:123])):
   data=bytearray(raw);data[offset:offset+len(value)]=value;v,shape=source(case,bytes(data))
   with self.subTest(offset=offset),self.assertRaises(c.CatalogError):read(v,shape)
  v,shape=source(case,raw[:-1])
  with self.assertRaises(c.InvalidStructure):read(v,shape)
 def test_bad_field_bytes_refused(self):
  case=cases()[2];raw=bytes.fromhex(case['physical']['raw_hex']);shape=compile_case(case)
  for name,value in (('Variant',b'\xff'),('Available',b'\2'),('ValidUntil',b'\xff'),('Note',b'\xff\xff')):
   place=shape.placements[next(i for i,a in enumerate(shape.attributes) if a.name==name)];data=bytearray(raw);data[101+place.offset:101+place.offset+len(value)]=value;v,shape=source(case,bytes(data))
   with self.subTest(name=name),self.assertRaises(c.CatalogError):read(v,shape)
 def test_exact_binding_profile_typed_declarations_and_bounds(self):
  case=cases()[2];v,shape=source(case)
  for bad in (replace(shape,register_id=True),replace(shape,record_size=100),replace(shape,dimension_count=True),replace(shape,resource_count=2),replace(shape,format_item=False),replace(shape,placements=shape.placements[::-1]),replace(shape,profile_identifier='other')):
   v,_=source(case)
   with self.assertRaises((ValueError,c.CatalogError)):read(v,bad)
  fields=list(shape.declarations);fields[0]=(fields[0][0],'B',1,16,0,'CS');v,_=source(case,declarations=tuple(fields))
  with self.assertRaises(c.UnsupportedLayout):read(v,shape)
  self.assertEqual(compile_case(case,limits=b.CatalogBindingLimits(max_record_bytes=101)).record_size,101)
  with self.assertRaises(b.CatalogBindingError):compile_case(case,limits=b.CatalogBindingLimits(max_record_bytes=100))
  for limits in (r.legacy.RecordLimits(max_slots=3),r.legacy.RecordLimits(max_active_records=2),r.legacy.RecordLimits(max_fields=5),r.legacy.RecordLimits(max_record_bytes=100)):
   v,shape=source(case)
   with self.assertRaises(c.ResourceLimit):read(v,shape,limits=limits)
 def test_dbnames_multi_role_bydims_positive_and_negative(self):
  case=cases()[6];args=list(inputs(case));index=args[-1];self.assertTrue(any(e.kind=='ByDims' for e in index.entries));compile_case(case)
  for change in ('missing','wrong','duplicate','alias','aux_alias'):
   entries=list(index.entries)
   if change=='missing':entries=[e for e in entries if e.kind!='InfoRg']
   elif change=='wrong':entries[-1]=replace(entries[-1],kind='Other')
   elif change=='duplicate':entries.append(replace(entries[-1],ordinal=len(entries)))
   elif change=='alias':entries.append(replace(entries[1],uuid='11111111-1111-4111-8111-111111111111',ordinal=len(entries)))
   else:entries[-1]=replace(entries[-1],id=entries[1].id)
   entries=tuple(replace(e,ordinal=i) for i,e in enumerate(entries));args[-1]=replace(index,entries=entries,declared_count=len(entries))
   with self.subTest(change=change),self.assertRaises(b.CatalogBindingError):b.compile_information_register_binding(*args,budget=c._Budget(c.CatalogLimits()))
 def test_identity_role_qualifier_profile_and_reference_fail_closed(self):
  args=list(inputs(cases()[2]))
  for bad in (replace(args[0],periodicity=1),replace(args[0],write_mode=True)):
   with self.assertRaises(b.CatalogBindingError):b.compile_information_register_binding(bad,*args[1:],budget=c._Budget(c.CatalogLimits()))
  dims=args[1]
  for bad in (replace(dims,attributes=dims.attributes[:1]),replace(dims,attributes=(replace(dims.attributes[0],reference_catalog_uuid=args[0].metadata_uuid),dims.attributes[1])),replace(dims,attributes=(dims.attributes[0],replace(dims.attributes[1],qualifiers=(9,2,0))))):
   with self.assertRaises(b.CatalogBindingError):b.compile_information_register_binding(args[0],bad,*args[2:],budget=c._Budget(c.CatalogLimits()))
 def test_graph_duck_poison_and_cross_stage_alias(self):
  case=cases()[2];v,shape=source(case);reader,catalog,graph=r.prepared(v)
  with self.assertRaises(ValueError):
   with graph.stage('records',binding=SimpleNamespace(table_name=shape.table_name,profile_identifier=b.PROFILE_IDENTIFIER)):pass
  v,shape=source(case);reader,catalog,graph=r.prepared(v)
  with self.assertRaises(ValueError):
   with graph.stage('records',binding=shape) as h:
    with self.assertRaises(c.UnsupportedLayout):d.read_bound_information_register_records(reader,catalog,replace(shape,record_size=100),handle=h)
    self.assertTrue(graph.failed);h._check()
  for page in (4,6):
   v,shape=source(case);v.page(page)[16:24]=(1).to_bytes(8,'little');v.page(page)[24:28]=u32(22)
   with self.subTest(page=page),self.assertRaises(c.UnsupportedSharing):read(v,shape)
if __name__=='__main__':unittest.main()
