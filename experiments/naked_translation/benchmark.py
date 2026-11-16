"""Small paired diagnostic benchmark. Trusted sources only; not an acceptance gate."""
import hashlib
import json
import os
import platform
from pathlib import Path
import statistics
import time

os.environ['YADINASSI_UNSAFE_COLLECTION_ABLATION'] = '1'
from yadinassi.experimental_naked_collections import prepare, REPAIRS
from yadinassi.experimental_naked_boundaries import BoundaryContext
from yadinassi.experimental_naked_control import SharedBoundaryContext

CASES = {
    'module_loop': 'r=0;For i=1 To 10000 Do r=r+1;EndDo;',
    'private_routine': 'Function F() r=0;For i=1 To 10000 Do r=r+1;EndDo;Return r;EndFunction r=F();',
    'array_operations': 'a=New Array;For i=1 To 1000 Do a.Add(i);EndDo;r=a.Count();',
}

def main():
    rows=[]
    for name,source in CASES.items():
        program=prepare(source,repairs=REPAIRS)
        contexts={'legacy':BoundaryContext(), 'shared':SharedBoundaryContext()}
        expected=1000 if name=='array_operations' else 10000
        for ctx in contexts.values():
            assert program.run(context=ctx)['r']==expected
        for trial in range(7):
            for variant in (('legacy','shared') if trial%2==0 else ('shared','legacy')):
                started=time.perf_counter_ns()
                for _ in range(10):
                    result=program.run(context=contexts[variant])['r']
                    assert result==expected
                rows.append({'case':name,'variant':variant,'trial':trial,'ms':(time.perf_counter_ns()-started)/10/1e6,'result':str(result)})
    summary={name:{variant:statistics.median(row['ms'] for row in rows if row['case']==name and row['variant']==variant) for variant in ('legacy','shared')} for name in CASES}
    hashes={str(path):hashlib.sha256(path.read_bytes()).hexdigest() for path in sorted(Path('yadinassi').glob('experimental_naked*.py'))}
    print(json.dumps({'python':platform.python_version(),'metric':'ms per run, preparation excluded','limits':'synthetic trusted fixtures; header budget is not AST budget; no global speedup claim','summary':summary,'samples':rows,'source_sha256':hashes},indent=2))

if __name__=='__main__':main()
