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

from .catalog_backend import CatalogSchema, FieldSchema, TabularSectionSchema
from .document_backend import DocumentSchema

MD = 'http://v8.1c.ru/8.3/MDClasses'
V8 = 'http://v8.1c.ru/8.1/data/core'
XS = 'http://www.w3.org/2001/XMLSchema'
CFG = 'http://v8.1c.ru/8.1/data/enterprise/current-config'
DUMP_INFO = 'http://v8.1c.ru/8.3/xcf/dumpinfo'
_XML_WHITESPACE = ' \t\r\n'
MAX_FILES = 2048
MAX_FILE_BYTES = 1024 * 1024
MAX_TOTAL_BYTES = 16 * 1024 * 1024
_RESERVED = frozenset(('code','код','description','наименование','ref','ссылка',
    'deletionmark','пометкаудаления','write','записать','isnew','этоновый',
    'metadata','метаданные','getobject','получитьобъект','setnewobjectref','установитьссылкунового'))
_CONFIGURATION_MODULES = ('ManagedApplicationModule', 'OrdinaryApplicationModule',
                          'ExternalConnectionModule', 'SessionModule')
_CATALOG_MODULES = ('ObjectModule', 'ManagerModule')
_MODULE_PATH_DIAGNOSTIC_LIMIT = 32
_MODULE_PATH_DIAGNOSTIC_JSON_LIMIT = 8192


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
    documents: tuple[DocumentSchema, ...] = ()


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
    return default if node is None else (node.text or '').strip(_XML_WHITESPACE)


def _int(props,name,minimum,maximum):
    value=_text(props,name)
    if type(value) is not str or len(value)>4 or not re.fullmatch(r'0|[1-9][0-9]*',value):_fail('invalid '+name)
    value=int(value)
    if not minimum<=value<=maximum:_fail('unsupported '+name)
    return value


def _qname(node,ns):
    text=(node.text or '').strip(_XML_WHITESPACE);parts=text.split(':')
    if len(parts)!=2 or not parts[0] or not parts[1] or parts[0] not in ns[id(node)]:_fail('unbound type QName')
    return ns[id(node)][parts[0]],parts[1]


def _type(props,ns,targets):
    t=props.get('{'+MD+'}Type')
    if t is None:_fail('missing field type')
    if t.attrib or (t.text or '').strip(_XML_WHITESPACE) or any((n.tail or '').strip(_XML_WHITESPACE) for n in t):_fail('unsupported type envelope')
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
        if nodes[0].attrib or (nodes[0].text or '').strip(_XML_WHITESPACE) or any((v.tail or '').strip(_XML_WHITESPACE) for v in nodes[0]):_fail('unsupported qualifier envelope')
        d=_children(nodes[0])
        if any(len(v) or v.attrib for v in d.values()):_fail('structured qualifier')
        return {k.removeprefix('{'+V8+'}'):(v.text or '').strip(_XML_WHITESPACE) for k,v in d.items()}
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
# Historical whole-object witness for catalog_query_behavior/generated/Catalog.xml.
# Its strict Designer redump was verified in run 41511900693; that run is not
# evidence of complete runtime parity. Defaults and qualifiers remain exact.
_SCALAR_PROFILE_SHA256 = '96cf0df15e450ae7ed0cc4e03aa2d76269ce56764a1d4d5c5cd89599da0a0572'
# Full normalized Attribute subtrees from that same unchanged owned fixture.
# Composition is a local bounded admission rule, not a new native observation.
_SCALAR_ATTRIBUTE_PROFILES = {
    ('number', (12, 2, 'Any'), None): 'd55966272aef1e46a455ee6a87ecce689e8448fb0b786bbcac404811ad9a609e',
    ('boolean', (), None): '0802cfae8fb0650b3def7d58ac06f0992d501936707383fe9609218a2edae03b',
    ('datetime', ('DateTime',), None): '08e273466c565e58f11547dfc59b50810e6a40da4cc60558f381d536e924b4a6',
}


def _profile_sha256(value):
    return sha256(json.dumps(value, ensure_ascii=True, separators=(',', ':')).encode('ascii')).hexdigest()


def _valid_uuid(text):
    if type(text) is not str:
        raise ValueError('UUID')
    value = UUID(text)
    if not value.int or str(value) != text.lower():
        raise ValueError('UUID')
    return value


