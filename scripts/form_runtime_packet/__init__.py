"""Local preparation only: this module does not launch 1C or claim acquisition.

A future reviewed route must preserve the module's explicit side directives,
verify re-dumped managed-form event wiring and bind output to the exact source.
"""
from pathlib import Path
import hashlib
import re
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parent
MAX_SOURCE = 8192
MAX_OUTPUT = 4096
COUNT = 40
# Assigned after the fixed public module is frozen. No runtime-derived dictionary.
SOURCE_SHA256 = 'e05fed09cf85803443be815b357c5e20d9b05ad9c6f39bc622e111d0da1d3b73'
KINDS = tuple('platform-lifecycle' if n in (24,25) else
              'direct-handler' if n in (31,32,33,34,37,39,40) else 'programmatic'
              for n in range(1,41))
UNMEASURED = ('automatic-field-change', 'automatic-command-dispatch',
              'platform-cancelled-close', 'cancelled-create-open', 'catalog-ref-transfer')


def source():
    raw = (ROOT/'module.bsl').read_bytes()
    if len(raw)>MAX_SOURCE or hashlib.sha256(raw).hexdigest()!=SOURCE_SHA256:
        raise ValueError('form source identity mismatch')
    return raw.decode('utf-8')


def validate_wiring(raw):
    if type(raw) is not bytes or len(raw)>MAX_SOURCE or b'<!' in raw:
        raise ValueError('invalid form wiring')
    root = ET.fromstring(raw)
    ns = '{http://v8.1c.ru/8.3/xcf/logform}'
    if root.tag!=ns+'Form': raise ValueError('invalid form wiring')
    events=root.findall(ns+'Events/'+ns+'Event')
    expected=[('OnCreateAtServer','FormCreate'),('OnOpen','FormOpen'),('BeforeClose','FormBeforeClose')]
    if [(n.attrib.get('name'),n.text) for n in events]!=expected or any(set(n.attrib)!={'name'} for n in events):
        raise ValueError('invalid form event binding')
    if len(root.findall('.//'+ns+'Event'))!=3: raise ValueError('unexpected event binding')
    return True


def parse_records(raw):
    if type(raw) is not bytes or len(raw)>MAX_OUTPUT: raise ValueError('invalid form observations')
    try: value=raw.decode('ascii')
    except UnicodeError: raise ValueError('invalid form observations') from None
    chunks=value.split('|')
    if len(chunks)!=COUNT+1 or chunks[-1]!='': raise ValueError('invalid form observation count')
    values=[]
    for index,chunk in enumerate(chunks[:-1],1):
        prefix='MF'+str(index)+'='
        if not chunk.startswith(prefix): raise ValueError('invalid form observation order')
        result=chunk[len(prefix):]
        if re.fullmatch(r'[A-Za-z0-9:!?_-]{0,64}',result) is None: raise ValueError('invalid form observation value')
        values.append(result)
    return tuple(values)


def require_available(values):
    if type(values) is not tuple or len(values)!=COUNT or any(type(v) is not str or v=='!E' for v in values):
        raise ValueError('incomplete form observations')
    # This means the programmatic/direct-call packet ran, NOT automatic UI parity.
    return values
