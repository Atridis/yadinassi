"""LOCAL observer grammar, not native acceptance or a Metadata implementation."""
from __future__ import annotations
import re

CASE_COUNT = 24
MAX_TEXT_UNITS = 64
MAX_OUTPUT_BYTES = 8192
C1 = b'CR-C1: [S0:]\n'
C2 = b'CR-C2: [S6:004100a0003b0022d83dde00]\n'
MAX_ENCODED_BYTES = len(C1 + C2) + CASE_COUNT * len(b'CR-01: [ok|S64:' + b'0000' * 64 + b']\n')


def decode_scalar(raw: str):
    if raw == 'U': return ('undefined', None)
    if raw in ('B0', 'B1'): return ('boolean', raw == 'B1')
    if re.fullmatch(r'N(?:0|[1-9][0-9]?)', raw):
        number = int(raw[1:])
        if number <= 64: return ('number', number)
        raise ValueError('number-bound')
    match = re.fullmatch(r'S(0|[1-9][0-9]?):([0-9a-f]*)', raw)
    if not match: raise ValueError('scalar')
    count = int(match[1]); encoded = match[2]
    if count > MAX_TEXT_UNITS or len(encoded) != count * 4: raise ValueError('text-bound')
    units = tuple(int(encoded[i:i+4], 16) for i in range(0,len(encoded),4))
    return ('string', units)


def validate_output(raw: bytes, *, case_count=CASE_COUNT):
    if type(case_count) is not int or case_count not in (12, 24): raise ValueError("case-count-contract")
    if type(raw) is not bytes or not raw or len(raw) > MAX_OUTPUT_BYTES: raise ValueError('wire-bound')
    if not raw.startswith(C1+C2) or not raw.endswith(b'\n') or b'\r' in raw: raise ValueError('framing')
    lines=raw[len(C1+C2):].splitlines()
    if len(lines) != case_count: raise ValueError('record-count')
    records=[]
    for index,line in enumerate(lines,1):
        text=line.decode('ascii')
        prefix=f'CR-{index:02}: ['
        if not text.startswith(prefix) or not text.endswith(']'): raise ValueError('record-label')
        body=text[len(prefix):-1]
        if body in ('action-error','observer-error'):
            records.append({'id':index,'status':body,'kind':None,'value':None});continue
        if not body.startswith('ok|'): raise ValueError('status')
        kind,value=decode_scalar(body[3:])
        records.append({'id':index,'status':'ok','kind':kind,'value':value})
    return records
