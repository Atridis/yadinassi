"""Non-production Map inlining and module-local upper-bound prototypes."""
import ast,json,statistics,sys,time
from decimal import Decimal
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from yadinassi import Interpreter
from yadinassi.experimental_naked_collections import _TypedMap
BASE='9516625c113621be72343fa363a9558f32a30dea'
old_get,old_set=_TypedMap.get,_TypedMap.__setitem__
def candidate_get(self,key,default=None):
    kind=type(key)
    token=(kind,key) if kind in (Decimal,bool,str) or key is None else (object,id(key))
    entry=dict.get(self,token)
    return default if entry is None else entry[1]
def candidate_set(self,key,value):
    kind=type(key)
    token=(kind,key) if kind in (Decimal,bool,str) or key is None else (object,id(key))
    dict.__setitem__(self,token,(key,value))

# Deliberately incomplete upper-bound experiment, never production lowering.
# Replacing all dictionary reads by Python locals fails live callback semantics.
def localize(plan):
    tree=ast.parse(plan._plan.generated_source);keys=set()
    def key(node):
        return node.slice.value if isinstance(node,ast.Subscript) and isinstance(node.value,ast.Name) and node.value.id=='_initial' and isinstance(node.slice,ast.Constant) and type(node.slice.value) is str else None
    class Rewrite(ast.NodeTransformer):
        def visit_Call(self,node):
            if isinstance(node.func,ast.Attribute) and isinstance(node.func.value,ast.Name) and node.func.value.id=='_initial' and node.func.attr=='get' and node.args and isinstance(node.args[0],ast.Constant) and type(node.args[0].value) is str:
                name=node.args[0].value;keys.add(name)
                return ast.copy_location(ast.Name(id='cache_'+name,ctx=ast.Load()),node)
            return self.generic_visit(node)
        def visit_Assign(self,node):
            new=[]
            for target in node.targets:
                name=key(target)
                if name is not None:keys.add(name);new.append(ast.Name(id='cache_'+name,ctx=ast.Store()))
                new.append(target)
            node.targets=new;node.value=self.visit(node.value);return node
        def visit_Subscript(self,node):
            name=key(node)
            if name is not None and isinstance(node.ctx,ast.Load):keys.add(name);return ast.copy_location(ast.Name(id='cache_'+name,ctx=ast.Load()),node)
            return self.generic_visit(node)
    tree=Rewrite().visit(tree)
    init=ast.parse('\n'.join('cache_'+name+' = _initial.get('+repr(name)+', _LIVE_UNSET)' for name in sorted(keys))).body
    tree.body[0].body=init+tree.body[0].body;ast.fix_missing_locations(tree)
    namespace=plan._plan.function.__globals__.copy();exec(compile(tree,'<unsafe locals measurement>','exec'),namespace)
    plan._plan.function=namespace['naked_module']

cases={
 'map_numeric':('m=New Map;For k=0 To 999 Do m.Insert(k,0);EndDo;For i=0 To 19999 Do k=i%1000;m.Insert(k,m.Get(k)+1);EndDo;r=0;For k=0 To 999 Do r=r+m.Get(k);EndDo;',20000),
 'map_strings':('keys=New Array;keys.Add("red");keys.Add("blue");keys.Add("green");keys.Add("yellow");m=New Map;For j=0 To 3 Do m.Insert(keys[j],0);EndDo;For i=0 To 19999 Do k=keys[i%4];m.Insert(k,m.Get(k)+1);EndDo;r=m.Get("red")+m.Get("blue")+m.Get("green")+m.Get("yellow");',20000),
 'array_sum':('a=New Array;For i=0 To 9999 Do a.Add(i);EndDo;r=0;For j=0 To a.Count()-1 Do r=r+a.Get(j);EndDo;',49995000),
 'numeric_sum':('r=0;For i=0 To 99999 Do r=r+i;EndDo;',4999950000)}
rows=[]
try:
 for candidate,names in [('map',('map_numeric','map_strings')),('locals',('array_sum','numeric_sum'))]:
  for pair in range(7):
   for mode in (('before','after') if pair%2==0 else ('after','before')):
    _TypedMap.get=candidate_get if candidate=='map' and mode=='after' else old_get
    _TypedMap.__setitem__=candidate_set if candidate=='map' and mode=='after' else old_set
    for name in names:
     vm=Interpreter();plan=vm.prepare(cases[name][0])
     if candidate=='locals' and mode=='after':localize(plan)
     times=[]
     for repeat in range(6):
      start=time.perf_counter();vm.execute_prepared(plan);times.append((time.perf_counter()-start)*1000)
      if vm.variables['r']!=cases[name][1]:raise RuntimeError('wrong result '+name)
     rows.append(dict(candidate=candidate,pair=pair,mode=mode,case=name,samples_ms=times));vm.close()
finally:_TypedMap.get=old_get;_TypedMap.__setitem__=old_set
# A real registered callback can read/write the same module variables mid-loop.
callback=[]
for localized in (False,True):
 vm=Interpreter();vm.register_function('Change',lambda:vm.variables.__setitem__('i',Decimal(10)))
 plan=vm.prepare('r=0;For i=0 To 2 Do Change();r=r+i;EndDo;')
 if localized:localize(plan)
 vm.execute_prepared(plan);callback.append(str(vm.variables['r']));vm.close()
summary={name:{mode:statistics.median(t for r in rows if r['case']==name and r['mode']==mode for t in r['samples_ms'][1:]) for mode in ('before','after')} for name in cases}
print(json.dumps(dict(baseline=BASE,python=sys.version,summary_ms=summary,callback_result=callback,cases=cases,samples=rows),indent=2))
