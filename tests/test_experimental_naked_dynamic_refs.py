import os
import unittest
from decimal import Decimal
from unittest.mock import patch
from yadinassi import Interpreter
from yadinassi.values import HostFunction,Reference
from yadinassi.experimental_naked_collections import prepare
from yadinassi.experimental_naked_boundaries import BoundaryContext

FLAGS=('service_boundaries','byref_routines','dynamic_host_refs','error_boundaries','array_index_contract')
class DynamicRefsTests(unittest.TestCase):
 def setUp(self):
  p=patch.dict(os.environ,{'YADINASSI_UNSAFE_COLLECTION_ABLATION':'1'});p.start();self.addCleanup(p.stop)
 def compare(self,source,signature=(0,),mutate=False):
  results=[]
  for naked in (False,True):
   events=[]
   def host(*args):
    events.append(tuple(isinstance(x,Reference) for x in args))
    for i,x in enumerate(args):
     if isinstance(x,Reference):x.set(Decimal(7) if len(args)==1 else x.get()+i+1)
   wrapper=HostFunction('h',host,reference_parameters=frozenset(signature))
   def change():wrapper.reference_parameters=frozenset({1});return Decimal(0)
   services={'Get':lambda:wrapper,'Change':change}
   p=None;vm=None
   try:
    if naked:
     p=prepare(source,source_name='ref.bsl',repairs=FLAGS);state=p.run(context=BoundaryContext(services=services))
    else:
     vm=Interpreter(execution_backend='interpreter')
     for name,fn in services.items():vm.register_function(name,fn)
     vm.execute(source,'ref.bsl');state=vm.variables
    status='ok'
   except Exception as e:
    status=(type(e).__name__,getattr(e,'message',str(e)),getattr(e,'line',None),getattr(e,'column',None));state=p.last_state if naked else vm.variables
   results.append((status,events,state.get('r'),state.get('x')))
  self.assertEqual(*results)
  return results[0]
 def test_name_and_canonical_reference(self):self.compare('x=1;f=Get();f(x);r=x;')
 def test_nonlvalue_stays_raw(self):self.assertEqual(self.compare('f=Get();f(1+2);')[1],[(False,)])
 def test_unknown_name_rejected(self):self.compare('f=Get();f(x);')
 def test_map_missing_output(self):self.compare('m=New Map;f=Get();f(m["x"]);r=m["x"];')
 def test_array_missing_rejected(self):self.compare('a=New Array;f=Get();f(a[0]);')
 def test_same_actual_live_alias(self):self.compare('x=1;f=Get();f(x,x);r=x;',signature=(0,1))
 def test_signature_mutation_live_per_argument(self):self.compare('x=1;f=Get();f(Change(),x);r=x;',signature=())
 def test_omissions_before_effects(self):self.compare('x=1;f=Get();f(,Change(),x);r=x;')
 def test_routine_local_and_boxed_forwarding(self):
  self.compare('Function G() x=1;f=Get();f(x);Return x;EndFunction r=G();')
  self.compare('Procedure G(x) f=Get();f(x);EndProcedure x=1;G(x);r=x;')
 def test_module_global_reference(self):self.compare('Var x;Procedure G() f=Get();f(x);EndProcedure x=1;G();r=x;')
 def test_lexical_not_value_attribute(self):
  p=prepare('x=1;f=Get();f(x);r=x;',repairs=FLAGS)
  self.assertNotIn('_Cell(',p.generated_source)
  self.assertIn('nonlocal',p.generated_source)
 def test_escaped_reference_lifetime_and_snapshot_limit(self):
  kept=[]
  wrapper=HostFunction('save',lambda ref:kept.append(ref),reference_parameters=frozenset({0}))
  p=prepare('x=1;f=Get();f(x);',repairs=FLAGS)
  state=p.run(context=BoundaryContext(services={'Get':lambda:wrapper}))
  self.assertIs(type(kept[0]),Reference)
  kept[0].set(Decimal(9))
  self.assertEqual(kept[0].get(),Decimal(9))
  # Deliberate current limitation: exported dict is not live VM module storage.
  self.assertEqual(state['x'],Decimal(1))
  self.assertIs(state,p.last_state)
 def test_missing_name_catchable_without_host_effect(self):
  self.compare('f=Get();Try f(x);Except r=7;EndTry;')
 def test_explicit_constructor_unchanged_with_dynamic_flag(self):
  events=[]
  p=prepare('x=New Box(7);',repairs=FLAGS,constructors=('Box',))
  result=p.run(context=BoundaryContext(services={'new:box':lambda v:events.append(v) or v}))
  self.assertEqual(result['x'],Decimal(7))
  self.assertEqual(events,[Decimal(7)])
