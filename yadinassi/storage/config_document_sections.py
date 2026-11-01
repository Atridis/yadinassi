"""Bounded Document tabular-section CONFIG projection, native 41263661105.

Only zero/one section, String32/Number9.2/fixed-reference column profile is
measured. This is CONFIG identity, never an XML or physical-offset input.
"""
from dataclasses import dataclass
from . import config_catalog_attributes as a
from .config_catalog_name import _IdentityCursor,CatalogNameError

COLLECTION_UUID='21c53e09-8950-4b5e-a6a0-1054f1bbc274'
COLUMN_UUID='888744e1-b616-11d4-9436-004095e12fc7'

@dataclass(frozen=True,slots=True)
class DocumentSection:
    metadata_uuid: str
    name: str
    type_uuid: str
    value_uuid: str
    row_type_uuid: str
    row_value_uuid: str
    line_number_length: int
    attributes: tuple


class _Sections(a._Walk):
    def __init__(self,data,budget,limits):
        super().__init__(data,budget,limits,linked=True)
        self.section_count=None;self.section={};self.sections=[];self.columns_done=False
    def kind(self,path):
        if path==(3,):return 'object'
        if path==(3,0):return 'sections_uuid'
        if path==(3,1):return 'sections_count'
        if path[:2]!=(3,2):return 'opaque'
        if self.section_count!=1:raise a.CatalogAttributeError('collection_count')
        tail=path[2:]
        routes={(0,0):'section_version',(0,1,0):'section_header',
            (0,1,1):'type_uuid',(0,1,2):'value_uuid',(0,1,3):'row_type_uuid',(0,1,4):'row_value_uuid',
            (0,1,5,1,1,2):'metadata_uuid',(0,1,5,1,2):'section_name',(0,2):'line_length',
            (1,):'section_children'}
        if tail in routes:return routes[tail]
        if tail[:1]==(2,):return super().kind((6,)+tail[1:])
        if any(route[:len(tail)]==tail for route in routes):return 'object'
        return 'opaque'
    def value(self,path,kind):
        if kind in ('sections_uuid','collection_uuid'):
            if _IdentityCursor.uuid(self)!=(COLLECTION_UUID if kind=='sections_uuid' else COLUMN_UUID):
                raise a.CatalogAttributeError('collection_uuid')
        elif kind=='sections_count':
            self.section_count=self.integer(1)
        elif kind in ('type_uuid','value_uuid','row_type_uuid','row_value_uuid','metadata_uuid'):
            self.section[kind]=_IdentityCursor.uuid(self)
        elif kind=='section_name':
            if self.peek()!=34:raise a.CatalogAttributeError('expected_scalar')
            self.section['name']=self.scalar(True)
        elif kind in ('section_version','section_header','line_length','section_children'):
            expected={'section_version':2,'section_header':11,'line_length':5,'section_children':1}[kind]
            if self.integer(expected)!=expected:raise a.CatalogAttributeError('type_unsupported')
            if kind=='line_length':self.section['line_number_length']=5
        else:super().value(path,kind)
    def close(self,path,children):
        if path[:3]==(3,2,2):
            done=super().close((6,)+path[3:],children)
            if done:self.columns_done=True
            return False
        if path==(3,2):
            if children!=3 or not self.columns_done or set(self.section)!={'metadata_uuid','name','type_uuid','value_uuid','row_type_uuid','row_value_uuid','line_number_length'}:
                raise a.CatalogAttributeError('missing_field')
            if len(self.rows)!=5:raise a.CatalogAttributeError('attribute_limit')
            kinds=tuple((x.type_token,x.qualifiers) for x in self.rows)
            profile=(('#',()),('N',(9,2,0)),('N',(9,2,0)),('N',(9,2,0)),('S',(32,1)))
            if kinds not in (profile,tuple(reversed(profile))):raise a.CatalogAttributeError('type_unsupported')
            ids=[self.section[k] for k in ('metadata_uuid','type_uuid','value_uuid','row_type_uuid','row_value_uuid')]+[x.metadata_uuid for x in self.rows]
            if len(set(ids))!=len(ids):raise a.CatalogAttributeError('duplicate_uuid')
            if len({x.name.casefold() for x in self.rows})!=5:raise a.CatalogAttributeError('duplicate_name')
            self.sections.append(DocumentSection(**self.section,attributes=tuple(self.rows)))
        if path==(3,):
            if self.section_count is None or children!=self.section_count+2 or len(self.sections)!=self.section_count:
                raise a.CatalogAttributeError('collection_count')
            return True
        return False


def project_document_sections(data,*,budget):
    if type(data) is not bytes:raise a.CatalogAttributeError('input_type')
    limits=a.CatalogAttributeLimits()
    if len(data)>limits.max_input_bytes:raise a.CatalogAttributeError('input_bytes')
    budget.charge('bytes_processed',8*len(data));budget.charge('output_bytes',a.OUTPUT_RESERVATION)
    try:
        walk=_Sections(data,budget,limits);walk.run();return tuple(walk.sections)
    except CatalogNameError as error:raise a.CatalogAttributeError(error.code) from None
    # !todo Multiple sections, composite columns and different qualifiers need
    # separate bounded evidence; unknown profiles remain refused.
