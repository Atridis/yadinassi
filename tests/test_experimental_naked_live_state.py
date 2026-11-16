import os
import unittest
from decimal import Decimal
from unittest.mock import patch
from yadinassi import Interpreter
from yadinassi.values import Reference,HostFunction
from yadinassi.errors import BSLRuntimeError
from yadinassi.experimental_naked_collections import prepare,UnsupportedNakedSyntax
from yadinassi.experimental_naked_boundaries import BoundaryContext,BoundaryViolation
FLAGS=('live_module_state','byref_routines','service_boundaries','dynamic_host_refs','error_boundaries')
class LiveModuleStateTests(unittest.TestCase):
 def setUp(self):
  e=patch.dict(os.environ,{'YADINASSI_UNSAFE_COLLECTION_ABLATION':'1'});e.start();self.addCleanup(e.stop)
 def run_live(self,source,state=None,services=None,**kwargs):
  state={} if state is None else state
  p=prepare(source,repairs=FLAGS,source_name='live.bsl',**kwargs)
  result=p.run(state,context=BoundaryContext(services=services))
  self.assertIs(result,state);self.assertIs(p.last_state,state)
  return result
 def test_callback_read_write_same_object(self):
  state={};seen=[]
  def host():seen.append(state['x']);state['x']=Decimal(8)
  self.run_live('x=1;Host();r=x;',state,{'Host':host})
  self.assertEqual(seen,[1]);self.assertEqual(state,{'x':8,'r':8})
 def test_delete_and_missing_error_does_not_republish(self):
  state={}
  with self.assertRaisesRegex(BSLRuntimeError,'не определена: x'):
   self.run_live('x=1;Delete();r=x;',state,{'Delete':lambda:state.pop('x')})
  self.assertEqual(state,{})
 def test_host_rebinds_its_own_variable_not_actual_namespace(self):
  original={};holder=[original]
  def host():holder[0]={};original['x']=Decimal(8)
  self.run_live('x=1;Host();r=x;',original,{'Host':host})
  self.assertEqual(original['r'],8);self.assertEqual(holder[0],{})
 def test_source_reference_alias(self):
  self.assertEqual(self.run_live('Procedure F(a,b) a=a+1;b=b+2;EndProcedure x=1;F(x,x);r=x;')['r'],4)
 def test_retained_host_reference_live_after_return(self):
  refs=[];h=HostFunction('h',lambda x:refs.append(x),reference_parameters=frozenset({0}))
  state=self.run_live('x=1;f=Get();f(x);',services={'Get':lambda:h})
  self.assertIs(type(refs[0]),Reference);refs[0].set(Decimal(9));self.assertEqual(state['x'],9)
 def test_seeded_reference_identity_and_source_forwarding(self):
  box=[Decimal(1)];ref=Reference(lambda:box[0],lambda v:box.__setitem__(0,v));seen=[]
  host=HostFunction('h',lambda arg:seen.append(arg is ref),reference_parameters=frozenset({0}))
  state={'x':ref}
  self.run_live('Procedure Bump(a) a=a+1;EndProcedure f=Get();f(x);Bump(x);',state,{'Get':lambda:host})
  self.assertEqual(seen,[True]);self.assertEqual(box[0],2);self.assertIs(state['x'],ref)
 def test_predeclaration_and_explicit_previous_module_names(self):
  self.assertIsNone(self.run_live('r=x;Var x;')['r'])
  self.assertEqual(self.run_live('Function F() x=x+1;Return x;EndFunction r=F();',{'x':Decimal(8)},module_names=('x',))['r'],9)
 def test_routine_private_locals_stay_private(self):
  source='Var x;Function F() Var y;y=8;x=x+1;Return y;EndFunction x=1;r=F();'
  state=self.run_live(source)
  self.assertEqual(state,{'x':2,'r':8});self.assertNotIn('y',state)
 def test_readonly_rhs_first_and_shadow(self):
  for source in ('ThisObject=Host();','Procedure F() ThisObject=Host();EndProcedure F();'):
   events=[]
   with self.assertRaisesRegex(BSLRuntimeError,'только для чтения'):
    self.run_live(source,services={'Host':lambda:events.append(1) or 1})
   self.assertEqual(events,[1])
  self.assertEqual(self.run_live('Var ThisObject;ThisObject=1;r=ThisObject;')['r'],1)
  self.assertEqual(self.run_live('Procedure F() Var ThisObject;ThisObject=1;EndProcedure F();'),{})
 def test_for_order_mutation_continue(self):
  state={};seen=[]
  def bound():seen.append(state['i']);return Decimal(3)
  def change():state['i']=Decimal(10)
  self.run_live('i=9;For i=1 To Bound() Do Change();Continue;EndDo;r=i;',state,{'Bound':bound,'Change':change})
  self.assertEqual(seen,[9]);self.assertEqual(state['r'],11)
 def test_counter_delete_errors_without_keyerror(self):
  state={}
  with self.assertRaisesRegex(BSLRuntimeError,'не определена: i'):
   self.run_live('For i=1 To 2 Do Delete();EndDo;',state,{'Delete':lambda:state.pop('i')})
  self.assertNotIn('i',state)
 def test_foreach_readonly_target_rejects_after_iterator_value(self):
  with self.assertRaisesRegex(BSLRuntimeError,'только для чтения'):
   self.run_live('a=New Array;a.Add(1);For Each ThisObject In a Do r=1;EndDo;')
 def test_partial_writes_before_error(self):
  state={}
  with self.assertRaises(BSLRuntimeError):self.run_live('x=1;y=1/0;',state)
  self.assertEqual(state,{'x':1})
 def test_foreign_mapping_and_casefold_keys_rejected_once_at_entry(self):
  p=prepare('x=1;',repairs=FLAGS)
  class Dict(dict):pass
  for state in (None,Dict(),{'X':1},{1:2}):
   with self.assertRaises((TypeError,ValueError)):p.run(state,context=BoundaryContext())
 def test_conditional_global_shadow_explicit_gap(self):
  with self.assertRaises(UnsupportedNakedSyntax):prepare('Var x;Function F() If False Then Var x;EndIf;Return x;EndFunction',repairs=FLAGS)
 def test_inline_read_and_no_final_copy(self):
  p=prepare('x=1;r=x;',repairs=FLAGS)
  self.assertIn("_initial['r'] = _initial['x']",p.generated_source)
  state={};self.assertIs(p.run(state,context=BoundaryContext()),state)
  self.assertEqual(state,{'x':Decimal(1),'r':Decimal(1)})
  self.assertNotIn('_scope',p.generated_source);self.assertNotIn('_locals = locals()',p.generated_source)
  self.assertNotIn('_Cell(',p.generated_source)
 def test_baseline_module_globals_and_loop_results(self):
  source='Var x;Procedure F(a) a=a+1;x=x+1;EndProcedure x=1;s=0;For i=1 To 5 Do F(x);s=s+x;EndDo;r=s;'
  vm=Interpreter(execution_backend='interpreter');vm.execute(source)
  state=self.run_live(source)
  for key in ('x','r','s','i'):self.assertEqual(state[key],vm.variables[key])
 def test_local_calls_have_no_service_guards_without_authority_flag(self):
  source='Function F(Val x) Return x+1;EndFunction r=F(1);'
  p=prepare(source,repairs=FLAGS)
  self.assertNotIn('_context._check()',p.generated_source)
  self.assertEqual(p.run({},context=BoundaryContext())['r'],2)
  guarded=prepare(source,repairs=FLAGS+('authority_checkpoints',))
  self.assertIn('_context._check()',guarded.generated_source)
 def test_service_revocation_still_stops_calling_local_body(self):
  context=BoundaryContext();context._services['stop']=context.revoke
  p=prepare('Procedure F() Stop();x=9;EndProcedure x=1;F();x=2;',repairs=FLAGS)
  state={}
  with self.assertRaises(BoundaryViolation):p.run(state,context=context)
  self.assertEqual(state['x'],1)
 def test_missing_read_and_reference_error_location_matches_baseline(self):
  for source in ('r=Missing;','Procedure F(a) a=7;EndProcedure F(Missing);'):
   outcomes=[]
   for live in (False,True):
    try:
     if live:self.run_live(source)
     else:Interpreter(execution_backend='interpreter').execute(source,'live.bsl')
    except BSLRuntimeError as error:outcomes.append((error.message,error.line,error.column))
   self.assertEqual(len(outcomes),2);self.assertEqual(*outcomes)

class LiveReferenceSpoofTests(unittest.TestCase):
 def test_reference_binding_does_not_consult_host_class_property(self):
  from yadinassi.experimental_naked_live_state import source_reference,host_reference
  events=[]
  class Host:
   @property
   def __class__(self):events.append('class');return Reference
  value=Host();state={'x':value}
  self.assertIs(source_reference(state,'x').get(),value)
  self.assertIs(host_reference(state,'x').get(),value)
  self.assertEqual(events,[])
