"""Bounded official Designer XML interchange; no native binary formats.

Accepted source bytes are retained independently of activation. Unsupported
modules/metadata semantics are explicit activation issues, never skipped hooks.
"""
from dataclasses import dataclass
from pathlib import PurePosixPath
from uuid import UUID
import io
import json
from hashlib import sha256
import re
import xml.etree.ElementTree as ET

from .catalog_backend import CatalogSchema, FieldSchema

MD = 'http://v8.1c.ru/8.3/MDClasses'
V8 = 'http://v8.1c.ru/8.1/data/core'
XS = 'http://www.w3.org/2001/XMLSchema'
CFG = 'http://v8.1c.ru/8.1/data/enterprise/current-config'
DUMP_INFO = 'http://v8.1c.ru/8.3/xcf/dumpinfo'
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
        # ElementTree normally discards processing instructions, including
        # prologue/epilogue instructions. No PI semantics are supported here.
        # XML declarations are parsed separately and are not PI events.
        for event,value in ET.iterparse(io.StringIO(text), events=('start','end','start-ns','pi')):
            if event=='pi': _fail('processing instructions forbidden')
            elif event=='start-ns': pending.append(value)
            elif event=='start':
                scope=dict(stack[-1]) if stack else {};scope.update(pending);pending.clear()
                stack.append(scope);namespaces[id(value)]=scope;count+=1
                if len(stack)>32 or count>20000:_fail('XML structure bound')
            else:
                root=value;stack.pop()
    except (UnicodeError,ET.ParseError): _fail('malformed UTF-8 XML')
    return root,namespaces


def _object(raw,kind, *, include_root=False):
    root,ns=_parse(raw)
    if root.tag!='{'+MD+'}MetaDataObject' or len(root)!=1 or root[0].tag!='{'+MD+'}'+kind:
        _fail('metadata object shape')
    obj=root[0];_uuid(obj.get('uuid'))
    return (obj,ns,root) if include_root else (obj,ns)


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
    if t.attrib or (t.text or '').strip() or any((n.tail or '').strip() for n in t):_fail('unsupported type envelope')
    types=[n for n in t if n.tag=='{'+V8+'}Type']
    if len(types)!=1 or types[0].attrib:_fail('composite or absent field type unsupported')
    namespace,name=_qname(types[0],ns)
    qualifier = {'string':'StringQualifiers','decimal':'NumberQualifiers','dateTime':'DateQualifiers'}.get(name) if namespace==XS else None
    allowed={'{'+V8+'}Type'}
    if qualifier:allowed.add('{'+V8+'}'+qualifier)
    if any(n.tag not in allowed for n in t) or len(types[0]):_fail('unsupported type components')
    def qualifiers(kind):
        nodes=[n for n in t if n.tag=='{'+V8+'}'+kind+'Qualifiers']
        if len(nodes)!=1:_fail('missing qualifiers')
        if nodes[0].attrib or (nodes[0].text or '').strip() or any((v.tail or '').strip() for v in nodes[0]):_fail('unsupported qualifier envelope')
        d=_children(nodes[0])
        if any(len(v) or v.attrib for v in d.values()):_fail('structured qualifier')
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



XR = 'http://v8.1c.ru/8.3/xcf/readable'
XSI = 'http://www.w3.org/2001/XMLSchema-instance'
_GENERATED = {'Object': 'CatalogObject', 'Ref': 'CatalogRef',
              'Selection': 'CatalogSelection', 'List': 'CatalogList',
              'Manager': 'CatalogManager'}
# Generated from scripts/catalog_object_behavior/generated/Catalog.xml after
# its owned Designer round-trip. See docs/official-catalog-xml-profile.md.
_PROFILE_SHA256 = '100592da54dc738bf82f1950f943a8408e848400082c7a38d7ab920274fed4bb'


def _valid_uuid(text):
    if type(text) is not str:
        raise ValueError('UUID')
    value = UUID(text)
    if not value.int or str(value) != text.lower():
        raise ValueError('UUID')
    return value


