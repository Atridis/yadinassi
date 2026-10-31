"""Exact empty-string observation is distinct from type and physical omission."""
import copy
import unittest
from unittest import mock
import test_native_catalog_zero_code_policy as f
import catalog_zero_code_policy as p
import protocol

class CodeEmptyObservationTests(unittest.TestCase):
 def test_bound_value_not_assumed_from_type_or_omission(self):
  for state,code,expected in [('string','',True),('string',' ',False),('string','X',False),('number','0',None),('unavailable','',None),('other','',None)]:
   real=f.witness
   def observed(*args,**kw):
    if kw.get('present',True):kw.update(state=state,code=code)
    return real(*args,**kw)
   with mock.patch.object(f,'witness',side_effect=observed):r=f.fixture()
   f.validate(r)
   states=r['zero_code_measurement']['states']
   self.assertIsNone(states[0]['witness']['code_is_empty'])
   self.assertTrue(all(s['witness']['code_is_empty']is expected for s in states[1:]))
 def test_legacy_absence_is_not_empty_evidence(self):
  r=f.fixture()
  for state in r['zero_code_measurement']['states']:state['witness'].pop('code_is_empty')
  f.validate(r)
  self.assertTrue(all('code_is_empty'not in s['witness']for s in r['zero_code_measurement']['states']))
 def test_shape_rejects_invalid_optional_truth(self):
  r=f.fixture()
  for index,values in [(0,[False,True,0,'',[]]),(1,[False,True,0,'',[]])]:
   for value in values:
    bad=copy.deepcopy(r);bad['zero_code_measurement']['states'][index]['witness']['code_is_empty']=value
    with self.subTest(index=index,value=value),self.assertRaises(protocol.OracleError):f.validate(bad)
  # A string observation requires an actual boolean, not null or integer.
  real=f.witness
  def observed(*a,**kw):
   if kw.get('present',True):kw.update(state='string',code='')
   return real(*a,**kw)
  with mock.patch.object(f,'witness',side_effect=observed):r=f.fixture()
  for value in (None,0,1,'true',[]):
   bad=copy.deepcopy(r);bad['zero_code_measurement']['states'][1]['witness']['code_is_empty']=value
   with self.assertRaises(protocol.OracleError):f.validate(bad)

if __name__=='__main__':unittest.main()
