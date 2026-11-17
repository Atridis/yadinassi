"""Paired fresh-process startup benchmarks with unchanged checkpoint checks."""
import json,subprocess,sys,statistics
from pathlib import Path
worker=r'''
import sys,time,json,statistics
sys.path.insert(0,'tests')
from test_configuration_source_runtime import source
from yadinassi.configuration_source_runtime import SourceApplication
out={}
for n in (0,100):
 code=('\n'.join('Function F%d(Val X=1) Return X;EndFunction'%i for i in range(n))+'\nProcedure OnStart() S=0;For I=1 To 1000 Do S=S+1;EndDo;Message(S);EndProcedure').encode()
 times=[]
 for _ in range(3):
  rows=[];app=SourceApplication(source(code),output=rows.append)
  start=time.perf_counter();app.start();times.append((time.perf_counter()-start)*1000)
  assert rows==['1\u00a0000'],rows
  app.close()
 out[str(n)]={'times_ms':times,'mean_ms':statistics.mean(times),'result':'1000'}
print(json.dumps(out))
'''
roots=[str(Path(x).resolve()) for x in sys.argv[1:]];samples=[[],[]]
for pair in range(7):
 for idx in ([0,1] if pair%2==0 else [1,0]):
  samples[idx].append(json.loads(subprocess.check_output([sys.executable,'-B','-c',worker],cwd=roots[idx],text=True)))
print(json.dumps({'samples':dict(zip(('before','after'),samples))},indent=2))
