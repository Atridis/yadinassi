"""Fresh, explicit source grant for a closed Balance accumulation profile.

This is an authored source-admission contract, not native Designer acceptance
or evidence of movement, grouping, sign, endpoint or virtual-table semantics.
The original XML/BSL bytes, including projected passive metadata and generated
identities, are retained and reimported on every canonical admission. No
legacy importer or migration is widened by this source grant. Runtime admission
additionally compiles the bound synchronous document handlers.
"""
from dataclasses import dataclass, fields, is_dataclass
from hashlib import sha256
from uuid import UUID

from . import configuration_xml as xml
from .configuration_diagnostics import location, metadata_name
from .accumulation_movements import (AccumulationRegisterSchema,
                                    validate_schema)
from .catalog_backend import BackendError, FieldSchema, TabularSectionSchema
from .document_backend import DocumentSchema

PROFILE = 'accumulation-balance-scalar-v1'
FORMAT_VERSION = 14
SOURCE_PROJECTION = 'authored-accumulation-source-shape-v1'

_MD = '{' + xml.MD + '}'
_XR = '{' + xml.XR + '}'
_XSI = '{' + xml.XSI + '}'
_SCALARS = frozenset(('string', 'number', 'boolean', 'datetime'))
_GENERATED = {
    'Document': ('Object', 'Ref', 'Selection', 'List', 'Manager'),
    'AccumulationRegister': ('Record', 'Manager', 'Selection', 'List',
                             'RecordSet', 'RecordKey'),
}
_PASSIVE = {'UseStandardCommands': 'false', 'StandardAttributes': '',
            'DataLockControlMode': 'Managed'}
_DOCUMENT_PASSIVE = {**_PASSIVE, 'NumberAllowedLength': 'Variable',
                     'SequenceFilling': 'AutoFill'}
_DOCUMENT_CONTROLS = {
    'NumberType': 'String', 'NumberPeriodicity': 'Nonperiodical',
    'CheckUnique': 'true', 'Posting': 'Allow', 'RealTimePosting': 'Deny',
    'RegisterRecordsDeletion': 'AutoDeleteOnUnpost',
    'RegisterRecordsWritingOnPost': 'WriteSelected',
    'PostInPrivilegedMode': 'false', 'UnpostInPrivilegedMode': 'false',
}
_PRESENTATION = {'Synonym', 'Comment'}


@dataclass(frozen=True, slots=True)
class AccumulationConfiguration:
    identity: UUID
    name: str
    files: tuple
    documents: tuple
    registers: tuple
    handlers: tuple
    profile: str
    source_digest: str


def _fail(reason):
    raise ValueError('accumulation source: ' + reason)


def _space(value):
    return not (value or '').strip(xml._XML_WHITESPACE)


def _container(node):
    if node.attrib or not _space(node.text) or not _space(node.tail):
        _fail('unsupported container')
    if any(not _space(child.tail) for child in node):
        _fail('mixed content')


def _identity(text, used):
    identity = xml._uuid(text)
    if text != str(identity) or identity in used:
        _fail('noncanonical or duplicate UUID')
    used.add(identity)
    return identity


def _shape(obj, allowed, required):
    if (set(obj.attrib) != {'uuid'} or not _space(obj.text)
            or not _space(obj.tail)):
        _fail('unsupported object envelope')
    children = xml._children(obj)
    tags = {_MD + name for name in allowed}
    if not {_MD + name for name in required} <= set(children) <= tags:
        _fail('unsupported object components')
    for node in children.values():
        _container(node)
    return children


def _properties(obj, allowed, *, structured=()):
    props = xml._props(obj)
    if _MD + 'Name' not in props:
        _fail('missing Name')
    for tag, node in props.items():
        name = tag.removeprefix(_MD)
        if (tag != _MD + name or name not in allowed or node.attrib
                or not _space(node.tail)):
            _fail('unsupported property')
        if name not in structured and len(node):
            _fail('structured scalar property')
        if name in _PRESENTATION and not _space(node.text):
            _fail('unsupported presentation metadata')
    return props


