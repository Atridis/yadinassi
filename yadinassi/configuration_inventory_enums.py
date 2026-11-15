"""Explicit authored EnumRef inventory source; not a storage activation grant.

Only this new immutable configuration type admits enum fields. Existing scalar,
catalog-reference and form source importers are unchanged. Original XML/BSL is
retained in full and reimported for canonical admission. No native wire GUID,
manager module, form, migration or implicit profile selection is inferred.
"""
from dataclasses import dataclass, fields, is_dataclass
from hashlib import sha256
from uuid import UUID

from . import configuration_accumulation as scalar
from . import configuration_xml as xml
from .accumulation_movements import (AccumulationRegisterSchema, MAX_DIMENSIONS,
                                    MAX_FIELDS, MAX_RECORDERS)
from .catalog_backend import BackendError, CatalogSchema, FieldSchema, TabularSectionSchema
from .configuration_diagnostics import location, metadata_name
from .configuration_enumerations import read_enumerations
from .document_backend import DocumentSchema
from .enum_storage_values import EnumValueDomain

PROFILE = 'inventory-enum-v1'
FORMAT_VERSION = 16
SOURCE_PROJECTION = 'authored-inventory-enum-source-v1'
VALUE_PROFILE = 'catalog_enum_reference_v1'
_MD = '{' + xml.MD + '}'


@dataclass(frozen=True, slots=True)
class InventoryEnumConfiguration:
    identity: UUID
    name: str
    files: tuple
    catalogs: tuple
    documents: tuple
    registers: tuple
    handlers: tuple
    enumerations: tuple
    profile: str
    source_digest: str


def _field(node, namespaces, used, names, *, enum_targets, targets=None, dimension=False):
    with location(field=metadata_name(node)):
        scalar._shape(node, {'Properties'}, {'Properties'})
        props = scalar._properties(node, {'Name', 'Type'} | scalar._PRESENTATION
            | ({'UseInTotals'} if dimension else set()), structured={'Type'})
        identity = scalar._identity(node.get('uuid'), used)
        name = xml._name(xml._text(props, 'Name'))
        if name.casefold() in names:
            scalar._fail('field name collision')
        names.add(name.casefold())
        if dimension:
            scalar._exact(props, {'UseInTotals': 'true'})
        with location(property='Type'):
            type_node = props.get(_MD + 'Type')
            types = ([] if type_node is None else
                     [n for n in type_node if n.tag == '{' + xml.V8 + '}Type'])
            if len(types) == 1:
                namespace, target_name = xml._qname(types[0], namespaces)
                if namespace == xml.CFG and target_name.startswith('EnumRef.'):
                    if (type_node.attrib or not scalar._space(type_node.text)
                            or len(type_node) != 1 or types[0].attrib or len(types[0])
                            or not scalar._space(types[0].tail)):
                        scalar._fail('unsupported enum type envelope')
                    target = enum_targets.get(target_name[len('EnumRef.'):].casefold())
                    if target is None:
                        scalar._fail('unknown enum reference target')
                    return FieldSchema(identity, name, 'enum_ref', (), target_enum_id=target)
            kind, qualifiers, target = xml._type(props, namespaces, targets or {})
            if not (kind in scalar._SCALARS and target is None or targets is not None
                    and kind == 'catalog_ref' and target in targets.values()):
                scalar._fail('unsupported enum inventory field')
            return FieldSchema(identity, name, kind, qualifiers, target)


