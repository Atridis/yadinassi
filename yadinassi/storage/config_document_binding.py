"""Measured Document binding: native 41256261065, report a879485a6ae04dccc62e59faf84c41704a71a1c890578a1b48246769ed6331e0.

Only String8 nonperiodical numbers and the two measured five-attribute orders.
No XML/physical descriptor is an input to the binding compiler.
"""
from dataclasses import dataclass
from types import SimpleNamespace
from .config_catalog_binding import (BoundCatalogAttribute, BoundFieldPlacement,
    CatalogBindingLimits, CatalogBindingError, _fail, _uuid, _name, _KIND, _linked_layout)
from .config_catalog_attributes import CatalogAttribute, CatalogAttributes
from .filedb_dbnames import DBNamesEntry, DBNamesIndex, DBNAMES_PROFILE_IDENTIFIER
from .config_document_metadata import DocumentIdentityPrefix

PROFILE_IDENTIFIER = 'owned_document_string8_linked_v1'

@dataclass(frozen=True, slots=True)
class DocumentBinding:
    metadata_uuid: str
    name: str
    table_name: str
    declarations: tuple
    attributes: tuple
    recordlock: str
    format_item: int
    record_size: int
    placements: tuple
    number_type: int = 1
    number_length: int = 8
    number_periodicity: int = 0
    profile_identifier: str = PROFILE_IDENTIFIER


def _layout(identity, attributes, limits):
    if (type(identity.number_type) is not int or identity.number_type!=1
        or type(identity.number_length) is not int or identity.number_length!=8
        or type(identity.number_periodicity) is not int or identity.number_periodicity!=0):
        _fail('standard_profile')
    if type(attributes) is not tuple or len(attributes)!=5: _fail('attribute_shape')
    if any(type(a) is not BoundCatalogAttribute for a in attributes): _fail('attribute_shape')
    kinds=tuple(a.type_token for a in attributes)
    if kinds not in (('S','N','B','D','#'),('#','D','B','N','S')): _fail('attribute_type')
    for a in attributes:
        if a.type_token=='S' and a.qualifiers!=(32,1): _fail('qualifiers')
        if a.type_token=='N' and a.qualifiers!=(9,2,0): _fail('qualifiers')
    # Reuse only measured primitive qualifier/reference/identity checks. Catalog
    # standard declarations are discarded, never admitted for Document tables.
    fake=SimpleNamespace(metadata_uuid=identity.metadata_uuid,name=identity.name,
                         code_type=1,code_length=2,description_length=8)
    ds,ps,_=_linked_layout(fake,attributes,CatalogBindingLimits(
        max_dbnames_entries=limits.max_dbnames_entries,
        max_string_length=limits.max_string_length,
        max_numeric_precision=limits.max_numeric_precision))
    declarations=(('_IDRREF','B',0,16,0,'CS'),('_VERSION','RV',0,0,0,'CS'),
        ('_MARKED','L',0,0,0,'CS'),('_DATE_TIME','DT',0,0,0,'CS'),
        ('_NUMBER','NVC',0,8,0,'CI'),('_POSTED','L',0,0,0,'CS'))+ds[6:]
    widths=(16,16,1,7,18,1)+tuple(x.width for x in ps[6:])
    size=1+sum(widths)
    if size>limits.max_record_bytes: _fail('record_bytes')
    offsets=[0]*len(widths);cursor=1
    for i in (1,0,*range(2,len(widths))): offsets[i]=cursor;cursor+=widths[i]
    return declarations,tuple(BoundFieldPlacement(d,offsets[i],widths[i]) for i,d in enumerate(declarations)),size


def compile_document_binding(identity, attributes, dbnames, *, budget, limits=None):
    if type(identity) is not DocumentIdentityPrefix or type(attributes) is not CatalogAttributes or type(dbnames) is not DBNamesIndex: _fail('input_type')
    if limits is not None and type(limits) is not CatalogBindingLimits: _fail('limits')
    limits=limits if limits is not None else CatalogBindingLimits()
    CatalogBindingLimits.__post_init__(limits)
    if (type(dbnames.entries) is not tuple or len(dbnames.entries)>limits.max_dbnames_entries
        or type(dbnames.declared_count) is not int or dbnames.declared_count!=len(dbnames.entries)
        or type(dbnames.profile) is not str or dbnames.profile!=DBNAMES_PROFILE_IDENTIFIER): _fail('dbnames_shape')
    if type(attributes.attributes) is not tuple or len(attributes.attributes)!=5: _fail('attribute_shape')
    budget.charge('output_bytes',16384)
    budget.charge('bytes_processed',8192+2048*len(dbnames.entries))
    budget.charge('tokens',256+24*len(dbnames.entries))
    if not _uuid(identity.metadata_uuid): _fail('identity')
    targets=[identity.metadata_uuid]
    for a in attributes.attributes:
        if type(a) is not CatalogAttribute or not _uuid(a.metadata_uuid): _fail('attribute_identity')
        targets.append(a.metadata_uuid)
    if len(set(targets))!=len(targets): _fail('attribute_identity')
    chosen={}
    for ordinal,e in enumerate(dbnames.entries):
        if (type(e) is not DBNamesEntry or not _uuid(e.uuid,nonzero=False)
                or type(e.kind) is not str or len(e.kind)>32 or _KIND.fullmatch(e.kind) is None
                or type(e.id) is not int or not 0<=e.id<=2147483647
                or type(e.ordinal) is not int or e.ordinal!=ordinal): _fail('dbnames_entry')
        if e.uuid in targets:
            if e.uuid in chosen: _fail('dbnames_ambiguous')
            if e.kind!=('Document' if e.uuid==identity.metadata_uuid else 'Fld'): _fail('dbnames_kind')
            if e.id==0: _fail('dbnames_id')
            chosen[e.uuid]=e
    if len(chosen)!=len(targets): _fail('dbnames_missing')
    if len({e.id for e in chosen.values()})!=len(targets): _fail('dbnames_collision')
    for e in dbnames.entries:
        for c in chosen.values():
            if e is not c and e.kind==c.kind and e.id==c.id: _fail('dbnames_collision')
    bound=tuple(BoundCatalogAttribute(a.metadata_uuid,a.name,'_FLD'+str(chosen[a.metadata_uuid].id)+('RREF' if a.type_token=='#' else ''),a.type_token,a.qualifiers,reference_type_uuid=a.reference_type_uuid,reference_catalog_uuid=a.reference_catalog_uuid) for a in attributes.attributes)
    declarations,placements,size=_layout(identity,bound,limits)
    return DocumentBinding(identity.metadata_uuid,identity.name,'_Document'+str(chosen[identity.metadata_uuid].id),declarations,bound,'0',0,size,placements)