def _exact(props, expected, *, optional=False):
    for name, value in expected.items():
        node = props.get(_MD + name)
        if node is None and optional:
            continue
        # Passive defaults and executable controls are exact source grants,
        # not inferred defaults or permissive Boolean/number conversions.
        if node is None or len(node) or (node.text or '') != value:
            _fail('unsupported control ' + name)


def _generated(obj, kind, name, used):
    internal = obj.find(_MD + 'InternalInfo')
    if internal is None:
        return
    categories = _GENERATED.get(kind, ())
    seen = set()
    for node in internal:
        category = node.get('category')
        if (node.tag != _XR + 'GeneratedType' or category not in categories
                or node.attrib != {'name': kind + category + '.' + name,
                                   'category': category}
                or category in seen or not _space(node.text)
                or not _space(node.tail)
                or [child.tag for child in node] != [_XR + 'TypeId', _XR + 'ValueId']):
            _fail('unsupported generated identity')
        seen.add(category)
        for child in node:
            if child.attrib or len(child) or not _space(child.tail):
                _fail('unsupported generated UUID')
            _identity(child.text, used)
    # An absent/empty InternalInfo is an authored shape. A nonempty native-
    # shaped inventory must be complete; no generated category is ignored.
    if seen and seen != set(categories):
        _fail('incomplete generated identities')


def _object(raw, kind, used, expected_name=None):
    obj, namespaces, root = xml._object(raw, kind, include_root=True)
    if (root.attrib != {'version': '2.20'} or not _space(root.text)
            or not _space(root.tail)):
        _fail('unsupported metadata document envelope')
    _shape(obj, {'Properties', 'ChildObjects', 'InternalInfo'},
           {'Properties', 'ChildObjects'})
    identity = _identity(obj.get('uuid'), used)
    name = xml._name(xml._text(xml._props(obj), 'Name'))
    if expected_name is not None and name != expected_name:
        _fail('filename/name mismatch')
    _generated(obj, kind, name, used)
    return obj, namespaces, identity, name


def _field(node, namespaces, used, names, *, dimension=False):
    with location(field=metadata_name(node)):
        _shape(node, {'Properties'}, {'Properties'})
        props = _properties(node, {'Name', 'Type'} | _PRESENTATION
                            | ({'UseInTotals'} if dimension else set()),
                            structured={'Type'})
        identity = _identity(node.get('uuid'), used)
        name = xml._name(xml._text(props, 'Name'))
        if name.casefold() in names:
            _fail('field name collision')
        names.add(name.casefold())
        if dimension:
            _exact(props, {'UseInTotals': 'true'})
        kind, qualifiers, target = xml._type(props, namespaces, {})
        if kind not in _SCALARS or target is not None:
            _fail('scalar fields only')
        return FieldSchema(identity, name, kind, qualifiers, target)


def _recorder_targets(props, namespaces, declarations):
    node = props.get(_MD + 'RegisterRecords')
    if node is None:
        _fail('recorder declarations missing')
    _container(node)
    targets = []
    for item in node:
        qname = item.get(_XSI + 'type', '').split(':')
        if (item.tag != _XR + 'Item' or len(item)
                or set(item.attrib) != {_XSI + 'type'} or len(qname) != 2
                or namespaces[id(item)].get(qname[0]) != xml.XR
                or qname[1] != 'MDObjectRef' or not _space(item.tail)):
            _fail('unknown recorder XML grant')
        text = item.text or ''
        prefix = 'AccumulationRegister.'
        if not text.startswith(prefix) or text.count('.') != 1:
            _fail('unsupported recorder declaration')
        target = xml._name(text[len(prefix):])
        if ('AccumulationRegister', target) not in declarations or target in targets:
            _fail('unknown or duplicate recorder target')
        targets.append(target)
    if not targets:
        _fail('empty accumulation movements')
    return tuple(targets)