def _catalog(raw, name, used, enum_targets):
    with location(file='Catalogs/' + name + '.xml', object=name):
        obj, namespaces, identity, _ = scalar._object(raw, 'Catalog', used, name)
        controls = {'CodeType': 'String', 'CodeAllowedLength': 'Variable',
                    'CheckUnique': 'true', 'Hierarchical': 'false'}
        props = scalar._properties(obj, {'Name', 'CodeLength', 'DescriptionLength',
            'Autonumbering'} | set(controls) | scalar._PRESENTATION | set(scalar._PASSIVE))
        scalar._exact(props, controls)
        scalar._exact(props, scalar._PASSIVE, optional=True)
        auto = xml._text(props, 'Autonumbering')
        if auto not in ('true', 'false'):
            scalar._fail('unsupported catalog numbering')
        code_length = xml._int(props, 'CodeLength', 1, 9)
        description_length = xml._int(props, 'DescriptionLength', 1, 1024)
        fields, names = [], set(xml._RESERVED)
        for node in obj.find(_MD + 'ChildObjects'):
            if node.tag != _MD + 'Attribute':
                scalar._fail('unsupported enum inventory catalog child')
            # Catalog-to-catalog fields/sections are not silently added to the
            # original inventory catalog surface by enum persistence.
            fields.append(_field(node, namespaces, used, names, enum_targets=enum_targets))
        if len(fields) > 64:
            scalar._fail('catalog field bound')
        return CatalogSchema(identity, name, code_length, description_length,
            tuple(fields), numbering='decimal_v1' if auto == 'true' else 'explicit')


def _document(raw, name, declarations, used, *, targets, enum_targets):
    with location(file='Documents/'+name+'.xml', object=name):
        obj, namespaces, identity, _ = scalar._object(raw, 'Document', used, name)
        allowed = ({'Name', 'NumberLength', 'Autonumbering', 'RegisterRecords'}
                   | scalar._PRESENTATION | set(scalar._DOCUMENT_CONTROLS) | set(scalar._DOCUMENT_PASSIVE))
        props = scalar._properties(obj, allowed, structured={'RegisterRecords'})
        scalar._exact(props, scalar._DOCUMENT_CONTROLS)
        scalar._exact(props, scalar._DOCUMENT_PASSIVE, optional=True)
        auto = xml._text(props, 'Autonumbering')
        if auto not in ('true', 'false'):
            scalar._fail('unsupported document numbering')
        length = xml._int(props, 'NumberLength', 1, 9)
        recorders = scalar._recorder_targets(props, namespaces, declarations)
        fields = []
        sections = []
        names = set(xml._DOCUMENT_RESERVED) | {
            'additionalproperties', 'дополнительныесвойства', 'registerrecords', 'движения',
            'thisobject', 'этотобъект', 'setnewobjectref', 'установитьссылкунового'}
        for node in obj.find(_MD + 'ChildObjects'):
            if node.tag == _MD + 'Attribute':
                fields.append(_field(node, namespaces, used, names, targets=targets, enum_targets=enum_targets))
            elif node.tag == _MD + 'TabularSection':
                scalar._shape(node, {'Properties', 'ChildObjects'}, {'Properties', 'ChildObjects'})
                section_props = scalar._properties(node, {'Name'} | scalar._PRESENTATION)
                section_name = xml._name(xml._text(section_props, 'Name'))
                section_id = scalar._identity(node.get('uuid'), used)
                if section_name.casefold() in names:
                    scalar._fail('section name collision')
                names.add(section_name.casefold())
                row_names = set(xml._DOCUMENT_RESERVED) | {'linenumber', 'номерстроки'}
                row_fields = []
                for field in node.find(_MD + 'ChildObjects'):
                    if field.tag != _MD + 'Attribute':
                        scalar._fail('unsupported section field')
                    row_fields.append(_field(field, namespaces, used, row_names, targets=targets, enum_targets=enum_targets))
                if len(row_fields) > 64:
                    scalar._fail('section field bound')
                sections.append(TabularSectionSchema(section_id, section_name, tuple(row_fields)))
            else:
                scalar._fail('unsupported document child')
        if len(fields) > 64 or len(sections) > 16:
            scalar._fail('document field bound')
        return (DocumentSchema(identity, name, length, tuple(fields), tuple(sections),
                               'decimal_v1' if auto == 'true' else 'explicit'), recorders)


