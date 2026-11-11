"""Exact two-form source/redump/marker admission; no process entry point."""
import hashlib
import json
import re
import xml.etree.ElementTree as ET
from . import ROOT, MAX_SOURCE, MAX_OUTPUT, PACKET_HASHES, SOURCE_SHA256, FORM_SHA256, packet, parse_records
SCHEMA='native-managed-form-results-v1'
MAX_MARKER=16384
MODULES=('Launcher/Forms/Main/Ext/Form/Module.bsl','Launcher/Forms/Child/Ext/Form/Module.bsl')
PHASES=('entered','completed','error')


def verify_hashes(hashes):
    if any(hashes.get('scripts/form_results_packet/'+p)!=h for p,h in PACKET_HASHES.items()):
        raise ValueError('packet staged identity')


def sources():
    values=packet()
    values[MODULES[0]]=values[MODULES[0]].replace(b'SOURCE_VALUE',SOURCE_SHA256.encode()).replace(b'FORM_VALUE',FORM_SHA256.encode())
    return values


def module():
    return sources()[MODULES[0]]


def normalized(raw):
    return raw.decode('utf-8-sig').replace('\r\n','\n').encode('utf-8')


def module_digest(values=None):
    values=sources() if values is None else values
    return hashlib.sha256(b''.join(p.encode()+b'\0'+normalized(values[p]) for p in MODULES)).hexdigest()


def _canonical(raw):
    if type(raw) is not bytes or not 0<len(raw)<=MAX_SOURCE: raise ValueError('XML size')
    try: text=raw.decode('utf-8-sig')
    except UnicodeDecodeError: raise ValueError('XML encoding') from None
    if '\x00' in text or '<!' in text: raise ValueError('XML envelope')
    declaration=re.match(r'^<\?xml\s+[^?]*\?>',text)
    if declaration:
        encoding=re.search(r'encoding\s*=\s*[\"\']([^\"\']+)',declaration[0])
        if encoding and encoding[1].lower()!='utf-8': raise ValueError('XML encoding')
    if '<?' in (text[declaration.end():] if declaration else text): raise ValueError('XML instructions')
    try: root=ET.fromstring(text)
    except ET.ParseError: raise ValueError('XML parse') from None
    if root.attrib.get('version') not in ('2.4','2.20'): raise ValueError('XML version')
    root.attrib['version']='2.4'
    ns='{http://v8.1c.ru/8.3/xcf/logform}'
    for events in root.findall(ns+'Events'):
        events[:]=sorted(events,key=lambda e:e.attrib.get('name',''))
    # QName-valued Type text must keep its exact prefix meaning, not merely text.
    import io
    bindings={};started=False
    for event,value in ET.iterparse(io.BytesIO(raw),events=('start-ns','start')):
        if event=='start':started=True
        else:
            if started or value[0] in bindings: raise ValueError('XML namespace scope')
            bindings[value[0]]=value[1]
    if root.tag==ns+'Form':
        for prefix,uri in {'':'http://v8.1c.ru/8.3/xcf/logform','cfg':'http://v8.1c.ru/8.1/data/enterprise/current-config','v8':'http://v8.1c.ru/8.1/data/core'}.items():
            if bindings.get(prefix)!=uri: raise ValueError('XML QName binding')
    rows=[];qnames=set();stack=[(root,0)]
    while stack:
        node,depth=stack.pop()
        if depth>16 or len(rows)>=256:raise ValueError('XML bounds')
        for value in [*(node.attrib.values()),(node.text or '').strip()]:
            if re.fullmatch(r'[A-Za-z_]\w*:[A-Za-z_]\w*(?:\.\w+)*',value):
                prefix=value.split(':',1)[0]
                if prefix not in bindings:raise ValueError('XML unbound QName')
                qnames.add((prefix,bindings[prefix]))
        rows.append((depth,node.tag,tuple(sorted(node.attrib.items())),(node.text or '').strip(),(node.tail or '').strip(),len(node)))
        stack.extend((child,depth+1) for child in reversed(list(node)))
    return tuple(sorted(qnames)),tuple(rows)


def validate_redump(files):
    expected=sources()
    if type(files) is not dict or set(files)!=set(expected):raise ValueError('packet inventory')
    for path,wanted in expected.items():
        actual=files[path]
        if type(actual) is not bytes or not 0<len(actual)<=MAX_SOURCE:raise ValueError('packet size')
        if path.endswith('.xml'):
            if _canonical(actual)!=_canonical(wanted):raise ValueError('packet XML binding')
        elif normalized(actual)!=normalized(wanted):raise ValueError('packet module binding')
    return module_digest(files)


def marker(raw,nonce,phase):
    if type(raw) is not bytes or not 0<len(raw)<=MAX_MARKER or not re.fullmatch('[0-9a-f]{32}',nonce) or phase not in PHASES:raise ValueError('marker envelope')
    def unique(pairs):
        result={}
        for key,value in pairs:
            if key in result:raise ValueError('marker duplicate')
            result[key]=value
        return result
    try:value=json.loads(raw.decode('utf-8-sig'),object_pairs_hook=unique)
    except (UnicodeDecodeError,json.JSONDecodeError):raise ValueError('marker encoding') from None
    if type(value) is not dict or set(value)!={'schema','nonce','phase','source_sha256','form_sha256','records'}:raise ValueError('marker shape')
    if value['schema']!=SCHEMA or value['nonce']!=nonce or value['phase']!=phase or value['source_sha256']!=SOURCE_SHA256 or value['form_sha256']!=FORM_SHA256:raise ValueError('marker binding')
    if type(value['records']) is not str:raise ValueError('marker records')
    if phase=='completed':parse_records(value['records'].encode('ascii'))
    elif value['records']!='':raise ValueError('marker phase payload')
    return value
