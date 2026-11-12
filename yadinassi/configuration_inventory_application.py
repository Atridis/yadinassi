"""Full-source inventory forms grant, distinct from the core format-15 grant.

The temporary core projection removes only explicitly validated form metadata.
It is never persisted or presented as original source. Canonical reimport binds
all form/handler bytes, catalog/reference schemas, command and report grants.
This module neither opens a database nor registers an execution authority.
"""
from dataclasses import dataclass
from hashlib import sha256
from uuid import UUID
import xml.etree.ElementTree as ET

from . import configuration_xml as xml
from .configuration_accumulation import _same
from .configuration_accumulation_references import (
    import_inventory_configuration, PROFILE as CORE_PROFILE)

PROFILE = 'accumulation-reference-forms-v1'
FORMAT_VERSION = 15
MANIFEST = 'InventoryApplication.xml'
NAMESPACE = 'urn:yadinassi:inventory-application:1'
MODES = ('Write', 'Post', 'UndoPosting')
VIEWS = ('Movements', 'Balance', 'Turnovers')
_M = '{' + xml.MD + '}'
_N = '{' + NAMESPACE + '}'


@dataclass(frozen=True, slots=True)
class InventoryCommandGrant:
    form: str
    command: str
    command_id: int
    mode: str


@dataclass(frozen=True, slots=True)
class InventoryReportGrant:
    name: str
    register: str
    register_id: UUID
    view: str


@dataclass(frozen=True, slots=True)
class InventoryApplicationConfiguration:
    identity: UUID
    name: str
    files: tuple
    catalogs: tuple
    documents: tuple
    registers: tuple
    handlers: tuple
    profile: str
    source_digest: str
    commands: tuple
    reports: tuple
    core_projection_digest: str


def _space(value):
    return not (value or '').strip()


def _project_owner(source, path, kind, name, expected, form_names):
    obj, namespaces, root = xml._object(source[path], kind, include_root=True)
    props = xml._props(obj)
    default = props.get(_M+'DefaultObjectForm')
    if (default is None or default.attrib or len(default) or not _space(default.tail)):
        raise ValueError('inventory default object form required')
    default_name = default.text or ''
    obj.find(_M+'Properties').remove(default)
    inventories = obj.findall(_M+'ChildObjects')
    if (len(inventories) != 1 or inventories[0].attrib
            or not _space(inventories[0].text)):
        raise ValueError('inventory owner declarations required')
    inventory = inventories[0]; owned = []
    for entry in list(inventory):
        if entry.tag == _M+'Form':
            if entry.attrib or len(entry) or not _space(entry.tail):
                raise ValueError('inventory form declaration shape')
            form = xml._name(entry.text or '')
            public = kind+'.'+name+'.Form.'+form
            if public.casefold() in form_names:
                raise ValueError('duplicate inventory form')
            form_names.add(public.casefold()); owned.append(public)
            prefix = kind+'s/'+name+'/Forms/'+form
            expected.update((prefix+'.xml', prefix+'/Ext/Form.xml'))
            module = prefix+'/Ext/Form/Module.bsl'
            if module in source: expected.add(module)
            inventory.remove(entry)
        elif entry.tag not in ({_M+'Attribute', _M+'TabularSection'} if kind == 'Document'
                                else {_M+'Attribute'}):
            raise ValueError('unsupported inventory form owner child')
    if default_name not in owned:
        raise ValueError('undeclared inventory default form')
    # Preserve QName-valued types and recorder declarations without changing
    # ElementTree's process-global namespace registry.
    for node in root.iter():
        values = [node.text or ''] if node.tag == '{'+xml.V8+'}Type' else []
        value = node.get('{http://www.w3.org/2001/XMLSchema-instance}type')
        if value is not None: values.append(value)
        for value in values:
            if ':' in value:
                prefix = value.split(':', 1)[0]
                uri = namespaces[id(node)].get(prefix)
                if uri is None: raise ValueError('unknown inventory QName namespace')
                node.set('xmlns:'+prefix, uri)
    return ET.tostring(root, encoding='utf-8')


