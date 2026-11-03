"""Bounded official XML installation for one output-only CatalogQuery packet.

No database files are read. Existing bootstrap permissions/modules are preserved;
only the owned catalog and its Read/Insert/Update permissions are added.
"""
from pathlib import Path, PurePosixPath
from uuid import UUID
import hashlib
import io
import json
import re
import xml.etree.ElementTree as ET
from xml.parsers import expat
from . import packet
try:
    from native_1c_bootstrap.inject_modules import ROLE_NAME, ROLE_FILES, ROLE_RIGHTS
except ModuleNotFoundError as error:
    if error.name not in ('native_1c_bootstrap','native_1c_bootstrap.inject_modules'):
        raise
    # Ordinary native bootstrap stages this same source module at its root.
    from inject_modules import ROLE_NAME, ROLE_FILES, ROLE_RIGHTS

MD='http://v8.1c.ru/8.3/MDClasses'
RIGHTS='http://v8.1c.ru/8.2/roles'
XSI='http://www.w3.org/2001/XMLSchema-instance'
V8='http://v8.1c.ru/8.1/data/core'
MAX_FILE=1024*1024
MAX_TOTAL=16*1024*1024
OWNED_RIGHTS=('Read','Insert','Update')
ASSET_HASHES = {'packet.py': '9a2158d07c2e58c1b3c0452ebdda3d68a82f3ee379a9f349293f87f4f99bff1c', 'Catalog.xml': 'bb1fd837dc38498e03a2ae71ab1eee571d8f0d8d6710f032782b07c2e7a68186', 'SOURCE.json': '65382a85c05990d99ac0d3cc3ecc13f2a2b05d5e17d3df264abf2d1a9c230350', 'generated/setup.json': '1030083630ba43bcd76c8c6287009e18ab216449bf9e7afe2d2163765a693c0c', 'generated/Catalog.xml': '5d9951f1f3d4db1f92dc7972ee3366b1347ba683783802f3ba612c2a0c57c233', 'generated/observe.bsl': '9fd13234641cba1526412d747d7cea62211178f7773808db8ad3b1c1b6f60be2'}


def _require(ok):
    if not ok:raise ValueError('invalid CatalogQuery XML fixture')


def _xml(raw):
    _require(type(raw) is bytes and len(raw)<=MAX_FILE and b'<!DOCTYPE' not in raw.upper() and b'<!ENTITY' not in raw.upper())
    try:
        pending=[];stack=[];scopes={};count=0
        for event,value in ET.iterparse(io.StringIO(raw.decode('utf-8-sig')),events=('start','end','start-ns')):
            if event=='start-ns':pending.append(value)
            elif event=='start':
                scope=dict(stack[-1]) if stack else {};scope.update(pending);pending.clear();stack.append(scope)
                scopes[id(value)]=scope;count+=1;_require(len(stack)<=32 and count<=20000)
            else:root=value;stack.pop()
        return root,scopes
    except (UnicodeError,ET.ParseError):raise ValueError('invalid CatalogQuery XML fixture') from None


def _signature(raw):
    root,scopes=_xml(raw)
    def qname(value,node):
        pieces=value.split(':');_require(len(pieces) in (1,2))
        prefix,local=('',pieces[0]) if len(pieces)==1 else pieces
        _require(local and prefix in scopes[id(node)])
        return '{'+scopes[id(node)][prefix]+'}'+local
    def visit(node):
        _require(not (node.tail or '').strip())
        text=node.text or ''
        if len(node):_require(not text.strip());text=''
        elif not text.strip():text=''
        if node.tag=='{'+V8+'}Type' and text:text=qname(text,node)
        attrs=tuple(sorted((key,qname(value,node) if key=='{'+XSI+'}type' else value) for key,value in node.attrib.items()))
        children=tuple(visit(child) for child in node)
        # These are sets in the official metadata/rights model, not default removal.
        if node.tag in ('{'+MD+'}ChildObjects','{'+RIGHTS+'}Rights','{'+RIGHTS+'}object'):
            children=tuple(sorted(children))
        return node.tag,attrs,text,children
    return visit(root)


