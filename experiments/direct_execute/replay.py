"""Run the original bounded native client child with a real owned SQLite fixture.

This reports advancement, not native parity; the original strict verifier is unchanged.
"""
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
with host._load_infobase_fixture().OwnedInfobase() as fixture:
    fixture.verify()
    args=[sys.executable,'-I','-B','-c',host.CLIENT_EXECUTE_SCRIPT,str(ROOT),
          'managed-thick-file',str(source),str(fixture.database_path)]
    code,output,stderr=fixture.run_child(args,ROOT,env=host.child_environment(),
        seconds=host.CASE_SECONDS,stdout_limit=host.MAX_FILE,stderr_limit=host.MAX_STDERR)
    fixture.verify()
if source.read_bytes()!=before:raise RuntimeError('source changed')
actual=json.loads(output)
expected=host.CLIENT_SQLITE_RUNTIME_VALUES+[host.PREPROCESSOR_RUNTIME_TOKEN]
a=actual.index('module.context.v1');b=expected.index('module.context.v1')
result=dict(source_sha256=hashlib.sha256(before).hexdigest(),exit_code=code,
    stderr_bytes=len(stderr),output_bytes=len(output),output_sha256=hashlib.sha256(output).hexdigest(),
    actual_count=len(actual),expected_count=len(expected),exact_match=actual==expected,
    prefix50_equal=actual[:50]==expected[:50],actual_object_section=actual[50:a],
    expected_object_section_count=b-50,
    aligned_tail_differences=[dict(actual_index=a+i,expected_index=b+i,actual=x,expected=y)
        for i,(x,y) in enumerate(zip(actual[a:],expected[b:])) if type(x)is not type(y) or x!=y])
print(json.dumps(result,ensure_ascii=False,indent=2))