def _catalog_profile_fingerprint(catalog, namespaces):
    if catalog.tag != '{'+MD+'}Catalog' or set(catalog.attrib) != {'uuid'}:
        raise ValueError('catalog shape')
    catalog_uuid = _valid_uuid(catalog.get('uuid'))
    props = catalog.find('{'+MD+'}Properties')
    if props is None:
        raise ValueError('properties')
    names = props.findall('{'+MD+'}Name')
    if len(names) != 1 or len(names[0]) or names[0].attrib:
        raise ValueError('name')
    name = (names[0].text or '').strip()
    if not name or (names[0].text or '') != name or not name.isidentifier() or len(name) > 128:
        raise ValueError('name')
    identities = {catalog_uuid}
    generated_seen = set()

    def node_value(node, parent=None):
        if (node.tail or '').strip():
            raise ValueError('mixed XML')
        text = node.text or ''
        if len(node):
            if text.strip():
                raise ValueError('mixed XML')
            text = ''
        attrs = dict(node.attrib)
        if node is catalog:
            attrs['uuid'] = '@CATALOG_UUID@'
        elif node.tag == '{'+XR+'}GeneratedType':
            if set(attrs) != {'name', 'category'}:
                raise ValueError('type attributes')
            category = attrs['category']
            if (category not in _GENERATED or category in generated_seen or
                    attrs['name'] != _GENERATED[category] + '.' + name):
                raise ValueError('type identity')
            generated_seen.add(category)
            attrs['name'] = _GENERATED[category] + '.@NAME@'
        elif node.tag in ('{'+XR+'}TypeId', '{'+XR+'}ValueId'):
            if parent is None or parent.tag != '{'+XR+'}GeneratedType' or attrs or len(node):
                raise ValueError('type identity')
            value = _valid_uuid(text)
            if value in identities:
                raise ValueError('duplicate identity')
            identities.add(value)
            text = '@GENERATED_UUID@'
        elif node is names[0]:
            text = '@NAME@'
        elif parent is props and node.tag in ('{'+MD+'}CodeLength', '{'+MD+'}DescriptionLength'):
            if attrs or len(node) or len(text) > 4 or not text.isascii() or not text.isdecimal():
                raise ValueError('length')
            n = int(text)
            if str(n) != text or not (1 <= n <= 64 if node.tag.endswith('CodeLength') else 0 <= n <= 1024):
                raise ValueError('length')
            text = '@LENGTH@'
        for key, value in tuple(attrs.items()):
            if key == '{'+XSI+'}type':
                parts = value.split(':')
                scope = namespaces.get(id(node), {})
                if len(parts) != 2 or not parts[1] or parts[0] not in scope:
                    raise ValueError('QName')
                attrs[key] = '{'+scope[parts[0]]+'}'+parts[1]
        return [node.tag, sorted(attrs.items()), text, [node_value(child, node) for child in node]]

    result = node_value(catalog)
    if generated_seen != set(_GENERATED) or len(identities) != 11:
        raise ValueError('generated identities')
    digest = sha256(json.dumps(result, ensure_ascii=True, separators=(',', ':')).encode('ascii')).hexdigest()
    return digest, frozenset(identities - {catalog_uuid})


def _catalog_generated_identities(catalog, namespaces):
    """Return ten validated identities only for an exact admitted profile."""
    try:
        digest, identities = _catalog_profile_fingerprint(catalog, namespaces)
        return identities if digest == _PROFILE_SHA256 else None
    except (ValueError, TypeError, KeyError, RecursionError):
        return None


def _activation_properties(obj, allowed, issues, owner):
    # Unknown configuration behavior is archived, never silently activated.
    if set(obj.attrib) != {'uuid'} or (obj.text or '').strip():
        issues.append('unsupported object envelope:'+owner)
    for node in obj:
        if (node.tail or '').strip():
            issues.append('unsupported metadata mixed content:'+owner)
        if node.tag not in {'{'+MD+'}Properties','{'+MD+'}ChildObjects','{'+MD+'}InternalInfo'}:
            issues.append('unsupported object component:'+owner+':'+node.tag)
        elif node.tag == '{'+MD+'}InternalInfo' and (node.attrib or len(node) or (node.text or '').strip()):
            issues.append('unsupported internal metadata:'+owner)
        elif node.tag in ('{'+MD+'}Properties','{'+MD+'}ChildObjects') and (node.attrib or (node.text or '').strip()):
            issues.append('unsupported metadata container:'+owner)
        if obj.tag == '{'+MD+'}Attribute' and node.tag == '{'+MD+'}ChildObjects' and len(node):
            issues.append('unsupported attribute child objects:'+owner)
    allowed_tags = {'{'+MD+'}'+name for name in allowed}
    for tag,node in _props(obj).items():
        if (node.tail or '').strip():
            issues.append('unsupported property mixed content:'+owner+':'+tag)
        if tag not in allowed_tags:
            issues.append('unsupported metadata property:'+owner+':'+tag)
        elif node.attrib:
            issues.append('unsupported property attributes:'+owner+':'+tag)
        elif tag in ('{'+MD+'}Synonym','{'+MD+'}Comment') and (len(node) or (node.text or '').strip()):
            issues.append('unsupported presentation metadata:'+owner+':'+tag)
    for container in obj.findall('{'+MD+'}ChildObjects'):
        for node in container:
            permitted = {'uuid'} if node.tag == '{'+MD+'}Attribute' else set()
            if (set(node.attrib) != permitted or (node.tail or '').strip()
                    or (len(node) and (node.text or '').strip())
                    or (node.tag == '{'+MD+'}Catalog' and len(node))):
                issues.append('unsupported child metadata envelope:'+owner)


