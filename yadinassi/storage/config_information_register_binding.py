"""Closed independent nonperiodical InfoRg binding, native run 41353896285.

CONFIG role collections and DBNames supply identities; physical declarations are
reconstructed, never accepted as compiler input. No arbitrary register profile.
"""
from dataclasses import dataclass
from types import SimpleNamespace
from .config_catalog_binding import (BoundCatalogAttribute, BoundFieldPlacement,
    CatalogBindingLimits, CatalogBindingError, _fail, _uuid, _name, _KIND, _linked_layout)
from .config_catalog_attributes import CatalogAttribute, CatalogAttributes
from .config_information_register_metadata import InformationRegisterIdentityPrefix
from .filedb_dbnames import DBNamesEntry, DBNamesIndex, DBNAMES_PROFILE_IDENTIFIER

PROFILE_IDENTIFIER = 'owned_information_register_independent_nonperiodical_v1'

@dataclass(frozen=True, slots=True)
class InformationRegisterBinding:
    metadata_uuid: str
    name: str
    register_id: int
    table_name: str
    declarations: tuple
    attributes: tuple
    recordlock: str
    format_item: int
    record_size: int
    placements: tuple
    dimension_count: int = 2
    resource_count: int = 3
    profile_identifier: str = PROFILE_IDENTIFIER


def _layout(binding, attributes, limits):
    if not _uuid(binding.metadata_uuid): _fail('identity')
    _name(binding.name)
    if type(binding.register_id) is not int or not 1 <= binding.register_id <= 2147483647: _fail('dbnames_id')
    if (type(binding.dimension_count) is not int or binding.dimension_count != 2
            or type(binding.resource_count) is not int or binding.resource_count != 3
            or type(attributes) is not tuple or len(attributes) != 6
            or any(type(a) is not BoundCatalogAttribute for a in attributes)): _fail('attribute_shape')
    if tuple(a.type_token for a in attributes) not in (('#','N','N','B','D','S'),('N','#','D','B','N','S')): _fail('attribute_type')
    for i,a in enumerate(attributes):
        if a.type_token == 'N' and a.qualifiers != (9,0 if i < 2 else 2,0): _fail('qualifiers')
        if a.type_token == 'S' and a.qualifiers != (32,1): _fail('qualifiers')
        if a.type_token == '#' and a.reference_catalog_uuid == binding.metadata_uuid: _fail('attribute_type')
    fake=SimpleNamespace(metadata_uuid=binding.metadata_uuid,name=binding.name,code_type=1,code_length=2,description_length=8)
    declarations,placements,_=_linked_layout(fake,attributes,CatalogBindingLimits(
        max_dbnames_entries=limits.max_dbnames_entries,max_string_length=limits.max_string_length,
        max_numeric_precision=limits.max_numeric_precision))
    if any(int(a.physical_name[4:].removesuffix('RREF')) == binding.register_id for a in attributes): _fail('dbnames_collision')
    declarations=declarations[6:]; widths=tuple(p.width for p in placements[6:])
    size=1+sum(widths)
    if size > limits.max_record_bytes: _fail('record_bytes')
    result=[];offset=1
    for d,w in zip(declarations,widths):
        result.append(BoundFieldPlacement(d,offset,w));offset+=w
    return declarations,tuple(result),size


