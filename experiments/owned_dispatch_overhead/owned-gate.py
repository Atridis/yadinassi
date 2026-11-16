import sys,time,tempfile,json,hashlib,subprocess
from pathlib import Path
root=Path('/workspace/yadinassi-owned');sys.path.insert(0,str(root))
from scripts import native_1c_full_host as h
fixture=root/'integrational_tests/tests/collections.bsl'
r=dict(commit=subprocess.check_output(['git','-C',str(root),'rev-parse','HEAD'],text=True).strip(),tree=subprocess.check_output(['git','-C',str(root),'rev-parse','HEAD^{tree}'],text=True).strip(),dirty=bool(subprocess.check_output(['git','-C',str(root),'status','--porcelain'])),backend='compiled-strict',limit=h.COLLECTIONS_MEASUREMENT_SECONDS,fixture_sha256=hashlib.sha256(fixture.read_bytes()).hexdigest(),harness_sha256=hashlib.sha256(Path(h.__file__).read_bytes()).hexdigest())
assert not r['dirty']
with tempfile.TemporaryDirectory() as cache:
 args=[sys.executable,'-I','-B','-X','pycache_prefix='+cache,'-c',h.EXECUTE_SCRIPT,str(root),str(fixture),h.LINUX_TARGET,'compiled-strict',cache+'/execution.json']
 t=time.perf_counter()
 try:
  code,out,err=h.bounded_child(args,root,seconds=h.COLLECTIONS_MEASUREMENT_SECONDS);r.update(code=code,bytes=len(out),stderr=len(err))
 except h.FullError as e:r['error']=str(e)
 r['seconds']=time.perf_counter()-t
print(json.dumps(r))
