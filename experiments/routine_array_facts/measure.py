import json,statistics
from time import perf_counter
from yadinassi import Interpreter
body='a=New Array;For i=0 To UPPER Do a.Add(i);EndDo;s=0;For j=0 To a.Count()-1 Do s=s+a.Get(j);EndDo;'
cases={'module':body.replace('UPPER','9999')+'r=s;',
       'routine_literal':'Function F() '+body.replace('UPPER','9999')+'Return s;EndFunction r=F();',
       'routine_val_n':'Function F(Val N) '+body.replace('UPPER','N-1')+'Return s;EndFunction r=F(10000);'}
result={}
for name,source in cases.items():
 vm=Interpreter()
 try:
  plan=vm.prepare(source)
  for route in ('prepared','execute_source'):
   times=[]
   for _ in range(3):
    start=perf_counter()
    if route=='prepared':vm.execute_prepared(plan)
    else:vm.execute(source)
    times.append((perf_counter()-start)*1000)
    assert vm.variables['r']==49995000
   result[name+'/'+route]=statistics.median(times)
 finally:vm.close()
print(json.dumps(result))
