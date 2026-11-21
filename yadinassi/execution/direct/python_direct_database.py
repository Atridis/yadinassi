"""Direct public catalog protocol over one host-selected database.

No arbitrary getattr, no backend access and no replacement for writer validation.
"""
from yadinassi.execution.codegen.experimental_naked_boundaries import BoundaryViolation
from . import python_direct_movements as movements
from yadinassi.db.registers.accumulation_posting_values import BSLAccumulationRow
from yadinassi.db.catalog.catalogs import BSLCatalogs, BSLCatalogManager, BSLCatalogObject, BSLCatalogSelection
from yadinassi.db.catalog.catalog_types import BSLCatalogReference
from yadinassi.db.catalog.catalog_backend import FieldSchema
from yadinassi.db.catalog.catalog_sections import BSLCatalogSection, BSLCatalogSectionRow
from yadinassi.db.registers.information_registers import (
    BSLInformationRegisters, BSLInformationRegisterManager, BSLInformationRegisterRecordManager,
    BSLInformationRegisterSelection, BSLInformationRegisterRecordSet, BSLInformationRegisterRecord,
    _RegisterFilter, _RegisterFilterItem,
)
from yadinassi.db.document.documents import BSLDocuments, BSLDocumentManager, BSLDocumentObject
from yadinassi.db.document.document_types import BSLDocumentReference
from yadinassi.db.document.document_lines import BSLDocumentLines, BSLDocumentLine
from yadinassi.db.metadata.enumerations import BSLEnumerations, BSLEnumManager
from yadinassi.db.metadata.enum_types import BSLEnumReference
from yadinassi.db.document.document_posting_values import DOCUMENT_WRITE_MODES
from yadinassi.collections.structures import BSLStructure, BSLFixedStructure, BSLKeyAndValue
from yadinassi.types.values import HostFunction, BSLArray, BSLFixedArray
from decimal import Decimal
from .python_direct_xml_ownership import reject_source_owned as _reject_source_xml
from yadinassi.formats.xml.dom_io import BSLDOMBuilder, BSLDOMWriter
from yadinassi.formats.xml.dom_nodes import _NODE_CLASSES, BSLDOMNodeList, BSLDOMElementList, BSLDOMAttributeMap
from yadinassi.formats.xml.dom_xpath import BSLDOMNamespaceResolver, BSLDOMXPathResult
from yadinassi.formats.xml.xml_io import BSLXMLReader, BSLXMLReaderSettings, BSLXMLNamespaceContext
from yadinassi.formats.xml.xml_writer import BSLXMLWriter, BSLXMLWriterSettings
from yadinassi.formats.regex.regex_functions import BSLRegexResult, BSLRegexGroup
from yadinassi.streams.file_io import BSLFile, BSLBinaryData
from yadinassi.http.http_client import BSLHTTPConnection, BSLHTTPRequest, BSLHTTPResponse
from yadinassi.streams.binary_streams import BSLBinaryDataBuffer, BSLMemoryStream, BSLStream
from yadinassi.collections.maps import BSLMap, BSLFixedMap
from yadinassi.collections.value_lists import BSLValueList, BSLValueListItem
from yadinassi.formats.json.json_processing import (BSLJSONReader, BSLJSONWriter, BSLJSONWriterSettings,
    _DIRECT_SOURCE_JSON_CLASSES, _DIRECT_SOURCE_JSON_DICT, _DIRECT_JSON_READ)
from .python_direct_names import NAMES as SYSTEM_NAMES, VALUE_IDS as SYSTEM_VALUE_IDS, ITERABLES
from yadinassi.configuration.metadata import (BSLMetadata, BSLCatalogMetadataCollection, BSLCatalogMetadata,
    BSLInformationRegisterMetadata, BSLInformationRegisterMetadataCollection)
