"""Progress of unchanged native strings source on the direct backend."""
import hashlib,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from yadinassi import Interpreter
from yadinassi.experimental_naked_collections import UnsupportedNakedSyntax
source=ROOT/'integrational_tests/tests/strings.bsl';raw=source.read_bytes();rows=[]
vm=Interpreter(rows.append,compilation_profile='managed-thick-file',native_target='linux-8.3.27.1508')
completed=False;blocker=None
try:
    vm.execute(raw.decode('utf-8-sig'));completed=True
except UnsupportedNakedSyntax as error:
    if str(error)!='constructor SearchDirection':raise
    blocker=str(error)
wire=('\n'.join(rows)+'\n').encode()
if source.read_bytes()!=raw:raise RuntimeError('source changed')
print(json.dumps(dict(source_sha256=hashlib.sha256(raw).hexdigest(),records=len(rows),
 output_bytes=len(wire),output_sha256=hashlib.sha256(wire).hexdigest(),
 completed=completed,remaining_blocker=blocker,native_reference_records=385),indent=2))
if len(rows)<372:raise SystemExit(1)
