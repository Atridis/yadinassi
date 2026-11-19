"""Small reproducible kernel + actual prepared BSL scan/index comparison."""
import json,time,statistics
from decimal import Decimal as D
from yadinassi.collections.plain_value_table_runtime import BSLValueTable
from yadinassi.collections.structures import BSLStructure
from yadinassi import Interpreter
from recovered_bare_fixture import Interpreter as BareInterpreter

def elapsed(fn,repeats=5):
    times=[]
    for _ in range(repeats):
        start=time.perf_counter();fn();times.append(time.perf_counter()-start)
    return statistics.median(times)

out=[]
for n in (512,4096):
    t=BSLValueTable();t.columns.add('K');t.columns.add('V')
    raw=[]
    for i in range(n):
        r=t.add();r.set_member('K',D(i%32));r.set_member('V',D(i));raw.append([D(i%32),D(i)])
    f=BSLStructure('K',D(3));expected=[r for r in t.rows if r[0]==D(3)]
    def query():
        got=t.find_rows(f).items
        assert len(got)==len(expected) and all(a is b for a,b in zip(got,expected))
    linear=elapsed(query);t.indexes.add('K');start=time.perf_counter();query();build=time.perf_counter()-start
    steady=elapsed(query)
    def batch():
        for r in t.rows:r.set_member('V',r[1])
        query()
    batch_time=elapsed(batch,3)
    def interleaved():
        for r in t.rows[:8]:r.set_member('V',r[1]);query()
    interleaved_time=elapsed(interleaved,3)
    raw_target=D(3)
    python=elapsed(lambda:[r for r in raw if r[0]==raw_target])
    source='T=New ValueTable;T.Columns.Add("K");For I=0 To '+str(n-1)+' Do R=T.Add();R.K=I%32;EndDo;'
    actual={}
    for cls in (Interpreter,BareInterpreter):
      for indexed in (False,True):
        vm=cls();vm.execute(source+('T.Indexes.Add("K");' if indexed else ''))
        plan=vm.prepare('Found=T.FindRows(New Structure("K",3));C=Found.Count();')
        def run():
            vm.execute_prepared(plan);assert vm.variables['c']==n//32
        actual[cls.__module__+ ('_indexed' if indexed else '_linear')]=elapsed(run,3)
    out.append(dict(n=n,python_scan=python,class_linear=linear,class_build=build,class_steady=steady,batch_write_search=batch_time,interleaved8=interleaved_time,prepared_bsl=actual))
print(json.dumps(out,indent=2))