def _document(raw, name, declarations, used):
    with location(file='Documents/'+name+'.xml', object=name):
        obj, namespaces, identity, _ = _object(raw, 'Document', used, name)
        allowed = ({'Name', 'NumberLength', 'Autonumbering', 'RegisterRecords'}
                   | _PRESENTATION | set(_DOCUMENT_CONTROLS) | set(_DOCUMENT_PASSIVE))
        props = _properties(obj, allowed, structured={'RegisterRecords'})
        _exact(props, _DOCUMENT_CONTROLS)
        _exact(props, _DOCUMENT_PASSIVE, optional=True)
        auto = xml._text(props, 'Autonumbering')
        if auto not in ('true', 'false'):
            _fail('unsupported document numbering')
        length = xml._int(props, 'NumberLength', 1, 9)
        targets = _recorder_targets(props, namespaces, declarations)
        fields = []
        sections = []
        names = set(xml._DOCUMENT_RESERVED) | {
            'additionalproperties', 'дополнительныесвойства', 'registerrecords', 'движения',
            'thisobject', 'этотобъект', 'setnewobjectref', 'установитьссылкунового'}
        for node in obj.find(_MD + 'ChildObjects'):
            if node.tag == _MD + 'Attribute':
                fields.append(_field(node, namespaces, used, names))
            elif node.tag == _MD + 'TabularSection':
                _shape(node, {'Properties', 'ChildObjects'}, {'Properties', 'ChildObjects'})
                section_props = _properties(node, {'Name'} | _PRESENTATION)
                section_name = xml._name(xml._text(section_props, 'Name'))
                section_id = _identity(node.get('uuid'), used)
                if section_name.casefold() in names:
                    _fail('section name collision')
                names.add(section_name.casefold())
                row_names = set(xml._DOCUMENT_RESERVED) | {'linenumber', 'номерстроки'}
                row_fields = []
                for field in node.find(_MD + 'ChildObjects'):
                    if field.tag != _MD + 'Attribute':
                        _fail('unsupported section field')
                    row_fields.append(_field(field, namespaces, used, row_names))
                if len(row_fields) > 64:
                    _fail('section field bound')
                sections.append(TabularSectionSchema(section_id, section_name, tuple(row_fields)))
            else:
                _fail('unsupported document child')
        if len(fields) > 64 or len(sections) > 16:
            _fail('document field bound')
        return (DocumentSchema(identity, name, length, tuple(fields), tuple(sections),
                               'decimal_v1' if auto == 'true' else 'explicit'), targets)


def _register(raw, name, owners, used):
    with location(file='AccumulationRegisters/'+name+'.xml', object=name):
        obj, namespaces, identity, _ = _object(raw, 'AccumulationRegister', used, name)
        props = _properties(obj, {'Name', 'RegisterType', 'EnableTotalsSplitting'}
                            | _PRESENTATION | set(_PASSIVE))
        _exact(props, {'RegisterType': 'Balance', 'EnableTotalsSplitting': 'false'})
        _exact(props, _PASSIVE, optional=True)
        groups = {'Dimension': [], 'Resource': [], 'Attribute': []}
        names = set(xml._REGISTER_RESERVED) | {'recordtype', 'виддвижения',
                                              'direction', 'направление'}
        for node in obj.find(_MD + 'ChildObjects'):
            kind = node.tag.removeprefix(_MD)
            if kind not in groups or node.tag != _MD + kind:
                _fail('unsupported accumulation field')
            field = _field(node, namespaces, used, names, dimension=kind == 'Dimension')
            if kind == 'Resource' and field.kind != 'number':
                _fail('numeric accumulation resources required')
            groups[kind].append(field)
        schema = AccumulationRegisterSchema(identity, name, owners,
            tuple(groups['Dimension']), tuple(groups['Resource']), tuple(groups['Attribute']))
        try:
            return validate_schema(schema)
        except BackendError:
            _fail('unsupported accumulation schema')