def _register(raw, name, owners, used, *, targets, enum_targets):
    with location(file='AccumulationRegisters/'+name+'.xml', object=name):
        obj, namespaces, identity, _ = scalar._object(raw, 'AccumulationRegister', used, name)
        props = scalar._properties(obj, {'Name', 'RegisterType', 'EnableTotalsSplitting'}
                            | scalar._PRESENTATION | set(scalar._PASSIVE))
        scalar._exact(props, {'RegisterType': 'Balance', 'EnableTotalsSplitting': 'false'})
        scalar._exact(props, scalar._PASSIVE, optional=True)
        groups = {'Dimension': [], 'Resource': [], 'Attribute': []}
        names = set(xml._REGISTER_RESERVED) | {'recordtype', 'виддвижения',
                                              'direction', 'направление'}
        for node in obj.find(_MD + 'ChildObjects'):
            kind = node.tag.removeprefix(_MD)
            if kind not in groups or node.tag != _MD + kind:
                scalar._fail('unsupported accumulation field')
            field = _field(node, namespaces, used, names, dimension=kind == 'Dimension', targets=targets, enum_targets=enum_targets)
            if kind == 'Resource' and field.kind != 'number':
                scalar._fail('numeric accumulation resources required')
            groups[kind].append(field)
        schema = AccumulationRegisterSchema(identity, name, owners,
            tuple(groups['Dimension']), tuple(groups['Resource']), tuple(groups['Attribute']),
            value_profile=VALUE_PROFILE)
        # This source-only construction is deliberately not fed to the old
        # scalar/catalog-reference validator. Format16 storage admission owns
        # the distinct value_profile; no old validator is widened here.
        if (not 1 <= len(owners) <= MAX_RECORDERS or len(set(owners)) != len(owners)
                or len(schema.dimensions) > MAX_DIMENSIONS or not schema.resources
                or len(schema.fields) > MAX_FIELDS):
            scalar._fail('unsupported accumulation schema bounds')
        return schema


def _enumerations(files, names, used):
    result = []
    for name in names:
        path = 'Enums/' + name + '.xml'
        with location(file=path, object=name):
            obj, _, root = xml._object(files[path], 'Enum', include_root=True)
            if (root.attrib != {'version': '2.20'} or not scalar._space(root.text)
                    or not scalar._space(root.tail) or not scalar._space(obj.tail)):
                scalar._fail('unsupported enum metadata document envelope')
            # The language reader performs semantic shape and global collision
            # checks. This authored persistence profile additionally uses the
            # same canonical spelling as its catalog/document UUIDs.
            for node in obj.iter():
                text = node.get('uuid')
                if node.tag in ('{' + xml.XR + '}TypeId', '{' + xml.XR + '}ValueId'):
                    text = node.text
                if text is not None and text != str(xml._uuid(text)):
                    scalar._fail('noncanonical enum metadata UUID')
            issues = []
            result.extend(read_enumerations(files, (name,), used, issues))
            if issues:
                scalar._fail('unsupported enum declaration envelope')
    return tuple(result)


