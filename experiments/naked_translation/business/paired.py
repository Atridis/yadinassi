import subprocess,os,sys,json,statistics,hashlib
from pathlib import Path
HERE=Path(__file__).parent;ROOT=Path(__file__).resolve().parents[3];rows=[]
backends=('interpreter','compiled-strict','experimental')
for trial in range(3):
 for name in ('invoice_batch','graph_batch'):
  order=backends[trial%3:]+backends[:trial%3]
  if trial%2:order=order[::-1]
  for backend in order:
   row=json.loads(subprocess.check_output([sys.executable,str(HERE/'probes.py'),'one',name,backend,'3'],env=dict(os.environ,PYTHONPATH=str(ROOT)),cwd=ROOT,timeout=20))
   rows.append(dict(trial=trial,**row))
summary={name:{backend:dict(cold_ms=statistics.median(r['cold_ms'] for r in rows if r['name']==name and r['backend']==backend),warm_ms=statistics.median(statistics.median(r['warm_ms']) for r in rows if r['name']==name and r['backend']==backend)) for backend in backends} for name in ('invoice_batch','graph_batch')}
hashes={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in ROOT.glob('yadinassi/experimental_naked*.py')}
result=dict(scope='synthetic business fixtures, not real1C; three rotating fresh-process trials/backend, three warm runs; cold includes creation/parse/prepare/execute, excludes Python import/startup',summary=summary,rows=rows,runtime_hashes=hashes,fixture_hashes={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in HERE.glob('*.bsl')})
(HERE/'paired-results.json').write_text(json.dumps(result,indent=2));print(json.dumps(summary,indent=2))
