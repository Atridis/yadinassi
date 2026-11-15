"""Explicit full-source format16 forms grant, separate from inventory-enum-v1.

Original bytes are persisted; only a validated temporary projection admits the
core schema. Neither source projection nor form loading grants root ownership.
"""
from dataclasses import dataclass
from hashlib import sha256
from uuid import UUID
from . import configuration_xml as xml
from .configuration_inventory_enums import (_same, import_inventory_enum_configuration,
    PROFILE as CORE_PROFILE)
from .configuration_inventory_application import (
    MANIFEST, _M, _space, _project_owner, _manifest)

PROFILE = 'inventory-enum-forms-v1'
FORMAT_VERSION = 16

@dataclass(frozen=True, slots=True)
class InventoryEnumApplicationConfiguration:
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
    commands: tuple
    reports: tuple
    core_projection_digest: str

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
        if child.tag not in (_M+'Catalog', _M+'Document', _M+'AccumulationRegister', _M+'Enum'):
            raise ValueError('inventory application metadata family')
        if child.attrib or len(child) or not _space(child.tail):
            raise ValueError('inventory declaration shape')
        name = xml._name(child.text or ''); kind = child.tag[len(_M):]
        path = kind+'s/'+name+'.xml'
        expected.add(path)
        if kind in ('AccumulationRegister', 'Enum'):
            projected[path] = source[path]
        else:
            projected[path] = _project_owner(source,path,kind,name,expected,form_names)
            if kind == 'Document':
                module = 'Documents/'+name+'/Ext/ObjectModule.bsl'
                expected.add(module); projected[module] = source[module]
    if set(source) != expected:
        raise ValueError('unexpected or missing inventory application source')
    core = import_inventory_enum_configuration(projected, inventory_runtime=CORE_PROFILE)
    from .configuration_forms import load_configuration_forms
    forms = load_configuration_forms(source, catalog_schemas=core.catalogs,
        document_schemas=core.documents, reference_catalogs=core.catalogs, posting_application=True, enum_definitions=core.enumerations)
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
    return InventoryEnumApplicationConfiguration(core.identity,core.name,original,core.catalogs,
        core.documents,core.registers,core.handlers,core.enumerations,PROFILE,digest,commands,reports,core.source_digest), core


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
    if (type(configuration) is not InventoryEnumApplicationConfiguration
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
