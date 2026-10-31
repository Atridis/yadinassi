"""Private measured zero-code shapes; no synthetic native Code API value."""
from dataclasses import replace
from decimal import Decimal
import unittest
import test_config_catalog_binding as f
import test_config_catalog_records as r
b=f.binding

def compile_zero(description=0,payload=32,*,identity=None,attributes=None,profile=None,limits=None):
 i,a=f.identities(code=0,string=payload)
 i=replace(i,description_length=description)if identity is None else identity
 return b.compile_catalog_binding(i,a if attributes is None else attributes,f.index(),
  profile=b.CatalogBindingProfile(b.ZERO_PROFILE_IDENTIFIER if profile is None else profile),
  budget=f.catalog._Budget(f.catalog.CatalogLimits()),limits=limits)

def physical(description,payload):
 # Explicit known declarations and offsets, never inferred from the binding.
 fields=(('_IDRREF','B',0,16,0,'CS'),('_VERSION','RV',0,0,0,'CS'),
         ('_MARKED','L',0,0,0,'CS'),('_PREDEFINEDID','B',0,16,0,'CS'))
 if description:fields+=(('_DESCRIPTION','NVC',0,8,0,'CI'),)
 fields+=(('_FLD62','NVC',0,payload,0,'CI'),('_FLD741','N',0,9,2,'CS'))
 row=b'\0'+b'V'*16+b'R'*16+b'\0'+b'P'*16
 if description:row+=r.text('name',8)
 row+=r.text('alpha',payload)+bytes.fromhex('1000000125')
 value,_=r.source(raw=b'\1'+b'\xab'*(len(row)-1)+row,declarations=fields)
 return value,fields

class ZeroStructuralTests(unittest.TestCase):
 def test_four_measured_shapes_read_without_code(self):
  for desc in (0,8):
   for payload in (32,64):
    with self.subTest(desc=desc,payload=payload):
     binding=compile_zero(desc,payload);value,fields=physical(desc,payload)
     self.assertEqual(binding.declarations,fields)
     self.assertEqual(binding.record_size,{(0,32):121,(0,64):185,(8,32):139,(8,64):203}[desc,payload])
     self.assertEqual(binding.placements[-2].offset,50 if desc==0 else 68)
     rows=r.read(value,binding);expected=[b'R'*16,b'V'*16,False,b'P'*16]
     if desc:expected+=['name']
     expected+=['alpha',Decimal('1.25')]
     self.assertEqual([x.value for x in rows.rows[0].fields],expected)
     self.assertNotIn('_CODE',[x[0]for x in binding.declarations])
 def test_old_profiles_keep_zero_rejection_and_new_rejects_positive(self):
  for profile in (b.PROFILE_IDENTIFIER,b.NUMERIC_PROFILE_IDENTIFIER):
   with self.assertRaises(b.CatalogBindingError):compile_zero(profile=profile)
  i,_=f.identities(code=2)
  with self.assertRaises(b.CatalogBindingError):compile_zero(identity=i)
 def test_zero_only_bounded_logical_inputs(self):
  i,a=f.identities(code=0)
  for key,vals in [('code_type',(0,True,1.0)),('code_length',(-1,True,0.0,1)),('description_length',(-1,1,17,True,0.0))]:
   for val in vals:
    with self.subTest(key=key,val=val),self.assertRaises(b.CatalogBindingError):compile_zero(identity=replace(i,**{key:val}))
  for string,precision,scale in [(31,9,2),(65,9,2),(32,8,2),(32,9,3)]:
   _,attrs=f.identities(code=0,string=string,precision=precision,scale=scale)
   with self.assertRaises(b.CatalogBindingError):compile_zero(attributes=attrs)
 def test_uuid_names_and_dbnames_are_not_fixture_constants(self):
  catalog='abcdefff-1111-2222-3333-123456789abc'
  string='abcdefff-1111-2222-3333-123456789abd'
  number='abcdefff-1111-2222-3333-123456789abe'
  identity=f.name.CatalogIdentityPrefix(catalog,'DifferentInventory',0,1,8)
  attributes=f.attrs.CatalogAttributes((f.attrs.CatalogAttribute(string,'Narrative','S',(64,1)),
                                      f.attrs.CatalogAttribute(number,'Total','N',(9,2,0))))
  names=f.index(((string,'Fld',914),(number,'Fld',502),(catalog,'Reference',873)))
  binding=b.compile_catalog_binding(identity,attributes,names,profile=b.CatalogBindingProfile(b.ZERO_PROFILE_IDENTIFIER),budget=f.catalog._Budget(f.catalog.CatalogLimits()))
  self.assertEqual((binding.metadata_uuid,binding.name,binding.table_name),(catalog,'DifferentInventory','_Reference873'))
  self.assertEqual([(a.metadata_uuid,a.name,a.physical_name)for a in binding.attributes],[(string,'Narrative','_FLD914'),(number,'Total','_FLD502')])
  self.assertEqual([d[0]for d in binding.declarations[-2:]],['_FLD914','_FLD502'])
  self.assertEqual((binding.record_size,binding.placements[-2].offset),(203,68))
  r.records._validate_binding(binding,f.catalog._Budget(f.catalog.CatalogLimits()))
 def test_limits_still_apply(self):
  for limits in [b.CatalogBindingLimits(max_record_bytes=120),b.CatalogBindingLimits(max_string_length=31),b.CatalogBindingLimits(max_numeric_precision=8)]:
   with self.assertRaises(b.CatalogBindingError):compile_zero(limits=limits)
 def test_forged_binding_rechecked_before_read(self):
  good=compile_zero();value,_=physical(0,32)
  cases=[replace(good,code_type=0),replace(good,code_type=True),replace(good,code_length=False),replace(good,description_length=17),replace(good,record_size=True),replace(good,record_size=123),replace(good,attributes=(replace(good.attributes[0],qualifiers=(31,1)),good.attributes[1])),replace(good,attributes=(good.attributes[0],replace(good.attributes[1],qualifiers=(9,3,0)))),replace(good,placements=(replace(good.placements[0],offset=True),)+good.placements[1:]),replace(good,declarations=good.declarations[:4]+(('_CODE','NVC',0,0,0,'CI'),)+good.declarations[4:])]
  for forged in cases:
   with self.subTest(forged=forged),self.assertRaises(f.catalog.UnsupportedLayout):r.read(value,forged)
 def test_descriptor_mismatch_not_admitted(self):
  good=compile_zero();_,fields=physical(0,32)
  wrong=fields[:4]+(('_CODE','NVC',0,0,0,'CI'),)+fields[4:]
  value,_=r.source(raw=b'\0'*121,declarations=wrong)
  with self.assertRaises(f.catalog.UnsupportedLayout):r.read(value,good)
if __name__=='__main__':unittest.main()
