"""Render timing references, never apply a performance threshold."""
import json
import math
from pathlib import Path
import sys


def render(report):
    if report['schema'] != 'execution-layers-v1':
        raise ValueError('unsupported benchmark report')
    environment = report['environment']
    lines = ['## Execution-layer performance reference', '',
             f"Commit: `{environment['git_head']}`", '',
             '| Workload | Native Python, ms | Python classes, ms | BSL direct, ms | Classes / Python | BSL / Python | BSL / classes |',
             '|---|---:|---:|---:|---:|---:|---:|']
    if not report['cases']:
        raise ValueError('empty benchmark report')
    for case in report['cases']:
        if case['route']['backend'] != 'python-direct':
            raise ValueError('reference job must measure the direct backend')
        values = [case['summary'][layer]['median_seconds'] for layer in ('python', 'python_classes', 'bsl')]
        if any(type(value) not in (int, float) or not math.isfinite(value) or value <= 0 for value in values):
            raise ValueError('invalid timing')
        native, classes, bsl = values
        name = case['case'].replace('|', '\\|').replace('\n', ' ')
        lines.append(f'| {name} | {native*1000:.3f} | {classes*1000:.3f} | {bsl*1000:.3f} | {classes/native:.2f}× | {bsl/native:.2f}× | {bsl/classes:.2f}× |')
    lines += ['', 'Ratios are time ratios: **lower is faster**, native Python = 1×. No speed threshold or speed-based failure.', '',
              'Wall-time medians; each invocation is checked for the expected Decimal result. '
              'Setup and first execution are recorded separately in the raw JSON. '
              'The BSL API is listed below: execute_program includes any preparation it performs internally. '
              'These microbenchmarks are not whole-application or full semantic equivalence; shared CI runners are noisy.', '']
    for case in report['cases']:
        lines.append(f"- {case['case']}: {case['iterations']} iterations, {len(case['samples'])//3} measured rounds; `{case['route'].get('api', 'unknown')}`.")
    lines += ['', f"Python: `{environment['python'].splitlines()[0]}`", f"CPU: `{environment['processor']}`", '',
              'Raw artifact includes all wall/CPU samples, source hashes, environment, setup and first-call timings.', '']
    return '\n'.join(lines)


if __name__ == '__main__':
    print(render(json.loads(Path(sys.argv[1]).read_text())), end='')
