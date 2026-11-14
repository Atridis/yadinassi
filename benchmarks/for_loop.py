"""Opt-in source interpreter benchmark; timings are never correctness gates.

Parent invocation alternates revisions in fresh processes. Each child warms up
then measures one execution with a fresh VM; parsing is timed separately.
"""
import argparse
import importlib.metadata
import json
import os
import platform
import random
import statistics
import subprocess
import sys
import time
from pathlib import Path

BODIES = {'empty': '', 'assign': 'Результат = НомерИтерации;',
          'add': 'Результат = Результат + НомерИтерации;',
          'arithmetic': 'Результат = Результат + НомерИтерации * 3 - 7;'}


def fixture(case, scope, n):
    source = f'Результат = 0; Для НомерИтерации = 1 По {n} Цикл {BODIES[case]} КонецЦикла;'
    if scope == 'routine':
        source = 'Функция Расчет() '+source+' Возврат Результат; КонецФункции Результат = Расчет();'
    return source


def expected(case, n):
    return {'empty': 0, 'assign': n, 'add': n*(n+1)//2,
            'arithmetic': 3*n*(n+1)//2-7*n}[case]


def git(repo, *args):
    return subprocess.check_output(['git', '-C', str(repo), *args], text=True).strip()


def environment(repo):
    deps={}
    for name in ('pyuca', 'prompt-toolkit', 'tzdata'):
        try: deps[name]=importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError: deps[name]=None
    return {'sha': git(repo, 'rev-parse', 'HEAD'), 'tree': git(repo, 'rev-parse', 'HEAD^{tree}'),
            'dirty': bool(git(repo,'status','--porcelain')), 'python': sys.version,
            'executable': sys.executable, 'platform': platform.platform(),
            'machine': platform.machine(), 'processor': platform.processor(),
            'cpu_count': os.cpu_count(), 'dependencies': deps, 'mode': 'source',
            'native_1c': None, 'compilation_profile': 'default'}


def child(args):
    from decimal import Decimal, getcontext
    sys.path.insert(0, str(Path(args.repo).resolve()))
    from yadinassi import Interpreter
    from yadinassi.syntax.parser import parse
    raw=fixture(args.case,args.scope,args.iterations)
    before=time.perf_counter(); program=parse(raw,'for_loop.bsl'); parse_time=time.perf_counter()-before
    # Warmup and measured execution both use fresh VM state, not accumulated results.
    times=[]
    for _ in range(args.warmups+1):
        vm=Interpreter(output=lambda _: None)
        try:
            before=time.perf_counter(); vm.execute_program(program); elapsed=time.perf_counter()-before
            result=vm.variables['результат']
            if result != Decimal(expected(args.case,args.iterations)):
                raise RuntimeError('incorrect benchmark result: '+str(result))
            times.append(elapsed)
        finally:
            vm.close()
    return {'parse_seconds':parse_time, 'warmup_seconds':times[:-1],
            'execution_seconds':times[-1], 'result':str(result),
            'decimal_external_context':str(getcontext())}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--repo',required=True,type=Path)
    p.add_argument('--baseline',type=Path)
    p.add_argument('--iterations',type=int,default=100000)
    p.add_argument('--repeats',type=int,default=5)
    p.add_argument('--warmups',type=int,default=1)
    p.add_argument('--seed',type=int,default=20261114)
    p.add_argument('--case',choices=BODIES,default='arithmetic',help='child mode only; parent runs all cases')
    p.add_argument('--scope',choices=('module','routine'),default='module',help='child mode only; parent runs both scopes')
    p.add_argument('--child',action='store_true',help=argparse.SUPPRESS)
    args=p.parse_args()
    if args.iterations<1 or args.repeats<1 or args.warmups<0:
        p.error('iterations/repeats positive and warmups nonnegative required')
    if args.child:
        print(json.dumps(child(args))); return
    repos={'candidate':args.repo.resolve()}
    if args.baseline: repos['baseline']=args.baseline.resolve()
    report={'schema':1,'iterations':args.iterations,'repeats':args.repeats,
            'seed':args.seed,'warmups':args.warmups,'profiled':False,
            'timing_policy':'fresh process per case/sample; parse and VM creation excluded; one measured execution',
            'environments':{name:environment(path) for name,path in repos.items()},'samples':[]}
    rng=random.Random(args.seed)
    for scope in ('module','routine'):
        for case in BODIES:
            first=list(repos); rng.shuffle(first)
            for repeat in range(args.repeats):
                order=first if repeat%2==0 else list(reversed(first))
                for name in order:
                    command=[sys.executable,str(Path(__file__).resolve()),'--child','--repo',str(repos[name]),
                             '--iterations',str(args.iterations),'--warmups',str(args.warmups),
                             '--case',case,'--scope',scope]
                    data=json.loads(subprocess.check_output(command,text=True))
                    report['samples'].append(dict(data,revision=name,case=case,scope=scope,repeat=repeat))
    summary=[]
    for scope in ('module','routine'):
        for case in BODIES:
            row={'scope':scope,'case':case}
            for name in repos:
                values=[s['execution_seconds'] for s in report['samples'] if (s['scope'],s['case'],s['revision'])==(scope,case,name)]
                row[name]={'median':statistics.median(values),'min':min(values),'max':max(values)}
            if args.baseline:row['ratio_baseline_over_candidate']=row['baseline']['median']/row['candidate']['median']
            summary.append(row)
    report['summary']=summary
    print(json.dumps(report,ensure_ascii=False,indent=2))


if __name__=='__main__':main()
