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
from yadinassi.syntax.parser import parse

D = Decimal
LAYERS = ('python', 'bsl')
HOST_CASES = ('arithmetic.host_control', 'arithmetic.host_after_loop')
CASES = ('arithmetic', 'arithmetic.int', 'arithmetic.fractional', 'branching', *HOST_CASES,
         'calls', 'byref', 'byref.array_element', 'string.length', 'array', 'array.foreach', 'map')
# Record denominator changes explicitly even when the BSL source is unchanged.
PYTHON_REFERENCES = {
    'arithmetic': 'native-int-arithmetic-v2',
    'arithmetic.fractional': 'int-counter-decimal-factor-v2',
    'map': 'native-int-map-v2',
    'byref': 'native-int-byref-v2',
    'byref.array_element': 'native-int-byref-element-v1',
    'array': 'native-int-array-v2',
    'array.foreach': 'native-int-array-foreach-v1',
}


@dataclass
class Workload:
    name: str
    source: str
    expected: Decimal
    native: object
    inputs: tuple = ()


def observe(value):
    return value


def workload(name, n):
    if type(n) is not int or not 1 <= n <= 100000:
        raise ValueError('iterations must be an integer in 1..100000')
    if name not in CASES:
        raise ValueError('unknown workload')
    one, three = D(1), D(3)
    inputs = ()
    if name in ('arithmetic', *HOST_CASES):
        host_call = name == 'arithmetic.host_after_loop'
        def native():
            s = 0
            for i in range(1, n + 1):
                s = s + i * 3 - 7
            result = D(s)
            return observe(result) if host_call else result
        body = f'r=0;For i=1 To {n} Do r=r+i*3-7;EndDo;'
        if host_call:
            body += 'r=Observe(r);'
        expected = D(3*n*(n+1)//2 - 7*n)
    elif name in ('arithmetic.int', 'arithmetic.fractional'):
        factor = three if name == 'arithmetic.int' else D('3.25')
        if name == 'arithmetic.int':
            def native():
                s = 0
                for i in range(1, n + 1):
                    s += i * 3
                return D(s)
            expected = D(3 * (n * (n + 1) // 2))
        else:
            def native():
                s = 0
                for i in range(1, n + 1):
                    s = s + i * factor
                return s
            expected = D(325 * (n * (n + 1) // 2)).scaleb(-2)
        body = f'r=0;For i=1 To {n} Do r=r+i*{factor};EndDo;'
    elif name == 'branching':
        def native():
            s = 0
            for i in range(1, n + 1):
                if i > 1 and (i % 2 == 0 or i == n):
                    s += i
            return D(s)
        body = (f'r=0;For i=1 To {n} Do '
                f'If i>1 And (i%2=0 Or i={n}) Then r=r+i;EndIf;EndDo;')
        half = n // 2
        expected = D(half * (half + 1) + (n if n > 1 and n % 2 else 0))
    elif name == 'string.length':
        sample = 'abcdefgh'
        inputs = (('s', sample),)
        def native():
            r = 0
            for _ in range(n):
                r += len(sample)
            return D(r)
        body = f'r=0;For i=1 To {n} Do r=r+StrLen(s);EndDo;'
        expected = D(8*n)
    elif name == 'calls':
        def native():
            def inc(x): return x + one
            s = D(0)
            for i in range(1, n + 1): s += inc(D(i))
            return s
        body = f'Function Inc(Val x) Return x+1;EndFunction r=0;For i=1 To {n} Do r=r+Inc(i);EndDo;'
        expected = D(n*(n+1)//2+n)
    elif name in ('byref', 'byref.array_element'):
        def native():
            cell = [0]
            def inc(x): x[0] += 1
            for _ in range(n): inc(cell)
            return D(cell[0])
        proc = 'Procedure Inc(x) x=x+1;EndProcedure '
        if name == 'byref':
            body = proc + f'r=0;For i=1 To {n} Do Inc(r);EndDo;'
        else:
            body = proc + f'a=New Array;a.Add(0);For i=1 To {n} Do Inc(a[0]);EndDo;r=a[0];'
        expected = D(n)
    elif name in ('array', 'array.foreach'):
        if name == 'array':
            def native():
                a = []
                for i in range(n): a.append(i)
                s = 0
                for i in range(n): s += a[i]
                return D(s)
            scan = f'For i=0 To {n-1} Do r=r+a[i];EndDo;'
        else:
            def native():
                a = []
                for i in range(n): a.append(i)
                s = 0
                for value in a: s += value
                return D(s)
            scan = 'For Each value In a Do r=r+value;EndDo;'
        body = f'a=New Array;For i=0 To {n-1} Do a.Add(i);EndDo;r=0;' + scan
        expected = D(n*(n-1)//2)
    else:
        def native():
            m = {}
            for i in range(n): m[i] = i
            s = 0
            for i in range(n): s += m.get(i)
            return D(s)
        body = f'm=New Map;For i=0 To {n-1} Do m.Insert(i,i);EndDo;r=0;For i=0 To {n-1} Do r=r+m.Get(i);EndDo;'
        expected = D(n*(n-1)//2)
    return Workload(name, body, expected, native, inputs)


def prepare_bsl(source, route, *, inputs=(), host=False):
    if route not in ('default', 'prepared'):
        raise ValueError('unknown BSL route')
    program = parse(source, '<execution-layer-benchmark>')
    vm = Interpreter(allow_extensions=True) if host else Interpreter()
    if host:
        vm.register_function('Observe', observe)
    vm.variables.update(inputs)
    info = {'backend': vm.execution_backend, 'requested_route': route,
            'allow_extensions': host}
    if route == 'default':
        def run():
            vm.execute_program(program)
            return vm.variables['r']
        return run, dict(info, api='execute_program(preparsed_ast)')
    plan = vm.prepare_program(program)
    def run():
        vm.execute_prepared(plan)
        return vm.variables['r']
    return run, dict(info, api='execute_prepared(plan)',
                     preparation_api='prepare_program(preparsed_ast)')


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
    bsl, route_info = prepare_bsl(job.source, route, inputs=job.inputs, host=case in HOST_CASES)
    bsl_setup = (time.perf_counter_ns()-t)/1e9
    functions = dict(zip(LAYERS, (job.native, bsl)))
    first = {}
    # First execution/compilation, allocator/cache warmup are separate from samples.
    for layer, run in functions.items():
        t = time.perf_counter_ns(); result = run()
        first[layer] = (time.perf_counter_ns()-t)/1e9
        validate(result, job.expected)
        validate(run(), job.expected)
    samples = []
    for turn in range(rounds):
        order = LAYERS[turn % len(LAYERS):] + LAYERS[:turn % len(LAYERS)]
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
    reference = {'python_reference': PYTHON_REFERENCES[case]} if case in PYTHON_REFERENCES else {}
    return {'case': case, 'iterations': n, 'route': route_info, 'expected': str(job.expected), **reference,
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
    parser.add_argument('--bsl-route', choices=('default', 'prepared'), default='default')
    parser.add_argument('--case', choices=CASES, action='append')
    args = parser.parse_args(argv)
    if not 1 <= args.iterations <= 100000 or args.rounds < 3:
        parser.error('iterations must be 1..100000; rounds must be >=3')
    report = {'schema': 'execution-layers-v1', 'environment': metadata(),
              'cases': [measure(case, args.iterations, args.rounds, args.bsl_route) for case in args.case or CASES]}
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
