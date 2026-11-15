"""Run one fresh process per sample, serial paired baseline/hybrid."""
import argparse,json,platform,sys,time,hashlib,subprocess,os
from pathlib import Path
from decimal import Decimal
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from yadinassi import Interpreter
from yadinassi.syntax.parser import parse
p=argparse.ArgumentParser();p.add_argument('--backend',choices=['baseline','hybrid'],required=True);p.add_argument('--iterations',type=int,default=10000000);a=p.parse_args()
if a.iterations < 1: p.error('--iterations must be positive')
source_path=ROOT/'benchmarks/hybrid_for.bsl'
source=source_path.read_text(encoding='utf-8').replace('КоличествоИтераций = 10000000;',f'КоличествоИтераций = {a.iterations};')
t=time.perf_counter();program=parse(source,str(source_path));parse_seconds=time.perf_counter()-t
output=[];vm=Interpreter(output=output.append,execution_backend='interpreter' if a.backend=='baseline' else 'hybrid')
t=time.perf_counter();cpu=time.process_time();vm.execute_program(program);cpu=time.process_time()-cpu;elapsed=time.perf_counter()-t
expected=3*a.iterations*(a.iterations+1)//2-7*a.iterations
if vm.variables['результат']!=Decimal(expected): raise RuntimeError('incorrect result')
if a.backend=='hybrid' and (vm.execution_backend_stats['compiled']!=2 or vm.execution_backend_stats['fallback']!=0):
    raise RuntimeError('hybrid path did not execute both loops')
print(json.dumps({'backend':a.backend,'iterations':a.iterations,'python':sys.version,'platform':platform.platform(),'cpu':platform.processor(),'code_sha256':{name:hashlib.sha256((source_path.parents[1]/'yadinassi'/name).read_bytes()).hexdigest() for name in ('runtime.py','hybrid_backend.py')},'sha':subprocess.check_output(['git','-C',str(ROOT),'rev-parse','HEAD'],text=True).strip(),'source_sha256':hashlib.sha256(source.encode()).hexdigest(),'parse_seconds':parse_seconds,'elapsed_seconds':elapsed,'process_cpu_seconds':cpu,'compile_seconds':vm.execution_backend_stats['compile_seconds'],'empty_seconds':str(vm.variables['времяпустогоцикла']/1000),'arithmetic_seconds':str(vm.variables['времяматематики']/1000),'result':str(vm.variables['результат']),'output':output},ensure_ascii=False),flush=True)