def _files(files):
    _require(type(files) is dict and 1<=len(files)<=256 and all(type(p) is str for p in files))
    total=0;folded=set()
    for path,raw in files.items():
        _require(0<len(path)<=256 and not path.startswith('/') and '\\' not in path and ':' not in path
                 and all(ord(c)>=32 for c in path) and all(p not in ('','.','..') for p in path.split('/')))
        _require(path.casefold() not in folded);folded.add(path.casefold())
        _require(type(raw) is bytes and len(raw)<=MAX_FILE);total+=len(raw);_require(total<=MAX_TOTAL)
        if path.endswith('.xml'):_signature(raw)
        elif path.endswith('.bsl'):
            try:raw.decode('utf-8-sig')
            except UnicodeError:raise ValueError('invalid CatalogQuery module') from None
        else:_require(False)
    return files


def _one(node,tag):
    values=[v for v in node if v.tag==tag];_require(len(values)==1);return values[0]


def _uuid(value):
    _require(type(value) is str)
    try:result=UUID(value)
    except ValueError:raise ValueError('invalid metadata UUID') from None
    _require(result.int and str(result)==value);return result


def load_saved():
    root=Path(__file__).parent;assets={}
    for path,digest in ASSET_HASHES.items():
        p=root/path
        _require(not p.is_symlink() and p.is_file() and p.stat().st_size<=MAX_FILE)
        raw=p.read_bytes();_require(hashlib.sha256(raw).hexdigest()==digest);assets[path]=raw
    def pairs(items):
        result={}
        for key,value in items:_require(key not in result);result[key]=value
        return result
    data=json.loads(assets['generated/setup.json'].decode('utf-8'),object_pairs_hook=pairs)
    _require(type(data) is dict and set(data)=={'name','metadata_uuid','generated_ids','field_ids','record_ids'}
             and all(type(data[k]) is list for k in ('generated_ids','field_ids','record_ids')))
    setup=packet.Setup(data['name'],data['metadata_uuid'],tuple(data['generated_ids']),
                       tuple(data['field_ids']),tuple(data['record_ids'])).validate()
    _require(packet.render_xml(setup)==assets['generated/Catalog.xml'])
    _require(packet.render_program(setup).encode('utf-8')==assets['generated/observe.bsl'])
    return setup,assets


def _baseline(files,setup):
    _files(files);_require('Configuration.xml' in files and all(p in files for p in ROLE_FILES))
    md='{'+MD+'}';rn='{'+RIGHTS+'}'
    root,_=_xml(files['Configuration.xml']);_require(root.tag==md+'MetaDataObject' and root.attrib=={'version':'2.20'} and len(root)==1)
    config=root[0];_require(config.tag==md+'Configuration' and set(config.attrib)=={'uuid'});config_id=_uuid(config.get('uuid'))
    props=_one(config,md+'Properties');name=_one(props,md+'Name').text
    _require(type(name) is str and name.isidentifier())
    mode=_one(props,md+'DefaultRunMode');_require(not mode.attrib and not len(mode) and mode.text=='ManagedApplication')
    defaults=[n for n in props if n.tag==md+'DefaultRoles']
    _require(len(defaults)<=1 and all(not n.attrib and not len(n) and not (n.text or '').strip() for n in defaults))
    children=_one(config,md+'ChildObjects');_require(not children.attrib)
    _require(all(n.tag in (md+'Language',md+'Role') and not n.attrib and not len(n) for n in children))
    roles=[n for n in children if n.tag==md+'Role'];_require(len(roles)==1 and roles[0].text==ROLE_NAME)
    _require(not any(p.startswith('Catalogs/') for p in files))
    _require({p for p in files if p.startswith('Roles/')}==set(ROLE_FILES))
    role_root,_=_xml(files[ROLE_FILES[0]]);_require(role_root.tag==md+'MetaDataObject' and role_root.attrib=={'version':'2.20'} and len(role_root)==1)
    role=role_root[0];_require(role.tag==md+'Role' and set(role.attrib)=={'uuid'});role_id=_uuid(role.get('uuid'));_require(role_id!=config_id)
    _require(len(role)==1);rp=_one(role,md+'Properties')
    _require([n.tag for n in rp]==[md+k for k in ('Name','Synonym','Comment')])
    _require(rp[0].text==ROLE_NAME and all(not n.attrib and not len(n) for n in rp) and all(not(n.text or '').strip() for n in rp[1:]))
    rights,_=_xml(files[ROLE_FILES[1]])
    _require(rights.tag==rn+'Rights' and rights.attrib=={'version':'2.20','{'+XSI+'}type':'Rights'})
    _require(dict(_signature(files[ROLE_FILES[1]])[1])['{'+XSI+'}type']==rn+'Rights')
    flags=('setForNewObjects','setForAttributesByDefault','independentRightsOfChildObjects')
    _require(len(rights)==4)
    for flag in flags:
        n=_one(rights,rn+flag);_require(not n.attrib and not len(n) and n.text=='false')
    obj=_one(rights,rn+'object');_require(not obj.attrib and len(obj)==len(ROLE_RIGHTS)+1)
    target=_one(obj,rn+'name');_require(not target.attrib and not len(target) and target.text=='Configuration.'+name)
    grants=[]
    for right in obj:
        if right is target:continue
        _require(right.tag==rn+'right' and not right.attrib and [n.tag for n in right]==[rn+'name',rn+'value'])
        _require(all(not n.attrib and not len(n) for n in right) and right[1].text=='true');grants.append(right[0].text)
    _require(len(grants)==len(ROLE_RIGHTS) and set(grants)==ROLE_RIGHTS)
    used=set()
    for path,raw in files.items():
        if path.endswith('.xml'):
            tree,_=_xml(raw)
            for node in tree.iter():
                if 'uuid' in node.attrib:used.add(_uuid(node.attrib['uuid']))
                if node.tag in ('{http://v8.1c.ru/8.3/xcf/readable}TypeId','{http://v8.1c.ru/8.3/xcf/readable}ValueId'):used.add(_uuid(node.text))
    _require(not used.intersection(UUID(v) for v in (setup.metadata_uuid,*setup.generated_ids,*setup.field_ids,*setup.record_ids)))


