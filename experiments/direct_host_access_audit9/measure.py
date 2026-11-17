"""Paired current-owner/array-Get changes; original BSL and real SQLite UI controls."""
import ast,io,json,runpy,statistics,subprocess,sys,time
from contextlib import redirect_stdout
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT),str(ROOT/'tests')]
from yadinassi import Interpreter
from yadinassi import python_direct_database as bridge
from yadinassi.python_direct_names import VALUES
BASE='31d65378662fa3909565218863986cbec8274495'
text=subprocess.check_output(['git','show',BASE+':yadinassi/python_direct_database.py'],cwd=ROOT,text=True)
body=next(n for n in ast.parse(text).body if isinstance(n,ast.ClassDef) and n.name=='CatalogBoundary').body
namespace=vars(bridge).copy();namespace['SYSTEM_VALUES']=VALUES
for name in ('_catalog_owner','resolve_member'):
    node=next(n for n in body if isinstance(n,ast.FunctionDef) and n.name==name)
    exec(compile(ast.Module(body=[node],type_ignores=[]),'<baseline>', 'exec'),namespace)
old_owner,old_member=namespace['_catalog_owner'],namespace['resolve_member']
new_owner,new_member=bridge.CatalogBoundary._catalog_owner,bridge.CatalogBoundary.resolve_member
samples=[]
try:
    for pair in range(5):
        modes=['before','owner','after'] if pair%2==0 else ['after','owner','before']
        for mode in modes:
            bridge.CatalogBoundary._catalog_owner=old_owner if mode=='before' else new_owner
            bridge.CatalogBoundary.resolve_member=new_member if mode=='after' else old_member
            row={'pair':pair,'mode':mode}
            vm=Interpreter();vm.execute('A=StrSplit("'+','.join(['token']*2000)+'",",");')
            array=vm.variables['a']
            plan=vm.prepare('S=0;For I=0 To A.Count()-1 Do S=S+StrLen(A.Get(I));EndDo;')
            times=[]
            for _ in range(7):
                start=time.perf_counter();vm.execute_prepared(plan);times.append((time.perf_counter()-start)*1000)
                if vm.variables['s']!=10000 or vm.variables['a'] is not array:raise RuntimeError('array control')
            row['split_get_ms']=times;vm.close()
            output=[];vm=Interpreter(output.append)
            plan=vm.prepare((ROOT/'integrational_tests/measurements/regex_family.bsl').read_text())
            times=[]
            for _ in range(3):
                output.clear();start=time.perf_counter();vm.execute_prepared(plan);times.append((time.perf_counter()-start)*1000)
                if len(output)!=42 or any(not s.startswith(f'RF-{i:02}: [ok|') for i,s in enumerate(output[2:],1)):raise RuntimeError('regex control')
            row['regex_prepared_ms']=times;vm.close()
            sink=io.StringIO()
            with redirect_stdout(sink):runpy.run_path(str(ROOT/'experiments/scalar_editor_source_boundary/worker.py'))
            row['ui']=json.loads(sink.getvalue())['samples'];samples.append(row)
finally:
    bridge.CatalogBoundary._catalog_owner=new_owner;bridge.CatalogBoundary.resolve_member=new_member
summary={key:{mode:statistics.median(t for row in samples if row['mode']==mode for t in row[key]) for mode in ('before','owner','after')} for key in ('split_get_ms','regex_prepared_ms')}
for profile in ('kind','product'):
    for operation in ('description_ms','save_ms'):
        summary[profile+'_'+operation]={mode:statistics.median(r[operation] for row in samples if row['mode']==mode for r in row['ui'] if r['profile']==profile and r['iteration']>0) for mode in ('before','owner','after')}
print(json.dumps({'baseline':BASE,'python':sys.version,'summary':summary,'samples':samples},indent=2))
