import subprocess,tempfile,json
roots=['/workspace/yadinassi-runtime-refresh','/workspace/yadinassi-owned','/workspace/yadinassi-owned-ablation']
with open('/tmp/yadinassi-review-evidence/owned-ablation.jsonl','w') as out:
 for i in (0,1,2,2,1,0):
  with tempfile.TemporaryDirectory() as cache:
   r=subprocess.run(['/tmp/yadinassi-review-venv/bin/python','-I','-B','-X','pycache_prefix='+cache,'/tmp/yadinassi-review-evidence/owned-bench.py',roots[i],'compiled-strict','strings'],capture_output=True,text=True,check=True,timeout=35)
  row=json.loads(r.stdout);assert not row['dirty'];out.write(json.dumps(row)+'\n');out.flush();print(row['commit'],row['total'],flush=True)
