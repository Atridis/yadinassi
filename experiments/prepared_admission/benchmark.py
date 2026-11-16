"""Paired prepared-module execution, imports/preparation excluded from timing.
Usage: python benchmark.py BASE_REPO CANDIDATE_REPO --python /path/to/python
"""
import argparse,json,subprocess,statistics
p=argparse.ArgumentParser();p.add_argument('baseline');p.add_argument('candidate');p.add_argument('--python',default='python');a=p.parse_args()
worker=r'''
import json,time,hashlib
from pathlib import Path
from yadinassi import Interpreter
for n in (1,1000):
 source='x=0;'+('x=x+1;'*n)+'x;'
 vm=Interpreter();plan=vm.prepare(source)
 assert vm.execute_prepared(plan)==n
 start=time.perf_counter_ns()
 for _ in range(15):result=vm.execute_prepared(plan)
 elapsed=(time.perf_counter_ns()-start)/15/1e6
 assert result==n and vm.variables['x']==n
 print(json.dumps(dict(statements=n,ms=elapsed,result=int(result),source_sha256=hashlib.sha256(source.encode()).hexdigest(),runtime_sha256=hashlib.sha256(Path('yadinassi/python_direct.py').read_bytes()).hexdigest())))
'''
rows=[]
for pair in range(7):
 for label in (('baseline','candidate') if pair%2==0 else ('candidate','baseline')):
  output=subprocess.check_output([a.python,'-c',worker],cwd=getattr(a,label),text=True)
  for line in output.splitlines():rows.append(dict(pair=pair,variant=label,**json.loads(line)))
print(json.dumps({'samples':rows,'medians_ms':{str(n):{label:statistics.median(r['ms'] for r in rows if r['statements']==n and r['variant']==label) for label in ('baseline','candidate')} for n in (1,1000)}},indent=2))