def _command_grants(node, definition, source):
    if len(node) != len(MODES):
        raise ValueError('all three document host commands required')
    declared = {c[0]: c[2] for c in definition.commands}
    parts = definition.name.split('.')
    raw, _ = xml._parse(source['Documents/'+parts[1]+'/Forms/'+parts[3]+'/Ext/Form.xml'])
    commands_node = raw.find('{http://v8.1c.ru/8.3/xcf/logform}Commands')
    ids = {} if commands_node is None else {c.get('name'): c.get('id') for c in commands_node}
    from .syntax import ast
    routines = {r.name.casefold(): r for r in definition.program.client.program()
                if type(r) is ast.Routine}
    modes = set(); names = set(); grants = []
    for command in node:
        name, mode = command.get('name'), command.get('mode')
        if (command.tag != _N+'Command' or set(command.attrib) != {'name','id','mode'}
                or len(command) or not _space(command.text) or not _space(command.tail)
                or name not in declared or command.get('id') != ids.get(name)
                or name in names or mode not in MODES or mode in modes):
            raise ValueError('exact source-granted inventory command required')
        routine = routines.get(declared[name].casefold())
        if (routine is None or routine.body or routine.is_function or routine.is_async
                or routine.is_dual or len(routine.parameters) != 1
                or routine.parameters[0].default is not None):
            raise ValueError('inventory host command requires an empty synchronous client handler')
        names.add(name); modes.add(mode)
        grants.append(InventoryCommandGrant(definition.name, name, int(command.get('id')), mode))
    return grants


def _manifest(raw, forms, source, registers):
    root, _ = xml._parse(raw)
    if (root.tag != _N+'InventoryApplication' or root.attrib != {'version':'1'}
            or not _space(root.text) or len(root) != 2
            or [node.tag for node in root] != [_N+'Forms', _N+'Reports']):
        raise ValueError('explicit inventory application manifest required')
    declared, reports_node = root
    if any(node.attrib or not _space(node.text) or not _space(node.tail) for node in root):
        raise ValueError('inventory manifest container shape')
    if not 1 <= len(declared) <= 64 or not 1 <= len(reports_node) <= 96:
        raise ValueError('inventory manifest bound')
    seen = set(); commands = []
    for node in declared:
        name = node.get('name', '')
        definition = forms.get(name.casefold())
        if (set(node.attrib) != {'name'} or definition is None or name != definition.name
                or name in seen or not _space(node.text) or not _space(node.tail)):
            raise ValueError('exact declared inventory form required')
        seen.add(name)
        if definition.document_schema is not None:
            if node.tag != _N+'DocumentForm': raise ValueError('document host grant required')
            commands.extend(_command_grants(node, definition, source))
        elif node.tag != _N+'CatalogForm' or len(node):
            raise ValueError('catalog forms have no posting host grant')
    if seen != {d.name for d in forms.values()}:
        raise ValueError('all inventory forms require explicit manifest binding')
    registry = {r.name:r for r in registers}
    report_names = set(); report_views = set(); reports = []
    for node in reports_node:
        if (node.tag != _N+'Report' or set(node.attrib) != {'name','register','registerId','view'}
                or len(node) or not _space(node.text) or not _space(node.tail)):
            raise ValueError('closed inventory report grant required')
        name = xml._name(node.get('name', '')); register = registry.get(node.get('register'))
        view = node.get('view')
        if (register is None or node.get('registerId') != str(register.identity)
                or view not in VIEWS or name.casefold() in report_names
                or (register.identity,view) in report_views):
            raise ValueError('exact unique inventory register report required')
        report_names.add(name.casefold()); report_views.add((register.identity,view))
        reports.append(InventoryReportGrant(name,register.name,register.identity,view))
    return tuple(commands), tuple(reports)


