"""Bounded A/A diagnostics. UUID-masked hashes never establish acceptance."""
import hashlib, io, json, re
import xml.etree.ElementTree as ET
from . import packet
from .mutations import projection
UUID=re.compile(r'(?i)(?<![0-9a-f])[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}(?![0-9a-f])')
MAX_FILES=64
MAX_BYTES=1024*1024
MAX_TOTAL=8*MAX_BYTES
HASH_FIELDS=('raw_sha256','strict_sha256','permutation_sha256','diagnostic_uuid_masked_sha256',
             'structure_sha256','attributes_sha256','text_sha256','namespace_sha256')

def digest(value):
    return hashlib.sha256(json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest()

def mask_uuid(value):
    if isinstance(value,str):return UUID.sub('<uuid>',value)
    if isinstance(value,(list,tuple)):return [mask_uuid(x) for x in value]
    return value

def xml_bounds(raw):
    depth=count=0
    for event,node in ET.iterparse(io.BytesIO(raw),events=('start','end')):
        if event=='start':
            depth+=1;count+=1
            if depth>64 or count>8192 or len(node.attrib)>256:raise ValueError('XML limit')
        else:depth-=1

def components(tree):
    shape=[];attrs=[];texts=[];scopes=[];stack=[(tree,0)]
    while stack:
        node,depth=stack.pop()
        shape.append((depth,node[0],len(node[4])));attrs.append(node[1]);scopes.append(node[2]);texts.append((node[3],node[5]))
        stack.extend((c,depth+1) for c in reversed(node[4]))
    return tuple(digest(x) for x in (shape,attrs,texts,scopes))

def fingerprint(files,known_names=()):
    """Include every file, including ConfigDumpInfo, in raw/exact comparisons.

    Opaque slots are aligned only with matching full inventory hashes. known_slot
    indexes sorted known input filenames (or -1 for a native-added file).
    Structural categories refer to projection, not raw-byte differences.
    """
    if type(files)!=dict or not 0<len(files)<=MAX_FILES:raise ValueError('inventory limit')
    if any(type(n)!=str or len(n.encode())>1024 or type(raw)!=bytes or len(raw)>MAX_BYTES for n,raw in files.items()):raise ValueError('file limit')
    if sum(map(len,files.values()))>MAX_TOTAL:raise ValueError('total limit')
    known=sorted(known_names)
    if len(known)>MAX_FILES or len(set(known))!=len(known):raise ValueError('known inventory')
    names=sorted(files);rows=[]
    for index,name in enumerate(names):
        raw=files[name];text=raw.decode('utf-8-sig')
        if '<!DOCTYPE' in text.upper() or '<!ENTITY' in text.upper():raise ValueError('DTD rejected')
        if name.endswith('.bsl'):
            strict=permitted=text.replace('\r\n','\n');kind='bsl';parts=(digest([]),digest([]),digest(strict),digest([]))
        elif name.endswith('.xml'):
            xml_bounds(raw)
            strict=projection(raw);permitted=projection(raw,allow=name in (packet.FORM,packet.META));kind='xml';parts=components(strict)
        else:raise ValueError('file kind')
        row=dict(slot=index,known_slot=known.index(name) if name in known else -1,kind=kind,
            legacy_excluded=name=='ConfigDumpInfo.xml',raw_sha256=hashlib.sha256(raw).hexdigest(),
            strict_sha256=digest(strict),permutation_sha256=digest(permitted),
            diagnostic_uuid_masked_sha256=digest(mask_uuid(permitted)),uuid_token_count=len(UUID.findall(text)))
        row.update(zip(HASH_FIELDS[4:],parts));rows.append(row)
    return dict(schema='xml-order-aa-fingerprint-v2',inventory_sha256=digest(names),
        known_inventory_sha256=digest(known),files=rows,acceptance_use=False)

def validate(value,known_names=()):
    def need(ok):
        if not ok:raise ValueError('fingerprint schema')
    def hashed(x):return type(x)==str and re.fullmatch('[0-9a-f]{64}',x) is not None
    need(type(value)==dict and set(value)=={'schema','inventory_sha256','known_inventory_sha256','files','acceptance_use'})
    need(value['schema']=='xml-order-aa-fingerprint-v2' and value['acceptance_use'] is False)
    need(hashed(value['inventory_sha256']) and value['known_inventory_sha256']==digest(sorted(known_names)))
    rows=value['files'];need(type(rows)==list and 0<len(rows)<=MAX_FILES)
    for i,row in enumerate(rows):
        need(type(row)==dict and set(row)=={'slot','known_slot','kind','legacy_excluded','uuid_token_count',*HASH_FIELDS})
        need(type(row['slot'])==int and row['slot']==i and type(row['known_slot'])==int and -1<=row['known_slot']<len(known_names))
        need(row['kind'] in ('xml','bsl') and type(row['legacy_excluded'])==bool)
        need(type(row['uuid_token_count'])==int and 0<=row['uuid_token_count']<=MAX_BYTES//36)
        need(all(hashed(row[k]) for k in HASH_FIELDS))
    return value

def compare(left,right):
    """Caller validates wire data first. No masked signal is an equality gate."""
    if left['inventory_sha256']!=right['inventory_sha256']:return {'comparison':'inventory_changed','slots':[],'raw_equal':False,'strict_equal':False,'permutation_equal':False}
    if len(left['files'])!=len(right['files']):raise ValueError('slot count')
    slots=[];equal=[True]*3
    for a,b in zip(left['files'],right['files']):
        if a['slot']!=b['slot']:raise ValueError('slot identity')
        for i,k in enumerate(HASH_FIELDS[:3]):equal[i] &= a[k]==b[k]
        if a['raw_sha256']==b['raw_sha256']:continue
        category=('raw_only_difference' if a['strict_sha256']==b['strict_sha256'] else
            'permitted_permutation_difference' if a['permutation_sha256']==b['permutation_sha256'] else
            'projected_uuid_token_difference_only' if a['diagnostic_uuid_masked_sha256']==b['diagnostic_uuid_masked_sha256'] else 'other_or_mixed_difference')
        slots.append(dict(slot=a['slot'],known_slot=a['known_slot'],kind=a['kind'],legacy_excluded=a['legacy_excluded'],category=category,
            components=[k.removesuffix('_sha256') for k in HASH_FIELDS[4:] if a[k]!=b[k]]))
    return dict(comparison='exact_equal' if equal[0] else 'different',slots=slots,
        raw_equal=equal[0],strict_equal=equal[1],permutation_equal=equal[2])

TRACE_CODES={'create','open_effect','closing_blocked','cancel_effect','closing_allowed','closed'}

def partial_trace(raw,nonce):
    """Offline finite trace diagnosis, including after timeout; never a witness.

No partial prefix, error code or timeout can satisfy packet.witness.
"""
    from native_1c_xml_order_ci_policy import unique
    if raw is None:return dict(state='missing',codes=[])
    if type(raw)!=bytes or len(raw)>4096:return dict(state='invalid',codes=[])
    try:
        t=json.loads(raw.decode('utf-8-sig'),object_pairs_hook=unique)
        if type(t)!=dict or set(t)!={'nonce','events'} or t['nonce']!=nonce:return dict(state='invalid',codes=[])
        if type(t['events'])!=list or len(t['events'])>12:return dict(state='invalid',codes=[])
        codes=[]
        allowed_items={','.join(packet.UI),','.join((packet.UI[1],packet.UI[0],*packet.UI[2:]))}
        for code in t['events']:
            if type(code)!=str:return dict(state='invalid',codes=[])
            if code in TRACE_CODES:codes.append(code)
            elif code.startswith('items:') and code[6:] in allowed_items:codes.append('items_observed')
            else:return dict(state='invalid',codes=[])
        return dict(state='empty' if not codes else 'partial_or_complete',codes=codes)
    except (ValueError,UnicodeError):return dict(state='invalid',codes=[])
