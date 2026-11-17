"""Diagnostic attribution for the next audit8 candidates, not speedup evidence."""
import cProfile
from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import pstats
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT/'tests')]
worker = (ROOT/'experiments/scalar_editor_source_boundary/worker.py').read_text()
# Profile only the four timed Description/Save sites, excluding fixture setup.
assert worker.count('t=time.perf_counter_ns();') == 4
assert worker.count('/1e6') == 4
worker = worker.replace('t=time.perf_counter_ns();', 'prof.enable();t=time.perf_counter_ns();').replace('/1e6', '/1e6;prof.disable()')
prof = cProfile.Profile()
with redirect_stdout(io.StringIO()):
    exec(compile(worker, '<actual UI worker>', 'exec'), {'prof': prof})
stats = pstats.Stats(prof)
rows = [{'file': str(Path(path).relative_to(ROOT)) if Path(path).is_relative_to(ROOT) else path,
         'line': line, 'function': name, 'calls': count, 'self_s': own, 'cumulative_s': total}
        for (path, line, name), (_, count, own, total, _) in stats.stats.items()]
print(json.dumps({'scope': '24 Description/Save actions, fixture setup excluded',
    'total_profiled_s': stats.total_tt,
    'candidates': [row for row in rows if row['function'] in ('_catalog_shape', 'definite_module_reads', 'token')],
    'top_cumulative': sorted(rows, key=lambda row: row['cumulative_s'], reverse=True)[:25]}, indent=2))