def import_accumulation_configuration(files, *, accumulation_runtime=None):
    """Admit fresh owned source only with the exact explicit profile grant.

    Handler grants bind the complete document ObjectModule bytes, not a claim
    that arbitrary handler code is supported. Compilation/runtime checks are a
    separate admission stage. Other modules and metadata source are forbidden.
    """
    with location(file='Configuration.xml'):
        if type(accumulation_runtime) is not str or accumulation_runtime != PROFILE:
            _fail('explicit accumulation source grant required')
        accepted_source = xml._accept_source_files(files)
        if 'Configuration.xml' not in files:
            _fail('Configuration.xml missing')
        used = set()
        obj, _, identity, name = _object(files['Configuration.xml'], 'Configuration', used)
        _properties(obj, {'Name'} | _PRESENTATION)
        declarations = {}
        names = set()
        for node in obj.find(_MD + 'ChildObjects'):
            kind = node.tag.removeprefix(_MD)
            if (kind not in ('Document', 'AccumulationRegister') or node.tag != _MD + kind
                    or node.attrib or len(node) or not _space(node.tail)):
                _fail('unsupported declaration')
            child_name = xml._name(node.text or '')
            key = (kind, child_name.casefold())
            if key in names:
                _fail('duplicate declaration')
            names.add(key)
            prefix = 'Documents/' if kind == 'Document' else 'AccumulationRegisters/'
            path = prefix + child_name + '.xml'
            if path not in files:
                _fail('declared metadata missing')
            declarations[kind, child_name] = path
        if len(declarations) > 512:
            _fail('metadata bound')
        documents = []
        links = {}
        handlers = []
        accepted = {'Configuration.xml'}
        for (kind, child_name), path in sorted(declarations.items()):
            if kind != 'Document':
                continue
            document, targets = _document(files[path], child_name, declarations, used)
            documents.append(document)
            links[document.identity] = targets
            module = 'Documents/' + child_name + '/Ext/ObjectModule.bsl'
            if module not in files:
                _fail('document handler source missing')
            handlers.append((document.identity, module, sha256(files[module]).hexdigest()))
            accepted.update((path, module))
        registers = []
        for (kind, child_name), path in sorted(declarations.items()):
            if kind != 'AccumulationRegister':
                continue
            owners = tuple(sorted((doc for doc, targets in links.items()
                                   if child_name in targets), key=str))
            if not owners:
                _fail('unowned accumulation register')
            registers.append(_register(files[path], child_name, owners, used))
            accepted.add(path)
        if not documents or not registers or set(files) != accepted:
            _fail('unsupported source or executable grant')
        source = tuple((item.path, item.content) for item in accepted_source)
        digest = sha256(b''.join(path.encode('utf-8') + b'\0' + sha256(raw).digest()
                                 for path, raw in source)).hexdigest()
        return AccumulationConfiguration(identity, name, source, tuple(sorted(documents, key=lambda d: str(d.identity))),
            tuple(registers), tuple(handlers), PROFILE, digest)


def canonical(configuration):
    """Reject forged metadata, ownership, module grants, digests or source drift."""
    if (type(configuration) is not AccumulationConfiguration
            or type(configuration.profile) is not str or configuration.profile != PROFILE):
        _fail('accumulation configuration required')
    if (type(configuration.files) is not tuple
            or any(type(item) is not tuple or len(item) != 2
                   or type(item[0]) is not str or type(item[1]) is not bytes
                   for item in configuration.files)):
        _fail('invalid canonical source')
    try:
        fresh = import_accumulation_configuration(dict(configuration.files),
                                                  accumulation_runtime=PROFILE)
    except (TypeError, UnicodeError):
        _fail('invalid canonical source')
    if not _same(fresh, configuration):
        _fail('source/schema divergence')
    return fresh


def _same(expected, actual):
    # Dataclass equality alone accepts 9.0 == 9 and True == 1. A canonical
    # schema is an exact typed projection, including immutable field groups.
    if type(expected) is not type(actual):
        return False
    if type(expected) is tuple:
        return len(expected) == len(actual) and all(
            _same(left, right) for left, right in zip(expected, actual))
    if is_dataclass(expected):
        return all(_same(getattr(expected, field.name), getattr(actual, field.name))
                   for field in fields(expected))
    return expected == actual
