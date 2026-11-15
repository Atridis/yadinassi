"""One fresh-process sample of the user-supplied two loops; no native-1C speed claim.

The supplied Markdown's escaped multiplication and NBSP indentation were
normalized in user_example.bsl; both measured blocks and checksum are retained.
Use serial, alternating fresh-process pairs on an otherwise idle machine.
"""
import argparse
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import platform
import subprocess
import sys
import time
from yadinassi import Interpreter
from yadinassi.syntax.parser import parse

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--backend', choices=('interpreter', 'compiled-strict'), required=True)
parser.add_argument('--iterations', type=int, default=10_000_000)
args = parser.parse_args()
compile_seconds = [0.0]
if args.backend == 'compiled-strict':
    from yadinassi.compiled_backend import Engine
    Engine.INLINE = True
    Engine.FAST_INLINE = True
    Engine.DETAILED_INLINE_STATS = False
    prepare = Engine.prepare
    def measured_prepare(self, *a, **kw):
        started = time.perf_counter()
        try:
            return prepare(self, *a, **kw)
        finally:
            compile_seconds[0] += time.perf_counter() - started
    Engine.prepare = measured_prepare
source_path = Path(__file__).with_name('user_example.bsl')
source = source_path.read_text(encoding='utf-8').replace(
    'КоличествоИтераций = 10000000;', f'КоличествоИтераций = {args.iterations};')
started = time.perf_counter()
program = parse(source, str(source_path))
parse_seconds = time.perf_counter() - started
output = []
vm = Interpreter(execution_backend=args.backend, output=output.append)
started, cpu = time.perf_counter(), time.process_time()
vm.execute_program(program)
elapsed, cpu = time.perf_counter() - started, time.process_time() - cpu
expected = Decimal(3 * args.iterations * (args.iterations + 1) // 2 - 7 * args.iterations)
if vm.variables['результат'] != expected:
    raise RuntimeError('benchmark checksum mismatch')
stats = getattr(vm, 'compiled_backend_stats', {})
if args.backend == 'compiled-strict':
    if any(stats.get(k, 0) for k in ('rejected_units', 'unsupported_executions', 'interpreter_fallbacks')):
        raise RuntimeError('strict benchmark contains rejection or fallback')
    if not stats.get('inline_blocks', 0):
        raise RuntimeError('no observed inline block execution')
print(json.dumps({'backend': args.backend, 'lowering': 'inline-fast' if stats else 'interpreter',
    'iterations': args.iterations, 'python': sys.version, 'platform': platform.platform(),
    'commit': subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip(),
    'source_sha256': hashlib.sha256(source.encode()).hexdigest(), 'parse_seconds': parse_seconds,
    'elapsed_seconds': elapsed, 'process_cpu_seconds': cpu, 'compile_seconds': compile_seconds[0],
    'empty_seconds': str(vm.variables['времяпустогоцикла'] / 1000),
    'arithmetic_seconds': str(vm.variables['времяматематики'] / 1000),
    'result': str(vm.variables['результат']), 'expected': str(expected), 'stats': stats,
    'output': output}, ensure_ascii=False), flush=True)
