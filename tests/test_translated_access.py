"""Value service differential/ordering; generated emitter integrated separately."""
from decimal import Decimal
import unittest
from unittest.mock import patch
from yadinassi import Interpreter
from yadinassi import runtime as R
from yadinassi import translated_access as A
from yadinassi.syntax.parser import parse

class TranslatedAccessTests(unittest.TestCase):
 def vm(self):
  vm=Interpreter(execution_backend='interpreter');self.addCleanup(vm.close);return vm
 def drive(self,vm,generator):return vm._scheduler.run_inline(generator)
 def test_collection_index_read_write_value_services(self):
  sources=['a=New Array();a.Add(2);','a=New Map();a.Insert(0,2);',
           'a=New Structure("x",2);','a=New ValueList();a.Add(2);']
  for source in sources:
   with self.subTest(source=source):
    vm=self.vm();vm.execute(source);value=vm.variables['a'];index='x' if 'Structure' in source else Decimal(0)
    expected=vm.execute('a["x"];' if type(index)is str else 'a[0];')
    with patch.object(vm,'_visit',side_effect=AssertionError('AST dispatch')):
     actual=self.drive(vm,A.prepare_index_read(vm,value).finish(index))
    self.assertIs(actual,expected) if isinstance(actual,R.BSLObject) else self.assertEqual(actual,expected)
    if 'ValueList' not in source:
     A.prepare_index_write(vm,value)(index)(Decimal(7))
     self.assertEqual(vm.execute('a["x"];' if type(index)is str else 'a[0];'),Decimal(7))
 def test_attribute_structure_live(self):
  vm=self.vm();vm.execute('a=New Structure("x",2);');value=vm.variables['a']
  self.assertEqual(self.drive(vm,A.read_attribute(vm,value,'x')),Decimal(2))
  A.prepare_attribute_write(vm,value,'x')(Decimal(11))
  self.assertEqual(vm.execute('a.x;'),Decimal(11))
 def test_generic_read_lookup_after_index(self):
  for candidate in (False,True):
   vm=self.vm();value=R.BSLArray();value.items.append(Decimal(1));events=[];vm.variables['a']=value
   def index():
    events.append('index');value.get=lambda key:events.append('new-get') or Decimal(9);return Decimal(0)
   vm.register_function('Index',index)
   if candidate:
    operation=A.prepare_index_read(vm,value);result=self.drive(vm,operation.finish(index()))
   else:result=vm.execute('a[Index()];')
   self.assertEqual(result,Decimal(9));self.assertEqual(events,['index','new-get'])
 def test_generic_write_lookup_between_index_and_rhs(self):
  for candidate in (False,True):
   vm=self.vm();value=R.BSLArray();value.items.append(Decimal(1));vm.variables['a']=value;events=[]
   def index():
    events.append('index');value.set=lambda k,v:events.append(('captured-set',k,v));return Decimal(0)
   def rhs():
    events.append('rhs');value.set=lambda k,v:events.append('late-set');return Decimal(9)
   vm.register_function('Index',index);vm.register_function('Rhs',rhs)
   if candidate:A.prepare_index_write(vm,value)(index())(rhs())
   else:vm.execute('a[Index()]=Rhs();')
   self.assertEqual(events,['index','rhs',('captured-set',Decimal(0),Decimal(9))])
 def test_attribute_writer_bound_before_rhs(self):
  for candidate in (False,True):
   vm=self.vm();vm.execute('a=New Structure("x",1);');value=vm.variables['a'];events=[]
   value.set_member=lambda n,v:events.append(('initial',n,v))
   def rhs():
    events.append('rhs');value.set_member=lambda n,v:events.append('late');return Decimal(5)
   vm.register_function('Rhs',rhs)
   if candidate:A.prepare_attribute_write(vm,value,'x')(rhs())
   else:vm.execute('a.x=Rhs();')
   self.assertEqual(events,['rhs',('initial','x',Decimal(5))])
 def test_source_index_method_bound_before_index(self):
  from yadinassi.source_document_sections import SourceDocumentSection
  vm=self.vm();value=object.__new__(SourceDocumentSection);events=[]
  with patch.object(SourceDocumentSection,'get_index',lambda self,caller,index:events.append('original') or index):
   operation=A.prepare_index_read(vm,value)
   with patch.object(SourceDocumentSection,'get_index',lambda *a:events.append('late')):
    self.assertEqual(self.drive(vm,operation.finish(Decimal(1))),Decimal(1))
  self.assertEqual(events,['original'])
 def test_invalid_receiver_precedes_operands(self):
  vm=self.vm();events=[]
  def effect():events.append('operand');return Decimal(1)
  with self.assertRaises(TypeError):A.prepare_index_read(vm,Decimal(3)).finish(effect())
  with self.assertRaises(TypeError):A.prepare_attribute_write(vm,Decimal(3),'x')(effect())
  with self.assertRaises(TypeError):A.prepare_index_write(vm,Decimal(3))(effect())(effect())
  self.assertEqual(events,[])
 def test_session_authority_before_index_and_rhs(self):
  vm=self.vm();value=object.__new__(R.BSLSessionParameters);events=[]
  def denied(*args):events.append('authorize');raise PermissionError('denied')
  with patch.object(R.BSLSessionParameters,'_authorize',denied):
   with self.assertRaises(PermissionError):A.prepare_index_read(vm,value)
   with self.assertRaises(PermissionError):A.prepare_index_write(vm,value)
   with self.assertRaises(PermissionError):A.prepare_attribute_write(vm,value,'x')
  self.assertEqual(events,['authorize']*3)
 def test_source_readonly_precedes_rhs(self):
  vm=self.vm();value=object();events=[]
  with patch('yadinassi.source_document_runtime.is_source_reference',lambda x:x is value):
   with self.assertRaisesRegex(ValueError,'readonly'):A.prepare_attribute_write(vm,value,'x')
   with self.assertRaisesRegex(ValueError,'readonly'):A.prepare_index_write(vm,value)
  self.assertEqual(events,[])
 def test_session_read_generator_preserves_suspend(self):
  vm=self.vm();value=object.__new__(R.BSLSessionParameters);events=[]
  def read(self,caller,name):
   events.append(('enter',name));yield 'pending';events.append('resume');return Decimal(7)
  with patch.object(R.BSLSessionParameters,'_authorize',lambda *a:events.append('authorize')),patch.object(R.BSLSessionParameters,'read',read):
   call=A.prepare_index_read(vm,value).finish('x');self.assertEqual(next(call),'pending')
   with self.assertRaises(StopIteration) as end:next(call)
   self.assertEqual(end.exception.value,Decimal(7))
  self.assertEqual(events,['authorize',('enter','x'),'resume'])
 def test_module_capability_not_restored_by_receiver(self):
  vm=self.vm();module=R._Module(vm)
  with patch.object(vm,'_require_module_storage_context',side_effect=PermissionError('no module')):
   with self.assertRaises(PermissionError):self.drive(vm,A.read_attribute(vm,module,'x'))
   with self.assertRaises(PermissionError):A.prepare_attribute_write(vm,module,'x')

if __name__=='__main__':unittest.main()
