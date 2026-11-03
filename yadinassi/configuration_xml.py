"""Bounded official Designer XML interchange; no native binary formats.

Accepted source bytes are retained independently of activation. Unsupported
modules/metadata semantics are explicit activation issues, never skipped hooks.
"""
from dataclasses import dataclass
from pathlib import PurePosixPath
from uuid import UUID
import io
import re
import xml.etree.ElementTree as ET

from .catalog_backend import CatalogSchema, FieldSchema

MD = 'http://v8.1c.ru/8.3/MDClasses'
V8 = 'http://v8.1c.ru/8.1/data/core'
XS = 'http://www.w3.org/2001/XMLSchema'
CFG = 'http://v8.1c.ru/8.1/data/enterprise/current-config'
MAX_FILES = 2048
MAX_FILE_BYTES = 1024 * 1024
MAX_TOTAL_BYTES = 16 * 1024 * 1024
_RESERVED = frozenset(('code','код','description','наименование','ref','ссылка',
    'deletionmark','пометкаудаления','write','записать','isnew','этоновый',
    'metadata','метаданные','getobject','получитьобъект','setnewobjectref','установитьссылкунового'))


@dataclass(frozen=True, slots=True)
class ConfigurationFile:
    path: str
    content: bytes
    kind: str


@dataclass(frozen=True, slots=True)
class ConfigurationModule:
    owner: UUID
    kind: str
    path: str


@dataclass(frozen=True, slots=True)
class ConfigurationImport:
    config_uuid: UUID
    name: str
    catalogs: tuple[CatalogSchema, ...]
    files: tuple[ConfigurationFile, ...]
    modules: tuple[ConfigurationModule, ...]
    activation_issues: tuple[str, ...]


def _fail(reason):
    raise ValueError('configuration XML: ' + reason)


def _name(value):
    if type(value) is not str or not 1 <= len(value) <= 128 or not value.isidentifier():
        _fail('invalid name')
    return value


def _uuid(value):
    if type(value) is not str:
        _fail('missing UUID')
    try: result = UUID(value)
    except ValueError: _fail('invalid UUID')
    if not result.int or str(result) != value.lower(): _fail('invalid UUID')
    return result


def _parse(raw):
    if b'<!DOCTYPE' in raw.upper() or b'<!ENTITY' in raw.upper():
        _fail('DTD/entities forbidden')
    try:
        text = raw.decode('utf-8-sig')
        pending=[]; stack=[]; namespaces={}; count=0
        for event,value in ET.iterparse(io.StringIO(text), events=('start','end','start-ns')):
            if event=='start-ns': pending.append(value)
            elif event=='start':
                scope=dict(stack[-1]) if stack else {};scope.update(pending);pending.clear()
                stack.append(scope);namespaces[id(value)]=scope;count+=1
                if len(stack)>32 or count>20000:_fail('XML structure bound')
            else:
                root=value;stack.pop()
    except (UnicodeError,ET.ParseError): _fail('malformed UTF-8 XML')
    return root,namespaces


def _object(raw,kind):
    root,ns=_parse(raw)
    if root.tag!='{'+MD+'}MetaDataObject' or len(root)!=1 or root[0].tag!='{'+MD+'}'+kind:
        _fail('metadata object shape')
    obj=root[0];_uuid(obj.get('uuid'))
    return obj,ns


def _children(node):
    result={}
    for child in node:
        if child.tag in result:_fail('duplicate property')
        result[child.tag]=child
    return result


def _props(obj):
    children=_children(obj);p=children.get('{'+MD+'}Properties')
    if p is None:_fail('missing Properties')
    return _children(p)


def _text(props,name,default=None):
    node=props.get('{'+MD+'}'+name)
    if node is not None and len(node):_fail('structured scalar '+name)
    return default if node is None else (node.text or '').strip()


def _int(props,name,minimum,maximum):
    value=_text(props,name)
    if type(value) is not str or len(value)>4 or not re.fullmatch(r'0|[1-9][0-9]*',value):_fail('invalid '+name)
    value=int(value)
    if not minimum<=value<=maximum:_fail('unsupported '+name)
    return value


def _qname(node,ns):
    text=(node.text or '').strip();parts=text.split(':')
    if len(parts)!=2 or parts[0] not in ns[id(node)]:_fail('unbound type QName')
    return ns[id(node)][parts[0]],parts[1]


