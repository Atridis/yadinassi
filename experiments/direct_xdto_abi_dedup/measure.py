"""Seven alternating fresh-process pairs for XDTO ABI requirement deduplication."""
import json,statistics,subprocess,sys
from pathlib import Path
worker=r'''
import hashlib,json,statistics,sys
from time import perf_counter
from pathlib import Path
import yadinassi
module_file=str(Path(yadinassi.__file__).resolve())
if Path(module_file).parent.parent!=Path.cwd().resolve():raise RuntimeError("wrong package root")
sys.path.insert(0,'tests')
from test_source_xdto_packages import SourceXDTOTests
from yadinassi.configuration_source_runtime import SourceApplication
from test_configuration_source_runtime import source
cases={}
for name in ('local_create_value','global_create_value','source_control'):
    app=SourceApplication(source(b'',SourceXDTOTests().mapping()),output=lambda _:None)
    app.start();vm=app.interpreter
    if name=='source_control':code='N=0;For I=1 To 10000 Do N=N+1;EndDo;N;';expected=10000
    else:
        vm.execute('F='+('New XDTOFactory' if name.startswith('local') else 'XDTOFactory')+';T=F.Type("http://www.w3.org/2001/XMLSchema","string");')
        code='N=0;For I=1 To 100 Do V=F.Create(T,"x");If V.Value="x" Then N=N+1;EndIf;EndDo;N;';expected=100
    vm.execute(code);times=[];outputs=[]
    for _ in range(3):
        start=perf_counter();value=vm.execute(code);times.append((perf_counter()-start)*1000)
        if value!=expected:raise RuntimeError('wrong result '+name)
        outputs.append(hashlib.sha256(str(value).encode()).hexdigest())
    app.close();cases[name]={'mean_ms':statistics.mean(times),'times_ms':times,'outputs':outputs}
print(json.dumps({'cases':cases,'module_file':module_file}))
'''
mode=sys.argv[1];roots=[str(Path(p).resolve()) for p in sys.argv[2:]]
if mode!='xdto' or len(roots)!=2:raise SystemExit('measure.py xdto BEFORE AFTER')
def state(root):
    def git(*args):return subprocess.check_output(['git',*args],cwd=root,text=True).strip()
    return {'head':git('rev-parse','HEAD'),'tree':git('rev-parse','HEAD^{tree}'),'status':git('status','--porcelain')}
before=[state(root) for root in roots]
if any(item['status'] for item in before):raise RuntimeError('benchmark roots must be clean')
samples=[[],[]];module_files=[[],[]]
for pair in range(7):
    for index in ([0,1] if pair%2==0 else [1,0]):
        result=subprocess.run([sys.executable,'-B','-c',worker,mode],cwd=roots[index],capture_output=True,text=True)
        if result.returncode:raise RuntimeError(result.stderr)
        payload=json.loads(result.stdout)
        samples[index].append(payload['cases']);module_files[index].append(payload['module_file'])
after=[state(root) for root in roots]
if before!=after:raise RuntimeError('benchmark roots changed during measurement')
for name in samples[0][0]:
    if len({out for group in samples for sample in group for out in sample[name]['outputs']})!=1:raise RuntimeError('output mismatch')
print(json.dumps({'python':sys.version,'mode':mode,'commits':[item['head'] for item in before],'root_state_before':before,'root_state_after':after,'module_files':module_files,
    'pairs':7,'samples':dict(zip(('before','after'),samples)),
    'median_ms':{side:{name:statistics.median(sample[name]['mean_ms'] for sample in group) for name in group[0]} for side,group in zip(('before','after'),samples)}},indent=2))