from yadinassi.db.query.queries import BSLQuery, BSLQueryResult, BSLQueryResultSelection
from yadinassi.collections.value_tables import (BSLValueTable, BSLValueTableRow, BSLCollectionIndex, BSLCollectionIndexes,
                           BSLValueTableColumn, BSLValueTableColumnCollection, _DIRECT_ITERATION_TYPES)
_CALL_TABLE, _CALL_COLUMNS, _CALL_ROW, _ = _DIRECT_ITERATION_TYPES
from yadinassi.types.type_descriptions import BSLTypeDescription
from yadinassi.types.type_qualifiers import (BSLNumberQualifiers, BSLStringQualifiers,
                              BSLDateQualifiers, BSLBinaryDataQualifiers)

NAMES=('metadata','метаданные','catalogs','справочники','documents','документы','informationregisters','регистрысведений','enums','перечисления','documentwritemode','режимзаписидокумента','accumulationrecordtype','виддвижениянакопления')

# Canonical detached receivers only; child rows/items and database owners still
# traverse live ownership validation. Public protocols retain resource guards.
_DOM_LISTS=(BSLDOMNodeList,BSLDOMElementList,BSLDOMAttributeMap)
_DETACHED_TYPES=(*_NODE_CLASSES,*_DOM_LISTS,BSLDOMBuilder,BSLDOMWriter,BSLDOMNamespaceResolver,BSLDOMXPathResult,BSLXMLReader, BSLXMLReaderSettings, BSLXMLNamespaceContext, BSLXMLWriter, BSLXMLWriterSettings, BSLValueList, BSLValueTable, BSLTypeDescription, BSLNumberQualifiers, BSLStringQualifiers, BSLDateQualifiers, BSLBinaryDataQualifiers, BSLQueryResult, BSLQueryResultSelection, BSLStructure, BSLFixedStructure, BSLKeyAndValue, BSLArray, BSLFixedArray, BSLFixedMap, BSLRegexResult, BSLRegexGroup, BSLFile, BSLBinaryData, BSLHTTPConnection, BSLHTTPRequest, BSLHTTPResponse, BSLBinaryDataBuffer, BSLMemoryStream, BSLStream, BSLMap, BSLJSONReader, BSLJSONWriter, BSLJSONWriterSettings)
_DETACHED_TYPE_IDS=frozenset(map(id,_DETACHED_TYPES))
_PURE_COLLECTION_TYPE_IDS=frozenset(map(id,(
    BSLValueTable, BSLValueTableRow, BSLValueTableColumn, BSLValueTableColumnCollection,
    BSLCollectionIndex, BSLCollectionIndexes, BSLFixedArray, BSLFixedStructure, BSLFixedMap,
    BSLTypeDescription, BSLNumberQualifiers, BSLStringQualifiers,
    BSLDateQualifiers, BSLBinaryDataQualifiers,
)))


# Read/Прочитать has a fixed no-argument, Boolean-returning contract and
# advances an already-buffered text snapshot. OpenFile/OpenStream still use
# their own resource gates. Inspect only hooks needed to grant this method.
_JSON_READER,_JSON_READ,_JSON_READ_CODE,_JSON_READ_MRO,_JSON_READ_FIELDS,_JSON_READ_SEAL = _DIRECT_JSON_READ


def _bind_json_read(boundary,value):
    boundary._check_effect()
    if _JSON_READER.__mro__ is not _JSON_READ_MRO or _JSON_READ.__code__ is not _JSON_READ_CODE:
        raise BoundaryViolation('JSON method metadata ABI changed')
    for namespace,size,entries in _JSON_READ_SEAL:
        if len(namespace)!=size or any(namespace.get(key) is not expected for key,expected in entries):
            raise BoundaryViolation('JSON method metadata ABI changed')
    fields=_DIRECT_SOURCE_JSON_DICT.__get__(value,_JSON_READER)
    if len(fields)!=len(_JSON_READ_FIELDS) or any(type(key) is not str or key not in _JSON_READ_FIELDS for key in fields):
        # The existing general contract still decides nonstandard layouts,
        # including benign embedding attributes and forbidden method shadows.
        return None

    def invoke(*args):
        boundary._check_effect()
        # The canonical signature reports excess arguments after they are
        # evaluated, at the original call site. No synthesized host wrapper.
        if _JSON_READ.__code__ is not _JSON_READ_CODE:
            raise BoundaryViolation('JSON method metadata ABI changed')
        try:return _JSON_READ(value,*args)
        finally:boundary._check_effect()
    return invoke


