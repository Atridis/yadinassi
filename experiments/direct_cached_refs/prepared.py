"""Reusable prepared-plan timing, excluding parse/prepare; no regression thresholds."""
import json,os,statistics,subprocess,sys,time
from pathlib import Path
CASES={
 'byref':'Procedure Inc(a) a=a+1;EndProcedure s=0;For i=1 To 10000 Do Inc(s);EndDo;',
 'byvalue':'Function F(Val a) Return a+1;EndFunction s=0;For i=1 To 10000 Do s=F(s);EndDo;',
 'arithmetic':'s=0;For i=1 To 10000 Do s=s+1;EndDo;'}
if len(sys.argv)>1 and sys.argv[1]=='one':
 from yadinassi.experimental_naked_collections import prepare
 from yadinassi.experimental_naked_boundaries import BoundaryContext
 from yadinassi.python_direct import REPAIRS
 rows=[]
 for name,source in CASES.items():
  plan=prepare(source,repairs=REPAIRS,_trusted_entry=True);state={};context=BoundaryContext()
  start=time.perf_counter();plan.run(state,context=context);elapsed=(time.perf_counter()-start)*1000
  assert state['s']==10000
  rows.append(dict(case=name,ms=elapsed,control=str(state['s'])))
 print(json.dumps(rows));raise SystemExit
before,after=map(Path,sys.argv[1:3]);rows=[]
for trial in range(7):
 for mode in (('before','after') if trial%2==0 else ('after','before')):
  root=before if mode=='before' else after
  result=json.loads(subprocess.check_output([sys.executable,str(Path(__file__).resolve()),'one'],cwd=root,env=dict(os.environ,PYTHONPATH=str(root))))
  rows.extend(dict(trial=trial,mode=mode,**r) for r in result)
summary={case:{mode:statistics.median(r['ms'] for r in rows if r['case']==case and r['mode']==mode) for mode in ('before','after')} for case in CASES}
print(json.dumps(summary,indent=2));Path(__file__).with_suffix('.json').write_text(json.dumps(dict(summary=summary,rows=rows),indent=2))
