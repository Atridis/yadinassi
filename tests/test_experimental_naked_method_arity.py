import os,unittest
from unittest.mock import patch
from yadinassi import Interpreter
from tests.retired_text_compiler import prepare
from yadinassi.experimental_naked_boundaries import BoundaryContext
class MethodArityTests(unittest.TestCase):
 def setUp(self):
  p=patch.dict(os.environ,{'YADINASSI_UNSAFE_COLLECTION_ABLATION':'1'});p.start();self.addCleanup(p.stop)
 def test_invalid_arity_preserves_argument_order_and_error_category(self):
  for kind,method,count in [('Array','Get',0),('Array','Get',2),('Array','Set',1),('Array','Set',3),('Array','Insert',0),('Array','Insert',3),('Array','Delete',0),('Array','Delete',2),('Map','Get',0),('Map','Get',2),('Map','Insert',3),('Map','Delete',0),('Map','Delete',2),('Structure','Insert',3),('Structure','Delete',0),('Array','Count',1),('Map','Count',1),('Structure','Count',1)]:
   source='a=New '+kind+';a.'+method+'('+','.join('Host('+str(i)+')' for i in range(count))+');'
   outcomes=[]
   for candidate in (False,True):
    effects=[]
    def host(i):effects.append(i);return i
    try:
     if candidate:prepare(source,source_name='arity.bsl',repairs=('service_boundaries','error_boundaries','array_index_contract','typed_map_keys','structure_fields')).run(context=BoundaryContext(services={'host':host}))
     else:
      vm=Interpreter(execution_backend='compiled-strict');vm.register_function('Host',host);vm.execute(source,'arity.bsl')
    except Exception as error:outcomes.append((type(error).__name__,str(error),effects))
    else:self.fail(source+' unexpectedly succeeded')
   self.assertEqual(outcomes[0][0],outcomes[1][0],source)
   self.assertEqual(outcomes[0][2],outcomes[1][2],source)
   self.assertIn('ожидает',outcomes[1][1]);self.assertIn('получено '+str(count),outcomes[1][1])
 def test_set_value_effect_precedes_bounds_error(self):
  source='a=New Array;a.Add(1);a.Set(-1,Host());'
  outcomes=[]
  for candidate in (False,True):
   effects=[]
   def host():effects.append('value');return 7
   try:
    if candidate:prepare(source,source_name='set.bsl',repairs=('service_boundaries','error_boundaries','array_index_contract')).run(context=BoundaryContext(services={'host':host}))
    else:
     vm=Interpreter(execution_backend='compiled-strict');vm.register_function('Host',host);vm.execute(source,'set.bsl')
   except Exception as error:outcomes.append((type(error).__name__,str(error),effects))
  self.assertEqual(outcomes[0],outcomes[1]);self.assertEqual(outcomes[1][2],['value'])
 def test_missing_delete_argument_does_not_delete_undefined_key(self):
  source='m=New Map;m.Insert(Undefined,7);Try m.Delete();Except EndTry;r=m.Count();'
  vm=Interpreter(execution_backend='compiled-strict');vm.execute(source)
  result=prepare(source,repairs=('service_boundaries','error_boundaries','typed_map_keys')).run(context=BoundaryContext())
  self.assertEqual((vm.variables['r'],result['r']),(1,1))
 def test_unsupported_native_method_is_catchable_before_arguments(self):
  for family,method in (('Array','Nonsense'),('Map','Set'),('Structure','Get')):
   events=[];source='a=New '+family+';r=False;Try a.'+method+'(Host());Except r=True;EndTry;'
   result=prepare(source,repairs=('service_boundaries','error_boundaries','typed_map_keys','structure_fields')).run(context=BoundaryContext(services={'host':lambda:events.append('arg')}))
   self.assertTrue(result['r']);self.assertEqual(events,[])
 def test_map_property_is_not_index_lookup(self):
  source='m=New Map;m.Insert("Count",7);r=False;Try x=m.Count;Except r=True;EndTry;'
  result=prepare(source,repairs=('typed_map_keys','service_boundaries','error_boundaries')).run(context=BoundaryContext())
  self.assertTrue(result['r'])
 def test_property_key_error_has_vm_source_position(self):
  source='s=New Structure("Name",7);v=0;result=s.Property("!",v);';messages=[]
  for candidate in (False,True):
   try:
    if candidate:prepare(source,source_name='property.bsl',repairs=('structure_fields','byref_routines','error_boundaries','service_boundaries')).run(context=BoundaryContext())
    else:Interpreter(execution_backend='compiled-strict').execute(source,'property.bsl')
   except Exception as error:messages.append(str(error))
  self.assertEqual(messages[0],messages[1])
 def test_native_map_iterator_failure_is_catchable_not_body_failure(self):
  source='m=New Map;m.Insert("x",1);r=False;Try For Each p In m Do m.Insert("y",2);EndDo;Except r=True;EndTry;'
  self.assertTrue(prepare(source,repairs=('typed_map_keys','error_boundaries','service_boundaries')).run(context=BoundaryContext())['r'])
  def host():raise RuntimeError('host runtime failure, not iterator')
  with self.assertRaisesRegex(RuntimeError,'host runtime failure'):
   prepare('m=New Map;m.Insert("x",1);For Each p In m Do Host();EndDo;',repairs=('typed_map_keys','error_boundaries','service_boundaries')).run(context=BoundaryContext(services={'host':host}))
 def test_missing_map_index_is_undefined_not_structure_missing_field(self):
  source='m=New Map;r=m["missing"];'
  vm=Interpreter(execution_backend='compiled-strict');vm.execute(source)
  result=prepare(source,repairs=('typed_map_keys','service_boundaries')).run(context=BoundaryContext())
  self.assertIsNone(vm.variables['r']);self.assertIsNone(result['r'])
  with self.assertRaisesRegex(ValueError,'Свойство структуры не найдено'):
   prepare('s=New Structure;r=s["missing"];',repairs=('structure_fields','service_boundaries')).run(context=BoundaryContext())
