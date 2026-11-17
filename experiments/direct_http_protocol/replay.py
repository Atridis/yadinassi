"""Unchanged HTTPFamily source, owned loopback server, exact native40 bytes."""
import hashlib,json,sys
from pathlib import Path
from tempfile import TemporaryDirectory
ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT),str(ROOT/'scripts')]
from native_1c_http_route import replay,SOURCE
from native_1c_http_fixture import owned_fixture
source=(ROOT/SOURCE).read_bytes()
with TemporaryDirectory(prefix='direct-http-') as tmp,owned_fixture() as fixture:
    output=replay(source,Path(tmp).resolve(),fixture.server_port)
expected=(ROOT/'tests/fixtures/http_family/native-initial/output.txt').read_bytes()
if source!=(ROOT/SOURCE).read_bytes():raise RuntimeError('source changed')
print(json.dumps(dict(source_sha256=hashlib.sha256(source).hexdigest(),
 output_bytes=len(output),output_sha256=hashlib.sha256(output).hexdigest(),
 native_sha256=hashlib.sha256(expected).hexdigest(),records=len(output.splitlines())-2,
 native_run=44103604012,native_summary_artifact=14337411357,
 exact_match=output==expected),indent=2))
if output!=expected:raise SystemExit(1)
