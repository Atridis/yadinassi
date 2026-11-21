"""Paired ordinary-direct / collection-region diagnostic, without CI thresholds.

Uses the existing public extended-reference workloads and complete collection
validation. Both paths use the same backend and source; only region selection
is disabled in the control. Alternates order, excludes validation from timings.
Run in an otherwise idle process, never alongside the full test suite.
"""
import argparse
from contextlib import ExitStack
import json
from pathlib import Path
import platform
from statistics import median
import sys
from time import perf_counter_ns, process_time_ns
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
from scripts import benchmark_extended_layers as reference
from yadinassi.execution.direct.python_direct_collection_regions import analyze


def run(iterations=512,rounds=15):
    if not 1<=iterations<=1000 or not 3<=rounds<=101:raise ValueError('bounded iterations/rounds required')
    report={'python':sys.version,'platform':platform.platform(),'iterations':iterations,'rounds':rounds,'results':[]}
    def disabled(*args,**kwargs):return 0,{},{}
    for route in ('prepared','default'):
        for name in ('valuetable.build_scan','valuelist.build_scan'):
            with ExitStack() as stack:
                cases=[]
                for enabled in (False,True):
                    with patch('yadinassi.execution.direct.python_direct_collection_regions.analyze',analyze if enabled else disabled):
                        cases.append(reference.make_case(name,iterations,route,stack))
                samples=[[],[]];cpu=[[],[]]
                for index in range(rounds+4):
                    for enabled in ((0,1) if index%2 else (1,0)):
                        case=cases[enabled]
                        with patch('yadinassi.execution.direct.python_direct_collection_regions.analyze',analyze if enabled else disabled):
                            start=perf_counter_ns();start_cpu=process_time_ns()
                            result=case.runs['bsl']()
                            elapsed_cpu=process_time_ns()-start_cpu;elapsed=perf_counter_ns()-start
                        reference.validate(case,'bsl',result)
                        if index>=4:samples[enabled].append(elapsed);cpu[enabled].append(elapsed_cpu)
                medians=[median(values)/1e6 for values in samples]
                report['results'].append(dict(case=name,route=route,ordinary_ms=medians[0],region_ms=medians[1],speedup=medians[0]/medians[1],wall_ns=samples,cpu_ns=cpu))
    return report


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--iterations',type=int,default=512);parser.add_argument('--rounds',type=int,default=15);parser.add_argument('--output',type=Path)
    args=parser.parse_args();report=run(args.iterations,args.rounds);text=json.dumps(report,indent=2)
    if args.output:args.output.write_text(text+'\n')
    print(text)
