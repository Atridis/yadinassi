"""Native-measured Items binding (41263661105); no physical/XML inputs."""
from dataclasses import dataclass
from types import SimpleNamespace
from .config_catalog_binding import (BoundCatalogAttribute, BoundFieldPlacement,
    CatalogBindingLimits, CatalogBindingError, _fail, _uuid, _name, _KIND, _linked_layout)
from .config_catalog_attributes import CatalogAttribute, CatalogAttributes
from .config_document_metadata import DocumentIdentityPrefix
from .filedb_dbnames import DBNamesEntry, DBNamesIndex, DBNAMES_PROFILE_IDENTIFIER

PROFILE_IDENTIFIER='owned_document_items_v1'

@dataclass(frozen=True, slots=True)
class DocumentLinesBinding:
    owner_metadata_uuid: str
    metadata_uuid: str
    name: str
    document_id: int
    section_id: int
    line_number_id: int
    table_name: str
    declarations: tuple
    attributes: tuple
    recordlock: str
    format_item: int
    record_size: int
    placements: tuple
    profile_identifier: str = PROFILE_IDENTIFIER


def _layout(binding,attributes,limits):
    if not _uuid(binding.owner_metadata_uuid) or not _uuid(binding.metadata_uuid) or binding.owner_metadata_uuid==binding.metadata_uuid:_fail('identity')
    _name(binding.name)
    ids=(binding.document_id,binding.section_id,binding.line_number_id)
    if any(type(n) is not int or not 1<=n<=2147483647 for n in ids) or len(set(ids))!=3:_fail('dbnames_id')
    if type(attributes) is not tuple or len(attributes)!=5 or any(type(a) is not BoundCatalogAttribute for a in attributes):_fail('attribute_shape')
    if tuple(a.type_token for a in attributes) not in (('#','N','N','N','S'),('S','N','N','N','#')):_fail('attribute_type')
    for a in attributes:
        if a.metadata_uuid==binding.owner_metadata_uuid:_fail('attribute_identity')
        if a.type_token=='S' and a.qualifiers!=(32,1):_fail('qualifiers')
        if a.type_token=='N' and a.qualifiers!=(9,2,0):_fail('qualifiers')
    fake=SimpleNamespace(metadata_uuid=binding.metadata_uuid,name=binding.name,code_type=1,code_length=2,description_length=8)
    ds,ps,_=_linked_layout(fake,attributes,CatalogBindingLimits(max_dbnames_entries=limits.max_dbnames_entries,
        max_string_length=limits.max_string_length,max_numeric_precision=limits.max_numeric_precision))
    if any(int(a.physical_name[4:].removesuffix('RREF')) in ids for a in attributes):_fail('dbnames_collision')
    declarations=(('_DOCUMENT'+str(binding.document_id)+'_IDRREF','B',0,16,0,'CS'),
        ('_KEYFIELD','B',0,4,0,'CS'),('_LINENO'+str(binding.line_number_id),'N',0,5,0,'CS'))+ds[6:]
    widths=(16,4,3)+tuple(p.width for p in ps[6:]);size=1+sum(widths)
    if size>limits.max_record_bytes:_fail('record_bytes')
    placements=[];offset=1
    for d,w in zip(declarations,widths):placements.append(BoundFieldPlacement(d,offset,w));offset+=w
    return declarations,tuple(placements),size


def compile_document_lines_binding(identity,section_uuid,section_name,attributes,dbnames,*,budget,limits=None):
    if type(identity) is not DocumentIdentityPrefix or type(attributes) is not CatalogAttributes or type(dbnames) is not DBNamesIndex:_fail('input_type')
    if limits is not None and type(limits) is not CatalogBindingLimits:_fail('limits')
    limits=limits if limits is not None else CatalogBindingLimits();CatalogBindingLimits.__post_init__(limits)
    if (type(identity.number_type) is not int or identity.number_type!=1 or type(identity.number_length) is not int or identity.number_length!=8
        or type(identity.number_periodicity) is not int or identity.number_periodicity!=0):_fail('standard_profile')
    if not _uuid(identity.metadata_uuid) or not _uuid(section_uuid):_fail('identity')
    _name(identity.name);_name(section_name)
    if (type(dbnames.entries) is not tuple or len(dbnames.entries)>limits.max_dbnames_entries or type(dbnames.declared_count) is not int
        or dbnames.declared_count!=len(dbnames.entries) or type(dbnames.profile) is not str or dbnames.profile!=DBNAMES_PROFILE_IDENTIFIER):_fail('dbnames_shape')
    if type(attributes.attributes) is not tuple or len(attributes.attributes)!=5:_fail('attribute_shape')
    budget.charge('output_bytes',16384);budget.charge('bytes_processed',8192+2048*len(dbnames.entries));budget.charge('tokens',256+24*len(dbnames.entries))
    targets={identity.metadata_uuid:('Document',),section_uuid:('VT','LineNo')}
    if len(targets)!=2:_fail('identity')
    for a in attributes.attributes:
        if type(a) is not CatalogAttribute or not _uuid(a.metadata_uuid) or a.metadata_uuid in targets:_fail('attribute_identity')
        targets[a.metadata_uuid]=('Fld',)
    chosen={}
    for ordinal,e in enumerate(dbnames.entries):
        if (type(e) is not DBNamesEntry or not _uuid(e.uuid,nonzero=False) or type(e.kind) is not str or len(e.kind)>32 or _KIND.fullmatch(e.kind) is None
            or type(e.id) is not int or not 0<=e.id<=2147483647 or type(e.ordinal) is not int or e.ordinal!=ordinal):_fail('dbnames_entry')
        if e.uuid in targets:
            if e.kind not in targets[e.uuid]:_fail('dbnames_kind')
            key=(e.uuid,e.kind)
            if key in chosen:_fail('dbnames_ambiguous')
            if not e.id:_fail('dbnames_id')
            chosen[key]=e
    if len(chosen)!=8:_fail('dbnames_missing')
    if len({e.id for e in chosen.values()})!=8:_fail('dbnames_collision')
    for e in dbnames.entries:
        for selected in chosen.values():
            if e is not selected and (e.kind,e.id)==(selected.kind,selected.id):_fail('dbnames_collision')
    bound=tuple(BoundCatalogAttribute(a.metadata_uuid,a.name,'_FLD'+str(chosen[a.metadata_uuid,'Fld'].id)+('RREF' if a.type_token=='#' else ''),a.type_token,a.qualifiers,
        reference_type_uuid=a.reference_type_uuid,reference_catalog_uuid=a.reference_catalog_uuid) for a in attributes.attributes)
    doc=chosen[identity.metadata_uuid,'Document'].id;section=chosen[section_uuid,'VT'].id;line=chosen[section_uuid,'LineNo'].id
    facts=SimpleNamespace(owner_metadata_uuid=identity.metadata_uuid,metadata_uuid=section_uuid,name=section_name,document_id=doc,section_id=section,line_number_id=line)
    ds,ps,size=_layout(facts,bound,limits)
    return DocumentLinesBinding(identity.metadata_uuid,section_uuid,section_name,doc,section,line,'_Document'+str(doc)+'_VT'+str(section),ds,bound,'0',0,size,ps)
