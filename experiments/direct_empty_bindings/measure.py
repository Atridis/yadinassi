"""Prepared invocation cost; preserve admission, do not retain generated callees."""
import json,statistics,subprocess,sys
from pathlib import Path
worker=r'''
import json,statistics
from decimal import Decimal
from time import perf_counter
from yadinassi import Interpreter
cases={}
for name in ('host_plain','host_with_routines','persistent_one','persistent_500','local_control'):
    vm=Interpreter()
    declarations='Function F(Val X) Return X+1; EndFunction\n'
    if name=='persistent_500':declarations+='\n'.join(f'Function Extra{i}() Return {i}; EndFunction' for i in range(499))
    if name in ('host_with_routines','persistent_one','persistent_500'):vm.execute(declarations)
    host=name.startswith('host')
    source='R=0;For I=1 To 10000 Do R=R+'+('StrLen("abc")' if host else 'F(I)')+';EndDo;'
    if name=='local_control':source=declarations+source
    plan=vm.prepare(source)
    vm.execute_prepared(plan)
    samples=[]
    for _ in range(5):
        start=perf_counter();vm.execute_prepared(plan);samples.append((perf_counter()-start)*1000)
        if vm.variables['r']!=Decimal(30000 if host else 50015000):raise RuntimeError('wrong result')
    cases[name]={'samples_ms':samples,'median_ms':statistics.median(samples),'result':str(vm.variables['r'])}
    vm.close()
print(json.dumps(cases))
'''
roots=[str(Path(arg).resolve()) for arg in sys.argv[1:]]
if len(roots)!=2:raise SystemExit('measure.py BEFORE AFTER')
samples=[[],[]]
for pair in range(7):
    for index in ([0,1] if pair%2==0 else [1,0]):
        result=subprocess.run([sys.executable,'-B','-c',worker],cwd=roots[index],capture_output=True,text=True,check=True)
        samples[index].append(json.loads(result.stdout))
print(json.dumps({'baseline':subprocess.check_output(['git','rev-parse','HEAD'],cwd=roots[0],text=True).strip(),
    'python':sys.version,'pairs':7,'iterations':10000,'warmup_runs':1,'measured_runs_per_case':5,
    'samples':dict(zip(('before','after'),samples)),
    'medians_ms':{label:{name:statistics.median(item[name]['median_ms'] for item in group) for name in group[0]}
        for label,group in zip(('before','after'),samples)}},indent=2))
