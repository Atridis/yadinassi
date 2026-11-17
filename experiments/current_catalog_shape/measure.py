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
from yadinassi import sqlite_main_demo_profile as profile
BASE = '0cdb512cacbcec8c2d0502a64e0593c184b6e0b4'

def original(module, path, name, owner=None):
    tree = ast.parse(subprocess.check_output(['git', 'show', BASE+':'+path], cwd=ROOT, text=True))
    body = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == owner).body if owner else tree.body
    node = next(n for n in body if isinstance(n, ast.FunctionDef) and n.name == name)
    namespace = vars(module).copy()
    exec(compile(ast.Module(body=[node], type_ignores=[]), '<baseline '+name+'>', 'exec'), namespace)
    return namespace[name]

old_validate = original(profile, 'yadinassi/sqlite_main_demo_profile.py', 'validate_main_demo_ddl')
old_shape = original(profile, 'yadinassi/sqlite_main_demo_profile.py', '_catalog_shape')
new_validate, new_shape = profile.validate_main_demo_ddl, profile._catalog_shape
# The reconstructed validator's globals must point at the selected shape path.
old_validate.__globals__['preflight_catalog_sections'] = profile.preflight_catalog_sections
samples = []
try:
    for pair in range(7):
        for mode in (('before', 'after') if pair % 2 == 0 else ('after', 'before')):
            profile.validate_main_demo_ddl = old_validate if mode == 'before' else new_validate
            profile._catalog_shape = old_shape if mode == 'before' else new_shape
            output = io.StringIO()
            with redirect_stdout(output):
                runpy.run_path(str(ROOT/'experiments/scalar_editor_source_boundary/worker.py'))
            samples.append({'pair': pair, 'mode': mode, **json.loads(output.getvalue())})
finally:
    profile.validate_main_demo_ddl, profile._catalog_shape = new_validate, new_shape
summary = {}
for kind in ('kind', 'product'):
    summary[kind] = {operation: {mode: statistics.median(
        row[operation] for sample in samples if sample['mode'] == mode
        for row in sample['samples'] if row['profile'] == kind and row['iteration'] > 0)
        for mode in ('before', 'after')} for operation in ('description_ms', 'save_ms')}
print(json.dumps({'baseline': BASE, 'pairs': 7, 'warm_median_ms': summary,
    'files': {p: hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in
        ('yadinassi/sqlite_main_demo_profile.py',)},
    'samples': samples}, indent=2))
