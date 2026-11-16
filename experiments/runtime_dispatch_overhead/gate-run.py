import sys,time,tempfile,json
from pathlib import Path
root=Path('/workspace/yadinassi-runtime');sys.path.insert(0,str(root))
from scripts import native_1c_full_host as h
with tempfile.TemporaryDirectory() as cache:
 args=[sys.executable,'-I','-B','-X','pycache_prefix='+cache,'-c',h.EXECUTE_SCRIPT,str(root),str(root/'integrational_tests/tests/collections.bsl'),h.LINUX_TARGET,'compiled-strict',cache+'/execution.json']
 t=time.perf_counter()
 try:
  code,out,err=h.bounded_child(args,root,seconds=h.COLLECTIONS_MEASUREMENT_SECONDS)
  result=dict(code=code,bytes=len(out),stderr=len(err))
 except h.FullError as e:result=dict(error=str(e))
 result['seconds']=time.perf_counter()-t;print(json.dumps(result))
