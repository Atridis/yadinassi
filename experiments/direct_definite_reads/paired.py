import json,time,statistics
from unittest.mock import patch
from yadinassi.python_direct_definite import definite_module_reads
from yadinassi.python_direct import REPAIRS
from yadinassi.experimental_naked_collections import prepare
from yadinassi.experimental_naked_boundaries import BoundaryContext
cases={
'arithmetic':'s=0;For i=1 To 20000 Do s=s+i*2;EndDo;',
'local_arithmetic':'Function F(Val n) s=0;For i=1 To n Do s=s+i*2;EndDo;Return s;EndFunction r=F(20000);',
'calls':'Function F(Val x) Return x+1;EndFunction s=0;For i=1 To 20000 Do s=s+F(i);EndDo;'}
rows=[]
for name,source in cases.items():
 plans={}
 for mode in ('before','after'):
  with patch('yadinassi.python_direct_definite.definite_module_reads',definite_module_reads if mode=='after' else lambda _:frozenset()):
   t=time.perf_counter();plans[mode]=prepare(source,repairs=REPAIRS,_trusted_entry=True)
   rows.append(dict(case=name,mode=mode,prepare_ms=(time.perf_counter()-t)*1000))
 for trial in range(9):
  outputs=[]
  for mode in (('before','after') if trial%2==0 else ('after','before')):
   p=plans[mode];state={};ctx=BoundaryContext();t=time.perf_counter();p.run(state,context=ctx);dt=(time.perf_counter()-t)*1000
   outputs.append(state)
   rows.append(dict(case=name,mode=mode,trial=trial,ms=dt,control=str(state.get('r',state.get('s')))))
  assert outputs[0]==outputs[1],outputs
summary={case:{mode:statistics.median(r['ms'] for r in rows if r['case']==case and r['mode']==mode and 'ms'in r) for mode in ('before','after')} for case in cases}
print(json.dumps(summary,indent=2));open(__file__.replace('.py','.json'),'w').write(json.dumps(dict(summary=summary,rows=rows),indent=2))
