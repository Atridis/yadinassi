"""Explicit authored catalog-reference inventory grant, separate from scalar v14.

These source/layout rules do not themselves establish native behavior. No legacy
profile, form runtime, module initializer or migration is granted by this type.
"""
from dataclasses import dataclass
from hashlib import sha256
from uuid import UUID

from . import configuration_accumulation as scalar
from . import configuration_xml as xml
from .catalog_backend import CatalogSchema
from .configuration_diagnostics import location

PROFILE = 'accumulation-reference-v1'
FORMAT_VERSION = 15
SOURCE_PROJECTION = 'authored-inventory-reference-source-v1'
_MD = '{' + xml.MD + '}'


@dataclass(frozen=True, slots=True)
class InventoryConfiguration:
    identity: UUID
    name: str
    files: tuple
    catalogs: tuple
    documents: tuple
    registers: tuple
    handlers: tuple
    profile: str
    source_digest: str


def _catalog(raw, name, used):
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
        fields = []
        names = set(xml._RESERVED)
        for node in obj.find(_MD + 'ChildObjects'):
            if node.tag != _MD + 'Attribute':
                scalar._fail('unsupported inventory catalog child')
            fields.append(scalar._field(node, namespaces, used, names))
        if len(fields) > 64:
            scalar._fail('catalog field bound')
        return CatalogSchema(identity, name, code_length, description_length,
            tuple(fields), numbering='decimal_v1' if auto == 'true' else 'explicit')


def import_inventory_configuration(files, *, inventory_runtime=None):
    with location(file='Configuration.xml'):
        if type(inventory_runtime) is not str or inventory_runtime != PROFILE:
            scalar._fail('explicit inventory reference grant required')
        accepted_source = xml._accept_source_files(files)
        if 'Configuration.xml' not in files:
            scalar._fail('Configuration.xml missing')
        used = set()
        obj, _, identity, name = scalar._object(files['Configuration.xml'], 'Configuration', used)
        scalar._properties(obj, {'Name'} | scalar._PRESENTATION)
        declarations = {}
        names = set()
        prefixes = {'Catalog': 'Catalogs/', 'Document': 'Documents/',
                    'AccumulationRegister': 'AccumulationRegisters/'}
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
        catalogs, documents, registers, handlers = [], [], [], []
        accepted = {'Configuration.xml'}
        for (kind, child_name), path in sorted(declarations.items()):
            if kind == 'Catalog':
                catalogs.append(_catalog(files[path], child_name, used))
                accepted.add(path)
        targets = {catalog.name.casefold(): catalog.identity for catalog in catalogs}
        if not targets:
            scalar._fail('inventory catalogs required')
        links = {}
        for (kind, child_name), path in sorted(declarations.items()):
            if kind != 'Document':
                continue
            document, recorders = scalar._document(files[path], child_name, declarations, used, targets=targets)
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
            registers.append(scalar._register(files[path], child_name, owners, used, targets=targets))
            accepted.add(path)
        if not documents or not registers or set(files) != accepted:
            scalar._fail('unsupported source or executable grant')
        source = tuple((item.path, item.content) for item in accepted_source)
        digest = sha256(b''.join(path.encode('utf-8') + b'\0' + sha256(raw).digest()
                                 for path, raw in source)).hexdigest()
        return InventoryConfiguration(identity, name, source,
            tuple(sorted(catalogs, key=lambda c: str(c.identity))),
            tuple(sorted(documents, key=lambda d: str(d.identity))),
            tuple(registers), tuple(handlers), PROFILE, digest)


def canonical(configuration):
    if (type(configuration) is not InventoryConfiguration
            or type(configuration.profile) is not str or configuration.profile != PROFILE
            or type(configuration.files) is not tuple
            or any(type(item) is not tuple or len(item) != 2 or type(item[0]) is not str
                   or type(item[1]) is not bytes for item in configuration.files)):
        scalar._fail('inventory configuration required')
    try:
        fresh = import_inventory_configuration(dict(configuration.files), inventory_runtime=PROFILE)
    except (TypeError, UnicodeError):
        scalar._fail('invalid canonical source')
    if not scalar._same(fresh, configuration):
        scalar._fail('source/schema divergence')
    return fresh


def canonical_runtime(configuration):
    return canonical(configuration) if type(configuration) is InventoryConfiguration else scalar.canonical(configuration)