def _verify_collection(boundary,value):
    return id(type(value)) not in _PURE_COLLECTION_TYPE_IDS or getattr(boundary,'_verify_context',True) is not False

_REGISTER_TYPES = frozenset(map(id, (
    BSLInformationRegisters, BSLInformationRegisterManager, BSLInformationRegisterRecordManager,
    BSLInformationRegisterSelection, BSLInformationRegisterRecordSet, BSLInformationRegisterRecord,
    _RegisterFilter, _RegisterFilterItem,
)))


def _check_register_owner(boundary, value):
    from yadinassi.db.database_context import SQLiteDBContext, require_database_context
    from yadinassi.db.sqlite.sqlite_catalog import SQLiteCatalogBackend
    vm = boundary.vm
    db = vm.database_context
    if db is None:
        require_database_context()
    root = boundary._register_root
    if (type(db) is not SQLiteDBContext or type(db.backend) is not SQLiteCatalogBackend
            or db.backend._closed is not False or type(root) is not BSLInformationRegisters
            or root is not vm._information_registers or root._context is not db
            or type(root._metadata) is not BSLInformationRegisterMetadataCollection
            or root._metadata is not vm._metadata._information_registers
            or root._catalogs is not vm._catalogs or root._documents is not vm._documents
            or type(root._managers) is not dict):
        raise BoundaryViolation('foreign or closed information register database')
    kind = type(value)
    if kind is BSLInformationRegisters:
        if value is root:
            return
        raise BoundaryViolation('foreign information register namespace')
    if kind is BSLInformationRegisterManager:
        manager = value
    elif kind in (BSLInformationRegisterRecordManager, BSLInformationRegisterSelection,
                  BSLInformationRegisterRecordSet):
        manager = value._manager
    else:
        owner = value._owner
        if type(owner) is not BSLInformationRegisterRecordSet:
            raise BoundaryViolation('foreign information register record set')
        if kind is _RegisterFilter and owner._filter is not value:
            raise BoundaryViolation('foreign information register filter')
        if (kind is _RegisterFilterItem
                and (type(owner._filter) is not _RegisterFilter or type(owner._filter._items) is not dict
                     or type(value._field) is not FieldSchema or type(value._field.name) is not str
                     or owner._filter._items.get(value._field.name.casefold()) is not value)):
            raise BoundaryViolation('foreign information register filter item')
        manager = owner._manager
    if type(manager) is not BSLInformationRegisterManager or manager._registers is not root:
        raise BoundaryViolation('foreign information register manager')
    item = manager._metadata
    if (type(item) is not BSLInformationRegisterMetadata or type(item._name) is not str
            or manager._catalogs is not root._catalogs or item._root is not vm._metadata
            or root._managers.get(item._name.casefold()) is not manager
            or type(root._metadata._items) is not dict
            or root._metadata._items.get(item._name.casefold()) is not item
            or item._schema is not manager._schema):
        raise BoundaryViolation('foreign information register metadata')
    # A detached buffer cannot be reassigned to a different register by
    # changing its manager link; it retains the exact type issued at creation.
    if ((kind is BSLInformationRegisterRecordManager and value._record_type is not manager._record_type)
            or (kind is BSLInformationRegisterSelection and value._selection_type is not manager._selection_type)
            or (kind is BSLInformationRegisterRecordSet and value._set_type is not manager._set_type)
            or (kind is BSLInformationRegisterRecord and value._row_type is not manager._row_type)):
        raise BoundaryViolation('information register receiver type changed')


