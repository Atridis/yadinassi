"""Independent Array-read and Map-token candidates, representative numeric work."""
import ast
from contextlib import closing
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import statistics
import subprocess
import sys
from time import perf_counter

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from yadinassi import Interpreter
from yadinassi import python_direct_arrays as arrays
from yadinassi import experimental_naked_collections as collections
BASE='f52b1bfacfb965505f86d2efb145f7ff214671d5'
namespace={'__package__':'yadinassi'}
exec(compile(subprocess.check_output(['git','show',BASE+':yadinassi/python_direct_arrays.py'],cwd=ROOT,text=True),'<baseline array facts>','exec'),namespace)
original_facts=namespace['array_facts']
def old_facts(*args,definite_reads=None,**kwargs):return original_facts(*args,**kwargs)
new_facts=arrays.array_facts
module=ast.parse(subprocess.check_output(['git','show',BASE+':yadinassi/experimental_naked_collections.py'],cwd=ROOT,text=True))
cls=next(n for n in module.body if isinstance(n,ast.ClassDef) and n.name=='_TypedMap')
namespace=vars(collections).copy()
exec(compile(ast.Module(body=[cls],type_ignores=[]),'<baseline map>','exec'),namespace)
old_token=namespace['_TypedMap'].token
original_token=collections._TypedMap.token
# Rejected production candidate retained here so the noisy Map result reproduces.
def candidate_token(key):
    kind=type(key)
    if kind is Decimal or kind is bool or kind is str or key is None:return kind,key
    return object,id(key)
new_token=candidate_token
body='a=New Array;For i=0 To 9999 Do a.Add(i);EndDo;s=0;For j=0 To a.Count()-1 Do s=s+a.Get(j);EndDo;'
cases={
 'array_sum':(body+'r=s;',49995000),
 'array_alias':('a=New Array;For i=0 To 9999 Do a.Add(i%100);EndDo;b=a;s=0;For j=0 To b.Count()-1 Do s=s+b[j]*2;EndDo;r=s;',990000),
 'routine_control':('Function F() '+body+'Return s;EndFunction r=F();',49995000),
 'map_numeric_counts':('m=New Map;For k=0 To 999 Do m.Insert(k,0);EndDo;For i=0 To 19999 Do k=i%1000;m.Insert(k,m.Get(k)+1);EndDo;r=0;For k=0 To 999 Do r=r+m.Get(k);EndDo;',20000),
 'map_string_counts':('keys=New Array;keys.Add("red");keys.Add("blue");keys.Add("green");keys.Add("yellow");m=New Map;For j=0 To 3 Do m.Insert(keys[j],0);EndDo;For i=0 To 19999 Do k=keys[i%4];m.Insert(k,m.Get(k)+1);EndDo;r=m.Get("red")+m.Get("blue")+m.Get("green")+m.Get("yellow");',20000),
}
rows=[]
try:
 for candidate in ('array','map'):
  selected=tuple(cases)[:3] if candidate=='array' else tuple(cases)[3:]
  for pair in range(7):
   for mode in (('before','after') if pair%2==0 else ('after','before')):
    arrays.array_facts=new_facts if candidate=='array' and mode=='after' else old_facts
    collections._TypedMap.token=staticmethod(new_token if candidate=='map' and mode=='after' else old_token)
    for name in selected:
     source,expected=cases[name]
     with closing(Interpreter()) as vm:
      plan=vm.prepare(source)
      for route in ('prepared','execute_source'):
       times=[]
       for repeat in range(6):
        start=perf_counter()
        if route=='prepared':vm.execute_prepared(plan)
        else:vm.execute(source)
        times.append((perf_counter()-start)*1000)
        if vm.variables['r']!=expected:raise RuntimeError('wrong result '+name)
       rows.append(dict(candidate=candidate,pair=pair,mode=mode,case=name,route=route,samples_ms=times))
finally:
 arrays.array_facts=new_facts;collections._TypedMap.token=staticmethod(original_token)
summary={}
for name in cases:
 summary[name]={route:{mode:statistics.median(t for row in rows if row['case']==name and row['route']==route and row['mode']==mode for t in row['samples_ms'][1:]) for mode in ('before','after')} for route in ('prepared','execute_source')}
print(json.dumps(dict(baseline=BASE,python=sys.version,summary_ms=summary,cases=cases,samples=rows),indent=2))