def _type(props,ns,targets):
    t=props.get('{'+MD+'}Type')
    if t is None:_fail('missing field type')
    types=[n for n in t if n.tag=='{'+V8+'}Type']
    if len(types)!=1:_fail('composite or absent field type unsupported')
    namespace,name=_qname(types[0],ns)
    qualifier = {'string':'StringQualifiers','decimal':'NumberQualifiers','dateTime':'DateQualifiers'}.get(name) if namespace==XS else None
    allowed={'{'+V8+'}Type'}
    if qualifier:allowed.add('{'+V8+'}'+qualifier)
    if any(n.tag not in allowed for n in t) or len(types[0]):_fail('unsupported type components')
    def qualifiers(kind):
        nodes=[n for n in t if n.tag=='{'+V8+'}'+kind+'Qualifiers']
        if len(nodes)!=1:_fail('missing qualifiers')
        d=_children(nodes[0])
        if any(len(v) for v in d.values()):_fail('structured qualifier')
        return {k.removeprefix('{'+V8+'}'):(v.text or '').strip() for k,v in d.items()}
    if namespace==XS and name=='string':
        q=qualifiers('String')
        if set(q)!={'Length','AllowedLength'} or q['AllowedLength']!='Variable':_fail('string qualifiers')
        if len(q['Length'])>4 or not re.fullmatch(r'[1-9][0-9]*',q['Length']) or not 1<=int(q['Length'])<=4096:_fail('string length')
        return 'string',(int(q['Length']),),None
    if namespace==XS and name=='decimal':
        q=qualifiers('Number')
        if set(q)!={'Digits','FractionDigits','AllowedSign'} or q['AllowedSign'] not in ('Any','Nonnegative'):_fail('number qualifiers')
        if any(len(q[k])>2 or not re.fullmatch(r'0|[1-9][0-9]*',q[k]) for k in ('Digits','FractionDigits')):_fail('number qualifiers')
        d,f=int(q['Digits']),int(q['FractionDigits'])
        if not 1<=d<=38 or not 0<=f<=d:_fail('number precision')
        return 'number',(d,f,q['AllowedSign']),None
    if namespace==XS and name=='boolean':return 'boolean',(),None
    if namespace==XS and name=='dateTime':
        q=qualifiers('Date')
        if q!={'DateFractions':'DateTime'}:_fail('date fractions')
        return 'datetime',('DateTime',),None
    if namespace==CFG and name.startswith('CatalogRef.'):
        target=targets.get(name[len('CatalogRef.'):].casefold())
        if target is None:_fail('unknown reference target')
        return 'catalog_ref',(),target
    _fail('unsupported field type')



def _activation_properties(obj, allowed, issues, owner):
    # !todo Execute configuration/module behavior only after an explicit engine
    # supports it. Unknown properties are archived but never silently activated.
    for node in obj:
        if node.tag not in {'{'+MD+'}Properties','{'+MD+'}ChildObjects','{'+MD+'}InternalInfo'}:
            issues.append('unsupported object component:'+owner+':'+node.tag)
    for tag,node in _props(obj).items():
        if tag not in {'{'+MD+'}'+name for name in allowed}:
            issues.append('unsupported metadata property:'+owner+':'+tag)


