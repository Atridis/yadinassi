"""Comparable workloads, not a speed gate. See docs/execution-layer-benchmarks.md."""
import argparse
from dataclasses import dataclass
from decimal import Decimal, getcontext
import hashlib
import json
import os
from pathlib import Path
import platform
import statistics
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from yadinassi import Interpreter
from yadinassi.maps import BSLMap
from yadinassi.runtime import binary_values
from yadinassi.syntax.parser import parse
from yadinassi.values import BSLArray, HostFunction, Reference

D = Decimal
LAYERS = ('python', 'python_classes', 'bsl')
CASES = ('arithmetic', 'calls', 'byref', 'array', 'map')


@dataclass
class Workload:
    name: str
    source: str
    expected: Decimal
    native: object
    classes: object


def workload(name, n):
    if type(n) is not int or not 1 <= n <= 100000:
        raise ValueError('iterations must be an integer in 1..100000')
    if name not in CASES:
        raise ValueError('unknown workload')
    # Decimal throughout: no int/float speed advantage or rounding mismatch.
    one, three, seven = D(1), D(3), D(7)
    if name == 'arithmetic':
        def native():
            s = D(0)
            for i in range(1, n + 1):
                s = s + D(i) * three - seven
            return s
        def classes():
            s = D(0)
            for i in range(1, n + 1):
                s = binary_values('-', binary_values('+', s, binary_values('*', D(i), three)), seven)
            return s
        body = f'r=0;For i=1 To {n} Do r=r+i*3-7;EndDo;'
        expected = D(3*n*(n+1)//2 - 7*n)
    elif name == 'calls':
        def native():
            def inc(x): return x + one
            s = D(0)
            for i in range(1, n + 1): s += inc(D(i))
            return s
        def classes():
            inc = HostFunction('Inc', lambda x: binary_values('+', x, one))
            s = D(0)
            for i in range(1, n + 1): s = binary_values('+', s, inc(D(i)))
            return s
        body = f'Function Inc(Val x) Return x+1;EndFunction r=0;For i=1 To {n} Do r=r+Inc(i);EndDo;'
        expected = D(n*(n+1)//2+n)
    elif name == 'byref':
        def native():
            cell = [D(0)]
            def inc(x): x[0] += one
            for _ in range(n): inc(cell)
            return cell[0]
        def classes():
            cell = [D(0)]
            ref = Reference(lambda: cell[0], lambda v: cell.__setitem__(0, v))
            inc = HostFunction('Inc', lambda x: x.set(binary_values('+', x.get(), one)),
                               reference_parameters=frozenset({0}), returns_value=False)
            for _ in range(n): inc(ref)
            return cell[0]
        body = f'Procedure Inc(x) x=x+1;EndProcedure r=0;For i=1 To {n} Do Inc(r);EndDo;'
        expected = D(n)
    elif name == 'array':
        def native():
            a = []
            for i in range(n): a.append(D(i))
            s = D(0)
            for i in range(n): s += a[i]
            return s
        def classes():
            a = BSLArray()
            for i in range(n): a.add(D(i))
            s = D(0)
            for i in range(n): s = binary_values('+', s, a.get(D(i)))
            return s
        body = f'a=New Array;For i=0 To {n-1} Do a.Add(i);EndDo;r=0;For i=0 To {n-1} Do r=r+a[i];EndDo;'
        expected = D(n*(n-1)//2)
    else:
        def native():
            m = {}
            for i in range(n): m[D(i)] = D(i)
            s = D(0)
            for i in range(n): s += m.get(D(i))
            return s
        def classes():
            m = BSLMap()
            for i in range(n): m.insert(D(i), D(i))
            s = D(0)
            for i in range(n): s = binary_values('+', s, m.get(D(i)))
            return s
        body = f'm=New Map;For i=0 To {n-1} Do m.Insert(i,i);EndDo;r=0;For i=0 To {n-1} Do r=r+m.Get(i);EndDo;'
        expected = D(n*(n-1)//2)
    return Workload(name, body, expected, native, classes)


def prepare_bsl(source, route):
    if route in ('default', 'compiled-strict'):
        program = parse(source, '<execution-layer-benchmark>')
        vm = Interpreter() if route == 'default' else Interpreter(execution_backend='compiled-strict')
        def run():
            vm.execute_program(program)
            return vm.variables['r']
        return run, {'backend': vm.execution_backend, 'requested_route': route, 'api': 'execute_program(preparsed_ast)'}
    if route == 'prepared':
        program = parse(source, '<execution-layer-benchmark>')
        vm = Interpreter()
        plan = vm.prepare_program(program)
        def run():
            vm.execute_prepared(plan)
            return vm.variables['r']
        return run, {'backend': vm.execution_backend, 'requested_route': route,
                     'api': 'execute_prepared(plan)', 'preparation_api': 'prepare_program(preparsed_ast)'}
    raise ValueError('unknown BSL route')


def validate(result, expected):
    # Equality alone would accidentally accept bool/int/float.
    if type(result) is not Decimal or result != expected:
        raise AssertionError(f'wrong result: {result!r} ({type(result).__name__}), expected Decimal({expected})')


def measure(case, n, rounds=9, route='default'):
    if type(rounds) is not int or rounds < 3:
        raise ValueError('at least three rounds required')
    t = time.perf_counter_ns()
    job = workload(case, n)
    python_setup = (time.perf_counter_ns()-t)/1e9
    t = time.perf_counter_ns()
    bsl, route_info = prepare_bsl(job.source, route)
    bsl_setup = (time.perf_counter_ns()-t)/1e9
    functions = dict(zip(LAYERS, (job.native, job.classes, bsl)))
    first = {}
    # First execution/compilation, allocator/cache warmup are separate from samples.
    for layer, run in functions.items():
        t = time.perf_counter_ns(); result = run()
        first[layer] = (time.perf_counter_ns()-t)/1e9
        validate(result, job.expected)
        validate(run(), job.expected)
    samples = []
    for turn in range(rounds):
        order = LAYERS[turn % 3:] + LAYERS[:turn % 3]
        for layer in order:
            cpu = time.process_time_ns(); start = time.perf_counter_ns()
            result = functions[layer]()
            elapsed = (time.perf_counter_ns()-start)/1e9
            cpu_elapsed = (time.process_time_ns()-cpu)/1e9
            validate(result, job.expected)
            samples.append({'round': turn, 'layer': layer, 'seconds': elapsed,
                            'cpu_seconds': cpu_elapsed, 'result': str(result)})
    summaries = {}
    for layer in LAYERS:
        times = [row['seconds'] for row in samples if row['layer'] == layer]
        median = statistics.median(times)
        summaries[layer] = {'median_seconds': median, 'min_seconds': min(times),
                            'max_seconds': max(times),
                            'mad_seconds': statistics.median(abs(t-median) for t in times)}
    return {'case': case, 'iterations': n, 'route': route_info, 'expected': str(job.expected),
            'source': job.source, 'source_sha256': hashlib.sha256(job.source.encode()).hexdigest(),
            'preparation_seconds': {'python_workload_factory': python_setup, 'bsl_parse_prepare': bsl_setup},
            'first_execution_seconds': first, 'samples': samples, 'summary': summaries,
            'ratios_to_python': {layer: summaries[layer]['median_seconds']/summaries['python']['median_seconds']
                                 for layer in LAYERS}}


def metadata():
    def git(*args):
        return subprocess.check_output(['git', '-C', str(ROOT), *args], text=True).strip()
    files = sorted((ROOT/'yadinassi').rglob('*.py')) + [Path(__file__)]
    digest = hashlib.sha256()
    for path in files:
        digest.update(str(path.relative_to(ROOT)).encode()+b'\0'+path.read_bytes()+b'\0')
    cpu_model = platform.processor()
    if not cpu_model and sys.platform.startswith('linux'):
        try:
            for line in Path('/proc/cpuinfo').read_text().splitlines():
                if line.startswith('model name'):
                    cpu_model = line.partition(':')[2].strip()
                    break
        except OSError:
            pass
    return {'python': sys.version, 'platform': platform.platform(), 'machine': platform.machine(),
            'processor': cpu_model, 'logical_cpus': os.cpu_count(), 'decimal_context': str(getcontext()),
            'git_head': git('rev-parse', 'HEAD'), 'git_status': git('status', '--porcelain'),
            'python_sources_sha256': digest.hexdigest(), 'timer': 'perf_counter_ns',
            'gc_policy': 'normal interpreter GC; not disabled', 'clock_resolution': time.get_clock_info('perf_counter').resolution}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--iterations', type=int, default=1000)
    parser.add_argument('--rounds', type=int, default=9)
    parser.add_argument('--bsl-route', choices=('default', 'prepared', 'compiled-strict'), default='default')
    parser.add_argument('--case', choices=CASES, action='append')
    args = parser.parse_args(argv)
    if not 1 <= args.iterations <= 100000 or args.rounds < 3:
        parser.error('iterations must be 1..100000; rounds must be >=3')
    report = {'schema': 'execution-layers-v1', 'environment': metadata(),
              'cases': [measure(case, args.iterations, args.rounds, args.bsl_route) for case in args.case or CASES]}
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
