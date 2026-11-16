"""Public default API timing, including parse/prepare; no regression thresholds."""
import json,os,statistics,subprocess,sys,time
from pathlib import Path
CASES={
 'byref':'Procedure Inc(a) a=a+1;EndProcedure s=0;For i=1 To 10000 Do Inc(s);EndDo;',
 'byvalue':'Function F(Val a) Return a+1;EndFunction s=0;For i=1 To 10000 Do s=F(s);EndDo;',
 'arithmetic':'s=0;For i=1 To 10000 Do s=s+1;EndDo;'}
if len(sys.argv)>1 and sys.argv[1]=='one':
 from yadinassi import Interpreter
 rows=[]
 for name,source in CASES.items():
  vm=Interpreter();start=time.perf_counter();vm.execute(source);elapsed=(time.perf_counter()-start)*1000
  assert vm.variables['s']==10000
  rows.append(dict(case=name,ms=elapsed,control=str(vm.variables['s'])))
 print(json.dumps(rows));raise SystemExit
before,after=map(Path,sys.argv[1:3]);rows=[]
for trial in range(7):
 for mode in (('before','after') if trial%2==0 else ('after','before')):
  root=before if mode=='before' else after
  result=json.loads(subprocess.check_output([sys.executable,str(Path(__file__).resolve()),'one'],cwd=root,env=dict(os.environ,PYTHONPATH=str(root))))
  rows.extend(dict(trial=trial,mode=mode,**r) for r in result)
summary={case:{mode:statistics.median(r['ms'] for r in rows if r['case']==case and r['mode']==mode) for mode in ('before','after')} for case in CASES}
print(json.dumps(summary,indent=2));Path(__file__).with_suffix('.json').write_text(json.dumps(dict(summary=summary,rows=rows),indent=2))
