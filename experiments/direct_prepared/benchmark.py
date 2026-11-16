"""Explicit public API reuse: cold preparation and warm execution separated."""
import json,time,statistics,sys
from pathlib import Path
from yadinassi import Interpreter
ROOT=Path(__file__).resolve().parents[2]
CASES={
 'invoice_batch':(ROOT/'experiments/naked_translation/business/invoice_batch.bsl').read_text(),
 'graph_batch':(ROOT/'experiments/naked_translation/business/graph_batch.bsl').read_text(),
 'arithmetic':'s=0;For i=1 To 10000 Do s=s+i;EndDo;',
 'byref':'Procedure Inc(a) a=a+1;EndProcedure s=0;For i=1 To 10000 Do Inc(s);EndDo;',
 'byvalue':'Function F(Val x) Return x+1;EndFunction s=0;For i=1 To 10000 Do s=F(s);EndDo;'}
EXPECTED={'invoice_batch':sum(i*(10+i) for i in range(1,1001)),'graph_batch':1000,'arithmetic':50005000,'byref':10000,'byvalue':10000}
def checksum(values,base):
 result=0
 for value in values:result=(result*base+value)%1000003
 return result
CONTROLS={
 'invoice_batch':dict(result=EXPECTED['invoice_batch'],eventotal=sum(i*(10+i) for i in range(2,1001,2)),oddtotal=sum(i*(10+i) for i in range(1,1001,2)),aliasquantity=11,rowcount=1000,trace=checksum([i%2 for i in range(1,1001)],10)),
 'graph_batch':dict(result=1000,trace=checksum(range(1,1001),1001),edges=1998,aliasfound=True,cloneabsent=True,queuecount=1000)}
rows=[]
for name,source in CASES.items():
 vms={mode:Interpreter() for mode in ('execute','prepared')};events={mode:[] for mode in vms}
 for mode,vm in vms.items():vm.register_function('Observe',events[mode].append)
 start=time.perf_counter();plan=vms['prepared'].prepare(source);prepare_ms=(time.perf_counter()-start)*1000
 for trial in range(8):
  for mode in (('execute','prepared') if trial%2==0 else ('prepared','execute')):
   vm=vms[mode];events[mode].clear();start=time.perf_counter()
   if mode=='execute':vm.execute(source)
   else:vm.execute_prepared(plan)
   elapsed=(time.perf_counter()-start)*1000
   value=vm.variables['result' if name.endswith('batch') else 's']
   assert value==EXPECTED[name],(name,mode,value)
   if name.endswith('batch'):
    assert {key:vm.variables[key] for key in CONTROLS[name]}==CONTROLS[name]
    assert events[mode]==([i%2 for i in range(1,1001)] if name=='invoice_batch' else list(range(1,1001)))
   rows.append(dict(case=name,mode=mode,trial=trial,ms=elapsed,prepare_ms=prepare_ms if mode=='prepared' else None,control=str(value),event_count=len(events[mode])))
summary={name:{mode:dict(first_run_ms=next(r['ms'] for r in rows if r['case']==name and r['mode']==mode),warm_median_ms=statistics.median(r['ms'] for r in rows if r['case']==name and r['mode']==mode and r['trial']>0)) for mode in ('execute','prepared')} for name in CASES}
for name in CASES:summary[name]['prepare_ms']=next(r['prepare_ms'] for r in rows if r['case']==name and r['mode']=='prepared')
Path(__file__).with_suffix('.json').write_text(json.dumps(dict(summary=summary,rows=rows),indent=2));print(json.dumps(summary,indent=2))
