import subprocess,tempfile,json
from pathlib import Path
p=Path('/tmp/yadinassi-review-evidence')
with (p/'routine-focused-oracle.jsonl').open('w') as out:
 for root in ('/workspace/yadinassi-entry','/workspace/yadinassi-routine'):
  with tempfile.TemporaryDirectory() as cache:
   r=subprocess.run(['/tmp/yadinassi-review-venv/bin/python','-I','-B','-X','pycache_prefix='+cache,str(p/'routine-focused-bench.py'),root,'interpreter','routine-cold-branches',str(p/'routine-cold-branches.bsl')],capture_output=True,text=True,check=True,timeout=35)
  row=json.loads(r.stdout);assert not row['dirty'];assert not row['stats'];out.write(json.dumps(row)+'\n');out.flush();print(row['total'],row['output_sha256'])
