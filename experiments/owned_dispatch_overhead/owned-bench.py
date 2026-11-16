import sys,time,hashlib,json,subprocess,platform
from pathlib import Path
root=Path(sys.argv[1]);backend=sys.argv[2];scenario=sys.argv[3]
sys.path.insert(0,str(root));t=time.perf_counter()
from yadinassi import Interpreter
from yadinassi.syntax.parser import parse
out=[];vm=Interpreter(execution_backend=backend,output=out.append,native_target='linux-8.3.27.1508')
source_path=root/'integrational_tests/tests'/f'{scenario}.bsl';source=source_path.read_text(encoding='utf-8-sig');init=time.perf_counter()-t
t=time.perf_counter();program=parse(source,str(source_path));parse_time=time.perf_counter()-t
t=time.perf_counter();cpu=time.process_time();vm.execute_program(program);cpu=time.process_time()-cpu;execute=time.perf_counter()-t
raw=('\n'.join(out)+'\n').encode();stats=vm.compiled_backend_stats
h=hashlib.sha256()
for p in sorted((root/'yadinassi').rglob('*.py')):h.update(str(p.relative_to(root)).encode()+b'\0'+p.read_bytes())
print(json.dumps(dict(root=str(root),commit=subprocess.check_output(['git','-C',str(root),'rev-parse','HEAD'],text=True).strip(),dirty=bool(subprocess.check_output(['git','-C',str(root),'status','--porcelain'])),source_tree_sha256=h.hexdigest(),python=sys.version,platform=platform.platform(),backend=backend,scenario=scenario,init=init,parse=parse_time,execute=execute,cpu=cpu,total=init+parse_time+execute,bytes=len(raw),output_sha256=hashlib.sha256(raw).hexdigest(),input_sha256=hashlib.sha256(source_path.read_bytes()).hexdigest(),stats=stats),ensure_ascii=False))
