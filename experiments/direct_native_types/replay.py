"""Replay the original whole client source against exact owned-SQLite expectations."""
import hashlib
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'scripts'))
import native_1c_full_host as host

source=ROOT/host.CLIENT_SOURCE
before=source.read_bytes()
if hashlib.sha256(before).hexdigest()!=host.PREPROCESSOR_SOURCE_SHA256:
    raise RuntimeError('source changed')
rows=[]
# The owned fixture has an exclusive name: execute these modes sequentially.
for profile,token in (('managed-thick-file',host.PREPROCESSOR_RUNTIME_TOKEN),
                      ('standalone',host.PREPROCESSOR_DEFAULT_TOKEN)):
    with host._load_infobase_fixture().OwnedInfobase() as fixture:
        fixture.verify()
        args=[sys.executable,'-I','-B','-c',host.CLIENT_EXECUTE_SCRIPT,str(ROOT),
              profile,str(source),str(fixture.database_path)]
        code,output,stderr=fixture.run_child(args,ROOT,env=host.child_environment(),
            seconds=host.CASE_SECONDS,stdout_limit=host.MAX_FILE,stderr_limit=host.MAX_STDERR)
        fixture.verify()
    if source.read_bytes()!=before:raise RuntimeError('source changed')
    expected=host.CLIENT_SQLITE_RUNTIME_VALUES+[token]
    expected_bytes=json.dumps(expected,ensure_ascii=False,separators=(',',':')).encode()
    actual=json.loads(output)
    rows.append(dict(profile=profile,exit_code=code,stderr_bytes=len(stderr),
        actual_count=len(actual),expected_count=len(expected),output_bytes=len(output),
        output_sha256=hashlib.sha256(output).hexdigest(),
        expected_sha256=hashlib.sha256(expected_bytes).hexdigest(),
        exact_match=code==0 and not stderr and output==expected_bytes,
        differences=[dict(index=i,actual=a,expected=b) for i,(a,b) in enumerate(zip(actual,expected))
                     if type(a)is not type(b) or a!=b]))
print(json.dumps(dict(source_sha256=hashlib.sha256(before).hexdigest(),runs=rows),ensure_ascii=False,indent=2))
if not all(row['exact_match'] for row in rows):raise SystemExit(1)