def compile_information_register_binding(identity, dimensions, resources, attributes, dbnames, *, budget, limits=None):
    if (type(identity) is not InformationRegisterIdentityPrefix
            or any(type(x) is not CatalogAttributes for x in (dimensions,resources,attributes))
            or type(dbnames) is not DBNamesIndex): _fail('input_type')
    if limits is not None and type(limits) is not CatalogBindingLimits: _fail('limits')
    limits=limits if limits is not None else CatalogBindingLimits();CatalogBindingLimits.__post_init__(limits)
    if type(identity.periodicity) is not int or identity.periodicity != 0 or type(identity.write_mode) is not int or identity.write_mode != 0: _fail('standard_profile')
    if not _uuid(identity.metadata_uuid): _fail('identity')
    _name(identity.name)
    if (type(dbnames.entries) is not tuple or len(dbnames.entries)>limits.max_dbnames_entries
            or type(dbnames.declared_count) is not int or dbnames.declared_count!=len(dbnames.entries)
            or type(dbnames.profile) is not str or dbnames.profile!=DBNAMES_PROFILE_IDENTIFIER): _fail('dbnames_shape')
    for group,n in ((dimensions,2),(resources,3),(attributes,1)):
        if type(group.attributes) is not tuple or len(group.attributes)!=n: _fail('attribute_shape')
    attrs=dimensions.attributes+resources.attributes+attributes.attributes
    targets={identity.metadata_uuid:('InfoRg',)}
    for i,a in enumerate(attrs):
        if type(a) is not CatalogAttribute or not _uuid(a.metadata_uuid) or a.metadata_uuid in targets: _fail('attribute_identity')
        targets[a.metadata_uuid]=('Fld','ByDims') if i<2 else ('Fld',)
    budget.charge('output_bytes',16384);budget.charge('bytes_processed',8192+2048*len(dbnames.entries));budget.charge('tokens',256+24*len(dbnames.entries))
    chosen={}
    for ordinal,e in enumerate(dbnames.entries):
        if (type(e) is not DBNamesEntry or not _uuid(e.uuid,nonzero=False) or type(e.kind) is not str or len(e.kind)>32 or _KIND.fullmatch(e.kind) is None
                or type(e.id) is not int or not 0<=e.id<=2147483647 or type(e.ordinal) is not int or e.ordinal!=ordinal): _fail('dbnames_entry')
        if e.uuid in targets:
            if e.kind not in targets[e.uuid]: _fail('dbnames_kind')
            key=(e.uuid,e.kind)
            if key in chosen: _fail('dbnames_ambiguous')
            if not e.id: _fail('dbnames_id')
            chosen[key]=e
    required={(identity.metadata_uuid,'InfoRg')}|{(a.metadata_uuid,'Fld') for a in attrs}
    if not required <= chosen.keys(): _fail('dbnames_missing')
    # ByDims is an auxiliary index identity, NOT a second value field. Only the
    # measured reference-dimension auxiliary entry is admitted; never global
    # UUID uniqueness (repeat 2 has Fld and ByDims for the same dimension).
    auxiliaries=[e for (u,k),e in chosen.items() if k=='ByDims']
    if len(auxiliaries)>1 or any(e.uuid not in {a.metadata_uuid for a in dimensions.attributes if a.type_token=='#'} for e in auxiliaries): _fail('dbnames_kind')
    if len({e.id for e in chosen.values()}) != len(chosen): _fail('dbnames_collision')
    selected_roles={(e.kind,e.id):e for e in chosen.values()}
    for e in dbnames.entries:
        if (e.kind,e.id) in selected_roles and e is not selected_roles[e.kind,e.id]: _fail('dbnames_collision')
    bound=tuple(BoundCatalogAttribute(a.metadata_uuid,a.name,'_FLD'+str(chosen[a.metadata_uuid,'Fld'].id)+('RREF' if a.type_token=='#' else ''),a.type_token,a.qualifiers,
        reference_type_uuid=a.reference_type_uuid,reference_catalog_uuid=a.reference_catalog_uuid) for a in attrs)
    register_id=chosen[identity.metadata_uuid,'InfoRg'].id
    facts=SimpleNamespace(metadata_uuid=identity.metadata_uuid,name=identity.name,register_id=register_id,dimension_count=2,resource_count=3)
    ds,ps,size=_layout(facts,bound,limits)
    return InformationRegisterBinding(identity.metadata_uuid,identity.name,register_id,'_InfoRg'+str(register_id),ds,bound,'0',0,size,ps)