def _import_source(files):
    accepted = xml._accept_source_files(files)
    source = {entry.path:entry.content for entry in accepted}
    if MANIFEST not in source or 'Configuration.xml' not in source:
        raise ValueError('inventory application source envelope required')
    config, _ = xml._object(source['Configuration.xml'], 'Configuration')
    declarations = config.findall(_M+'ChildObjects')
    if len(declarations) != 1 or declarations[0].attrib or not _space(declarations[0].text):
        raise ValueError('inventory declaration envelope')
    expected = {'Configuration.xml', MANIFEST}
    projected = {'Configuration.xml':source['Configuration.xml']}; form_names = set()
    for child in declarations[0]:
        if child.tag not in (_M+'Catalog', _M+'Document', _M+'AccumulationRegister'):
            raise ValueError('inventory application metadata family')
        if child.attrib or len(child) or not _space(child.tail):
            raise ValueError('inventory declaration shape')
        name = xml._name(child.text or ''); kind = child.tag[len(_M):]
        path = kind+'s/'+name+'.xml'
        expected.add(path)
        if kind == 'AccumulationRegister':
            projected[path] = source[path]
        else:
            projected[path] = _project_owner(source,path,kind,name,expected,form_names)
            if kind == 'Document':
                module = 'Documents/'+name+'/Ext/ObjectModule.bsl'
                expected.add(module); projected[module] = source[module]
    if set(source) != expected:
        raise ValueError('unexpected or missing inventory application source')
    core = import_inventory_configuration(projected, inventory_runtime=CORE_PROFILE)
    from .configuration_forms import load_configuration_forms
    forms = load_configuration_forms(source, catalog_schemas=core.catalogs,
        document_schemas=core.documents, reference_catalogs=core.catalogs, posting_application=True)
    if (set(forms.forms) != form_names or any(not d.object_fields or
            (d.document_schema is None and d.catalog_schema is None) for d in forms.forms.values())):
        raise ValueError('bound inventory object forms required')
    commands, reports = _manifest(source[MANIFEST],forms.forms,source,core.registers)
    # Include generated native metadata type/value identities too. Core already
    # validates their closed shape; forms may not reuse those otherwise-hidden IDs.
    identities = []
    for path, raw in core.files:
        if not path.endswith('.xml'): continue
        root, _ = xml._parse(raw)
        for node in root.iter():
            if 'uuid' in node.attrib: identities.append(UUID(node.get('uuid')))
            if node.tag in ('{'+xml.XR+'}TypeId', '{'+xml.XR+'}ValueId'):
                identities.append(UUID(node.text))
    identities.extend(d.identity for d in forms.forms.values())
    if len(identities) != len(set(identities)):
        raise ValueError('duplicate inventory application metadata identity')
    original = tuple(sorted(source.items()))
    digest = sha256(b''.join(path.encode('utf-8')+b'\0'+sha256(raw).digest()
                            for path,raw in original)).hexdigest()
    return InventoryApplicationConfiguration(core.identity,core.name,original,core.catalogs,
        core.documents,core.registers,core.handlers,PROFILE,digest,commands,reports,core.source_digest), core


def _import(files):
    try:
        return _import_source(files)
    except KeyError:
        raise ValueError('missing inventory application source') from None


def import_inventory_application(files, *, inventory_runtime=None):
    if type(inventory_runtime) is not str or inventory_runtime != PROFILE:
        raise ValueError('explicit inventory application source grant required')
    return _import(files)[0]


def _checked(configuration):
    if (type(configuration) is not InventoryApplicationConfiguration
            or type(configuration.profile) is not str or configuration.profile != PROFILE
            or type(configuration.files) is not tuple
            or any(type(item) is not tuple or len(item) != 2 or type(item[0]) is not str
                   or type(item[1]) is not bytes for item in configuration.files)
            or len({p for p,raw in configuration.files}) != len(configuration.files)):
        raise ValueError('inventory application configuration required')
    fresh, core = _import(dict(configuration.files))
    if not _same(fresh,configuration):
        raise ValueError('inventory application source/schema divergence')
    return fresh, core


def canonical(configuration):
    return _checked(configuration)[0]


def validated_core(configuration):
    """Trusted projection only after exact full-source and manifest validation."""
    return _checked(configuration)[1]
