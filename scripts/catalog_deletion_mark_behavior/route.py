"""Source-pinned 32-Boolean transport; no native result is assumed.

This packet is deliberately not wired into the older 24-observation host.
"""
from pathlib import Path
import hashlib
import json
import re

PROFILE = 'catalog-deletion-mark-behavior-v1'
SCHEMA = 'native-1c-catalog-deletion-mark-v1'
STAGE_SCHEMA = 'native-1c-catalog-deletion-mark-stage-v1'
SOURCE_SHA256 = '6934171e56557c704c2ac95543524199661a624a9a5bc368a7a6703ec7d515b6'
SETUP_SHA256 = 'ad6a3cb83c6522c3619fc3d26da52c1f3a27871492d198947ac42d901e70a6a7'
CATALOG_SHA256 = '3414505a0fbab2d873777e0abf549f3e3868c8b0fa676c9b1d40774fe481545a'
MAX_OUTPUT = 8192
COUNT = 32


def source():
    path = Path(__file__).with_name('observe.bsl')
    if path.is_symlink() or not path.is_file():
        raise ValueError('source unavailable')
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
Message("CDM|@@NONCE@@|entered");
'''.replace('@@NONCE@@', nonce).encode('utf-8')
    result = prefix + source() + ('Message("CDM|'+nonce+'|completed");\n').encode('ascii')
    if len(result) > MAX_OUTPUT:
        raise ValueError('source bound')
    return result


def canonical(values):
    if type(values) not in (list, tuple) or len(values) != COUNT or any(type(v) is not bool for v in values):
        raise ValueError('invalid observations')
    return (json.dumps(list(values), separators=(',', ':')) + '\n').encode('ascii')


def parse_wire(raw, nonce):
    if (type(raw) is not bytes or not 0 < len(raw) <= MAX_OUTPUT or type(nonce) is not str
            or re.fullmatch('[0-9a-f]{32}', nonce) is None):
        raise ValueError('wire bound')
    try:
        text = raw.decode('ascii')
    except UnicodeError:
        raise ValueError('wire encoding') from None
    prefix = 'CDM|' + nonce + '|'
    if '\r' in text or not text.endswith('\n'):
        raise ValueError('wire lines')
    lines = text.splitlines()
    if len(lines) != COUNT + 2 or lines[0] != prefix + 'entered' or lines[-1] != prefix + 'completed':
        raise ValueError('wire markers')
    result = []
    for index, line in enumerate(lines[1:-1], 1):
        expected = prefix + str(index) + '|B|'
        if line not in (expected+'0', expected+'1'):
            raise ValueError('wire identity')
        result.append(line.endswith('1'))
    canonical(result)
    return result
