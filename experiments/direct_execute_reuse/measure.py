"""Alternating fresh-process Execute preparation benchmark."""
import json,subprocess,sys,statistics
from pathlib import Path
CHILD='''import sys,time,json
sys.path.insert(0,sys.argv[1])
from yadinassi import Interpreter
extra="".join("L%d=%d;"%(i,i) for i in range(int(sys.argv[2])))
s='Function F() '+extra+' S=0;For I=1 To 1000 Do Execute("S=S+1;");EndDo;Return S;EndFunction R=F();'
v=Interpreter();p=v.prepare(s);start=time.perf_counter();v.execute_prepared(p);elapsed=time.perf_counter()-start
assert v.variables['r']==1000
print(json.dumps({'seconds':elapsed,'result':str(v.variables['r'])}))'''
if __name__=='__main__':
 baseline,candidate=sys.argv[1:3]; rows=[]
 for locals in (0,100):
  for pair in range(7):
   for label,path in ((('baseline',baseline),('candidate',candidate)) if pair%2==0 else (('candidate',candidate),('baseline',baseline))):
    data=json.loads(subprocess.check_output([sys.executable,'-B','-c',CHILD,str(Path(path).resolve()),str(locals)],text=True)); rows.append(dict(pair=pair,locals=locals,variant=label,**data))
 print(json.dumps(rows,indent=2))
