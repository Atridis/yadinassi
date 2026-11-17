"""Alternating fresh-process paired prepared server calls; timings exclude preparation."""
import argparse,json,statistics,subprocess,sys
from pathlib import Path
CHILD=r'''
import json,sys,time
sys.path.insert(0,sys.argv[1])
from yadinassi import Interpreter
source="\n&AtServer\nFunction F(Val X) Return X; EndFunction\nR=0;For I=1 To 10000 Do R=F(42); EndDo;"
case=sys.argv[2]
if case=='nested':source=source.replace('R=0;', 'A=New Array;A.Add(42);R=0;').replace('F(42)', 'F(A)')
if case=='same_side':source=source.replace('&AtServer', '')
vm=Interpreter();plan=vm.prepare(source);vm.execute_prepared(plan)
times=[]
for _ in range(3):
 t=time.perf_counter();vm.execute_prepared(plan);times.append(time.perf_counter()-t)
 assert vm.variables['r']==([42] if case=='nested' else 42)
print(json.dumps(dict(seconds=times,result=str(vm.variables['r']))))
'''
p=argparse.ArgumentParser();p.add_argument('baseline');p.add_argument('candidate');a=p.parse_args()
rows=[]
for pair in range(7):
 row={'pair':pair}
 for label in (('baseline','candidate') if pair%2==0 else ('candidate','baseline')):
  row[label]={case:json.loads(subprocess.check_output([sys.executable,'-I','-B','-c',CHILD,str(Path(getattr(a,label)).resolve()),case])) for case in ('scalar','nested','same_side')}
 rows.append(row)
print(json.dumps({'pairs':rows,'median_seconds':{case:{k:statistics.median(statistics.median(r[k][case]['seconds']) for r in rows) for k in ('baseline','candidate')} for case in ('scalar','nested','same_side')}},indent=2))