def import_inventory_enum_configuration(files, *, inventory_runtime=None):
    """Admit full authored source only under this exact explicit profile."""
    with location(file='Configuration.xml'):
        if type(inventory_runtime) is not str or inventory_runtime != PROFILE:
            scalar._fail('explicit enum inventory grant required')
        accepted_source = xml._accept_source_files(files)
        if 'Configuration.xml' not in files:
            scalar._fail('Configuration.xml missing')
        used = set()
        obj, _, identity, name = scalar._object(files['Configuration.xml'], 'Configuration', used)
        scalar._properties(obj, {'Name'} | scalar._PRESENTATION)
        declarations, names = {}, set()
        prefixes = {'Catalog': 'Catalogs/', 'Document': 'Documents/',
                    'AccumulationRegister': 'AccumulationRegisters/', 'Enum': 'Enums/'}
        for node in obj.find(_MD + 'ChildObjects'):
            kind = node.tag.removeprefix(_MD)
            if (kind not in prefixes or node.tag != _MD + kind or node.attrib
                    or len(node) or not scalar._space(node.tail)):
                scalar._fail('unsupported declaration')
            child_name = xml._name(node.text or '')
            key = kind, child_name.casefold()
            if key in names:
                scalar._fail('duplicate declaration')
            names.add(key)
            path = prefixes[kind] + child_name + '.xml'
            if path not in files:
                with location(file=path, object=child_name):
                    scalar._fail('declared metadata missing')
            declarations[kind, child_name] = path
        if len(declarations) > 512:
            scalar._fail('metadata bound')
        enum_names = tuple(child_name for kind, child_name in sorted(declarations) if kind == 'Enum')
        if not 1 <= len(enum_names) <= 128:
            scalar._fail('enum declaration bound')
        enumerations = _enumerations(files, enum_names, used)
        try:
            # Identity-only validation; this temporary domain neither survives
            # import nor asserts a database binding or a runtime issuer.
            EnumValueDomain(identity, enumerations)
        except BackendError:
            scalar._fail('invalid enum declarations')
        enum_targets = {item.name.casefold(): item.identity for item in enumerations}
        catalogs, documents, registers, handlers = [], [], [], []
        accepted = {'Configuration.xml', *('Enums/' + name + '.xml' for name in enum_names)}
        for (kind, child_name), path in sorted(declarations.items()):
            if kind == 'Catalog':
                catalogs.append(_catalog(files[path], child_name, used, enum_targets))
                accepted.add(path)
        targets = {catalog.name.casefold(): catalog.identity for catalog in catalogs}
        if not targets:
            scalar._fail('enum inventory catalogs required')
        links = {}
        for (kind, child_name), path in sorted(declarations.items()):
            if kind != 'Document':
                continue
            document, recorders = _document(files[path], child_name, declarations, used,
                                           targets=targets, enum_targets=enum_targets)
            documents.append(document)
            links[document.identity] = recorders
            module = 'Documents/' + child_name + '/Ext/ObjectModule.bsl'
            if module not in files:
                scalar._fail('document handler source missing')
            handlers.append((document.identity, module, sha256(files[module]).hexdigest()))
            accepted.update((path, module))
        for (kind, child_name), path in sorted(declarations.items()):
            if kind != 'AccumulationRegister':
                continue
            owners = tuple(sorted((doc for doc, recorders in links.items()
                                   if child_name in recorders), key=str))
            if not owners:
                scalar._fail('unowned accumulation register')
            registers.append(_register(files[path], child_name, owners, used,
                                       targets=targets, enum_targets=enum_targets))
            accepted.add(path)
        if not documents or not registers or set(files) != accepted:
            scalar._fail('unsupported source or executable grant')
        source = tuple((item.path, item.content) for item in accepted_source)
        digest = sha256(b''.join(path.encode('utf-8') + b'\0' + sha256(raw).digest()
                                 for path, raw in source)).hexdigest()
        return InventoryEnumConfiguration(identity, name, source,
            tuple(sorted(catalogs, key=lambda c: str(c.identity))),
            tuple(sorted(documents, key=lambda d: str(d.identity))), tuple(registers),
            tuple(handlers), enumerations, PROFILE, digest)


def _same(expected, actual):
    if type(expected) is not type(actual):
        return False
    if type(expected) is UUID:
        # Exact UUID class alone must not execute an injected integer equality
        # hook in a forged in-memory schema. Fresh import supplies valid UUIDs.
        try:
            value = actual.int
        except AttributeError:
            return False
        return type(value) is int and expected.int == value
    if type(expected) is tuple:
        return len(expected) == len(actual) and all(_same(a, b) for a, b in zip(expected, actual))
    if is_dataclass(expected):
        try:
            return all(_same(getattr(expected, f.name), getattr(actual, f.name)) for f in fields(expected))
        except AttributeError:
            return False
    return expected == actual


def canonical(configuration):
    """Reject source/schema/grant drift without projecting into core15."""
    if type(configuration) is not InventoryEnumConfiguration:
        scalar._fail('enum inventory configuration required')
    try:
        if (type(configuration.profile) is not str or configuration.profile != PROFILE
                or type(configuration.files) is not tuple
                or any(type(item) is not tuple or len(item) != 2 or type(item[0]) is not str
                       or type(item[1]) is not bytes for item in configuration.files)):
            scalar._fail('enum inventory configuration required')
        fresh = import_inventory_enum_configuration(dict(configuration.files), inventory_runtime=PROFILE)
    except (TypeError, UnicodeError, AttributeError):
        scalar._fail('invalid canonical enum source')
    if not _same(fresh, configuration):
        scalar._fail('source/schema divergence')
    return fresh