def _envelope_issues(root, obj, issues, owner):
    if root.attrib != {'version':'2.20'} or (root.text or '').strip() or (obj.tail or '').strip():
        issues.append('unsupported metadata document envelope:'+owner)


def _dump_info_matches(raw, config_uuid, name, catalogs, metadata_versions):
    """Admit only the closed catalog inventory described in the profile doc.

    Version tokens are opaque bookkeeping, not content hashes or semantic
    evidence. A matching inventory never clears other activation issues.
    """
    root, _ = _parse(raw)
    # _parse decodes bytes itself. Do not admit a contradictory declaration
    # merely because ElementTree accepts an already decoded Unicode stream.
    text = raw.decode('utf-8-sig')
    if text.startswith('\ufeff'): return False  # Reject a second BOM before a declaration.
    declaration = re.match(r'<\?xml\s+(.*?)\?>', text, re.DOTALL)
    if declaration:
        attrs = {key: value for key, _, value in re.findall(
            r'''([A-Za-z]+)\s*=\s*(['"])(.*?)\2''', declaration[1])}
        if attrs.get('version') != '1.0' or attrs.get('encoding', 'utf-8').lower() != 'utf-8':
            return False
    if (root.tag != '{'+DUMP_INFO+'}ConfigDumpInfo'
            or root.attrib != {'format':'Hierarchical', 'version':'2.20'}
            or set(metadata_versions) != {'2.20'} or len(root) != 1):
        return False
    versions = root[0]
    if versions.tag != '{'+DUMP_INFO+'}ConfigVersions' or versions.attrib:
        return False
    # Only XML formatting whitespace is ignorable, not arbitrary Unicode text.
    if any((node.text or '').strip(' \t\r\n') or (node.tail or '').strip(' \t\r\n')
           for node in root.iter()):
        return False
    expected = {'Configuration.'+name: (config_uuid, {})}
    for catalog in catalogs:
        full_name = 'Catalog.'+catalog.name
        expected[full_name] = (catalog.identity, {
            full_name+'.Attribute.'+field.name: field.identity for field in catalog.fields})
    for node in versions:
        if node.tag != '{'+DUMP_INFO+'}Metadata' or set(node.attrib) != {'name','id','configVersion'}:
            return False
        item = expected.pop(node.get('name'), None)
        if item is None or not re.fullmatch(r'[0-9a-fA-F]{40}', node.get('configVersion')):
            return False
        identity, fields = item
        try:
            if _valid_uuid(node.get('id')) != identity:
                return False
            for child in node:
                if (child.tag != '{'+DUMP_INFO+'}Metadata'
                        or set(child.attrib) != {'name','id'} or len(child)):
                    return False
                field_id = fields.pop(child.get('name'), None)
                if field_id is None or _valid_uuid(child.get('id')) != field_id:
                    return False
        except ValueError:
            return False
        if fields:
            return False
    return not expected


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
    config,_,config_root=_object(files['Configuration.xml'],'Configuration',include_root=True);config_uuid=_uuid(config.get('uuid'));props=_props(config)
    name=_name(_text(props,'Name'));issues=[];objects={};used={config_uuid}
    _envelope_issues(config_root,config,issues,name)
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
        obj,ns,root=_object(files[path],'Catalog',include_root=True);p=_props(obj);identity=_uuid(obj.get('uuid'))
        if identity in used:_fail('duplicate metadata UUID')
        used.add(identity)
        if _text(p,'Name')!=cname:_fail('catalog filename/name mismatch')
        objects[cname.casefold()]=(identity,obj,p,ns,root)
    targets={key:v[0] for key,v in objects.items()};catalogs=[]
    for cname in catalog_names:
        identity,obj,p,ns,root=objects[cname.casefold()]
        # Admit only the entire, exact owned native profile; a mismatch follows
        # the existing fail-closed path, never a partial property whitelist.
        generated = (_catalog_generated_identities(obj, ns)
                     if root.attrib == {'version':'2.20'} and not (root.text or '').strip()
                     and not (obj.tail or '').strip() else None)
        if generated is None:
            _envelope_issues(root,obj,issues,cname)
            _activation_properties(obj,{'Name','Synonym','Comment','Hierarchical','CodeType','CodeLength','DescriptionLength','Autonumbering','CheckUnique','CodeSeries','Owners'},issues,cname)
        else:
            if generated & used:_fail('duplicate generated metadata UUID')
            used.update(generated)
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
        elif entry.path == 'ConfigDumpInfo.xml':
            versions = (config_root.get('version'), *(obj[4].get('version') for obj in objects.values()))
            if not _dump_info_matches(entry.content, config_uuid, name, catalogs, versions):
                issues.append('unsupported configuration file:'+entry.path)
        elif entry.path not in expected:
            _parse(entry.content);issues.append('unsupported configuration file:'+entry.path)
    return ConfigurationImport(config_uuid,name,tuple(catalogs),tuple(accepted),tuple(modules),tuple(sorted(set(issues))))
