"""Small warm-loop comparison, not a complete BSL/VM performance benchmark.

Run in fresh alternating processes against both checkouts, without concurrent
profiles/tests. Compilation precedes the BSL timer; parsing, preparation, warmup
and output are not part of the reported loop time. Decimal operations and live
loop counters are retained. No production checks are patched by this script.

    python benchmarks/python_scalar_regions.py --backend compiled-strict
    python benchmarks/python_scalar_regions.py --backend interpreter
"""
import argparse
import hashlib
import json
from pathlib import Path
import platform
import sys
import time
from decimal import Decimal

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from yadinassi import Interpreter

CASES = {
    'module_arithmetic': ('s=0;For i=1 To 10000 Do s=s+i*3-7;EndDo;', 's', '149945000'),
    'local_arithmetic': ('Function Work() s=0;For i=1 To 10000 Do s=s+i*3-7;EndDo;Return s;EndFunction r=Work();', 'r', '149945000'),
    'local_while': ('Function Work() s=0;i=0;While i<10000 Do i=i+1;s=s+i*3-7;EndDo;Return s;EndFunction r=Work();', 'r', '149945000'),
    'nested_control': ('Function Work() s=0;For i=1 To 3000 Do If i%2=0 Then s=s+i*3-7;Else s=s+1;EndIf;EndDo;Return s;EndFunction r=Work();', 'r', '6745500'),
}

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--backend', choices=('compiled-strict', 'interpreter'), default='compiled-strict')
    args = parser.parse_args()
    for name, (body, result, expected) in CASES.items():
        vm = Interpreter(execution_backend=args.backend)
        vm.register_function('BenchClock', lambda: Decimal(time.perf_counter_ns()) / Decimal(1000000))
        # Warm independently, without retaining the measured program's admission.
        vm.execute('warm=1;For wi=1 To 50 Do warm=warm+wi;EndDo;')
        source = 'benchstart=BenchClock();' + body + 'benchelapsed=BenchClock()-benchstart;'
        vm.execute(source)
        actual = str(vm.variables[result])
        if actual != expected:
            raise AssertionError((name, actual, expected))
        stats = vm.compiled_backend_stats
        if args.backend == 'compiled-strict':
            if any(stats.get(key, 0) for key in ('interpreter_fallbacks', 'unsupported_executions', 'rejected_units')) or stats.get('force_translation_gaps'):
                raise AssertionError('strict execution rejected or fell back')
        print(json.dumps(dict(case=name, backend=args.backend, milliseconds=float(vm.variables['benchelapsed']),
                              result=actual, python=sys.version, platform=platform.platform(),
                              source_sha256=hashlib.sha256(source.encode()).hexdigest(), stats=stats)))

if __name__ == '__main__':
    main()
