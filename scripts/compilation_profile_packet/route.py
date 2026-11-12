"""Exact owned source and nonce-bound two-event marker admission."""
import hashlib
import json
import re
from . import MAX_SOURCE, MAX_OUTPUT, PACKET_HASHES, SOURCE_SHA256, FORM_SHA256, MODULES_SHA256, packet, parse_records
SCHEMA='native-compilation-profile-v1'
MAX_MARKER=16384
MODULES=tuple(p for p in PACKET_HASHES if p.endswith('.bsl'))
PHASES=('entered','event1_done','completed','error')

def verify_hashes(hashes):
    if any(hashes.get('scripts/compilation_profile_packet/'+p)!=h for p,h in PACKET_HASHES.items()):raise ValueError('packet staged identity')

def sources():
    values=packet()
    p='Launcher/Forms/Main/Ext/Form/Module.bsl'
    values[p]=values[p].replace(b'SOURCE_VALUE',SOURCE_SHA256.encode()).replace(b'FORM_VALUE',FORM_SHA256.encode()).replace(b'MODULES_VALUE',MODULES_SHA256.encode())
    return values

def normalized(raw):
    return raw.decode('utf-8-sig').replace('\r\n','\n').encode('utf-8')

def module_digest(values=None):
    values=sources() if values is None else values
    return hashlib.sha256(b''.join(p.encode()+b'\0'+normalized(values[p]) for p in MODULES)).hexdigest()

def validate_prepared(files):
    expected=sources()
    if type(files) is not dict or set(files)!=set(expected):raise ValueError('packet inventory')
    for path,wanted in expected.items():
        actual=files[path]
        if type(actual) is not bytes or not 0<len(actual)<=MAX_SOURCE:raise ValueError('packet size')
        if (normalized(actual)!=normalized(wanted) if path.endswith('.bsl') else actual!=wanted):raise ValueError('packet identity')
    return module_digest(files)

def marker(raw,nonce,phase):
    if type(raw) is not bytes or not 0<len(raw)<=MAX_MARKER:raise ValueError('marker budget')
    if phase not in PHASES or not re.fullmatch('[0-9a-f]{32}',nonce):raise ValueError('marker phase')
    def pairs(items):
        value={}
        for k,v in items:
            if k in value:raise ValueError('duplicate marker key')
            value[k]=v
        return value
    try:value=json.loads(raw.decode('utf-8-sig'),object_pairs_hook=pairs)
    except (UnicodeDecodeError,json.JSONDecodeError):raise ValueError('marker encoding') from None
    if type(value) is not dict or set(value)!={'schema','nonce','phase','source_sha256','form_sha256','modules_sha256','records'}:raise ValueError('marker shape')
    if (value['schema']!=SCHEMA or value['nonce']!=nonce or value['phase']!=phase or value['source_sha256']!=SOURCE_SHA256 or value['form_sha256']!=FORM_SHA256 or value['modules_sha256']!=MODULES_SHA256):raise ValueError('marker binding')
    if type(value['records']) is not str:raise ValueError('marker records')
    if phase in ('completed','event1_done'):parse_records(value['records'].encode('ascii'),16 if phase=='completed' else 15)
    elif value['records']!='':raise ValueError('marker phase payload')
    return value

def module():
    return sources()['Launcher/Forms/Main/Ext/Form/Module.bsl']
