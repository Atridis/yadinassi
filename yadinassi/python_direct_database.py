"""Direct public catalog protocol over one host-selected database.

No arbitrary getattr, no backend access and no replacement for writer validation.
"""
from .experimental_naked_boundaries import BoundaryViolation
from .catalogs import BSLCatalogs, BSLCatalogManager, BSLCatalogObject, BSLCatalogSelection
from .catalog_types import BSLCatalogReference
from .catalog_sections import BSLCatalogSection, BSLCatalogSectionRow
from .documents import BSLDocuments, BSLDocumentManager, BSLDocumentObject
from .document_types import BSLDocumentReference
from .document_lines import BSLDocumentLines, BSLDocumentLine
from .enumerations import BSLEnumerations, BSLEnumManager
from .enum_types import BSLEnumReference
from .document_posting_values import DOCUMENT_WRITE_MODES
from .structures import BSLStructure, BSLFixedStructure
from .values import HostFunction
from .queries import BSLQuery, BSLQueryResult, BSLQueryResultSelection

NAMES=('catalogs','справочники','documents','документы','enums','перечисления','documentwritemode','режимзаписидокумента')

class CatalogBoundary:
    def _catalog_owner(self, value):
        self._check()
        root=self.vm._catalogs
        kind=type(value)
        if value is DOCUMENT_WRITE_MODES:return
        if kind is BSLDocuments: owner=value._catalogs
        elif kind is BSLDocumentManager: owner=value._catalogs
        elif kind is BSLDocumentObject: owner=value._manager._catalogs
        elif kind is BSLDocumentLines: owner=value._owner._manager._catalogs
        elif kind is BSLDocumentLine: owner=value._section._owner._manager._catalogs
        elif kind is BSLDocumentReference:
            if value.value_type.snapshot is self.vm._documents._metadata:return
            owner=None
        elif kind is BSLEnumerations:
            if value is self.vm._metadata._enumerations:return
            owner=None
        elif kind in (BSLEnumManager,BSLEnumReference):
            enum_type=value._value_type if kind is BSLEnumManager else value.value_type
            enums=self.vm._metadata._enumerations
            if enums is not None and enum_type.snapshot is enums.metadata:return
            owner=None
        elif kind is BSLQuery: owner=value._catalogs
        elif kind in (BSLQueryResult, BSLQueryResultSelection, BSLStructure, BSLFixedStructure):
            # Detached result data: these public methods cannot execute queries
            # or write. Returned references still require the current root.
            return
        elif kind is BSLCatalogs: owner=value
        elif kind is BSLCatalogManager: owner=value._catalogs
        elif kind in (BSLCatalogObject, BSLCatalogSelection): owner=value._manager._catalogs
        elif kind is BSLCatalogSection: owner=value._owner._manager._catalogs
        elif kind is BSLCatalogSectionRow: owner=value._section._owner._manager._catalogs
        elif kind is BSLCatalogReference:
            if value.value_type.snapshot is root._metadata:return
            owner=None
        else: owner=None
        if owner is not root:
            raise BoundaryViolation('unregistered or foreign database receiver')

    def resolve_service(self,name,*args,**kwargs):
        if name.casefold() in ('new:query','new:запрос'):
            self._check()
            function=self.vm.types.get(name.split(':',1)[1].casefold())
            if type(function) is not HostFunction:
                raise BoundaryViolation('query constructor requires canonical registration')
            return super().resolve_callable(function)
        return super().resolve_service(name,*args,**kwargs)

    def external_get(self,name):
        self._check()
        if name in ('catalogs','справочники'):return self.vm._catalogs
        if name in ('documents','документы'):return self.vm._documents
        if name in ('enums','перечисления'):
            if self.vm._metadata._enumerations is None:raise ValueError('enumerations require an active configuration application')
            return self.vm._metadata._enumerations
        if name in ('documentwritemode','режимзаписидокумента'):
            if self.vm._documents.posting_runtime() is None:raise ValueError('posting profile required')
            return DOCUMENT_WRITE_MODES
        return super().external_get(name)

    def external_set(self,name,value):
        self._check()
        raise ValueError('catalog namespace is read-only')

    def get_member(self,value,name):
        self._catalog_owner(value)
        try:return value.get_member(name)
        finally:self._check()

    def resolve_set_member(self,value,name):
        self._catalog_owner(value)
        def write(new_value):
            self._catalog_owner(value)
            try:value.set_member(name,new_value)
            finally:self._check()
        return write

    def resolve_member(self,value,name):
        self._catalog_owner(value)
        if name=='__getitem__': function=lambda index:value.get_index(index)
        elif name=='__setitem__': function=lambda index,new:value.set_index(index,new)
        elif name=='__iter__':
            raise BoundaryViolation('direct database iterator not connected')
        else:
            function=value.get_method(name)
            if type(function) is not HostFunction:
                raise BoundaryViolation('database method requires canonical HostFunction')
        self._check()
        def invoke(*args):
            self._catalog_owner(value)
            try:return function(*args)
            finally:self._check()
        return invoke
