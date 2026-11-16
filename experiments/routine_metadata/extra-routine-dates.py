import subprocess,json,tempfile,hashlib
from pathlib import Path
python='/tmp/yadinassi-review-venv/bin/python';base='/workspace/yadinassi-entry';candidate='/workspace/yadinassi-routine';script='/tmp/yadinassi-review-evidence/runtime-bench.py'
output=Path('/tmp/yadinassi-review-evidence/routine-paired.jsonl');previous=[json.loads(x) for x in output.read_text().splitlines()];expected=next(x for x in previous if x['scenario']=='dates')
with output.open('a') as out:
 for n,root in enumerate((candidate,base,base,candidate),4):
  with tempfile.TemporaryDirectory(prefix='runtime-bench-cache-') as cache:
   r=subprocess.run([python,'-I','-B','-X','pycache_prefix='+cache,script,root,'compiled-strict','dates'],capture_output=True,text=True,timeout=55,check=True)
  assert not r.stderr;r=json.loads(r.stdout);assert not r['dirty'];r['order']=n;r['label']='baseline' if root==base else 'candidate'
  assert (r['bytes'],r['output_sha256'])==(expected['bytes'],expected['output_sha256'])
  assert r['stats']==expected['stats']
  out.write(json.dumps(r)+'\n');out.flush();print(r['label'],r['total'],flush=True)
print('COMPLETE',hashlib.sha256(output.read_bytes()).hexdigest(),flush=True)
