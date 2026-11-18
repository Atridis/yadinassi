"""Direct public catalog protocol over one host-selected database.

No arbitrary getattr, no backend access and no replacement for writer validation.
"""
from .experimental_naked_boundaries import BoundaryViolation
from . import python_direct_movements as movements
from .catalogs import BSLCatalogs, BSLCatalogManager, BSLCatalogObject, BSLCatalogSelection
from .catalog_types import BSLCatalogReference
from .catalog_sections import BSLCatalogSection, BSLCatalogSectionRow
from .documents import BSLDocuments, BSLDocumentManager, BSLDocumentObject
from .document_types import BSLDocumentReference
from .document_lines import BSLDocumentLines, BSLDocumentLine
from .enumerations import BSLEnumerations, BSLEnumManager
from .enum_types import BSLEnumReference
from .document_posting_values import DOCUMENT_WRITE_MODES
from .structures import BSLStructure, BSLFixedStructure, BSLKeyAndValue
from .values import HostFunction, BSLArray, BSLFixedArray
from decimal import Decimal
from .regex_functions import BSLRegexResult, BSLRegexGroup
from .file_io import BSLFile, BSLBinaryData
from .http_client import BSLHTTPConnection, BSLHTTPRequest, BSLHTTPResponse
from .binary_streams import BSLBinaryDataBuffer, BSLMemoryStream, BSLStream
from .maps import BSLMap, BSLFixedMap
from .value_lists import BSLValueList, BSLValueListItem
from .json_processing import BSLJSONReader, BSLJSONWriter, BSLJSONWriterSettings
from .python_direct_names import NAMES as SYSTEM_NAMES, VALUE_IDS as SYSTEM_VALUE_IDS, ITERABLES
from .metadata import BSLMetadata, BSLCatalogMetadataCollection, BSLCatalogMetadata
from .queries import BSLQuery, BSLQueryResult, BSLQueryResultSelection
from .value_tables import (BSLValueTable, BSLValueTableRow, BSLCollectionIndex, BSLCollectionIndexes,
                           BSLValueTableColumn, BSLValueTableColumnCollection, _DIRECT_ITERATION_TYPES)
_CALL_TABLE, _CALL_COLUMNS, _CALL_ROW, _ = _DIRECT_ITERATION_TYPES
from .type_descriptions import BSLTypeDescription
from .type_qualifiers import (BSLNumberQualifiers, BSLStringQualifiers,
                              BSLDateQualifiers, BSLBinaryDataQualifiers)

NAMES=('metadata','метаданные','catalogs','справочники','documents','документы','enums','перечисления','documentwritemode','режимзаписидокумента','accumulationrecordtype','виддвижениянакопления')

# Canonical detached receivers only; child rows/items and database owners still
# traverse live ownership validation. Public protocols retain resource guards.
_DETACHED_TYPES=(BSLValueList, BSLValueTable, BSLTypeDescription, BSLNumberQualifiers, BSLStringQualifiers, BSLDateQualifiers, BSLBinaryDataQualifiers, BSLQueryResult, BSLQueryResultSelection, BSLStructure, BSLFixedStructure, BSLKeyAndValue, BSLArray, BSLFixedArray, BSLFixedMap, BSLRegexResult, BSLRegexGroup, BSLFile, BSLBinaryData, BSLHTTPConnection, BSLHTTPRequest, BSLHTTPResponse, BSLBinaryDataBuffer, BSLMemoryStream, BSLStream, BSLMap, BSLJSONReader, BSLJSONWriter, BSLJSONWriterSettings)
_DETACHED_TYPE_IDS=frozenset(map(id,_DETACHED_TYPES))

