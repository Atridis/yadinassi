"""Alternating real MainDemoHost/SQLite operations with and without quote cache."""
import ast,io,json,runpy,statistics,subprocess,sys
from contextlib import redirect_stdout
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];sys.path[:0]=[str(ROOT),str(ROOT/'tests')]
from yadinassi import sqlite_catalog_layout as layout
cached=layout._quote_identifier;function=layout.quote_identifier;current_code=function.__code__;rows=[]
BASE='9516625c113621be72343fa363a9558f32a30dea'
source=subprocess.check_output(['git','show',BASE+':yadinassi/sqlite_catalog_layout.py'],cwd=ROOT,text=True)
node=next(n for n in ast.parse(source).body if isinstance(n,ast.FunctionDef) and n.name=='quote_identifier')
namespace=vars(layout).copy();exec(compile(ast.Module(body=[node],type_ignores=[]),'<exact baseline quote>','exec'),namespace)
baseline_code=namespace['quote_identifier'].__code__
try:
 for pair in range(7):
  for mode in (('before','after') if pair%2==0 else ('after','before')):
   cached.cache_clear();function.__code__=baseline_code if mode=='before' else current_code
   sink=io.StringIO()
   with redirect_stdout(sink):runpy.run_path(str(ROOT/'experiments/scalar_editor_source_boundary/worker.py'))
   rows.append(dict(pair=pair,mode=mode,**json.loads(sink.getvalue())))
finally:function.__code__=current_code
summary={kind:{op:{mode:statistics.median(r[op] for row in rows if row['mode']==mode for r in row['samples'] if r['profile']==kind and r['iteration']>0) for mode in ('before','after')} for op in ('description_ms','save_ms')} for kind in ('kind','product')}
print(json.dumps(dict(baseline='9516625c113621be72343fa363a9558f32a30dea',python=sys.version,summary_ms=summary,samples=rows),indent=2))