def _append(raw,path,make):
    # Expat supplies byte offsets; preserve every original byte outside insertion.
    parser=expat.ParserCreate(namespace_separator='}');stack=[];found=[]
    def start(name,attrs):
        stack.append(name)
        if tuple(stack)==path:found.append([parser.CurrentByteIndex,None])
    def end(name):
        if tuple(stack)==path:found[-1][1]=parser.CurrentByteIndex
        stack.pop()
    parser.StartElementHandler=start;parser.EndElementHandler=end;parser.Parse(raw,True)
    _require(len(found)==1);start,end=found[0]
    match=re.match(rb'<([A-Za-z_][A-Za-z_0-9.:-]*)',raw[start:]);_require(match is not None)
    name=match.group(1).decode('ascii');prefix=name.rsplit(':',1)[0]+':' if ':' in name else ''
    index=start+len(match.group(0));quote=None
    while index<len(raw):
        b=raw[index]
        if quote is not None:
            if b==quote:quote=None
        elif b in (34,39):quote=b
        elif b==62:break
        index+=1
    _require(index<len(raw));addition=make(prefix).encode('utf-8')
    if raw[start:index].rstrip().endswith(b'/'):
        slash=raw.rfind(b'/',start,index)
        return raw[:slash]+b'>'+addition+('</'+name+'>').encode()+raw[index+1:]
    return raw[:end]+addition+raw[end:]


def prepare(files):
    setup,assets=load_saved();_baseline(files,setup);expected=dict(files)
    expected['Configuration.xml']=_append(files['Configuration.xml'],(MD+'}MetaDataObject',MD+'}Configuration',MD+'}ChildObjects'),lambda p:'<'+p+'Catalog>'+setup.name+'</'+p+'Catalog>')
    def grants(p):
        return '<'+p+'object><'+p+'name>Catalog.'+setup.name+'</'+p+'name>'+''.join('<'+p+'right><'+p+'name>'+r+'</'+p+'name><'+p+'value>true</'+p+'value></'+p+'right>' for r in OWNED_RIGHTS)+'</'+p+'object>'
    expected[ROLE_FILES[1]]=_append(files[ROLE_FILES[1]],(RIGHTS+'}Rights',),grants)
    expected['Catalogs/'+setup.name+'.xml']=assets['generated/Catalog.xml'];_files(expected)
    return setup,expected


def verify_redump(expected,actual):
    _files(expected);_files(actual);_require(set(expected)==set(actual))
    for path in expected:
        if path=='ConfigDumpInfo.xml':continue # Designer's export bookkeeping only.
        if path.endswith('.xml'):_require(_signature(expected[path])==_signature(actual[path]))
        elif path.endswith('.bsl'):
            _require(expected[path].decode('utf-8-sig').replace('\r\n','\n')==actual[path].decode('utf-8-sig').replace('\r\n','\n'))
        else:_require(expected[path]==actual[path])
    return True