def _catalog_profile_fingerprint(catalog, namespaces, *, scalar_attributes=False, envelope_only=False):
    """Normalize a complete object; optionally compose closed Attribute profiles.

    The envelope projection excludes only fully visited, verified direct fields.
    The original tree, source bytes, field order and namespace scopes stay intact.
    """
    if envelope_only and not scalar_attributes:
        raise ValueError('profile mode')
    if catalog.tag != '{'+MD+'}Catalog' or set(catalog.attrib) != {'uuid'}:
        raise ValueError('catalog shape')
    catalog_uuid = _valid_uuid(catalog.get('uuid'))
    props = catalog.find('{'+MD+'}Properties')
    if props is None:
        raise ValueError('properties')
    names = props.findall('{'+MD+'}Name')
    if len(names) != 1 or len(names[0]) or names[0].attrib:
        raise ValueError('name')
    name = (names[0].text or '').strip(_XML_WHITESPACE)
    if not name or (names[0].text or '') != name or not name.isidentifier() or len(name) > 128:
        raise ValueError('name')
    identities = {catalog_uuid}
    generated_seen = set()
    attributes = set()
    attribute_names = set()
    attribute_ids = set()
    type_nodes = set()
    attribute_profiles = {}
    child_objects = None
    if scalar_attributes:
        # A catalog is admitted only when its entire envelope and every field
        # match. Never infer safe behavior from a partial property whitelist.
        children = catalog.findall('{'+MD+'}ChildObjects')
        if len(children) != 1 or len(children[0]) > 64:
            raise ValueError('scalar inventory')
        child_objects = children[0]
        field_names = set(_RESERVED)
        for field in child_objects:
            if field.tag != '{'+MD+'}Attribute' or set(field.attrib) != {'uuid'}:
                raise ValueError('scalar attribute')
            field_id = _valid_uuid(field.get('uuid'))
            if field_id in identities:
                raise ValueError('duplicate identity')
            identities.add(field_id)
            attribute_ids.add(field_id)
            fp = _props(field)
            field_name = fp.get('{'+MD+'}Name')
            if field_name is None or field_name.attrib or len(field_name):
                raise ValueError('field name')
            value = _name(field_name.text)
            if value.casefold() in field_names:
                raise ValueError('field name collision')
            field_names.add(value.casefold())
            expected = _SCALAR_ATTRIBUTE_PROFILES.get(_type(fp, namespaces, {}))
            if expected is None:
                raise ValueError('scalar type')
            attribute_profiles[field] = expected
            attributes.add(field)
            attribute_names.add(field_name)
            type_nodes.add(fp['{'+MD+'}Type'].find('{'+V8+'}Type'))

    def node_value(node, parent=None):
        if (node.tail or '').strip(_XML_WHITESPACE):
            raise ValueError('mixed XML')
        text = node.text or ''
        if len(node) or node is child_objects:
            # ChildObjects remains a structural container even with zero fields.
            # Only XML formatting whitespace is inert, never Unicode spaces.
            if text.strip(_XML_WHITESPACE):
                raise ValueError('mixed XML')
            text = ''
        attrs = dict(node.attrib)
        if node is catalog:
            attrs['uuid'] = '@CATALOG_UUID@'
        elif node in attributes:
            attrs['uuid'] = '@ATTRIBUTE_UUID@'
        elif node in attribute_names:
            text = '@ATTRIBUTE_NAME@'
        elif node in type_nodes:
            namespace, local_name = _qname(node, namespaces)
            text = '{'+namespace+'}'+local_name
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
                if len(parts) != 2 or not parts[0] or not parts[1] or parts[0] not in scope:
                    raise ValueError('QName')
                attrs[key] = '{'+scope[parts[0]]+'}'+parts[1]
        result = [node.tag, sorted(attrs.items()), text, [node_value(child, node) for child in node]]
        if node in attributes and _profile_sha256(result) != attribute_profiles[node]:
            raise ValueError('scalar attribute profile')
        if envelope_only and node is child_objects:
            # Only after recursive validation: retain this container's tag,
            # attributes, text/tail checks and position in the catalog envelope.
            result[3] = []
        return result

    result = node_value(catalog)
    if generated_seen != set(_GENERATED) or len(identities) != 11 + len(attribute_ids):
        raise ValueError('generated identities')
    digest = _profile_sha256(result)
    return digest, frozenset(identities - {catalog_uuid} - attribute_ids)


def _catalog_generated_identities(catalog, namespaces):
    """Return ten generated identities only for a whole admitted catalog."""
    try:
        digest, identities = _catalog_profile_fingerprint(
            catalog, namespaces, scalar_attributes=True, envelope_only=True)
        if digest == _PROFILE_SHA256:
            return identities
    except (ValueError, TypeError, KeyError, RecursionError):
        pass
    return None


def _activation_properties(obj, allowed, issues, owner):
    # Unknown configuration behavior is archived, never silently activated.
    if set(obj.attrib) != {'uuid'} or (obj.text or '').strip(_XML_WHITESPACE):
        issues.append('unsupported object envelope:'+owner)
    for node in obj:
        if (node.tail or '').strip(_XML_WHITESPACE):
            issues.append('unsupported metadata mixed content:'+owner)
        if node.tag not in {'{'+MD+'}Properties','{'+MD+'}ChildObjects','{'+MD+'}InternalInfo'}:
            issues.append('unsupported object component:'+owner+':'+node.tag)
        elif node.tag == '{'+MD+'}InternalInfo' and (node.attrib or len(node) or (node.text or '').strip(_XML_WHITESPACE)):
            issues.append('unsupported internal metadata:'+owner)
        elif node.tag in ('{'+MD+'}Properties','{'+MD+'}ChildObjects') and (node.attrib or (node.text or '').strip(_XML_WHITESPACE)):
            issues.append('unsupported metadata container:'+owner)
        if obj.tag == '{'+MD+'}Attribute' and node.tag == '{'+MD+'}ChildObjects' and len(node):
            issues.append('unsupported attribute child objects:'+owner)
    allowed_tags = {'{'+MD+'}'+name for name in allowed}
    for tag,node in _props(obj).items():
        if (node.tail or '').strip(_XML_WHITESPACE):
            issues.append('unsupported property mixed content:'+owner+':'+tag)
        if tag not in allowed_tags:
            issues.append('unsupported metadata property:'+owner+':'+tag)
        elif node.attrib:
            issues.append('unsupported property attributes:'+owner+':'+tag)
        elif tag in ('{'+MD+'}Synonym','{'+MD+'}Comment') and (len(node) or (node.text or '').strip(_XML_WHITESPACE)):
            issues.append('unsupported presentation metadata:'+owner+':'+tag)
    for container in obj.findall('{'+MD+'}ChildObjects'):
        for node in container:
            permitted = {'uuid'} if node.tag == '{'+MD+'}Attribute' or (obj.tag in ('{'+MD+'}Catalog', '{'+MD+'}Document') and node.tag == '{'+MD+'}TabularSection') else set()
            if (set(node.attrib) != permitted or (node.tail or '').strip(_XML_WHITESPACE)
                    or (len(node) and (node.text or '').strip(_XML_WHITESPACE))
                    or (node.tag in ('{'+MD+'}Catalog', '{'+MD+'}Document') and obj.tag == '{'+MD+'}Configuration' and len(node))):
                issues.append('unsupported child metadata envelope:'+owner)