class CatalogBoundary:
    _register_root = None

    def _catalog_owner(self, value, *, verify=True):
        if verify:
            if getattr(self,'_verify_context',True):self._check()
            else:self._check_effect()
        if movements.owns(value):
            movements.check(self,value);return
        if value is movements.NAMESPACE:
            movements.namespace(self);return
        if id(value) in SYSTEM_VALUE_IDS:return
        root=self.vm._catalogs
        kind=type(value)
        if id(kind) in _REGISTER_TYPES:
            _check_register_owner(self, value)
            return
        if kind is BSLXMLReader or kind is BSLXMLWriter:_reject_source_xml(value)
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

    def resolve_callable(self,value,*,require_value=False,allow_references=False,_extension_value=False):
        from .python_direct_fixed_find import captured
        bound=captured(self,value,require_value=require_value,allow_references=allow_references)
        if bound is not None:return bound
        bound=movements.captured(self,value,require_value=require_value,allow_references=allow_references)
        if bound is not None:return bound
        return super().resolve_callable(value,require_value=require_value,allow_references=allow_references,_extension_value=_extension_value)

    def resolve_service(self,name,*args,**kwargs):
        if name.casefold() in ('new:query','new:запрос'):
            self._check_effect()
            function=self.vm.types.get(name.split(':',1)[1].casefold())
            if type(function) is not HostFunction:
                raise BoundaryViolation('query constructor requires canonical registration')
            return super().resolve_callable(function)
        return super().resolve_service(name,*args,**kwargs)

    def external_get(self,name):
        self._check_effect()
        if name in SYSTEM_NAMES:return SYSTEM_NAMES[name]
        if name in ('metadata','метаданные'):return self.vm._metadata
        if name in ('catalogs','справочники'):return self.vm._catalogs
        if name in ('documents','документы'):return self.vm._documents
        if name in ('informationregisters','регистрысведений'):
            root = self.vm._information_registers
            _check_register_owner(self, root)
            return root
        if name in ('enums','перечисления'):
            if self.vm._metadata._enumerations is None:raise ValueError('enumerations require an active configuration application')
            return self.vm._metadata._enumerations
        if name in ('accumulationrecordtype','виддвижениянакопления'):return movements.namespace(self)
        if name in ('documentwritemode','режимзаписидокумента'):
            if self.vm._documents.posting_runtime() is None:raise ValueError('posting profile required')
            return DOCUMENT_WRITE_MODES
        return super().external_get(name)

    def external_set(self,name,value):
        self._check_effect()
        raise ValueError('catalog namespace is read-only')

    def get_member(self,value,name):
        verify=_verify_collection(self,value)
        self._catalog_owner(value,verify=verify)
        try:return value.get_member(name)
        finally:
            if verify:self._check_effect()

    def resolve_set_member(self,value,name):
        verify=_verify_collection(self,value)
        self._catalog_owner(value,verify=verify)
        def write(new_value):
            self._catalog_owner(value,verify=verify)
            try:value.set_member(name,new_value)
            finally:
                if verify:self._check_effect()
        return write

    def reference_member(self,value,name):
        from . import python_direct_table_references as table_refs
        if table_refs.member(value):return table_refs.bind(self,value,name)
        kind=type(value)
        if (kind is BSLQueryResultSelection
                or kind is BSLNumberQualifiers and name.casefold() in
                    ('digits','разрядность','fractiondigits','разрядностьдробнойчасти')
                or kind is BSLAccumulationRow and name.casefold() in ('linenumber','номерстроки')):
            return self._readonly_property_reference(value,name)
        if kind is not BSLValueListItem:return super().reference_member(value,name)
        self._catalog_owner(value)
        value.reference_get_member(name)
        def read():
            self._catalog_owner(value)
            try:return value.reference_get_member(name)
            finally:self._check_effect()
        def write(new_value):
            self._catalog_owner(value)
            try:value.reference_set_member(name,new_value)
            finally:self._check_effect()
        from yadinassi.execution.codegen.experimental_naked_live_state import _ForwardReference
        from yadinassi.types.values import Reference
        return _ForwardReference(Reference(read,write))

    def _readonly_property_reference(self,value,name):
        # Keep the current property live across forwarding. Methods are not
        # readable output slots, including QuerySelection.Next without a column.
        def read():
            result=self.get_member(value,name)
            if type(result) is HostFunction:
                raise BoundaryViolation('method is not a host reference: '+name)
            return result
        def write(new_value):
            if _verify_collection(self,value):self._check_effect()
            raise ValueError('Свойство недоступно для записи: '+name)
        read()
        from yadinassi.execution.codegen.experimental_naked_live_state import _ForwardReference
        from yadinassi.types.values import Reference
        return _ForwardReference(Reference(read,write))

    def reference_index(self,value,index):
        from . import python_direct_table_references as table_refs
        if table_refs.indexed(value):return table_refs.bind(self,value,index,index=True)
        return super().reference_index(value,index)

    def resolve_optional_open_file(self,value,name,*,require_value=False,omitted=(),argument_count=None):
        kind=type(value)
        if kind is not BSLJSONReader and kind is not BSLJSONWriter:
            return super().resolve_optional_open_file(value,name,require_value=require_value,
                                                     omitted=omitted,argument_count=argument_count)
        self._catalog_owner(value)
        if require_value:
            raise TypeError('Процедура не возвращает значение: '+name)
        limit=2 if kind is BSLJSONReader else 4
        if not 1<=argument_count<=limit or any(not 1<=i<argument_count for i in omitted):
            raise TypeError('Пропуск обязательного аргумента или неверное количество аргументов JSON OpenFile')
        # Normal JSON OpenFile already handles None for optional arguments, and
        # uses the same regular-file and ownership checks as no-hole calls.
        return self.resolve_member(value,name)

    def resolve_member_call(self,value,name,*,require_value=False,omitted=()):
        if type(value) is BSLXMLReader or type(value) is BSLXMLWriter:
            self._catalog_owner(value)
            function=value.get_method(name)
            if type(function) is not HostFunction:raise BoundaryViolation('XML method requires canonical wrapper')
            self._validate_host_function(function,require_value)
            key=name.casefold();optional=()
            if key in ('openfile','открытьфайл','openstream','открытьпоток'):
                optional=(1,2,3) if type(value) is BSLXMLReader else (1,2)
            elif key in ('setstring','установитьстроку'):
                optional=(1,2) if type(value) is BSLXMLReader else (0,)
            elif type(value) is BSLXMLReader and key in ('movetocontent','перейтиксодержимому'):
                optional=(0,)
            if any(index not in optional for index in omitted):raise TypeError('XML required argument omitted')
            def invoke(*args):
                self._catalog_owner(value)
                values=list(args) if omitted else args
                for index in omitted:values[index]=None
                for argument in values:
                    if type(argument) is BSLXMLReader or type(argument) is BSLXMLWriter:_reject_source_xml(argument)
                try:return function(*values)
                finally:self._check_effect()
            return invoke
        # Preserve the public JSON function/procedure contract before argument
        # evaluation. This is only a restriction on an already admitted surface.
        if require_value and any(type(value) is cls for cls in (BSLJSONReader, BSLJSONWriter)):
            if (type(value) is _JSON_READER and not omitted and type(name) is str
                    and name.casefold() in ('read','прочитать')
                    and self._verify_context is False and self.policy is None
                    and not getattr(self,'_server_side',False) and self.vm._has_module_context
                    and self.vm.database_context is None):
                cursor = _bind_json_read(self,value)
                if cursor is not None:return cursor
            self._catalog_owner(value)
            # Validate definition-time receiver/base ABI before reading metadata;
            # neither a class override nor an instance hook may run here.
            for cls,mro,entries in _DIRECT_SOURCE_JSON_CLASSES:
                if not any(cls is base for base in type(value).__mro__):continue
                current=vars(cls)
                if (len(cls.__mro__)!=len(mro)
                        or any(actual is not expected for actual,expected in zip(cls.__mro__,mro))
                        or len(current)!=len(entries)
                        or any(current.get(key) is not expected for key,expected in entries)):
                    raise BoundaryViolation('JSON method metadata ABI changed')
            fields=vars(value)
            if (any(type(key) is not str for key in fields)
                    or any(key in vars(base) for key in fields for base in type(value).__mro__)):
                raise BoundaryViolation('JSON method instance metadata changed')
            function=value.get_method(name)
            if type(function) is not HostFunction:
                raise BoundaryViolation('JSON method requires canonical HostFunction')
            if not function.returns_value:
                raise TypeError('Процедура не возвращает значение: '+name)
        # Tables already have an admitted method boundary. Only omission calls
        # need the extra call-site protocol; ordinary calls remain unchanged.
        table_holes=bool(omitted) and any(type(value) is cls for cls in (_CALL_TABLE,_CALL_COLUMNS,_CALL_ROW))
        if not table_holes and not any(type(value) is cls for cls in (BSLValueList,BSLValueListItem)):
            return super().resolve_member_call(value,name,require_value=require_value,omitted=omitted)
        verify=_verify_collection(self,value)
        self._catalog_owner(value,verify=verify)
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
            self._catalog_owner(value,verify=verify)
            values=list(arguments) if omitted else arguments
            for index in omitted:values[index]=defaults[index]
            try:return function(*values)
            finally:
                if verify:self._check_effect()
        return invoke

    def resolve_member(self,value,name):
        from . import python_direct_fixed_find as fixed_find
        if fixed_find.owns(value,name):return fixed_find.resolve(self,value,name)
        if name=='__iter__':
            from . import python_direct_table_iteration as tables
            if tables.owns(value):return tables.resolve(self,value)
        verify=_verify_collection(self,value)
        self._catalog_owner(value,verify=verify)
        if type(value) in (BSLArray, BSLFixedArray) and name.casefold() in ('get','получить'):
            function=value.get
        elif name=='__getitem__' and any(type(value) is kind for kind in _DOM_LISTS):
            function=value.item
        elif name=='__getitem__':
            function=value.get if type(value) in (BSLArray, BSLFixedArray, BSLMap, BSLFixedStructure) else lambda index:value.get_index(index)
        elif name=='__setitem__':
            function=value.set if type(value) in (BSLArray, BSLFixedArray, BSLMap, BSLFixedMap, BSLFixedStructure) else lambda index,new:value.set_index(index,new)
        elif name=='__iter__':
            if type(value) not in (BSLArray, BSLFixedArray, BSLFixedStructure, BSLFixedMap, BSLValueList, BSLCollectionIndex, BSLCollectionIndexes, BSLInformationRegisterRecordSet) and not any(value is item for item in ITERABLES) and not any(type(value) is kind for kind in _DOM_LISTS):
                raise BoundaryViolation('direct database iterator not connected')
            function=lambda:iter(value)
        else:
            function=value.get_method(name)
            if type(function) is not HostFunction:
                raise BoundaryViolation('database method requires canonical HostFunction')
        if verify:self._check_effect()
        def invoke(*args):
            self._catalog_owner(value,verify=verify)
            if type(value) is BSLDOMBuilder or type(value) is BSLDOMWriter:
                for argument in args:
                    if type(argument) is BSLXMLReader or type(argument) is BSLXMLWriter:_reject_source_xml(argument)
            try:return function(*args)
            finally:
                if verify:self._check_effect()
        return invoke
