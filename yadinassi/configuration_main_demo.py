"""One exact-source demo: original catalog policy plus inventory documents.

A new immutable grant, never a widening of historical demo or enum profiles.
Import is pure: it neither executes stored code nor allocates a database.
"""
from copy import deepcopy
from functools import lru_cache
from dataclasses import dataclass
from hashlib import sha256
from uuid import UUID
import xml.etree.ElementTree as ET
from . import configuration_xml as xml
from .catalog_backend import CatalogSchema, FieldSchema, TabularSectionSchema
from .configuration_inventory_enums import _same, _enumerations, _document, _register
from .configuration_inventory_application import MANIFEST, _project_owner, _manifest
from .main_demo_source import SOURCE_SHA256

PROFILE = 'main-demo-v1'
FORMAT_VERSION = 16
M = '{' + xml.MD + '}'

@dataclass(frozen=True, slots=True)
class MainDemoConfiguration:
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
    catalog_handlers: tuple
    catalog_sources: tuple


def _digest(files):
    return sha256(b''.join(p.encode('utf-8') + b'\0' + sha256(raw).digest()
                           for p, raw in sorted(files))).hexdigest()


def _catalogs(source, inventory):
    owners = {c.name: c for c in inventory}
    kinds, warehouses, products = (owners[n] for n in ('ВидыНоменклатуры', 'Склады', 'Номенклатура'))
    # These schema projections are authorised only after the complete exact-byte
    # envelope, including original object/form modules, has been checked.
    obj, _ = xml._object(source[products.path], 'Catalog')
    children = obj.find(M+'ChildObjects')
    attribute, = children.findall(M+'Attribute')
    section, = children.findall(M+'TabularSection')
    row, = section.find(M+'ChildObjects').findall(M+'Attribute')
    result = (
        CatalogSchema(kinds.identity, kinds.name, 9, 100, numbering='decimal_v1'),
        CatalogSchema(warehouses.identity, warehouses.name, 9, 100, numbering='decimal_v1'),
        CatalogSchema(products.identity, products.name, 9, 150,
            (FieldSchema(UUID(attribute.get('uuid')), 'ВидНоменклатуры', 'catalog_ref', (), kinds.identity),),
            (TabularSectionSchema(UUID(section.get('uuid')), 'Склады',
                (FieldSchema(UUID(row.get('uuid')), 'Склад', 'catalog_ref', (), warehouses.identity),)),),
            numbering='decimal_v1'))
    return tuple(sorted(result, key=lambda c: str(c.identity)))


