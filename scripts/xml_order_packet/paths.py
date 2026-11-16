"""Finite scalar diagnostics for two fixed public XML filenames; no raw values.

Sequence indices are retained. No sorting of children/properties/events occurs.
QName vocabulary is derived from pinned public Configuration.xml plus the closed
ConfigDumpInfo/ConfigVersions/Metadata envelope (native format, no arbitrary names).
"""
import hashlib,re,xml.etree.ElementTree as ET
from . import measurement as m
FILES=('Configuration.xml','ConfigDumpInfo.xml')
DUMP='{http://v8.1c.ru/8.3/xcf/dumpinfo}'
MD='{http://v8.1c.ru/8.3/MDClasses}'
MAX_ROWS=512

def parsed(raw):
    if type(raw)!=bytes or len(raw)>m.MAX_BYTES:raise ValueError('path input limit')
    if b'<!DOCTYPE' in raw.upper() or b'<!ENTITY' in raw.upper():raise ValueError('DTD')
    m.xml_bounds(raw);return ET.fromstring(raw)

def vocabulary(source):
    root=parsed(source['Configuration.xml'])
    tags={n.tag for n in root.iter()};attrs={k for n in root.iter() for k in n.attrib}
    tags.update(DUMP+n for n in ('ConfigDumpInfo','ConfigVersions','Metadata'))
    attrs.update(('format','version','name','id','configVersion'))
    return tags,attrs

def kind(text):
    if m.UUID.fullmatch(text):return 'uuid'
    if re.fullmatch('[0-9a-fA-F]{32,64}',text):return 'hex'
    return 'other'

def scalars(raw,source):
    root=parsed(raw);tags,attrs=vocabulary(source);rows=[];omitted=0
    config_name=parsed(source['Configuration.xml']).find('./'+MD+'Configuration/'+MD+'Properties/'+MD+'Name').text
    def walk(node,path,depth,positions):
        nonlocal omitted
        if node.tag not in tags or depth>16:
            omitted+=1;return
        # Path only contains reviewed public QName vocabulary, never native values.
        identity='configuration' if node.tag==DUMP+'Metadata' and node.get('name')=='Configuration.'+config_name else 'none'
        values=[('#text',node.text)] if node.text and node.text.strip() else []
        values += [('@'+k,v) for k,v in sorted(node.attrib.items()) if k in attrs]
        omitted+=sum(k not in attrs for k in node.attrib)
        for field,value in values:
            if len(rows)>=MAX_ROWS:raise ValueError('path row limit')
            rows.append(dict(path=path,positions=positions,field=field,kind=kind(value),sha256=hashlib.sha256(value.encode()).hexdigest(),public_identity=identity))
        counts={}
        for absolute,child in enumerate(node,1):
            counts[child.tag]=counts.get(child.tag,0)+1
            # All sequence positions remain observable, including metadata lists.
            walk(child,path+[[child.tag,counts[child.tag]]],depth+1,positions+[absolute])
    walk(root,[[root.tag,1]],1,[1])
    return dict(rows=rows,omitted=omitted)

def key(row):return tuple((n,i) for n,i in row['path']),row['field']

def export(files,source):
    result={}
    for name in FILES:
        if name not in files:raise ValueError('required diagnostic file missing')
        data=scalars(files[name],source)
        initial=scalars(source[name],source) if name in source else dict(rows=[])
        before={key(r):r['sha256'] for r in initial['rows']}
        for row in data['rows']:
            old=before.get(key(row));row['source_relation']='absent' if old is None else 'same' if old==row['sha256'] else 'changed'
        result[name]=data
    return result

def validate(value,source):
    def need(x):
        if not x:raise ValueError('path schema')
    tags,attrs=vocabulary(source)
    need(type(value)==dict and set(value)==set(FILES))
    for data in value.values():
        need(type(data)==dict and set(data)=={'rows','omitted'})
        need(type(data['omitted'])==int and 0<=data['omitted']<=16384)
        need(type(data['rows'])==list and len(data['rows'])<=MAX_ROWS)
        seen=set()
        for r in data['rows']:
            need(type(r)==dict and set(r)=={'path','positions','field','kind','sha256','public_identity','source_relation'})
            need(type(r['path'])==list and 1<=len(r['path'])<=16)
            need(type(r['positions'])==list and len(r['positions'])==len(r['path']) and all(type(i)==int and 1<=i<=8192 for i in r['positions']))
            for pair in r['path']:
                need(type(pair)==list and len(pair)==2 and type(pair[0])==str and pair[0] in tags and type(pair[1])==int and 1<=pair[1]<=8192)
            need(type(r['field'])==str and (r['field']=='#text' or r['field'].startswith('@') and r['field'][1:] in attrs))
            need(r['kind'] in ('uuid','hex','other') and r['public_identity'] in ('none','configuration') and r['source_relation'] in ('same','changed','absent'))
            need(type(r['sha256'])==str and re.fullmatch('[0-9a-f]{64}',r['sha256']))
            need(key(r) not in seen);seen.add(key(r))
    return value

def compare(left,right):
    result={}
    for name in FILES:
        a={key(r):r for r in left[name]['rows']};b={key(r):r for r in right[name]['rows']};changes=[]
        for k in sorted(a.keys()|b.keys()):
            x,y=a.get(k),b.get(k)
            if x is not None and y is not None and x['sha256']==y['sha256'] and x['positions']==y['positions']:continue
            r=x or y
            changes.append(dict(path=r['path'],field=r['field'],kind=r['kind'],public_identity=r['public_identity'],
                category='added' if x is None else 'removed' if y is None else 'position_changed' if x['sha256']==y['sha256'] else 'value_changed',
                left_positions=None if x is None else x['positions'],right_positions=None if y is None else y['positions'],
                left_source=None if x is None else x['source_relation'],right_source=None if y is None else y['source_relation']))
        result[name]=dict(changes=changes,left_omitted=left[name]['omitted'],right_omitted=right[name]['omitted'])
    return result
