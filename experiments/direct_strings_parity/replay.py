"""Compare unchanged strings source to a downloaded native outputs artifact."""
import argparse,hashlib,json,sys,zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from yadinassi import Interpreter
args=argparse.ArgumentParser();args.add_argument('native_zip');options=args.parse_args()
z=zipfile.ZipFile(options.native_zip);provenance=json.loads(z.read('provenance.json'))
case=next(c for c in provenance['cases'] if c['name']=='strings')
native=z.read('strings.out');source=(ROOT/'integrational_tests/tests/strings.bsl').read_bytes()
if hashlib.sha256(source).hexdigest()!=case['source_sha256']:raise RuntimeError('source mismatch')
if hashlib.sha256(native).hexdigest()!=case['output_sha256']:raise RuntimeError('native output hash mismatch')
rows=[];Interpreter(rows.append,compilation_profile='managed-thick-file',native_target='linux-8.3.27.1508').execute(source.decode('utf-8-sig'))
direct=('\n'.join(rows)+'\n').encode();left=native.splitlines();right=direct.splitlines()
print(json.dumps(dict(source_sha256=case['source_sha256'],native_repository_commit=provenance['repository']['commit'],native_run_id=provenance['repository']['github_run_id'],records=len(rows),native_sha256=hashlib.sha256(native).hexdigest(),direct_sha256=hashlib.sha256(direct).hexdigest(),native_bytes=len(native),direct_bytes=len(direct),native_lines=len(left),direct_lines=len(right),byte_equal=native==direct,differing_lines=[i+1 for i,(a,b) in enumerate(zip(left,right)) if a!=b]),indent=2))
if len(rows)!=385 or len(left)!=len(right):raise SystemExit(1)
if native!=direct:raise SystemExit('native byte mismatch')