def import_main_demo_configuration(files, *, profile=None):
    if type(profile) is not str or profile != PROFILE:
        raise ValueError('explicit main demo source grant required')
    accepted = xml._accept_source_files(files)
    source = {f.path: f.content for f in accepted}
    if {p: sha256(raw).hexdigest() for p, raw in source.items()} != SOURCE_SHA256:
        raise ValueError('main demo source mismatch')
    # Inert inventory checks catalog/form identities without granting execution.
    archive, inventory = xml._inert_configuration(source)
    catalogs = _catalogs(source, inventory)
    root, _ = xml._object(source['Configuration.xml'], 'Configuration')
    declarations = {}
    for node in root.find(M+'ChildObjects'):
        kind = node.tag.removeprefix(M)
        if kind in ('Catalog', 'Document', 'AccumulationRegister', 'Enum'):
            name = xml._name(node.text or '')
            declarations[kind, name] = kind+'s/'+name+'.xml'
    used = {archive.config_uuid}
    for catalog in catalogs:
        used.add(catalog.identity)
        used.update(f.identity for f in catalog.fields)
        for section in catalog.tabular_sections:
            used.add(section.identity); used.update(f.identity for f in section.fields)
    enum_names = tuple(n for kind,n in declarations if kind == 'Enum')
    enumerations = _enumerations(source, enum_names, used)
    enum_targets = {e.name.casefold():e.identity for e in enumerations}
    targets = {c.name.casefold():c.identity for c in catalogs}
    documents, handlers, registers, links = [], [], [], {}
    expected, form_names, projected = set(), set(), {}
    for (kind, name), path in declarations.items():
        if kind != 'Document': continue
        raw = _project_owner(source, path, kind, name, expected, form_names)
        projected[path] = raw
        document, recorders = _document(raw, name, declarations, used,
                                        targets=targets, enum_targets=enum_targets)
        documents.append(document); links[document.identity] = recorders
        module = 'Documents/'+name+'/Ext/ObjectModule.bsl'
        handlers.append((document.identity,module,sha256(source[module]).hexdigest()))
    for (kind, name), path in declarations.items():
        if kind != 'AccumulationRegister': continue
        owners = tuple(sorted((d for d,r in links.items() if name in r),key=str))
        registers.append(_register(source[path],name,owners,used,
                                   targets=targets,enum_targets=enum_targets))
    # Original native catalog forms use their own bound policy. The strict
    # document form loader receives only document declarations, never a fake
    # generic grant for those original catalog modules or their list form.
    from .configuration_forms import load_configuration_forms
    form_source = dict(source)
    _, _, form_root = xml._object(source['Configuration.xml'], 'Configuration', include_root=True)
    form_config = form_root.find(M+'Configuration')
    children = form_config.find(M+'ChildObjects')
    for node in list(children):
        if node.tag != M+'Document': children.remove(node)
    form_source['Configuration.xml'] = ET.tostring(form_root,encoding='utf-8')
    forms = load_configuration_forms(form_source, document_schemas=tuple(documents),
        reference_catalogs=catalogs, posting_application=True, enum_definitions=enumerations)
    if set(forms.forms) != form_names:
        raise ValueError('main demo document forms mismatch')
    commands, reports = _manifest(source[MANIFEST],forms.forms,source,tuple(registers))
    catalog_handlers = tuple((c.identity, 'Catalogs/'+c.name+'/Ext/ObjectModule.bsl',
        sha256(source['Catalogs/'+c.name+'/Ext/ObjectModule.bsl']).hexdigest())
        for c in catalogs if 'Catalogs/'+c.name+'/Ext/ObjectModule.bsl' in source)
    original = tuple(sorted(source.items()))
    return MainDemoConfiguration(archive.config_uuid,archive.name,original,catalogs,
        tuple(sorted(documents,key=lambda d:str(d.identity))),tuple(registers),tuple(handlers),enumerations,PROFILE,_digest(original),
        commands,reports,_digest(projected.items()),catalog_handlers,inventory)


@lru_cache(maxsize=1)
def _parsed_source_witness(files):
    """Private pure parse memo, never a database/owner/write admission.

    The key contains exact immutable source bytes, not a config object or a
    data_version. Nothing from this cached object is returned to a caller.
    Failures are not cached. Database readers still independently verify their
    actual bytes, marker, database identity and DDL in the current snapshot.
    """
    return import_main_demo_configuration(dict(files), profile=PROFILE)


def canonical(configuration):
    if (type(configuration) is not MainDemoConfiguration
            or type(configuration.profile) is not str or configuration.profile != PROFILE
            or type(configuration.files) is not tuple
            or any(type(x) is not tuple or len(x)!=2 or type(x[0]) is not str
                   or type(x[1]) is not bytes for x in configuration.files)
            or len({p for p,raw in configuration.files}) != len(configuration.files)):
        raise ValueError('main demo configuration required')
    # Rehash the full current envelope even on a parse-cache hit. Bounds and
    # the closed path/hash set are checked before consulting process-local data.
    if (len(configuration.files) != len(SOURCE_SHA256)
            or any(len(raw) > xml.MAX_FILE_BYTES for _, raw in configuration.files)
            or sum(len(raw) for _, raw in configuration.files) > xml.MAX_TOTAL_BYTES
            or {p: sha256(raw).hexdigest() for p, raw in configuration.files} != SOURCE_SHA256):
        raise ValueError('main demo source mismatch')
    witness = _parsed_source_witness(tuple(sorted(configuration.files)))
    # A caller may forge even frozen dataclasses via object.__setattr__. Compare
    # every schema/handler/profile field, then return a detached copy so such a
    # caller cannot poison the private positive parse witness for another owner.
    fresh = deepcopy(witness)
    if not _same(fresh,configuration):
        raise ValueError('main demo source/schema divergence')
    return fresh
