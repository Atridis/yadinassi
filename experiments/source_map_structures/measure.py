"""Alternating, fresh-process pairs for source-map cold preparation/execution."""
import hashlib,json,statistics,subprocess,sys
from pathlib import Path

worker=r'''
import hashlib,json,statistics
from pathlib import Path
from time import perf_counter
from yadinassi import Interpreter
source=Path('integrational_tests/measurements/regex_family.bsl').read_text()
times=[];prepare_times=[];fingerprints=[]
for _ in range(3):
    output=[];start=perf_counter()
    vm=Interpreter(output.append,compilation_profile='managed-thick-file')
    prep=perf_counter();plan=vm.prepare(source);prepare_times.append((perf_counter()-prep)*1000)
    vm.execute_prepared(plan);vm.close();times.append((perf_counter()-start)*1000)
    if len(output)!=42:raise RuntimeError('incomplete regex replay')
    fingerprints.append(hashlib.sha256(json.dumps(output,ensure_ascii=False).encode()).hexdigest())
print(json.dumps({'execute_ms':statistics.mean(times),'prepare_ms':statistics.mean(prepare_times),
    'outputs':fingerprints,'source_sha256':hashlib.sha256(source.encode()).hexdigest()}))
'''
roots=[str(Path(arg).resolve()) for arg in sys.argv[1:]]
if len(roots)!=2:raise SystemExit('measure.py BEFORE_WORKTREE AFTER_WORKTREE')
samples=[[],[]]
for pair in range(7):
    for index in ([0,1] if pair%2==0 else [1,0]):
        result=subprocess.run([sys.executable,'-B','-c',worker],cwd=roots[index],capture_output=True,text=True,check=True)
        samples[index].append(json.loads(result.stdout))
if len({item['source_sha256'] for group in samples for item in group})!=1:raise RuntimeError('source mismatch')
if len({fingerprint for group in samples for item in group for fingerprint in item['outputs']})!=1:raise RuntimeError('output mismatch')
print(json.dumps({'baseline':subprocess.check_output(['git','rev-parse','HEAD'],cwd=roots[0],text=True).strip(),
    'python':sys.version,'pairs':7,'operations_per_process':3,
    'samples':dict(zip(('before','after'),samples)),
    'median_ms':{name:{metric:statistics.median(item[metric] for item in group)
        for metric in ('execute_ms','prepare_ms')} for name,group in zip(('before','after'),samples)}},indent=2))
