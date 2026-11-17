"""Alternating fresh-process pairs for isolated layout or regex candidates."""
import json,statistics,subprocess,sys
from pathlib import Path
worker=r'''
import hashlib,json,statistics,sys
from time import perf_counter
from yadinassi import Interpreter
from yadinassi.values import BSLArray
mode=sys.argv[1];cases={};count=50000
configs=[('server_one',1,0),('server_group100_empty',100,0),('server_group100_layout32',100,32)] if mode=='layout' else [('host_operation',0,0),('same_module_control',0,0)]
for name,group,variables in configs:
    vm=Interpreter(compilation_profile='managed-thick-file')
    if mode=='layout':
        source=('&AtServer\nVar '+','.join('S'+str(i) for i in range(variables))+';\n') if variables else ''
        source+='&AtServer\nFunction F(Val X) Return X+1;EndFunction\n'
        source+='\n'.join('&AtServer\nFunction G'+str(i)+'() Return '+str(i)+';EndFunction' for i in range(group-1))
        vm.execute(source);call='F(I)';prefix='';expected=count*(count+1)//2+count
    elif name=='host_operation':
        prefix='';expected=3*count
        if mode=='detached':
            a=BSLArray();a.add(3);vm.variables['a']=a;call='A.Get(0)'
        else:call='StrLen("abc")'
    else:call='F(I)';prefix='Function F(Val X) Return X+1;EndFunction ';expected=count*(count+1)//2+count
    source=prefix+'N=0;For I=1 To '+str(count)+' Do N=N+'+call+';EndDo;N;'
    plan=vm.prepare(source);vm.execute_prepared(plan);times=[];outputs=[]
    for _ in range(3):
        start=perf_counter();value=vm.execute_prepared(plan);times.append((perf_counter()-start)*1000)
        if value!=expected:raise RuntimeError('wrong result '+name)
        outputs.append(hashlib.sha256(str(value).encode()).hexdigest())
    vm.close();cases[name]={'mean_ms':statistics.mean(times),'times_ms':times,'outputs':outputs}
print(json.dumps(cases))
'''
mode=sys.argv[1];roots=[str(Path(p).resolve()) for p in sys.argv[2:]]
if mode not in ('layout','regex','detached') or len(roots)!=2:raise SystemExit('measure.py layout|regex BEFORE AFTER')
samples=[[],[]]
for pair in range(7):
    for index in ([0,1] if pair%2==0 else [1,0]):
        result=subprocess.run([sys.executable,'-B','-c',worker,mode],cwd=roots[index],capture_output=True,text=True,check=True)
        samples[index].append(json.loads(result.stdout))
for name in samples[0][0]:
    if len({out for group in samples for sample in group for out in sample[name]['outputs']})!=1:raise RuntimeError('output mismatch')
print(json.dumps({'python':sys.version,'mode':mode,'commits':[subprocess.check_output(['git','rev-parse','HEAD'],cwd=root,text=True).strip() for root in roots],
    'pairs':7,'samples':dict(zip(('before','after'),samples)),
    'median_ms':{side:{name:statistics.median(sample[name]['mean_ms'] for sample in group) for name in group[0]} for side,group in zip(('before','after'),samples)}},indent=2))
