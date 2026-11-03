"""Strict source and nonce transport for 20 Boolean diagnostics."""
from pathlib import Path
import hashlib
import json
import re

PROFILE = 'catalog-deletion-mark-diagnostic-v1'
SCHEMA = 'native-1c-catalog-deletion-mark-diagnostic-v1'
STAGE_SCHEMA = 'native-1c-catalog-deletion-mark-diagnostic-stage-v1'
SOURCE_SHA256 = '83ea20a0c0fd6722431bc1b0638c3e57b112859f0c9ee95708ece09a6dea361f'
CATALOG_RIGHTS = ('Read', 'Insert', 'Update', 'Delete')
MAX_OUTPUT = 8192
COUNT = 20


def source():
    path = Path(__file__).with_name('observe.bsl')
    if path.is_symlink() or not path.is_file(): raise ValueError('source unavailable')
    raw = path.read_bytes()
    if len(raw) > MAX_OUTPUT or hashlib.sha256(raw).hexdigest() != SOURCE_SHA256:
        raise ValueError('source changed')
    raw.decode('utf-8')
    return raw


def program(setup, nonce):
    if (type(nonce) is not str or re.fullmatch('[0-9a-f]{32}', nonce) is None
            or getattr(setup, 'name', None) != 'OwnedCatalog4f4ccaa9'
            or getattr(setup, 'metadata_uuid', None) != 'db779364-756d-4493-92d8-654ed6bb546e'):
        raise ValueError('packet identity')
    prefix = '''Procedure CDMEmit(Val N,Val V)
    If TypeOf(V)<>Type("Boolean") Then Raise "CDM scalar unsupported"; EndIf;
    If V Then Text="1"; Else Text="0"; EndIf;
    Message("CDM|@@NONCE@@|"+String(N)+"|B|"+Text);
EndProcedure
'''.replace('@@NONCE@@', nonce).encode('utf-8')
    raw = source()
    boundary = b"\nM = Catalogs."
    if raw.count(boundary) != 1:
        raise ValueError('source layout')
    declarations, body = raw.split(boundary, 1)
    if declarations.count(b'Function CDMClass(') != 1 or declarations.count(b'EndFunction') != 1:
        raise ValueError('source declarations')
    entered = ('Message("CDM|'+nonce+'|entered");\n').encode('ascii')
    result = prefix + declarations + b'\n' + entered + b'M = Catalogs.' + body + ('Message("CDM|'+nonce+'|completed");\n').encode('ascii')
    if len(result) > MAX_OUTPUT: raise ValueError('source bound')
    return result


def canonical(values):
    if (type(values) not in (list, tuple) or len(values) != COUNT
            or any(type(v) is not bool for v in values)
            or sum(values[0:5]) != 1 or sum(values[10:15]) != 1):
        raise ValueError('invalid observations')
    return (json.dumps(list(values), separators=(',', ':'))+'\n').encode('ascii')


def parse_wire(raw, nonce):
    if (type(raw) is not bytes or not 0 < len(raw) <= MAX_OUTPUT or type(nonce) is not str
            or re.fullmatch('[0-9a-f]{32}', nonce) is None): raise ValueError('wire bound')
    try: text = raw.decode('ascii')
    except UnicodeError: raise ValueError('wire encoding') from None
    prefix = 'CDM|' + nonce + '|'
    if '\r' in text or not text.endswith('\n'): raise ValueError('wire lines')
    lines = text.splitlines()
    if len(lines) != COUNT+2 or lines[0] != prefix+'entered' or lines[-1] != prefix+'completed':
        raise ValueError('wire markers')
    result = []
    for index, line in enumerate(lines[1:-1], 1):
        expected = prefix+str(index)+'|B|'
        if line not in (expected+'0', expected+'1'): raise ValueError('wire identity')
        result.append(line.endswith('1'))
    canonical(result)
    return result
