import subprocess,json,tempfile,time,hashlib
from pathlib import Path
python='/tmp/yadinassi-review-venv/bin/python'
base='/workspace/yadinassi-integration';candidate='/workspace/yadinassi-runtime'
script='/tmp/yadinassi-review-evidence/runtime-bench.py'
output=Path('/tmp/yadinassi-review-evidence/runtime-paired.jsonl')
expected={}
with output.open('w') as out:
 for scenario in ('collections','functions','values','numbers','strings','dates'):
  for number,root in enumerate((base,candidate,candidate,base)):
   with tempfile.TemporaryDirectory(prefix='runtime-bench-cache-') as cache:
    result=subprocess.run([python,'-I','-B','-X','pycache_prefix='+cache,script,root,'compiled-strict',scenario],capture_output=True,text=True,timeout=55,check=True)
   assert not result.stderr,result.stderr
   row=json.loads(result.stdout);assert not row['dirty']
   row['order']=number;row['label']='baseline' if root==base else 'candidate'
   signature=(row['bytes'],row['output_sha256'])
   expected.setdefault(scenario,signature);assert signature==expected[scenario],(scenario,signature,expected[scenario])
   stats=row['stats'];assert stats.get('python_translated_blocks',0)>0
   assert not any(stats.get(k,0) for k in ('interpreter_fallbacks','rejected_units','unsupported_executions','plain_adapter_blocks','emitted_executions','helper_executions'))
   out.write(json.dumps(row)+'\n');out.flush()
   print(scenario,row['label'],round(row['total'],4),flush=True)
 # Explicit oracle controls, never branch-default constructor substitution.
 for scenario in ('collections','functions','values','numbers','strings','dates'):
  for root in (base,candidate):
   with tempfile.TemporaryDirectory(prefix='runtime-oracle-cache-') as cache:
    result=subprocess.run([python,'-I','-B','-X','pycache_prefix='+cache,script,root,'interpreter',scenario],capture_output=True,text=True,timeout=35,check=True)
   assert not result.stderr,result.stderr
   row=json.loads(result.stdout);assert not row['dirty'];row['label']='baseline' if root==base else 'candidate'
   assert (row['bytes'],row['output_sha256'])==expected[scenario]
   assert not row['stats']
   out.write(json.dumps(row)+'\n');out.flush()
   print(scenario,'oracle',row['label'],round(row['total'],4),flush=True)
print('COMPLETE',hashlib.sha256(output.read_bytes()).hexdigest(),flush=True)
