"""Trusted synthetic fixtures; not native1C evidence or general service support."""
import os,sys,json,time,subprocess,hashlib
from pathlib import Path
from decimal import Decimal
ROOT=Path(__file__).resolve().parents[3];HERE=Path(__file__).parent
os.environ['YADINASSI_UNSAFE_COLLECTION_ABLATION']='1'
FLAGS=('typed_map_keys','array_index_contract','array_insert_shape','constructor_bounds','byref_routines','error_boundaries','service_boundaries','bsl_truth','bsl_presentation','native_order','typed_find','structure_fields','method_values','dynamic_host_refs','live_module_state')
def normalize(x):
 if type(x) is Decimal:return str(x)
 if type(x) in (bool,str,type(None)):return x
 raise TypeError(type(x).__name__)
CONTROLS={'invoice':{'result':'301','eventotal':'176','oddtotal':'125','aliasquantity':'11','rowcount':'6','trace':'101010'},'graph_bfs':{'result':'4','trace':'1234','edges':'5','aliasfound':True,'cloneabsent':True,'queuecount':'4'}}
def checksum(values,base):
 result=0
 for value in values:result=(result*base+value)%1000003
 return str(result)
CONTROLS['invoice_batch']={'result':str(sum(i*(10+i) for i in range(1,1001))),'eventotal':str(sum(i*(10+i) for i in range(2,1001,2))),'oddtotal':str(sum(i*(10+i) for i in range(1,1001,2))),'aliasquantity':'11','rowcount':'1000','trace':checksum([i%2 for i in range(1,1001)],10)}
CONTROLS['graph_batch']={'result':'1000','trace':checksum(range(1,1001),1001),'edges':'1998','aliasfound':True,'cloneabsent':True,'queuecount':'1000'}
def one(name,backend,warm=0):
 from yadinassi.runtime import Interpreter
 from yadinassi.syntax.parser import parse
 from yadinassi.experimental_naked_collections import prepare
 from yadinassi.experimental_naked_boundaries import BoundaryContext
 from yadinassi.values import HostFunction
 events=[]
 def observe(value):events.append(normalize(value))
 expected_events=([str(i%2) for i in range(1,1001)] if name=='invoice_batch' else [str(i) for i in range(1,1001)] if name=='graph_batch' else ['1','0','1','0','1','0'] if name=='invoice' else ['1','2','3','4'])
 source=(HERE/(name+'.bsl')).read_text();start=time.perf_counter_ns()
 if backend=='experimental':
  program=prepare(source,repairs=FLAGS);ctx=BoundaryContext(services={'Observe':observe});live={}
  def run():
   events.clear();return program.run(live,context=ctx)
 else:
  vm=Interpreter(execution_backend=backend);vm.functions['observe']=HostFunction('Observe',observe);program=parse(source)
  if backend=='compiled-strict':vm._compiled().prepare(program,module_entry=True)
  def run():
   events.clear();vm._scheduler.run_inline(vm.block(program));return vm.variables
 state=run();cold=(time.perf_counter_ns()-start)/1e6
 actual={k:normalize(state[k]) for k in CONTROLS[name]}
 if events!=expected_events:raise AssertionError(('events',events))
 if actual!=CONTROLS[name]:raise AssertionError((name,backend,actual,CONTROLS[name]))
 samples=[]
 for _ in range(warm):
  start=time.perf_counter_ns();state=run();samples.append((time.perf_counter_ns()-start)/1e6)
  if events!=expected_events:raise AssertionError(('warm events',events))
  if {k:normalize(state[k]) for k in CONTROLS[name]}!=CONTROLS[name]:raise AssertionError('warm control')
 return dict(name=name,backend=backend,controls=actual,events=events[:] if len(events)<10 else {'count':len(events),'sha256':hashlib.sha256(json.dumps(events).encode()).hexdigest()},cold_ms=cold,warm_ms=samples)
if sys.argv[1]=='prepare':
 from yadinassi.experimental_naked_collections import prepare
 path=Path(sys.argv[2]);start=time.perf_counter_ns()
 try:
  p=prepare(path.read_text(encoding='utf-8-sig'),repairs=FLAGS)
  result=dict(status='prepared_not_executed',generated_bytes=len(p.generated_source.encode()),required_services=list(p.required_services))
 except Exception as e:result=dict(status='unsupported_or_error',error_type=type(e).__name__,first_error=str(e))
 print(json.dumps(dict(file=path.name,elapsed_ms=(time.perf_counter_ns()-start)/1e6,**result)))
elif sys.argv[1]=='one':
 print(json.dumps(one(sys.argv[2],sys.argv[3],int(sys.argv[4]))))
elif sys.argv[1]=='coverage':
 rows=[]
 for p in sorted((ROOT/'integrational_tests/tests').glob('*.bsl')):
  try:rows.append(json.loads(subprocess.check_output([sys.executable,__file__,'prepare',str(p)],env=dict(os.environ,PYTHONPATH=str(ROOT)),timeout=20)))
  except subprocess.TimeoutExpired:rows.append(dict(file=p.name,status='timeout_20s_not_executed'))
 print(json.dumps(dict(flags=FLAGS,scope='prepare only; no fixture executed; no automatic constructor declaration',rows=rows),indent=2))
else:
 rows=[]
 for name in CONTROLS:
  for backend in ('interpreter','compiled-strict','experimental'):
   try:rows.append(one(name,backend,int(sys.argv[1])))
   except Exception as e:rows.append(dict(name=name,backend=backend,error_type=type(e).__name__,error=str(e)))
 print(json.dumps(dict(flags=FLAGS,scope='trusted synthetic; not native1C; cold includes parse/admission/first execution; warm excludes prepare',rows=rows),indent=2))
