"""Pure computation on plain and real DB-enabled VMs; database setup excluded."""
import json,statistics
from time import perf_counter
from yadinassi import Interpreter
import test_python_direct_database as fixture
kernels={'numeric':'s=0;For i=1 To 10000 Do s=s+i;EndDo;',
         'array':'a=New Array;For i=0 To 9999 Do a.Add(i);EndDo;s=0;For j=0 To 9999 Do s=s+a.Get(j);EndDo;'}
f=fixture.DirectDatabaseTests();f.setUp()
plain=Interpreter();out={}
try:
 for name,source in kernels.items():
  for mode,vm in [('plain',plain),('database',f.vm)]:
   plan=vm.prepare(source)
   for route in ('prepared','execute_source'):
    times=[]
    for repeat in range(3):
     start=perf_counter()
     if route=='prepared':vm.execute_prepared(plan)
     else:vm.execute(source)
     times.append((perf_counter()-start)*1000)
     assert vm.variables['s']==(50005000 if name=='numeric' else 49995000)
    out[name+'/'+mode+'/'+route]=statistics.median(times)
 assert f.context.backend._active is None
 print(json.dumps(out))
finally:plain.close();f.doCleanups()
