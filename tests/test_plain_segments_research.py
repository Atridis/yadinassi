import unittest
from decimal import Decimal
from yadinassi import Interpreter
SOURCE='Function F(Val x) x=x+1;y=Host(x);Return x+y;EndFunction r=F(3);'
from compiled_contract_fixture import legacy_compiler_fixture

@legacy_compiler_fixture
class SegmentTests(unittest.TestCase):
 def compare(self,change):
  results=[]
  for enabled in (False,True):
   events=[];vm=Interpreter(execution_backend='compiled-strict',compiled_plain_routines=enabled)
   def host(x):events.append(x);change(vm);return x
   vm.register_function('Host',host)
   try:vm.execute(SOURCE);result=('ok',vm.variables.get('r'))
   except Exception as error:result=(type(error).__name__,str(error))
   self.assertEqual(events,[Decimal(4)]);self.assertIsNone(vm.locals)
   self.assertEqual(vm._compiled().active_frames,0);self.assertEqual(vm.compiled_backend_stats['interpreter_fallbacks'],0)
   results.append(result)
  self.assertEqual(*results);return vm,results[0]
 def test_live_mutation_reloaded_not_stale(self):
  vm,result=self.compare(lambda vm:vm.locals.__setitem__('x',Decimal(99)))
  self.assertEqual(result,('ok',Decimal(103)));self.assertEqual(vm.compiled_backend_stats.get('plain_segment_entries'),1)
 def test_deleted_live_in_denies_without_replay(self):
  vm,result=self.compare(lambda vm:vm.locals.pop('x'))
  self.assertEqual(vm.compiled_backend_stats.get('plain_resume_denied_missing'),1)
  self.assertEqual(vm.compiled_backend_stats.get('plain_segment_entries',0),0)
 def test_retyped_live_in_denies(self):
  vm,result=self.compare(lambda vm:vm.locals.__setitem__('x',[]))
  self.assertEqual(vm.compiled_backend_stats.get('plain_resume_denied_type'),1)
 def test_changed_scope_identity_denies(self):
  vm,result=self.compare(lambda vm:setattr(vm,'locals',dict(vm.locals,x=Decimal(7))))
  self.assertEqual(result,('ok',Decimal(11)));self.assertEqual(vm.compiled_backend_stats.get('plain_resume_denied_context'),1)
 def test_late_budget_change_never_compiles(self):
  vm,result=self.compare(lambda vm:setattr(vm._compiled(),'MAX_INLINE_UNIT_BYTES',0))
  self.assertEqual(result,('ok',Decimal(8)));self.assertEqual(vm.compiled_backend_stats.get('plain_segment_entries'),1)

@legacy_compiler_fixture
class GuardOrderingTests(unittest.TestCase):
 def engine(self):
  vm=Interpreter(execution_backend='compiled-strict',compiled_plain_routines=True)
  vm.execute('Function F(Val x) y=Host(x);Return y+1;EndFunction')
  engine=vm._compiled();root=next(value[1] for value in engine._plain_routines.values() if value[1] and value[1].segments)
  routine=next(value[0] for value in engine._plain_routines.values() if value[1] is root)
  return vm,engine,routine,root.segments[0]
 def test_replaced_locals_accessor_not_touched_by_gate(self):
  from unittest.mock import patch
  vm,engine,routine,segment=self.engine();saved=engine._plain_scope_snapshot();events=[]
  original=Interpreter.locals
  def getter(instance):events.append(1);return original.fget(instance)
  with patch.object(Interpreter,'locals',property(getter,original.fset)):
   self.assertIsNone(engine._resume_plain_segment(routine,segment,saved))
  self.assertEqual(events,[])
 def test_hostile_stack_overrides_not_touched_by_gate(self):
  for name in ('_context_stack','_module_context_stack'):
   vm,engine,routine,segment=self.engine();saved=engine._plain_scope_snapshot();events=[]
   class Hostile(list):
    def __len__(self):events.append('len');return super().__len__()
    def __iter__(self):events.append('iter');return super().__iter__()
   original=getattr(vm,name);setattr(vm,name,Hostile(original))
   try:self.assertIsNone(engine._resume_plain_segment(routine,segment,saved))
   finally:setattr(vm,name,original)
   self.assertEqual(events,[])
 def test_multiple_opaque_boundaries(self):
  for enabled in (False,True):
   effects=[];vm=Interpreter(execution_backend='compiled-strict',compiled_plain_routines=enabled)
   def host(x):effects.append(x);return x+1
   vm.register_function('Host',host)
   vm.execute('Function F(Val x) y=Host(x);y=y+2;z=Host(y);Return z*2;EndFunction r=F(1);')
   self.assertEqual(vm.variables['r'],10);self.assertEqual(effects,[Decimal(1),Decimal(4)])
   if enabled:self.assertEqual(vm.compiled_backend_stats.get('plain_segment_entries'),2)

 def test_vm_hash_and_colliding_scope_key_not_touched(self):
  from unittest.mock import patch
  vm,engine,routine,segment=self.engine();saved=engine._plain_scope_snapshot();events=[]
  def hostile_hash(instance):events.append('hash');return object.__hash__(instance)
  with patch.object(Interpreter,'__hash__',hostile_hash):
   self.assertIsNone(engine._resume_plain_segment(routine,segment,saved))
  self.assertEqual(events,[])
  class Key:
   def __hash__(self):return object.__hash__(vm)
   def __eq__(self,other):events.append('eq');return False
  context=vm._scheduler.active_context;old=context.locals
  key=Key();context.locals={key:{}};events.clear()
  try:self.assertIsNone(engine._resume_plain_segment(routine,segment,saved))
  finally:context.locals=old
  self.assertEqual(events,[])

 def test_hash_descriptor_and_getattribute_attestation_is_inert(self):
  from unittest.mock import patch
  vm,engine,routine,segment=self.engine();saved=engine._plain_scope_snapshot();events=[]
  class Descriptor:
   def __get__(self,instance,owner):events.append('descriptor');return object.__hash__
  with patch.object(Interpreter,'__hash__',Descriptor()):
   self.assertIsNone(engine._resume_plain_segment(routine,segment,saved))
  self.assertEqual(events,[])
  def hostile(instance,name):events.append(name);return object.__getattribute__(instance,name)
  with patch.object(Interpreter,'__getattribute__',hostile):
   self.assertIsNone(engine._plain_scope_snapshot())
  self.assertEqual(events,[])

 def test_hostile_storage_keys_rejected_before_lookup(self):
  for target,keyname in (('vm','_scheduler'),('scheduler','active_context'),('context','locals')):
   vm,engine,routine,segment=self.engine();saved=engine._plain_scope_snapshot();events=[]
   obj={'vm':vm,'scheduler':vm._scheduler,'context':vm._scheduler.active_context}[target]
   fields=object.__getattribute__(obj,'__dict__');value=fields.pop(keyname)
   class Key(str):
    def __eq__(self,other):events.append('eq');return str.__eq__(self,other)
    __hash__=str.__hash__
   key=Key(keyname);fields[key]=value;events.clear()
   try:self.assertIsNone(engine._plain_scope_snapshot())
   finally:fields.pop(key);fields[keyname]=value
   self.assertEqual(events,[])

if __name__=='__main__':unittest.main()
