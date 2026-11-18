import os,unittest
from unittest.mock import patch
from yadinassi import Interpreter
from tests.retired_text_compiler import prepare
from yadinassi.experimental_naked_boundaries import BoundaryContext
class NamespaceTests(unittest.TestCase):
 def setUp(self):
  p=patch.dict(os.environ,{'YADINASSI_UNSAFE_COLLECTION_ABLATION':'1'});p.start();self.addCleanup(p.stop)
 def compare(self,source):
  vm=Interpreter(execution_backend='compiled-strict');events=[]
  vm.register_function('Get',lambda:lambda:events.append('unauthorized'))
  vm.execute(source)
  for flags in ((),('byref_routines',),('service_boundaries',),('service_boundaries','byref_routines','error_boundaries')):
   p=prepare(source,repairs=flags)
   actual=p.run({'get':lambda:lambda:events.append('unauthorized')},context=BoundaryContext(services={'get':lambda:lambda:events.append('unauthorized')}))
   self.assertEqual(actual['r'],vm.variables['r']);self.assertEqual(events,[])
 def test_assignment_does_not_replace_function(self):
  for assignment in ('7','Get()'):
   self.compare('Function F() Return 1;EndFunction F='+assignment+';r=F();')
 def test_local_variable_does_not_replace_function(self):
  self.compare('Function F() Return 1;EndFunction Function G() F=7;Return F();EndFunction r=G();')
 def test_variable_value_still_accessible(self):
  self.compare('Function F() Return 1;EndFunction F=7;r=F+F();')
 def test_recursion(self):
  self.compare('Function F(Val n) If n=0 Then Return 0;EndIf;Return F(n-1)+1;EndFunction r=F(10);')
 def test_function_value_is_not_exposed(self):
  source='Function F() Return 1;EndFunction r=F;'
  for candidate in (False,True):
   with self.assertRaisesRegex(Exception,'Процедуру или функцию необходимо вызвать: F'):
    if candidate:prepare(source,repairs=('error_boundaries',)).run()
    else:Interpreter(execution_backend='compiled-strict').execute(source)
 def test_no_routine_registry_in_generated_code(self):
  generated=prepare('Function F() Return 1;EndFunction r=F();',repairs=('service_boundaries',)).generated_source
  self.assertNotIn('register_routine',generated);self.assertNotIn('resolve_routine',generated)
 def test_procedure_value_rejected_before_arguments(self):
  events=[]
  p=prepare('Procedure F(x) EndProcedure r=F(Arg());',repairs=('service_boundaries','error_boundaries'))
  with self.assertRaisesRegex(Exception,'Процедура не возвращает значение: F'):
   p.run(context=BoundaryContext(services={'arg':lambda:events.append('arg')}))
  self.assertEqual(events,[])
 def test_invalid_static_arity_has_no_argument_effects(self):
  for signature,call in (('','Host()'),('x,y','Host()')):
   events=[]
   p=prepare('Procedure F('+signature+') EndProcedure F('+call+');',repairs=('service_boundaries','byref_routines','error_boundaries'))
   with self.assertRaisesRegex(Exception,'F ожидает .* аргументов, получено 1'):
    p.run(context=BoundaryContext(services={'host':lambda:events.append('host')}))
   self.assertEqual(events,[])
 def test_grouped_direct_routine_preserves_byref(self):
  source='Procedure F(x) x=7;EndProcedure r=0;((F))(r);'
  for flags in (('byref_routines',),('byref_routines','service_boundaries')):
   self.assertEqual(prepare(source,repairs=flags).run(context=BoundaryContext())['r'],7)
