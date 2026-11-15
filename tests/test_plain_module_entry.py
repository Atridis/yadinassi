"""Pure-block prototype differential, not production dispatch coverage."""
from decimal import Decimal, localcontext
import unittest
from yadinassi import Interpreter
from yadinassi.syntax.parser import parse
from yadinassi.plain_modules import lower_module
from yadinassi.plain_routines import Ineligible
class PlainModuleEntryTests(unittest.TestCase):
 def run_case(self,source,inputs=None,plain=False):
  vm=Interpreter(execution_backend='compiled-strict' if plain else 'interpreter');self.addCleanup(vm.close)
  vm.variables.update(inputs or {});result=None;error=None
  with localcontext() as ctx:
   ctx.prec=12;ctx.clear_flags()
   try:
    if plain:
     program=parse(source);engine=vm._compiled();engine.prepare_block(program);block=engine._owned.existing(program)
     plan=lower_module(block);self.assertIs(plan.block,block);self.assertTrue(plan.storage_eligible(vm.variables,vm.imports))
     def invoke():
      if False:yield
      return plan.function(vm,vm.variables)
     result=vm._scheduler.run_inline(invoke());self.assertEqual(vm.compiled_backend_stats['interpreter_fallbacks'],0)
    else:result=vm.execute(source)
   except Exception as caught:error=(type(caught).__name__,str(caught))
   flags={k.__name__:v for k,v in ctx.flags.items()}
  self.assertIsNone(vm.locals)
  return result,dict(vm.variables),error,flags
 def pair(self,source,inputs=None):
  expected=self.run_case(source,inputs);actual=self.run_case(source,inputs,True);self.assertEqual(actual,expected);return actual
 def plan(self,source):
  vm=Interpreter(execution_backend='compiled-strict');self.addCleanup(vm.close)
  p=parse(source);e=vm._compiled();e.prepare_block(p);return lower_module(e._owned.existing(p))
 def test_arithmetic_return(self):
  result,values,error,_=self.pair('x=2;y=x*3+1;y;');self.assertIsNone(error);self.assertEqual(result,Decimal(7))
 def test_partial_write_rhs_error(self):
  _,v,e,_=self.pair('x=1;y=8;y=1/0;');self.assertIsNotNone(e);self.assertEqual(v,{'x':Decimal(1),'y':Decimal(8)})
 def test_loop_partial_write_error(self):
  _,v,e,_=self.pair('s=0;For i=1 To 4 Do s=s+i;x=1/(3-i);EndDo;');self.assertIsNotNone(e);self.assertEqual(v['s'],Decimal(6));self.assertEqual(v['i'],Decimal(3))
 def test_bounds_once_fractional_counter_mutation(self):
  self.pair('n=4;s=0;For i=0.5 To n Do s=s+i;n=0;EndDo;s;')
  self.pair('s=0;For i=1 To 7 Do s=s+i;i=i+1;EndDo;s;')
 def test_continue_break_nested(self):
  self.pair('s=0;For i=1 To 5 Do If i=2 Then Continue;EndIf;If i=4 Then Break;EndIf;For j=1 To 2 Do s=s+i;EndDo;EndDo;s;')
 def test_while_and_statement_result(self):
  self.pair('x=0;While x<4 Do x=x+1;EndDo;');self.pair('x=1;If x=1 Then 99;Else 100;EndIf;')
 def test_short_circuit_conditional(self):
  self.pair('x=False And 1/0>1;y=True Or 1/0>1;x;');self.pair('x=?(True,3,1/0);x;')
 def test_var_keeps_prior(self):
  self.pair('Var x;x;',{'x':Decimal(9)});self.pair('Var x;x;')
 def test_decimal_errors_flags(self):
  self.pair('x=1/7;x;');self.pair('y=1;x=n+1;',{'n':Decimal('sNaN')})
 def test_storage_gate(self):
  p=self.plan('x=n+1;x;');self.assertFalse(p.storage_eligible({},{}));self.assertFalse(p.storage_eligible({'n':None},{'x':object()}));events=[]
  class Key(str):
   def __eq__(self,other):events.append('eq');return super().__eq__(other)
   __hash__=str.__hash__
  self.assertFalse(p.storage_eligible({Key('n'):Decimal(2)},{}));self.assertFalse(p.storage_eligible({'n':object()},{}));self.assertEqual(events,[])
  with self.assertRaises(Ineligible):self.plan('ThisObject=1;')
 def test_opaque_rejects_whole_body(self):
  for s in ('x=1;Message(x);','x=1;Execute "x=2;";','x=1;Try x=2;Except EndTry;','x=1;Goto ~Done;~Done:x=2;','Function F() Return 1;EndFunction x=1;'):
   with self.subTest(source=s),self.assertRaises(Ineligible):self.plan(s)
 def test_owned_source_budget(self):
  with self.assertRaises(Ineligible):lower_module(parse('x=1;'))
  p=self.plan('x=1;');self.assertGreater(p.source_bytes,0)
  with self.assertRaises(Ineligible):lower_module(p.block,max_source_bytes=1)
 def test_repeat_live_globals(self):
  p=self.plan('x=x+1;x;');vm=Interpreter(execution_backend='compiled-strict');self.addCleanup(vm.close);storage={'x':Decimal(1)}
  self.assertTrue(p.storage_eligible(storage,{}));self.assertEqual(p.function(vm,storage),Decimal(2));storage['x']=Decimal(20);self.assertEqual(p.function(vm,storage),Decimal(21))
if __name__=='__main__':unittest.main()
