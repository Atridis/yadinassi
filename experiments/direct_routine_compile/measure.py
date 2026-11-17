"""Alternating cold regex executions in two supplied worktrees; no fixture edits."""
import json, statistics, subprocess, sys
from pathlib import Path

worker = """from pathlib import Path
from time import perf_counter
from yadinassi import Interpreter
source=Path('integrational_tests/measurements/regex_family.bsl').read_text()
start=perf_counter()
for _ in range(3):
    output=[]
    vm=Interpreter(output.append,compilation_profile='managed-thick-file')
    vm.execute(source)
    if len(output)!=42:raise RuntimeError('incomplete regex replay')
    vm.close()
print((perf_counter()-start)*1000/3)
"""
roots=[str(Path(arg).resolve()) for arg in sys.argv[1:]]
if len(roots)!=2:raise SystemExit('measure.py BEFORE_WORKTREE AFTER_WORKTREE')
samples=[[],[]]
for pair in range(5):
    for index in ([0,1] if pair%2==0 else [1,0]):
        result=subprocess.run([sys.executable,'-B','-c',worker],cwd=roots[index],capture_output=True,text=True,check=True)
        samples[index].append(float(result.stdout))
print(json.dumps({'baseline':'6b060d62740a14ac549feea7de63259a17771bbe',
    'python':sys.version,'pairs':5,'operations_per_process':3,
    'milliseconds':dict(zip(('before','after'),samples)),
    'median_ms':dict(zip(('before','after'),map(statistics.median,samples)))},indent=2))
