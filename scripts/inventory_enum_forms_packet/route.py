"""Nonce/source-bound acquisition framing, never runtime semantic parity."""
import hashlib
import json
import re
from pathlib import Path
from .records import GROUPS, MAX_OUTPUT, parse_records
from .assets import ASSET_HASHES
ROOT=Path(__file__).resolve().parent
PROFILE='configuration-owned-enum-forms-v1'
SCHEMA='native-owned-enum-forms-v1'
STAGE_SCHEMA='native-1c-owned-enum-forms-stage-v1'
MAX_SOURCE=262144
MAX_MARKER=16384
PACKET_HASHES=ASSET_HASHES
SOURCE_SHA256=hashlib.sha256(json.dumps(ASSET_HASHES,sort_keys=True,separators=(',',':')).encode()).hexdigest()
FORM_SHA256=hashlib.sha256(b''.join(p.encode()+b'\0'+bytes.fromhex(h) for p,h in sorted(ASSET_HASHES.items()) if p.endswith('.xml'))).hexdigest()
EXECUTABLE_MODULES=('Launcher/Forms/Main/Ext/Form/Module.bsl','Launcher/Ext/ObjectModule.bsl')
PHASES=('entered','completed','error')


def packet():
    result={}
    for path,digest in ASSET_HASHES.items():
        target=ROOT/path
        if target.is_symlink() or not target.is_file():raise ValueError('owned packet file')
        raw=target.read_bytes()
        if len(raw)>MAX_SOURCE or hashlib.sha256(raw).hexdigest()!=digest:raise ValueError('owned packet hash')
        result[path]=raw
    return result


def sources():
    result={p:raw for p,raw in packet().items() if p=='Launcher.xml' or p.startswith('Launcher/')}
    name=EXECUTABLE_MODULES[0]
    result[name]=result[name].replace(b'SOURCE_VALUE',SOURCE_SHA256.encode()).replace(b'FORM_VALUE',FORM_SHA256.encode())
    return result


def module():
    return sources()[EXECUTABLE_MODULES[0]]


def verify_hashes(hashes):
    if any(hashes.get('scripts/inventory_enum_forms_packet/'+p)!=h for p,h in ASSET_HASHES.items()):
        raise ValueError('owned packet staged hash')


def normalized(raw):return raw.decode('utf-8-sig').replace('\r\n','\n').encode()


def module_digest(files=None):
    files=sources() if files is None else files
    return hashlib.sha256(b''.join(p.encode()+b'\0'+normalized(files[p]) for p in EXECUTABLE_MODULES)).hexdigest()


def validate_executable_redump(files):
    expected=sources()
    if type(files) is not dict or set(files)!=set(EXECUTABLE_MODULES):raise ValueError('launcher executable inventory')
    if any(normalized(files[p])!=normalized(expected[p]) for p in EXECUTABLE_MODULES):raise ValueError('launcher executable drift')
    return module_digest(files)


def validate_redump(files):
    expected=sources()
    if type(files) is not dict or set(files)!=set(expected):raise ValueError('launcher source inventory')
    if any((normalized(files[p])!=normalized(expected[p]) if p.endswith('.bsl') else files[p]!=expected[p])
           for p in files):raise ValueError('launcher source drift')
    return module_digest(files)


def _json(raw):
    def unique(pairs):
        result={}
        for key,value in pairs:
            if key in result:raise ValueError('duplicate witness key')
            result[key]=value
        return result
    if type(raw) is not bytes or not 0<len(raw)<=MAX_MARKER:raise ValueError('witness bound')
    return json.loads(raw.decode('utf-8-sig'),object_pairs_hook=unique)


def marker(raw,nonce,phase):
    value=_json(raw)
    if (not re.fullmatch('[0-9a-f]{32}',nonce) or phase not in PHASES or type(value) is not dict
            or set(value)!={'schema','nonce','phase','source_sha256','form_sha256','records'}
            or value['schema']!=SCHEMA or value['nonce']!=nonce or value['phase']!=phase
            or value['source_sha256']!=SOURCE_SHA256 or value['form_sha256']!=FORM_SHA256
            or type(value['records']) is not str):raise ValueError('owned marker binding')
    if phase=='completed':parse_records(value['records'].encode('ascii'))
    elif value['records']!='':raise ValueError('owned marker phase')
    return value


def lifecycle(raw,nonce):
    value=_json(raw)
    if type(value) is not dict or set(value)!={'nonce','events'} or value['nonce']!=nonce or type(value['events']) is not list:
        raise ValueError('owned lifecycle envelope')
    expected={(flow,instance):[] for flow in range(1,9) for instance in ((1,2) if flow in (3,8) else (1,))}
    if len(value['events'])!=30:raise ValueError('complete owned lifecycles required')
    for event in value['events']:
        if type(event) is not dict or set(event)!={'flow','instance','code'}:raise ValueError('owned lifecycle event')
        flow,instance=event['flow'],event['instance']
        if type(flow) is not int or type(instance) is not int or (flow,instance) not in expected:raise ValueError('owned lifecycle identity')
        expected[flow,instance].append(event['code'])
    if any(codes!=['create','open','observed'] for codes in expected.values()):raise ValueError('actual lifecycle order')
    # Independent drafts must both be open before either authored observation.
    independent=[e for e in value['events'] if e['flow']==8]
    first_observed=next(i for i,e in enumerate(independent) if e['code']=='observed')
    if {e['instance'] for e in independent[:first_observed] if e['code']=='open'}!={1,2}:raise ValueError('independent live form pair')
    return True


def require_available(records):
    if tuple(name for name,_ in records)!=GROUPS:raise ValueError('all eight groups required')
    return records
