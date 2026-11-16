"""Source-owned enum report domains; no inventory grant or backend read lease."""
from dataclasses import dataclass,replace
import weakref
from uuid import UUID
from .enum_types import BSLEnumReference,BSLEnumType


@dataclass(frozen=True,slots=True,eq=False)
class SourceEnumBinding:
    ownerapp: object
    collection: object
    value_type: object
    identity: tuple
    kind: str = 'enum_ref'

    def require_owner(self):
        from .configuration_source_runtime import SourceApplication
        from .enumerations import BSLEnumerations,BSLEnumManager
        from .source_constant_store import SourceConstantStore
        from .source_catalog_store import SourceCatalogStore
        from .source_document_store import SourceDocumentStore
        from .source_document_section_store import SourceDocumentSectionStore
        if type(self.ownerapp) is not weakref.ReferenceType:raise TypeError('Source enum requires owner')
        app=self.ownerapp()
        if type(app) is not SourceApplication:raise ValueError('Source enum application is closed')
        app.require_open()
        if (self.collection is not app.interpreter._catalogs or type(self.kind) is not str or self.kind!='enum_ref'
                or type(app.enumerations) is not BSLEnumerations
                or type(app.constant_store) not in (SourceConstantStore,SourceCatalogStore,SourceDocumentStore,SourceDocumentSectionStore)
                or app.constant_store._closed or type(self.value_type) is not BSLEnumType):
            raise TypeError('Invalid source enum query owner')
        manager=app.enumerations.get_index(self.value_type.name)
        if (type(manager) is not BSLEnumManager or manager._value_type is not self.value_type
                or type(self.identity) is not tuple or len(self.identity)!=2
                or self.identity[0] is not self.value_type.snapshot
                or type(self.identity[1]) is not UUID or self.identity[1]!=self.value_type.metadata_uuid):
            raise TypeError('Source enum requires canonical metadata')
        return app,manager

    def require_context(self,catalogs,documents):
        if catalogs is not self.collection:raise TypeError('Foreign source enum query context')
        self.require_owner()

    def value(self,value):
        _,manager=self.require_owner()
        if type(value) is not BSLEnumReference or not any(value is v for v in (manager._empty,*manager._values)):
            raise TypeError('Source enum query requires canonical owned value')
        return value

    def descriptor(self,scope):
        if type(scope) is not SourceEnumScope:raise TypeError('Source enum requires source scope')
        self.require_context(scope.catalogs,None)
        if self.ownerapp() is not scope.app:raise TypeError('Foreign source enum scope')
        return scope.descriptor(self.value_type.metadata_uuid)


@dataclass(frozen=True,slots=True,eq=False)
class _Descriptor:
    scope: object
    value_type: object


class SourceEnumScope:
    def __init__(self,app,catalogs):
        self.app,self.catalogs=app,catalogs
        self.binding=self
        self._descriptors={};self._retired=False;self.condition_budget=[0,0]
        self.require_current()

    def require_current(self):
        from .configuration_source_runtime import SourceApplication
        if self._retired or type(self.app) is not SourceApplication:raise ValueError('Source enum scope closed')
        self.app.require_open()
        if self.catalogs is not self.app.interpreter._catalogs:raise TypeError('Foreign source enum scope')

    def descriptor(self,enum_id):
        self.require_current()
        if type(enum_id) is not UUID:raise TypeError('Enum identity requires UUID')
        manager=next((m for m in self.app.enumerations._managers.values() if m._value_type.metadata_uuid==enum_id),None)
        if manager is None:raise ValueError('Unknown source enum identity')
        typ=manager._value_type
        descriptor=self._descriptors.get(id(typ))
        if descriptor is None:
            descriptor=_Descriptor(self,typ);self._descriptors[id(typ)]=descriptor
        self.domain(descriptor).require_owner()
        return descriptor

    def require_descriptor(self,descriptor):
        self.require_current()
        if (type(descriptor) is not _Descriptor or descriptor.scope is not self
                or self._descriptors.get(id(descriptor.value_type)) is not descriptor):
            raise TypeError('Foreign or forged source enum descriptor')
        self.domain(descriptor).require_owner()
        return descriptor

    def domain(self,descriptor):
        typ=descriptor.value_type
        return SourceEnumBinding(weakref.ref(self.app),self.catalogs,typ,(typ.snapshot,typ.metadata_uuid))

    def value_type(self,enum_id):return self.descriptor(enum_id).value_type
    def owned_key(self,value):
        if type(value) is not BSLEnumReference:raise TypeError('Source enum value required')
        descriptor=self.descriptor(value.value_type.metadata_uuid)
        self.domain(descriptor).value(value)
        return value
    def value_descriptor(self,value):
        self.owned_key(value);return self.descriptor(value.value_type.metadata_uuid)
    def require_same(self,descriptors):
        if type(descriptors) is not tuple or not descriptors:raise TypeError('Enum descriptors required')
        first=self.require_descriptor(descriptors[0])
        if any(self.require_descriptor(d) is not first for d in descriptors):raise TypeError('Mixed enum query domains')
        return first
    def validate_frozen_parameters(self,parameters):
        from .relational_queries import snapshot_parameters,_ParameterList
        from .source_query_references import make_binding
        from .catalog_types import BSLCatalogReference
        from .document_types import BSLDocumentReference
        self.require_current()
        frozen=snapshot_parameters(parameters)
        for value in frozen.values():
            for item in (value.values if type(value) is _ParameterList else (value,)):
                if type(item) is BSLEnumReference:self.owned_key(item)
                elif type(item) in (BSLCatalogReference,BSLDocumentReference):
                    family='Catalog' if type(item) is BSLCatalogReference else 'Document'
                    make_binding(self.app,self.catalogs,item.value_type.name,family).value(item)
        return frozen
    def require_query(self,query):
        from . import query_parser as syntax
        self.require_current()
        for node in syntax.walk_nodes((query,)):
            if type(node) in (syntax.Select,syntax.Source) and node.derived is None and not (node.external or node.temporary):
                raise ValueError('Source enum reports cannot acquire legacy persistent sources')
    def prepare_tables(self,tables):
        from .query_packages import _Table
        from .values import NULL
        result={}
        for name,table in tables.items():
            columns=[]
            for index,column in enumerate(table.columns):
                if column.kind=='enum_ref':
                    domain=column.reference_binding
                    if type(domain) is not SourceEnumBinding:raise TypeError('Source report rejects legacy enum domain')
                    descriptor=domain.descriptor(self)
                    for row in table.rows:
                        if row[index] is not NULL:domain.value(row[index])
                    column=replace(column,enum_descriptor=descriptor)
                columns.append(column)
            result[name]=_Table(tuple(columns),table.rows)
        return result
