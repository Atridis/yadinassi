import json,os,subprocess,statistics,argparse
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument("baseline");p.add_argument("candidate");p.add_argument("--python",default="python");args=p.parse_args()
roots={"base":args.baseline,"repo":args.candidate}
rows=[]
for pair in range(7):
 for variant in (('base','repo') if pair%2==0 else ('repo','base')):
  data=json.loads(subprocess.check_output([args.python,str(Path(__file__).with_name('worker.py').resolve())],cwd=roots[variant],env={**os.environ,'PYTHONPATH':'tests:.'},text=True))
  rows.extend(dict(pair=pair,variant=variant,hashes=data['hashes'],**r) for r in data['samples'])
summary={profile:{metric:{variant:statistics.median(r[metric] for r in rows if r['profile']==profile and r['variant']==variant and r['iteration']>0) for variant in ('base','repo')} for metric in ('description_ms','save_ms')} for profile in ('kind','product')}
print(json.dumps(dict(samples=rows,warm_medians_ms=summary),indent=2))