class CatalogBoundary:
    def _catalog_owner(self, value):
        self._check()
        if movements.owns(value):
            movements.check(self,value);return
        if value is movements.NAMESPACE:
            movements.namespace(self);return
        if id(value) in SYSTEM_VALUE_IDS:return
        root=self.vm._catalogs
        kind=type(value)
        if id(kind) in _DETACHED_TYPE_IDS:return
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
        elif kind in (BSLValueTableRow, BSLValueTableColumn, BSLValueTableColumnCollection,
                      BSLCollectionIndex, BSLCollectionIndexes):
            # Detached table data has no database authority. Its public protocol
            # still enforces row/column ownership, deletion and slice restrictions.
            if type(value.table) is BSLValueTable:
                if kind in (BSLCollectionIndex, BSLCollectionIndexes) and value.table._bounded_slice_read:
                    raise BoundaryViolation('bounded slice index receiver is not connected')
                return
            raise BoundaryViolation('noncanonical value table owner')
        elif kind is BSLValueListItem:
            owner=value._owner_ref()
            if owner is not None and type(owner) is not BSLValueList:
                raise BoundaryViolation('noncanonical value list owner')
            return
        elif kind is BSLMetadata:
            if value is self.vm._metadata:return
            owner=None
        elif kind is BSLCatalogMetadataCollection:
            if value is self.vm._metadata._catalogs:return
            owner=None
        elif kind is BSLCatalogMetadata:
            if value._root is self.vm._metadata:return
            owner=None
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

    def resolve_callable(self,value,*,require_value=False,allow_references=False):
        bound=movements.captured(self,value,require_value=require_value,allow_references=allow_references)
        if bound is not None:return bound
        return super().resolve_callable(value,require_value=require_value,allow_references=allow_references)

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
        if name in SYSTEM_NAMES:return SYSTEM_NAMES[name]
        if name in ('metadata','метаданные'):return self.vm._metadata
        if name in ('catalogs','справочники'):return self.vm._catalogs
        if name in ('documents','документы'):return self.vm._documents
        if name in ('enums','перечисления'):
            if self.vm._metadata._enumerations is None:raise ValueError('enumerations require an active configuration application')
            return self.vm._metadata._enumerations
        if name in ('accumulationrecordtype','виддвижениянакопления'):return movements.namespace(self)
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

    def reference_member(self,value,name):
        if type(value) is not BSLValueListItem:return super().reference_member(value,name)
        self._catalog_owner(value)
        value.reference_get_member(name)
        def read():
            self._catalog_owner(value)
            try:return value.reference_get_member(name)
            finally:self._check()
        def write(new_value):
            self._catalog_owner(value)
            try:value.reference_set_member(name,new_value)
            finally:self._check()
        from .experimental_naked_live_state import _ForwardReference
        from .values import Reference
        return _ForwardReference(Reference(read,write))

    def resolve_member_call(self,value,name,*,require_value=False,omitted=()):
        # Tables already have an admitted method boundary. Only omission calls
        # need the extra call-site protocol; ordinary calls remain unchanged.
        table_holes=bool(omitted) and any(type(value) is cls for cls in (_CALL_TABLE,_CALL_COLUMNS,_CALL_ROW))
        if not table_holes and type(value) not in (BSLValueList,BSLValueListItem):
            return super().resolve_member_call(value,name,require_value=require_value,omitted=omitted)
        self._catalog_owner(value)
        function=value.get_method(name)
        if type(function) is not HostFunction:
            raise BoundaryViolation('table/list method requires canonical HostFunction')
        if require_value and not function.returns_value:
            raise TypeError('Процедура не возвращает значение: '+name)
        defaults=()
        if type(value) is BSLValueList:
            if name.casefold() in ('add','добавить'):defaults=(None,'',False)
            elif name.casefold() in ('insert','вставить'):defaults=(None,None,'',False)
        elif type(value) is _CALL_COLUMNS:
            if name.casefold() in ('add','добавить'):defaults=('',None,'',Decimal(0))
            elif name.casefold() in ('insert','вставить'):defaults=(None,'',None,'',Decimal(0))
        elif type(value) is _CALL_TABLE:
            if name.casefold() in ('copy','скопировать'):defaults=(None,None)
            elif name.casefold() in ('copycolumns','скопироватьколонки'):defaults=(None,)
            elif name.casefold() in ('fillvalues','заполнитьзначения'):defaults=(None,None)
        first=1 if name.casefold() in ('insert','вставить','fillvalues','заполнитьзначения') else 0
        optional=range(first,len(defaults))
        if any(index not in optional for index in omitted):
            raise TypeError('Пропуск обязательного аргумента метода таблицы или списка значений')
        def invoke(*arguments):
            self._catalog_owner(value)
            values=list(arguments) if omitted else arguments
            for index in omitted:values[index]=defaults[index]
            try:return function(*values)
            finally:self._check()
        return invoke

    def resolve_member(self,value,name):
        if name=='__iter__':
            from . import python_direct_table_iteration as tables
            if tables.owns(value):return tables.resolve(self,value)
        self._catalog_owner(value)
        if type(value) in (BSLArray, BSLFixedArray) and name.casefold() in ('get','получить'):
            function=value.get
        elif name=='__getitem__':
            function=value.get if type(value) in (BSLArray, BSLFixedArray, BSLMap, BSLFixedStructure) else lambda index:value.get_index(index)
        elif name=='__setitem__':
            function=value.set if type(value) in (BSLArray, BSLFixedArray, BSLMap, BSLFixedMap, BSLFixedStructure) else lambda index,new:value.set_index(index,new)
        elif name=='__iter__':
            if type(value) not in (BSLArray, BSLFixedArray, BSLFixedStructure, BSLFixedMap, BSLValueList, BSLCollectionIndex, BSLCollectionIndexes) and not any(value is item for item in ITERABLES):
                raise BoundaryViolation('direct database iterator not connected')
            function=lambda:iter(value)
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