def _envelope_issues(root, obj, issues, owner):
    if root.attrib != {'version':'2.20'} or (root.text or '').strip(_XML_WHITESPACE) or (obj.tail or '').strip(_XML_WHITESPACE):
        issues.append('unsupported metadata document envelope:'+owner)


def _dump_info_matches(raw, config_uuid, name, catalogs, metadata_versions):
    """Admit only the closed catalog inventory described in the profile doc.

    Version tokens are opaque bookkeeping, not content hashes or semantic
    evidence. A matching inventory never clears other activation issues.
    """
    root, _ = _parse(raw)
    # The admitted PR201 inventory profile covers only catalog attributes.
    # Do not accept an owner-only inventory while silently ignoring sections.
    # A nested section inventory needs its own source-reviewed profile.
    if any(catalog.tabular_sections for catalog in catalogs): return False
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
    if any((node.text or '').strip(_XML_WHITESPACE) or (node.tail or '').strip(_XML_WHITESPACE)
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


def _accept_source_files(files):
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
    return tuple(accepted)



_DOCUMENT_RESERVED = _RESERVED | frozenset((
    'number', 'номер', 'date', 'дата', 'posted', 'проведен', 'проведён',
    'setdeletionmark', 'установитьпометкуудаления', 'copy', 'скопировать',
    'fill', 'заполнить', 'checkfill', 'проверитьзаполнение'))


def _document_schema(raw, name, targets, used, issues):
    """Authored XML-shaped document profile, not full Designer export parity.

    Only unposted documents, whole-series unique strings and explicit or local
    decimal numbering are admitted. Unknown behavior stays an activation issue.
    """
    obj, ns, root = _object(raw, 'Document', include_root=True)
    props = _props(obj)
    identity = _uuid(obj.get('uuid'))
    if identity in used: _fail('duplicate metadata UUID')
    used.add(identity)
    if _text(props, 'Name') != name: _fail('document filename/name mismatch')
    _envelope_issues(root, obj, issues, name)
    _activation_properties(obj, {'Name', 'Synonym', 'Comment', 'NumberType',
        'NumberLength', 'NumberPeriodicity', 'CheckUnique', 'Autonumbering',
        'Posting'}, issues, name)
    if any(_text(props, key) != value for key, value in (
            ('NumberType', 'String'), ('NumberPeriodicity', 'Nonperiodical'),
            ('CheckUnique', 'true'), ('Posting', 'Deny'))):
        _fail('unsupported document semantics')
    auto = _text(props, 'Autonumbering')
    if auto not in ('false', 'true'): _fail('unsupported document numbering')
    length = _int(props, 'NumberLength', 1, 9)
    names = set(_DOCUMENT_RESERVED)
    fields = []; sections = []

    def field_schema(field, field_names, owner):
        if field.tag != '{'+MD+'}Attribute': _fail('document child object unsupported')
        _activation_properties(field, {'Name', 'Synonym', 'Comment', 'Type'}, issues, owner)
        fp = _props(field); fn = _name(_text(fp, 'Name')); fid = _uuid(field.get('uuid'))
        if fn.casefold() in field_names or fid in used: _fail('field identity/name collision')
        field_names.add(fn.casefold()); used.add(fid)
        kind, qualifiers, target = _type(fp, ns, targets)
        return FieldSchema(fid, fn, kind, qualifiers, target)

    children = obj.find('{'+MD+'}ChildObjects')
    for item in (() if children is None else children):
        if item.tag == '{'+MD+'}Attribute':
            fields.append(field_schema(item, names, name))
        elif item.tag == '{'+MD+'}TabularSection':
            _activation_properties(item, {'Name', 'Synonym', 'Comment'}, issues, name)
            sp = _props(item); sn = _name(_text(sp, 'Name')); sid = _uuid(item.get('uuid'))
            if sn.casefold() in names or sid in used: _fail('section identity/name collision')
            names.add(sn.casefold()); used.add(sid)
            rows = item.find('{'+MD+'}ChildObjects')
            row_names = set(_DOCUMENT_RESERVED) | {'linenumber', 'номерстроки'}
            row_fields = tuple(field_schema(f, row_names, name+'.'+sn)
                               for f in (() if rows is None else rows))
            if len(row_fields) > 64: _fail('section field count')
            sections.append(TabularSectionSchema(sid, sn, row_fields))
            if len(sections) > 16: _fail('tabular section count')
        else:
            _fail('document child object unsupported')
    if len(fields) > 64: _fail('field count')
    return DocumentSchema(identity, name, length, tuple(fields), tuple(sections),
                          'decimal_v1' if auto == 'true' else 'explicit')


def import_configuration(files, *, numbering_policy='explicit'):
    """Import closed XML; decimal_v1 is an explicit local numbering choice.

    It does not assert native numbering parity or waive other activation gates.
    """
    if type(numbering_policy) is not str or numbering_policy not in ('explicit', 'decimal_v1'):
        _fail('unsupported numbering policy')
    accepted = _accept_source_files(files)
    if 'Configuration.xml' not in files:_fail('missing Configuration.xml')
    config,_,config_root=_object(files['Configuration.xml'],'Configuration',include_root=True);config_uuid=_uuid(config.get('uuid'));props=_props(config)
    name=_name(_text(props,'Name'));issues=[];objects={};used={config_uuid}
    _envelope_issues(config_root,config,issues,name)
    _activation_properties(config,{'Name','Synonym','Comment'},issues,name)
    children=config.find('{'+MD+'}ChildObjects')
    if children is None:_fail('missing configuration ChildObjects')
    catalog_names=[];document_names=[]
    for node in children:
        if node.tag=='{'+MD+'}Document':
            document_names.append(_name((node.text or '').strip(_XML_WHITESPACE)));continue
        if node.tag!='{'+MD+'}Catalog':
            issues.append('unsupported metadata family:'+node.tag.rsplit('}',1)[-1]);continue
        catalog_names.append(_name((node.text or '').strip(_XML_WHITESPACE)))
    if not 1<=len(catalog_names)+len(document_names)<=512:_fail('metadata inventory')
    if len({x.casefold() for x in catalog_names})!=len(catalog_names):_fail('catalog inventory')
    if len({x.casefold() for x in document_names})!=len(document_names):_fail('document inventory')
    for cname in catalog_names:
        path='Catalogs/'+cname+'.xml'
        if path not in files:_fail('missing catalog XML')
        obj,ns,root=_object(files[path],'Catalog',include_root=True);p=_props(obj);identity=_uuid(obj.get('uuid'))
        if identity in used:_fail('duplicate metadata UUID')
        used.add(identity)
        if _text(p,'Name')!=cname:_fail('catalog filename/name mismatch')
        objects[cname.casefold()]=(identity,obj,p,ns,root)
    targets={key:v[0] for key,v in objects.items()};catalogs=[];section_count=0
    for cname in catalog_names:
        identity,obj,p,ns,root=objects[cname.casefold()]
        # Admit only the whole closed envelope with fully verified fields; any
        # mismatch retains the fail-closed path, never a partial whitelist.
        generated = (_catalog_generated_identities(obj, ns)
                     if root.attrib == {'version':'2.20'} and not (root.text or '').strip(_XML_WHITESPACE)
                     and not (obj.tail or '').strip(_XML_WHITESPACE) else None)
        if generated is None:
            _envelope_issues(root,obj,issues,cname)
            _activation_properties(obj,{'Name','Synonym','Comment','Hierarchical','CodeType','CodeLength','DescriptionLength','Autonumbering','CheckUnique','CodeSeries','Owners'},issues,cname)
        else:
            if generated & used:_fail('duplicate generated metadata UUID')
            used.update(generated)
        auto_numbering = _text(p, 'Autonumbering', 'false')
        if auto_numbering not in ('false', 'true') or (auto_numbering == 'true' and numbering_policy != 'decimal_v1'):
            _fail('unsupported catalog semantics')
        if (_text(p,'Hierarchical','false')!='false' or _text(p,'CodeType','String')!='String'
                or _text(p,'CheckUnique','true')!='true'
                or _text(p,'CodeSeries','WholeCatalog')!='WholeCatalog'):_fail('unsupported catalog semantics')
        owners=p.get('{'+MD+'}Owners')
        if owners is not None and (len(owners) or (owners.text or '').strip(_XML_WHITESPACE)):_fail('catalog owners unsupported')
        for node in obj.iter():
            local=node.tag.rsplit('}',1)[-1];text=(node.text or '').strip(_XML_WHITESPACE)
            if local=='FillChecking' and text not in ('','DontCheck'):issues.append('required field validation unsupported:'+cname)
            if local in ('FillFromFillingValue','DataHistory','RegisterRecords') and text not in ('','false','DontUse'):issues.append('automatic metadata behavior unsupported:'+cname)
        fields=[];sections=[];names=set(_RESERVED);child=obj.find('{'+MD+'}ChildObjects')
        def field_schema(field, field_names, owner, row=False):
            if field.tag!='{'+MD+'}Attribute':_fail('child object unsupported')
            if row:
                section_components(field)
                nested=field.find('{'+MD+'}ChildObjects')
                if nested is not None and len(nested):_fail('attribute child object unsupported')
            # Rich Designer defaults require the envelope and every full field.
            # Every unmatched field retains the restrictive activation path.
            if generated is None or row:
                _activation_properties(field,{'Name','Synonym','Comment','Type'},issues,owner)
            fp=_props(field);fn=_name(_text(fp,'Name'));fid=_uuid(field.get('uuid'))
            if fn.casefold() in field_names or fid in used:_fail('field identity/name collision')
            field_names.add(fn.casefold());used.add(fid);kind,q,target=_type(fp,ns,targets)
            return FieldSchema(fid,fn,kind,q,target)
        def section_components(section):
            # Inline executable payloads are outside this bounded metadata format,
            # even when hidden inside otherwise descriptive properties.
            for node in section.iter():
                local=node.tag.rsplit('}',1)[-1].casefold()
                if local.endswith('module') or local in ('code','script','procedure','function'):
                    _fail('embedded executable component unsupported')
        for item in () if child is None else child:
            if item.tag=='{'+MD+'}Attribute':
                fields.append(field_schema(item,names,cname))
            elif item.tag=='{'+MD+'}TabularSection':
                section_components(item)
                _activation_properties(item,{'Name','Synonym','Comment'},issues,cname)
                sp=_props(item);sn=_name(_text(sp,'Name'));sid=_uuid(item.get('uuid'))
                if sn.casefold() in names or sid in used:_fail('section identity/name collision')
                names.add(sn.casefold());used.add(sid)
                row_names=set(_RESERVED)|{'linenumber','номерстроки'}
                rows=item.find('{'+MD+'}ChildObjects')
                row_fields=tuple(field_schema(f,row_names,cname+'.'+sn,True)
                                 for f in (() if rows is None else rows))
                if len(row_fields)>64:_fail('section field count')
                sections.append(TabularSectionSchema(sid,sn,row_fields));section_count+=1
                if len(sections)>16 or section_count>512:_fail('tabular section count')
            else:_fail('catalog child object unsupported')
        if len(fields)>64:_fail('field count')
        numbering = 'decimal_v1' if auto_numbering == 'true' else 'explicit'
        code_length = _int(p, 'CodeLength', 1, 9 if numbering == 'decimal_v1' else 64)
        catalogs.append(CatalogSchema(identity,cname,code_length,_int(p,'DescriptionLength',0,1024),tuple(fields),tuple(sections),numbering))
    documents=[]
    for dname in document_names:
        path='Documents/'+dname+'.xml'
        if path not in files:
            # Historical unsupported-family archives may declare a document
            # without supplying its source. Preserve those archives as inactive.
            issues.append('missing document XML:'+dname);continue
        document=_document_schema(files[path],dname,targets,used,issues)
        section_count+=len(document.tabular_sections)
        if section_count>512:_fail('tabular section count')
        documents.append(document)
    modules=[];expected={'Configuration.xml',*(f'Catalogs/{n}.xml' for n in catalog_names),
                        *(f'Documents/{n}.xml' for n in document_names)}
    # Closed canonical hierarchical paths, not a generic Ext/*.bsl allowance.
    # A source archive may contain unknown modules, but it must not activate or
    # invent a Configuration owner for a file whose metadata owner is unknown.
    module_paths = {f'Ext/{kind}.bsl': (config_uuid, kind)
                    for kind in _CONFIGURATION_MODULES}
    for cname in catalog_names:
        for kind in _CATALOG_MODULES:
            module_paths[f'Catalogs/{cname}/Ext/{kind}.bsl'] = (targets[cname.casefold()], kind)
    for document in documents:
        for kind in _CATALOG_MODULES:
            module_paths[f'Documents/{document.name}/Ext/{kind}.bsl'] = (document.identity, kind)
    unknown_module_count = 0
    unknown_module_issues = []
    unknown_module_json_size = 2  # The enclosing JSON array brackets.
    for entry in accepted:
        if entry.kind=='module':
            binding = module_paths.get(entry.path)
            if binding is None:
                unknown_module_count += 1
                if unknown_module_issues is not None:
                    detail = 'unsupported module path:'+entry.path
                    # Match SQLite's compact ensure_ascii=True representation,
                    # including surrogate-pair escapes for astral characters.
                    size = len(json.dumps(detail, ensure_ascii=True, separators=(',', ':')))
                    size += bool(unknown_module_issues)  # Separator before this item.
                    if (unknown_module_count > _MODULE_PATH_DIAGNOSTIC_LIMIT or
                            unknown_module_json_size + size > _MODULE_PATH_DIAGNOSTIC_JSON_LIMIT):
                        unknown_module_issues = None
                    else:
                        unknown_module_issues.append(detail)
                        unknown_module_json_size += size
            else:
                owner, kind = binding
                modules.append(ConfigurationModule(owner,kind,entry.path))
            code='\n'.join(line.split('//',1)[0] for line in entry.content.decode('utf-8-sig').splitlines()).strip()
            if code:issues.append('module execution unsupported:'+entry.path)
        elif entry.path == 'ConfigDumpInfo.xml':
            versions = (config_root.get('version'), *(obj[4].get('version') for obj in objects.values()))
            if document_names or not _dump_info_matches(entry.content, config_uuid, name, catalogs, versions):
                issues.append('unsupported configuration file:'+entry.path)
        elif entry.path not in expected:
            _parse(entry.content);issues.append('unsupported configuration file:'+entry.path)
    if unknown_module_issues is None:
        issues.append('unsupported module paths:'+str(unknown_module_count)+
                      ' (individual paths retained in configuration files)')
    else:
        issues.extend(unknown_module_issues)
    return ConfigurationImport(config_uuid,name,tuple(catalogs),tuple(accepted),tuple(modules),tuple(sorted(set(issues))),tuple(documents))


# This marker selects a durable inert-only storage profile. It is never an
# activation issue that an ordinary importer may silently clear.
INERT_SOURCE_ISSUE = 'inert configuration source archive:v1'
_LOGFORM = 'http://v8.1c.ru/8.3/xcf/logform'


@dataclass(frozen=True, slots=True)
class _InertForm:
    identity: UUID
    name: str
    path: str
    definition_path: str
    module_path: str


@dataclass(frozen=True, slots=True)
class _InertCatalog:
    identity: UUID
    name: str
    path: str
    default_object_form: str
    forms: tuple[_InertForm, ...]


def _inert_configuration(files):
    """Inventory identity/ownership only, never executable catalog semantics."""
    accepted = _accept_source_files(files)
    if 'Configuration.xml' not in files: _fail('missing Configuration.xml')
    config, _ = _object(files['Configuration.xml'], 'Configuration')
    config_id = _uuid(config.get('uuid'))
    def scalar(props, name, default=None):
        node = props.get('{'+MD+'}'+name)
        if node is not None and (node.attrib or (node.tail or '').strip(_XML_WHITESPACE)):
            _fail('inert scalar envelope')
        return _text(props, name, default)

    name = _name(scalar(_props(config), 'Name'))
    used = {config_id}

    def container(obj):
        nodes = obj.findall('{'+MD+'}ChildObjects')
        if len(nodes) != 1 or nodes[0].attrib or (nodes[0].text or '').strip(_XML_WHITESPACE):
            _fail('inert ChildObjects envelope')
        return nodes[0]

    def declaration(node):
        if node.attrib or len(node) or (node.tail or '').strip(_XML_WHITESPACE):
            _fail('inert declaration envelope')
        return _name((node.text or '').strip(_XML_WHITESPACE))

    def identity(obj):
        value = _uuid(obj.get('uuid'))
        if value in used: _fail('duplicate metadata UUID')
        used.add(value)
        return value

    cnames = [declaration(n) for n in container(config) if n.tag == '{'+MD+'}Catalog']
    if not 1 <= len(cnames) <= 512 or len({n.casefold() for n in cnames}) != len(cnames):
        _fail('catalog inventory')
    catalogs = []
    total_forms = 0
    for cname in cnames:
        path = 'Catalogs/'+cname+'.xml'
        if path not in files: _fail('missing catalog XML')
        obj, _ = _object(files[path], 'Catalog')
        cid = identity(obj)
        props = _props(obj)
        if scalar(props, 'Name') != cname: _fail('catalog filename/name mismatch')
        children = container(obj)
        fnames = [declaration(n) for n in children if n.tag == '{'+MD+'}Form']
        total_forms += len(fnames)
        if len(fnames) > 32 or total_forms > 512 or len({n.casefold() for n in fnames}) != len(fnames):
            _fail('form inventory')
        # Attribute/section UUIDs cannot impersonate an indexed form or catalog.
        for node in obj.iter():
            if node is not obj and 'uuid' in node.attrib: identity(node)
        forms = []
        for fname in fnames:
            prefix = 'Catalogs/'+cname+'/Forms/'+fname
            fpath, dpath, mpath = prefix+'.xml', prefix+'/Ext/Form.xml', prefix+'/Ext/Form/Module.bsl'
            if fpath not in files or dpath not in files: _fail('missing form source')
            form, _ = _object(files[fpath], 'Form')
            fid = identity(form)
            fp = _props(form)
            if scalar(fp, 'Name') != fname: _fail('form filename/name mismatch')
            if scalar(fp, 'FormType') != 'Managed': _fail('unsupported inert form type')
            definition, _ = _parse(files[dpath])
            if definition.tag != '{'+_LOGFORM+'}Form': _fail('form definition envelope')
            forms.append(_InertForm(fid, fname, fpath, dpath, mpath))
        default = scalar(props, 'DefaultObjectForm', '')
        allowed = {'Catalog.'+cname+'.Form.'+f.name for f in forms}
        if default and default not in allowed: _fail('unbound default object form')
        catalogs.append(_InertCatalog(cid, cname, path, default, tuple(forms)))
    # Identity stubs have no usable fields, code or description. Inert storage
    # is permanently denied all catalog read/write/activation entry points.
    stubs = tuple(CatalogSchema(c.identity, c.name, 0, 0) for c in catalogs)
    imported = ConfigurationImport(config_id, name, stubs, accepted, (), (INERT_SOURCE_ISSUE,))
    return imported, tuple(catalogs)


def import_inert_configuration(files):
    """Preserve bounded Designer XML/BSL without admitting runtime semantics.

    The result can only create an inert owned archive with activate=False.
    This does not admit ordinary configuration import or execute any module.
    """
    return _inert_configuration(files)[0]


# A complete byte envelope, not a semantic projection or general demo support.
# These are the original editable demo sources introduced by 6111e02. Even inert
# sources and presentation-only settings must stay exact. Changing this manifest
# requires a fresh review of the entire profile, not an automatic fixture rehash.
DEMO_KINDS_PROFILE = 'demo_kinds_v1'
DEMO_KINDS_SOURCE_ISSUE = 'bounded configuration source profile:demo_kinds_v1'
DEMO_PRODUCTS_PROFILE = 'demo_products_v1'
DEMO_PRODUCTS_SOURCE_ISSUE = 'bounded configuration source profile:demo_products_v1'
DEMO_DIRECTORIES_PROFILE = 'demo_directories_v1'
DEMO_DIRECTORIES_SOURCE_ISSUE = 'bounded configuration source profile:demo_directories_v1'
_DEMO_KINDS_SOURCE_SHA256 = {
    'Catalogs/ВидыНоменклатуры.xml':
        '723c973982629b92c183d68b24aef8fde1771b34e649e536749354d7a14cc2d0',
    'Catalogs/ВидыНоменклатуры/Forms/ФормаЭлемента.xml':
        'ccf4960ad91cc507a0e8165c973f79d88c9fe5e1773d1bf8fd1bb90584275a28',
    'Catalogs/ВидыНоменклатуры/Forms/ФормаЭлемента/Ext/Form.xml':
        '3d5d1cdf429fbc5ece392c4bc4df6621c8753f152c8260a1aa5a83557a2a088d',
    'Catalogs/ВидыНоменклатуры/Forms/ФормаЭлемента/Ext/Form/Module.bsl':
        '1362d0c9ab909625f98648a719e87422dd7665634e2cc2e55ce01517a198f53f',
    'Catalogs/Номенклатура.xml':
        '6418b0b403932a38b24c75bb5db5496837cef396897225fa0bc5b80f905fa156',
    'Catalogs/Номенклатура/Ext/ObjectModule.bsl':
        'b329bc9a92db51032415bc62f779672acff65beb081237105adedab0f16edec9',
    'Catalogs/Номенклатура/Forms/ФормаСписка.xml':
        'ce2e8373aab443a70990c7c1a7f1166e2efc45f025952959ae48de4553f474c2',
    'Catalogs/Номенклатура/Forms/ФормаСписка/Ext/Form.xml':
        '192dcb7c76a5805afdff477c9bc27f1f67149f1aa53be5a0894dcae931c4afc6',
    'Catalogs/Номенклатура/Forms/ФормаСписка/Ext/Form/Module.bsl':
        'cedc20b94809fc639f72ee65d180eb5e6dadb647e02a2ed02d85af7dd1533127',
    'Catalogs/Номенклатура/Forms/ФормаЭлемента.xml':
        '0d55e449ebff7d194f09af8c92dff5fd53c05db17927a0c478dfae9ad9a7dc6e',
    'Catalogs/Номенклатура/Forms/ФормаЭлемента/Ext/Form.xml':
        'ba70bc4129509c979033632d305d4866e0e311f5e25322369bdf3998b055add6',
    'Catalogs/Номенклатура/Forms/ФормаЭлемента/Ext/Form/Module.bsl':
        '86bccc60f288b6d8bec57dd01701b3535a73c297b1a42a97d2f5528f066426e3',
    'Catalogs/Склады.xml':
        '3f123ebb7eed85b1b845ae8867749e91cde2d6154cd6e8b5da16a74c9658bb3a',
    'Configuration.xml':
        '348fb96905c8e87e4803ee40fb6de3bca75902c939386346c6872223bec0c719',
    'Ext/ClientApplicationInterface.xml':
        '407d37fdc9c46dc9ef03573c8241f574c382e329cc9670bf5eba0d529860b16a',
    'Ext/CommandInterface.xml':
        'b36fdd6e977f07daa40e5b4efd4bf8ad1c536f08402642df470587600848315a',
    'Ext/HomePageWorkArea.xml':
        '16188438d96e87c4103ba71fe773543c1b71f3ca98e93476f3174d816672010e',
    'Languages/Русский.xml':
        'e0438b24e18c15da067173886270b2a4806aff1ea97031b2211c3f586181cf3c',
    'Subsystems/НормативнаяИнформация.xml':
        'e824868068ac9018757c8fea8adbe4eee1c597a82e0fd6d8215c8d2f94858412',
}


def _demo_kinds_configuration(files):
    """Admit one local catalog from an exact full archive; inventory the rest.

    The source hashes close every XML/BSL envelope before any activation grant.
    The form analyzer is only a further structural check, never a replacement
    for complete admission. Other catalogs/modules remain archived and inert.
    """
    archive, catalog_sources = _inert_configuration(files)
    if {f.path: sha256(f.content).hexdigest() for f in archive.files} != _DEMO_KINDS_SOURCE_SHA256:
        _fail('demo_kinds_v1 source mismatch')
    # Read only the immutable accepted snapshot, never the caller's mapping again.
    source = {f.path: f.content for f in archive.files}
    catalog = next(c for c in catalog_sources if c.name == 'ВидыНоменклатуры')
    form, = catalog.forms
    obj, _ = _object(source[catalog.path], 'Catalog')
    props = _props(obj)
    code_length = _int(props, 'CodeLength', 1, 9)
    description_length = _int(props, 'DescriptionLength', 0, 1024)
    if (code_length != 9 or description_length != 100 or
            _text(props, 'Autonumbering') != 'true' or
            _text(props, 'Hierarchical') != 'false' or
            _text(props, 'CodeType') != 'String' or
            _text(props, 'CodeSeries') != 'WholeCatalog' or
            _text(props, 'CheckUnique') != 'true'):
        _fail('demo_kinds_v1 catalog semantics')
    from .form_module_analysis import FormModuleBinding, analyze_form_module
    raw = tuple(source[path] for path in (
        form.module_path, catalog.path, form.path, form.definition_path))
    # This pure import has no database yet. The sentinel is solely an analyzer
    # input and is never returned or persisted as a storage/source capability.
    binding = FormModuleBinding(UUID(int=1), archive.config_uuid, 1,
        catalog.identity, catalog.name, form.identity, form.name,
        *(sha256(content).hexdigest() for content in raw))
    analyze_form_module(raw[0], binding, catalog_xml=raw[1], form_xml=raw[2],
        definition_xml=raw[3], catalog_path=catalog.path, form_path=form.path,
        definition_path=form.definition_path, module_path=form.module_path)
    schema = CatalogSchema(catalog.identity, catalog.name, code_length,
                           description_length, numbering='decimal_v1')
    imported = ConfigurationImport(archive.config_uuid, archive.name, (schema,),
        archive.files, (), (DEMO_KINDS_SOURCE_ISSUE,))
    return imported, catalog_sources


def import_demo_kinds_configuration(files):
    """Admit only the exact original demo's kinds catalog for storage v6.

    The complete 19-file archive is retained byte-for-byte. Only the original
    ВидыНоменклатуры schema is eligible for the local decimal_v1 numbering policy;
    Номенклатура, Склады, and their source modules remain inert. This does not
    enable general configuration import, arbitrary forms, or native 1C parity.
    The marker requires the dedicated storage profile, not ordinary activation.
    """
    return _demo_kinds_configuration(files)[0]


def _demo_directories_configuration(files):
    """Add the original module-free warehouse catalog to the exact demo.

    The kinds admission freezes the complete source mapping first. No second
    caller mapping read, rewritten XML or unbound module activation is allowed.
    Warehouse presentation settings remain a bounded host-autoform projection,
    not a claim of native standard-form behavior.
    """
    kinds, catalogs = _demo_kinds_configuration(files)
    source = {f.path: f.content for f in kinds.files}
    warehouse = next(c for c in catalogs if c.name == 'Склады')
    obj, _ = _object(source[warehouse.path], 'Catalog')
    props = _props(obj)
    expected = {'Autonumbering': 'true', 'Hierarchical': 'false',
                'CodeType': 'String', 'CodeSeries': 'WholeCatalog',
                'CheckUnique': 'true', 'DefaultObjectForm': '',
                'DefaultListForm': '', 'DataHistory': 'DontUse'}
    child = obj.find('{' + MD + '}ChildObjects')
    owners = props.get('{' + MD + '}Owners')
    if (warehouse.forms or warehouse.default_object_form
            or child is None or len(child)
            or owners is None or len(owners) or (owners.text or '').strip()
            or any(_text(props, name) != value for name, value in expected.items())
            or _int(props, 'CodeLength', 1, 9) != 9
            or _int(props, 'DescriptionLength', 0, 1024) != 100
            or any(f.path.startswith('Catalogs/Склады/') for f in kinds.files)):
        _fail('demo_directories_v1 warehouse semantics')
    schema = CatalogSchema(warehouse.identity, warehouse.name, 9, 100,
                           numbering='decimal_v1')
    imported = ConfigurationImport(kinds.config_uuid, kinds.name,
        (*kinds.catalogs, schema), kinds.files, (), (DEMO_DIRECTORIES_SOURCE_ISSUE,))
    return imported, catalogs


def import_demo_directories_configuration(files):
    """Admit original kinds and warehouses, leaving products archived/inert.

    This fresh source profile reuses the v6 physical layout. Existing kinds-only
    databases and inert v5 archives are not migrated or activated in place.
    """
    return _demo_directories_configuration(files)[0]


def _demo_products_configuration(files):
    """Fresh exact-demo product admission; execution is a bounded host policy.

    The complete original archive, including the inactive list form, remains
    byte-bound. No generic module activation or native form parity is implied.
    """
    directories, catalogs = _demo_directories_configuration(files)
    source = {f.path: f.content for f in directories.files}
    product = next(c for c in catalogs if c.name == 'Номенклатура')
    obj, _ = _object(source[product.path], 'Catalog')
    props = _props(obj)
    if (_int(props, 'CodeLength', 1, 9) != 9
            or _int(props, 'DescriptionLength', 0, 1024) != 150
            or _text(props, 'Autonumbering') != 'true'
            or _text(props, 'Hierarchical') != 'false'):
        _fail('demo_products_v1 product semantics')
    children = obj.find('{' + MD + '}ChildObjects')
    attribute, = children.findall('{' + MD + '}Attribute')
    section, = children.findall('{' + MD + '}TabularSection')
    row_attribute, = section.find('{' + MD + '}ChildObjects').findall('{' + MD + '}Attribute')
    kind, warehouse = directories.catalogs
    # These identities/names/types come from the already closed full-byte
    # envelope, not a permissive import of arbitrary product metadata.
    schema = CatalogSchema(product.identity, product.name, 9, 150,
        (FieldSchema(_uuid(attribute.get('uuid')), 'ВидНоменклатуры',
                     'catalog_ref', (), kind.identity),),
        (TabularSectionSchema(_uuid(section.get('uuid')), 'Склады',
            (FieldSchema(_uuid(row_attribute.get('uuid')), 'Склад',
                         'catalog_ref', (), warehouse.identity),)),),
        numbering='decimal_v1')
    return ConfigurationImport(directories.config_uuid, directories.name,
        (*directories.catalogs, schema), directories.files, (),
        (DEMO_PRODUCTS_SOURCE_ISSUE,)), catalogs


def import_demo_products_configuration(files):
    """Admit three original catalogs in a fresh, exact-source host profile."""
    return _demo_products_configuration(files)[0]


def _demo_configuration(files, profile):
    # The version-6 source-bound layout also serves explicitly opted-in generic
    # forms. This dispatch does not extend any historical demo hash grant.
    from .configuration_catalog_profile import CATALOG_FORMS_PROFILE, catalog_forms_configuration
    if profile == CATALOG_FORMS_PROFILE:
        return catalog_forms_configuration(files)
    if profile == DEMO_PRODUCTS_PROFILE:
        return _demo_products_configuration(files)
    if profile == DEMO_KINDS_PROFILE:
        return _demo_kinds_configuration(files)
    if profile == DEMO_DIRECTORIES_PROFILE:
        return _demo_directories_configuration(files)
    _fail('unsupported demo source profile')


def import_catalog_forms_configuration(files):
    """Explicit scalar catalog object-form profile; ordinary import stays inert."""
    from .configuration_catalog_profile import catalog_forms_configuration
    return catalog_forms_configuration(files)[0]
