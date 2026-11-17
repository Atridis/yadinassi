"""Original source-bound CatalogQuery replay against accepted native output hash."""
import hashlib,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT),str(ROOT/'scripts')]
from catalog_query_behavior.replay import replay
source=ROOT/'scripts/catalog_query_behavior/generated/observe.bsl'
before=source.read_bytes()
rows=replay()
wire=(json.dumps(rows,separators=(',',':'))+'\n').encode()
expected='2a0a0e7db4025a5babc7ece3edd833feddba7ccffc16027bd6139cc184aa5c84'
actual=hashlib.sha256(wire).hexdigest()
if source.read_bytes()!=before:raise RuntimeError('source changed')
result=dict(source_sha256=hashlib.sha256(before).hexdigest(),records=len(rows),
 output_bytes=len(wire),output_sha256=actual,native_sha256=expected,
 native_run=44098520311,native_artifact=14334693411,exact_match=actual==expected)
print(json.dumps(result,indent=2))
if actual!=expected:raise SystemExit(1)
