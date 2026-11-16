import subprocess,json,os,statistics,sys
from pathlib import Path
roots={'base':sys.argv[1],'candidate':sys.argv[2]};rows=[]
worker=str(Path(__file__).with_name('worker.py').resolve())
for pair in range(5):
 for variant in (('base','candidate') if pair%2==0 else ('candidate','base')):
  result=json.loads(subprocess.check_output([sys.executable,worker],cwd=roots[variant],env={**os.environ,'PYTHONPATH':'tests:.'},text=True))
  rows.append(dict(pair=pair,variant=variant,**result))
print(json.dumps({'samples':rows,'medians_ms':{v:statistics.median(x for r in rows if r['variant']==v for x in r['description_ms'][1:]) for v in roots}},indent=2))
