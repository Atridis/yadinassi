"""Seven alternating pairs of real MainDemoHost/SQLite description and Save."""
import ast
from contextlib import redirect_stdout
import hashlib
import io
import json
from pathlib import Path
import runpy
import statistics
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT/'tests')]
from yadinassi import sqlite_catalog as catalog
from yadinassi import sqlite_inventory_enum_profile as profile
BASE = '8da658715130a90a6a95b79e838f22d71f01d7ec'

def original(module, path, name, owner=None):
    tree = ast.parse(subprocess.check_output(['git', 'show', BASE+':'+path], cwd=ROOT, text=True))
    body = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == owner).body if owner else tree.body
    node = next(n for n in body if isinstance(n, ast.FunctionDef) and n.name == name)
    namespace = vars(module).copy()
    exec(compile(ast.Module(body=[node], type_ignores=[]), '<baseline '+name+'>', 'exec'), namespace)
    return namespace[name]

old_begin = original(catalog, 'yadinassi/sqlite_catalog.py', '_begin', 'SQLiteCatalogBackend')
old_admit = original(profile, 'yadinassi/sqlite_inventory_enum_profile.py', 'admit')
new_begin, new_admit = catalog.SQLiteCatalogBackend._begin, profile.admit
samples = []
try:
    for pair in range(7):
        for mode in (('before', 'after') if pair % 2 == 0 else ('after', 'before')):
            catalog.SQLiteCatalogBackend._begin = old_begin if mode == 'before' else new_begin
            profile.admit = old_admit if mode == 'before' else new_admit
            output = io.StringIO()
            with redirect_stdout(output):
                runpy.run_path(str(ROOT/'experiments/scalar_editor_source_boundary/worker.py'))
            samples.append({'pair': pair, 'mode': mode, **json.loads(output.getvalue())})
finally:
    catalog.SQLiteCatalogBackend._begin, profile.admit = new_begin, new_admit
summary = {}
for kind in ('kind', 'product'):
    summary[kind] = {operation: {mode: statistics.median(
        row[operation] for sample in samples if sample['mode'] == mode
        for row in sample['samples'] if row['profile'] == kind and row['iteration'] > 0)
        for mode in ('before', 'after')} for operation in ('description_ms', 'save_ms')}
print(json.dumps({'baseline': BASE, 'pairs': 7, 'warm_median_ms': summary,
    'files': {p: hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in
        ('yadinassi/sqlite_catalog.py', 'yadinassi/sqlite_inventory_enum_profile.py')},
    'samples': samples}, indent=2))
