import unittest
from decimal import Decimal,localcontext,Overflow
from unittest.mock import patch
from yadinassi import Interpreter
SOURCE='Function Sum(Val n) s=0;For i=1 To n Do s=s+i; EndDo; Return s; EndFunction r=Sum(n);'
class PlainTests(unittest.TestCase):
 def execute(self,source,n=10,mode='compiled-strict'):
  v=Interpreter(compiled_plain_routines=True,execution_backend=mode);v.variables['n']=Decimal(n);v.execute(source);return v
 def test_for_decimal_slots(self):
  for n in (-1,0,1,10,101):
   v=self.execute(SOURCE,n);old=self.execute(SOURCE,n,'interpreter')
   self.assertEqual(v.variables['r'],old.variables['r']);self.assertEqual(v.compiled_backend_stats['plain_routine_calls'],1)
   self.assertEqual(v.compiled_backend_stats['interpreter_fallbacks'],0);self.assertIsNone(v.locals)
 def test_byref_stays_adapter(self):
  v=self.execute(SOURCE.replace('Val n','n'));self.assertEqual(v.variables['r'],55)
  self.assertEqual(v.compiled_backend_stats.get('plain_routine_calls',0),0)
 def test_module_write_stays_adapter(self):
  v=self.execute('Var s;'+SOURCE);self.assertEqual(v.variables['s'],55)
  self.assertEqual(v.compiled_backend_stats.get('plain_routine_calls',0),0)
 def test_hooks_stay_adapter(self):
  seen=[]
  with patch.object(Interpreter,'compiled_before',lambda vm,node:seen.append(type(node).__name__)):
   v=self.execute(SOURCE)
  self.assertTrue(seen);self.assertEqual(v.compiled_backend_stats.get('plain_routine_calls',0),0)
 def test_host_call_stays_adapter(self):
  v=self.execute(SOURCE.replace('s=s+i;','s=s+i;Message(i);'))
  self.assertEqual(v.compiled_backend_stats.get('plain_routine_calls',0),0)
 def test_nondecimal_stays_adapter(self):
  v=Interpreter(compiled_plain_routines=True,execution_backend='compiled-strict');v.variables['n']='oops'
  with self.assertRaises(Exception):v.execute(SOURCE)
  self.assertEqual(v.compiled_backend_stats.get('plain_routine_calls',0),0);self.assertIsNone(v.locals)
 def test_read_after_maybe_zero_loop_rejected(self):
  v=self.execute('Function F(Val n) For i=1 To n Do s=1;EndDo;Return s;EndFunction r=F(n);')
  self.assertEqual(v.compiled_backend_stats.get('plain_routine_calls',0),0)
 def test_live_snapshot_and_rebind(self):
  v=self.execute(SOURCE);v.routines['sum'].body[-1].value.name='n'
  v.execute('r=Sum(10);');self.assertEqual(v.variables['r'],55)
  v.execute('Function Sum(Val n) Return n+2;EndFunction r=Sum(10);');self.assertEqual(v.variables['r'],12)
 def test_source_error_matches_existing_snapshot(self):
  source='Function F(Val n)\nReturn n+1;\nEndFunction\nr=F(n);'
  results=[]
  for mode in ('interpreter','compiled-strict'):
   v=Interpreter(compiled_plain_routines=True,execution_backend=mode);v.variables['n']=Decimal('sNaN')
   try:v.execute(source)
   except Exception as e:results.append((type(e).__name__,str(e)))
   self.assertIsNone(v.locals)
  self.assertEqual(results[0],results[1])
 def test_cache_release(self):
  v=self.execute(SOURCE);self.assertTrue(v._compiled()._plain_routines)
  v._compiled().release();self.assertEqual(v._compiled()._plain_routines,{})
 def test_deep_arithmetic_stays_adapter(self):
  expression='n'
  for _ in range(24):expression='('+expression+'+1)'
  v=self.execute('Function F(Val n) Return '+expression+';EndFunction r=F(n);')
  self.assertEqual(v.variables['r'],34)
  self.assertEqual(v.compiled_backend_stats.get('plain_routine_calls',0),0)
 def test_optional_source_budget_keeps_adapter(self):
  v=Interpreter(compiled_plain_routines=True,execution_backend='compiled-strict');v._compiled().MAX_PLAIN_SOURCE_BYTES=0
  v.variables['n']=Decimal(10);v.execute(SOURCE)
  self.assertEqual(v.variables['r'],55)
  self.assertEqual(v.compiled_backend_stats.get('plain_routine_calls',0),0)
 def test_trace_and_profile_live_scope_stay_adapter(self):
  import sys
  for setter in (sys.settrace,sys.setprofile):
   v=Interpreter(compiled_plain_routines=True,execution_backend='compiled-strict');seen=[]
   def observe(frame,event,arg):
    if event=='call' and frame.f_code.co_name in ('generated','lowered') and v.locals is not None and 'x' in v.locals and not seen:
     seen.append(1);v.locals['x']=Decimal(99)
    return observe
   try:
    setter(observe);v.execute('Function F(Val x) Return x;EndFunction r=F(1);')
   finally:setter(None)
   self.assertEqual(v.variables['r'],99);self.assertTrue(seen)
   self.assertEqual(v.compiled_backend_stats.get('plain_routine_calls',0),0)
 def test_optional_source_charged_to_admission_and_limit_keeps_adapter(self):
  from yadinassi.syntax.parser import parse
  source='Function F(Val n) Return n+1;EndFunction'
  off=Interpreter(compiled_plain_routines=True,execution_backend='compiled-strict');off._compiled().MAX_PLAIN_SOURCE_BYTES=0
  off._compiled().prepare(parse(source));base=off._compiled()._inline_unit_bytes
  on=Interpreter(compiled_plain_routines=True,execution_backend='compiled-strict');on._compiled().prepare(parse(source))
  charged=sum(len(v[1].source.encode()) for v in on._compiled()._plain_routines.values() if v[1] is not None)
  self.assertGreater(charged,0);self.assertEqual(on._compiled()._inline_unit_bytes,base+charged)
  limited=Interpreter(compiled_plain_routines=True,execution_backend='compiled-strict');limited._compiled().MAX_INLINE_UNIT_BYTES=base
  limited._compiled().prepare(parse(source))
  self.assertTrue(all(v[1] is None for v in limited._compiled()._plain_routines.values()))
 def test_failed_optional_admission_rolls_back_registry(self):
  from yadinassi.syntax.parser import parse
  from yadinassi.plain_routines import lower
  count=[]
  def fail_second(*args,**kwargs):
   count.append(1)
   if len(count)==2:raise RuntimeError('injected compile failure')
   return lower(*args,**kwargs)
  v=Interpreter(compiled_plain_routines=True,execution_backend='compiled-strict');engine=v._compiled()
  with patch('yadinassi.plain_routines.lower',fail_second):
   with self.assertRaisesRegex(RuntimeError,'injected'):
    engine.prepare(parse('Function F(Val x) Return x+1;EndFunction Function G(Val x) Return x+2;EndFunction'))
  self.assertEqual(engine._plain_routines,{});self.assertEqual(engine._nodes,{})
 def test_reused_plain_source_rechecks_optional_budget(self):
  from yadinassi.syntax.parser import parse
  v=Interpreter(compiled_plain_routines=True,execution_backend='compiled-strict');engine=v._compiled()
  program=parse('Function F(Val n) Return n+1;EndFunction')
  engine.prepare(program);self.assertTrue(any(x[1] is not None for x in engine._plain_routines.values()))
  engine.MAX_PLAIN_SOURCE_BYTES=0;engine.prepare(program,allow_reprepare=False)
  self.assertTrue(all(x[1] is None for x in engine._plain_routines.values()))

class OptInTests(unittest.TestCase):
 def test_default_off_and_family_inheritance(self):
  vm=Interpreter(execution_backend='compiled-strict');vm.variables['n']=Decimal(10);vm.execute(SOURCE)
  self.assertEqual(vm.variables['r'],55);self.assertFalse(vm.compiled_plain_routines)
  self.assertEqual(vm.compiled_backend_stats.get('plain_routine_calls',0),0)
  self.assertEqual(vm._compiled()._plain_routines,{})
  with self.assertRaises(AttributeError):vm.compiled_plain_routines=True
  owner=Interpreter(compiled_plain_routines=True)
  self.assertTrue(Interpreter(family_owner=owner).compiled_plain_routines)
  self.assertFalse(Interpreter(family_owner=owner,compiled_plain_routines=False).compiled_plain_routines)
  for bad in (1,'true',object()):
   with self.assertRaises(ValueError):Interpreter(compiled_plain_routines=bad)

if __name__ == '__main__': unittest.main()