def import_configuration(files):
    if type(files) is not dict or not 1<=len(files)<=MAX_FILES:_fail('file count')
    if any(type(path) is not str for path in files):_fail('invalid path type')
    accepted=[];total=0;normalized=set()
    for path,raw in sorted(files.items()):
        if (type(path) is not str or len(path)>256 or '\\' in path or ':' in path
                or path.startswith('/') or any(ord(c)<32 for c in path) or any(x in ('','.', '..') for x in path.split('/'))):_fail('unsafe path')
        p=PurePosixPath(path)
        if p.suffix.lower() not in ('.xml','.bsl'):_fail('only XML/BSL interchange supported')
        if path.casefold() in normalized:_fail('case-colliding paths')
        normalized.add(path.casefold())
        if type(raw) is not bytes or len(raw)>MAX_FILE_BYTES:_fail('file byte bound')
        total+=len(raw)
        if total>MAX_TOTAL_BYTES:_fail('total byte bound')
        try:raw.decode('utf-8-sig')
        except UnicodeError:_fail('non UTF-8 source')
        if p.suffix.lower()=='.xml':_parse(raw)
        accepted.append(ConfigurationFile(path,raw,'module' if p.suffix.lower()=='.bsl' else 'xml'))
    if 'Configuration.xml' not in files:_fail('missing Configuration.xml')
    config,_=_object(files['Configuration.xml'],'Configuration');config_uuid=_uuid(config.get('uuid'));props=_props(config)
    name=_name(_text(props,'Name'));issues=[];objects={};used={config_uuid}
    _activation_properties(config,{'Name','Synonym','Comment'},issues,name)
    children=config.find('{'+MD+'}ChildObjects')
    if children is None:_fail('missing configuration ChildObjects')
    catalog_names=[]
    for node in children:
        if node.tag!='{'+MD+'}Catalog':
            issues.append('unsupported metadata family:'+node.tag.rsplit('}',1)[-1]);continue
        catalog_names.append(_name((node.text or '').strip()))
    if not 1<=len(catalog_names)<=512 or len({x.casefold() for x in catalog_names})!=len(catalog_names):_fail('catalog inventory')
    for cname in catalog_names:
        path='Catalogs/'+cname+'.xml'
        if path not in files:_fail('missing catalog XML')
        obj,ns=_object(files[path],'Catalog');p=_props(obj);identity=_uuid(obj.get('uuid'))
        if identity in used:_fail('duplicate metadata UUID')
        used.add(identity)
        if _text(p,'Name')!=cname:_fail('catalog filename/name mismatch')
        objects[cname.casefold()]=(identity,obj,p,ns)
    targets={key:v[0] for key,v in objects.items()};catalogs=[]
    for cname in catalog_names:
        identity,obj,p,ns=objects[cname.casefold()]
        _activation_properties(obj,{'Name','Synonym','Comment','Hierarchical','CodeType','CodeLength','DescriptionLength','Autonumbering','CheckUnique','CodeSeries','Owners'},issues,cname)
        if (_text(p,'Hierarchical','false')!='false' or _text(p,'CodeType','String')!='String'
                or _text(p,'Autonumbering','false')!='false' or _text(p,'CheckUnique','true')!='true'
                or _text(p,'CodeSeries','WholeCatalog')!='WholeCatalog'):_fail('unsupported catalog semantics')
        owners=p.get('{'+MD+'}Owners')
        if owners is not None and (len(owners) or (owners.text or '').strip()):_fail('catalog owners unsupported')
        for node in obj.iter():
            local=node.tag.rsplit('}',1)[-1];text=(node.text or '').strip()
            if local=='FillChecking' and text not in ('','DontCheck'):issues.append('required field validation unsupported:'+cname)
            if local in ('FillFromFillingValue','DataHistory','RegisterRecords') and text not in ('','false','DontUse'):issues.append('automatic metadata behavior unsupported:'+cname)
        fields=[];names=set(_RESERVED);child=obj.find('{'+MD+'}ChildObjects')
        for field in () if child is None else child:
            if field.tag!='{'+MD+'}Attribute':_fail('catalog child object unsupported')
            _activation_properties(field,{'Name','Synonym','Comment','Type'},issues,cname)
            fp=_props(field);fn=_name(_text(fp,'Name'));fid=_uuid(field.get('uuid'))
            if fn.casefold() in names or fid in used:_fail('field identity/name collision')
            names.add(fn.casefold());used.add(fid);kind,q,target=_type(fp,ns,targets)
            fields.append(FieldSchema(fid,fn,kind,q,target))
        if len(fields)>64:_fail('field count')
        catalogs.append(CatalogSchema(identity,cname,_int(p,'CodeLength',1,64),_int(p,'DescriptionLength',0,1024),tuple(fields)))
    modules=[];expected={'Configuration.xml',*(f'Catalogs/{n}.xml' for n in catalog_names)}
    for entry in accepted:
        if entry.kind=='module':
            parts=entry.path.split('/');owner=config_uuid;kind=parts[-1][:-4]
            if len(parts)==4 and parts[0]=='Catalogs' and parts[2]=='Ext' and parts[1].casefold() in targets:owner=targets[parts[1].casefold()]
            elif not (len(parts)==2 and parts[0]=='Ext'):issues.append('unsupported module path:'+entry.path)
            modules.append(ConfigurationModule(owner,kind,entry.path))
            code='\n'.join(line.split('//',1)[0] for line in entry.content.decode('utf-8-sig').splitlines()).strip()
            if code:issues.append('module execution unsupported:'+entry.path)
        elif entry.path not in expected and entry.path!='ConfigDumpInfo.xml':
            _parse(entry.content);issues.append('unsupported configuration file:'+entry.path)
    return ConfigurationImport(config_uuid,name,tuple(catalogs),tuple(accepted),tuple(modules),tuple(sorted(set(issues))))
