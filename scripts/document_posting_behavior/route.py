"""Exactly twelve bounded raw scalar observations, no expected behavior."""
from pathlib import Path
import hashlib
import json
import re
PROFILE='document-posting-observation-v1'
SCHEMA='native-1c-document-posting-v1'
STAGE_SCHEMA='native-1c-document-posting-stage-v1'
COUNT=12
MAX_OUTPUT=16384
SOURCE_SHA256='405c94d686297f96488673f8d6bd8f7279b891d6ef6c0829744c4f316db0850d'
def source():
    p=Path(__file__).with_name('observe.bsl')
    if p.is_symlink():raise ValueError('source symlink')
    raw=p.read_bytes()
    if not 0<len(raw)<=MAX_OUTPUT or hashlib.sha256(raw).hexdigest()!=SOURCE_SHA256:raise ValueError('source changed')
    return raw

def program(setup,nonce):
    if type(nonce) is not str or re.fullmatch('[0-9a-f]{32}',nonce) is None:raise ValueError('nonce')
    prefix=('Procedure PostingEmit(N,V)\nMessage("POST|'+nonce+'|"+String(N)+"|"+V);\nEndProcedure\nMessage("POST|'+nonce+'|entered");\n').encode()
    return prefix+source()+('Message("POST|'+nonce+'|completed");\n').encode()

def canonical(values):
    if type(values) is not list or len(values)!=COUNT or any(type(v) is not str or len(v)>512 or re.fullmatch(r'[A-Za-z0-9,;:| .-]+',v) is None for v in values):raise ValueError('observations')
    return (json.dumps(values,separators=(',',':'))+'\n').encode('ascii')

def parse_wire(raw,nonce):
    if type(raw) is not bytes or not 0<len(raw)<=MAX_OUTPUT or re.fullmatch('[0-9a-f]{32}',nonce) is None:raise ValueError('wire')
    lines=raw.decode('ascii').splitlines();prefix='POST|'+nonce+'|'
    if len(lines)!=COUNT+2 or lines[0]!=prefix+'entered' or lines[-1]!=prefix+'completed':raise ValueError('markers')
    values=[]
    for n,line in enumerate(lines[1:-1],1):
        expected=prefix+str(n)+'|'
        if not line.startswith(expected):raise ValueError('order')
        values.append(line[len(expected):])
    canonical(values);return values
