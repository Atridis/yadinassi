import subprocess,tempfile,json
from pathlib import Path
p=Path('/tmp/yadinassi-review-evidence');base='/workspace/yadinassi-entry';candidate='/workspace/yadinassi-routine'
with (p/'routine-focused.jsonl').open('a') as out:
 for n,root in enumerate((candidate,base,base,candidate),4):
  with tempfile.TemporaryDirectory() as cache:
   r=subprocess.run(['/tmp/yadinassi-review-venv/bin/python','-I','-B','-X','pycache_prefix='+cache,str(p/'routine-focused-bench.py'),root,'compiled-strict','routine-cold-branches',str(p/'routine-cold-branches.bsl')],capture_output=True,text=True,check=True,timeout=55)
  row=json.loads(r.stdout);assert not row['dirty'];row['order']=n;out.write(json.dumps(row)+'\n');out.flush();print(row['commit'],row['total'],row['output_sha256'],flush=True)
