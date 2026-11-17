"""Alternating fresh-process pairs, exact output checks, no speed gate."""
import json,statistics,subprocess,sys
from pathlib import Path
worker=r'''
import hashlib,json,statistics
from time import perf_counter
from yadinassi import Interpreter
cases={}
for name,count,observe in [('small_silent',0,False),('large_silent',100,False),('large_description',100,True)]:
    functions='\n'.join('Function F'+str(i)+'() Return '+str(i)+';EndFunction' for i in range(count))
    source=functions+'\nN=0;For I=1 To 1000 Do Try X=1/0;Except N=N+1;'+('D=ErrorDescription();' if observe else '')+'EndTry;EndDo;'
    vm=Interpreter();plan=vm.prepare(source,'measured.bsl');times=[];outputs=[]
    for _ in range(3):
        start=perf_counter();vm.execute_prepared(plan);times.append((perf_counter()-start)*1000)
        if vm.variables['n']!=1000:raise RuntimeError('wrong handled count')
        outputs.append(hashlib.sha256(json.dumps([str(vm.variables['n']),vm.variables.get('d')]).encode()).hexdigest())
    vm.close();cases[name]={'mean_ms':statistics.mean(times),'times_ms':times,'outputs':outputs}
print(json.dumps(cases))
'''
roots=[str(Path(root).resolve()) for root in sys.argv[1:]]
if len(roots)!=2:raise SystemExit('measure.py BEFORE AFTER')
samples=[[],[]]
for pair in range(7):
    for index in ([0,1] if pair%2==0 else [1,0]):
        result=subprocess.run([sys.executable,'-B','-c',worker],cwd=roots[index],capture_output=True,text=True,check=True)
        samples[index].append(json.loads(result.stdout))
for name in samples[0][0]:
    if len({value for group in samples for sample in group for value in sample[name]['outputs']})!=1:raise RuntimeError('output mismatch: '+name)
print(json.dumps({'python':sys.version,'commits':[subprocess.check_output(['git','rev-parse','HEAD'],cwd=root,text=True).strip() for root in roots],
    'pairs':7,'executions_per_case':3,'samples':dict(zip(('before','after'),samples)),
    'median_ms':{side:{name:statistics.median(sample[name]['mean_ms'] for sample in group) for name in group[0]} for side,group in zip(('before','after'),samples)}},indent=2))
