"""Live recorder/accumulation buffers belonging to the current database host."""
from types import MethodType,FunctionType
from uuid import UUID
from decimal import Decimal
from yadinassi.temporal.dates import BSLDate
from yadinassi.db.catalog.catalog_types import BSLCatalogReference
from yadinassi.db.document.document_types import BSLDocumentReference
from yadinassi.db.metadata.enum_types import BSLEnumReference
from yadinassi.db.catalog.catalog_backend import FieldSchema
from yadinassi.db.document.document_backend import DocumentKey,DocumentSchema
from yadinassi.db.document.document_movements import RecorderRegisterSchema
from yadinassi.db.registers.accumulation_movements import AccumulationRegisterSchema
from yadinassi.configuration.configuration_accumulation import AccumulationConfiguration
from yadinassi.configuration.configuration_posting import PostingConfiguration
from yadinassi.configuration.configuration_accumulation_references import InventoryConfiguration
from yadinassi.configuration.configuration_inventory_application import InventoryApplicationConfiguration
from yadinassi.configuration.configuration_inventory_enums import InventoryEnumConfiguration
from yadinassi.configuration.configuration_inventory_enum_application import InventoryEnumApplicationConfiguration
from yadinassi.configuration.configuration_main_demo import MainDemoConfiguration
from yadinassi.configuration.configuration_posting_application import PostingApplicationConfiguration
from weakref import ReferenceType
from yadinassi.db.document import document_posting_values as recorder
from yadinassi.db.registers import accumulation_posting_values as accumulation
from yadinassi.db.document.documents import BSLDocuments,BSLDocumentManager,BSLDocumentObject
from yadinassi.db.catalog.catalogs import BSLCatalogs
from yadinassi.db.database_context import SQLiteDBContext
from yadinassi.db.sqlite.sqlite_catalog import SQLiteCatalogBackend
from yadinassi.configuration.metadata import BSLMetadata,BSLDocumentMetadataCollection,BSLDocumentMetadata
from yadinassi.db.document.document_posting import PostingRuntime
from yadinassi.types.values import HostFunction,_DIRECT_COLLECTION_CLASS_ABI
from yadinassi.execution.codegen.experimental_naked_boundaries import BoundaryViolation

from yadinassi.db.document.documents import _DIRECT_MOVEMENT_PARENT_CLASSES as _ABI_0
from yadinassi.db.catalog.catalogs import _DIRECT_MOVEMENT_PARENT_CLASSES as _ABI_1
from yadinassi.configuration.metadata import _DIRECT_MOVEMENT_PARENT_CLASSES as _ABI_2
from yadinassi.db.database_context import _DIRECT_MOVEMENT_PARENT_CLASSES as _ABI_3
from yadinassi.db.sqlite.sqlite_catalog import _DIRECT_MOVEMENT_PARENT_CLASSES as _ABI_4
from yadinassi.db.document.document_posting import _DIRECT_MOVEMENT_PARENT_CLASSES as _ABI_5
from yadinassi.db.document.document_backend import _DIRECT_MOVEMENT_PARENT_CLASSES as _ABI_6
from yadinassi.db.document.document_movements import _DIRECT_MOVEMENT_PARENT_CLASSES as _ABI_7
from yadinassi.db.registers.accumulation_movements import _DIRECT_MOVEMENT_PARENT_CLASSES as _ABI_8
from yadinassi.db.catalog.catalog_backend import _DIRECT_MOVEMENT_PARENT_CLASSES as _ABI_9
from yadinassi.configuration.configuration_accumulation import _DIRECT_MOVEMENT_PARENT_CLASSES as _ABI_10
from yadinassi.configuration.configuration_posting import _DIRECT_MOVEMENT_PARENT_CLASSES as _ABI_11
from yadinassi.configuration.configuration_accumulation_references import _DIRECT_MOVEMENT_PARENT_CLASSES as _ABI_12
from yadinassi.configuration.configuration_inventory_application import _DIRECT_MOVEMENT_PARENT_CLASSES as _ABI_13
from yadinassi.configuration.configuration_inventory_enums import _DIRECT_MOVEMENT_PARENT_CLASSES as _ABI_14
from yadinassi.configuration.configuration_inventory_enum_application import _DIRECT_MOVEMENT_PARENT_CLASSES as _ABI_15
from yadinassi.configuration.configuration_main_demo import _DIRECT_MOVEMENT_PARENT_CLASSES as _ABI_16
from yadinassi.configuration.configuration_posting_application import _DIRECT_MOVEMENT_PARENT_CLASSES as _ABI_17
_PARENT_ABI=_ABI_0+_ABI_1+_ABI_2+_ABI_3+_ABI_4+_ABI_5+_ABI_6+_ABI_7+_ABI_8+_ABI_9+_ABI_10+_ABI_11+_ABI_12+_ABI_13+_ABI_14+_ABI_15+_ABI_16+_ABI_17

_CONFIGURATIONS=(AccumulationConfiguration,PostingConfiguration,InventoryConfiguration,InventoryApplicationConfiguration,InventoryEnumConfiguration,InventoryEnumApplicationConfiguration,MainDemoConfiguration,PostingApplicationConfiguration)

_COLLECTIONS=(recorder.BSLRecorderCollection,accumulation.BSLAccumulationCollection)
_SETS=(recorder.BSLRecorderSet,accumulation.BSLAccumulationSet)
_ROWS=(recorder.BSLRecorderRow,accumulation.BSLAccumulationRow)
_TYPES=_COLLECTIONS+_SETS+_ROWS
_FIELD_NAMES={
    **{cls:frozenset(('_document','_sets')) for cls in _COLLECTIONS},
    **{cls:frozenset(('_document','_schema','_rows','_selected','_bytes')) for cls in _SETS},
    recorder.BSLRecorderRow:frozenset(('_owner','_active','_values','_bytes')),
    accumulation.BSLAccumulationRow:frozenset(('_owner','_active','_values','_bytes','_period','_direction','_written')),
}
_METHODS=tuple(dict.fromkeys(getattr(cls,name) for cls in _SETS for name in ('add','clear','count','get','write')))
_HOST_ABI=_DIRECT_COLLECTION_CLASS_ABI[-1]
_ORIGINS=recorder._DIRECT_MOVEMENT_ORIGINS
NAMESPACE=accumulation._DIRECT_MOVEMENT_NAMESPACE


def owns(value):return any(type(value) is cls for cls in _TYPES)


def _fields(value):
    fields=vars(value)
    if type(fields) is not dict or any(type(k) is not str for k in fields):raise BoundaryViolation('movement owner fields changed')
    allowed=next((names for cls,names in _FIELD_NAMES.items() if type(value) is cls),None)
    if allowed is not None and fields.keys()!=allowed:raise BoundaryViolation('movement receiver field shape changed')
    # Parent objects retain their native optional state, but never instance
    # replacements for class-defined helpers traversed by movement operations.
    for cls in type(value).__mro__:
        for name,implementation in vars(cls).items():
            if (type(implementation) is FunctionType or type(implementation) is staticmethod
                    or type(implementation) is classmethod or type(implementation) is property) and name in fields:
                raise BoundaryViolation('movement owner helper shadowed')
    return fields


def _mapping(value):
    if type(value) is not dict or any(type(k) is not str for k in value):raise BoundaryViolation('movement membership mapping changed')
    return value


def _check_hooks(records):
    for cls,mro,fields in records:
        current=vars(cls)
        if cls.__mro__ is not mro or len(current)!=len(fields) or any(current.get(k) is not v for k,v in fields):
            raise BoundaryViolation('movement public protocol hooks changed')


def _hooks():
    for module in (recorder,accumulation):
        for name,value in module._DIRECT_MOVEMENT_BINDINGS:
            if vars(module).get(name) is not value:raise BoundaryViolation('movement native binding changed')
    if accumulation.ACCUMULATION_RECORD_TYPES is not NAMESPACE:raise BoundaryViolation('movement namespace changed')
    _check_hooks(_PARENT_ABI)
    _check_hooks(recorder._DIRECT_MOVEMENT_CLASSES+accumulation._DIRECT_MOVEMENT_CLASSES+(_HOST_ABI,))


def _origin(value,kind):
    record=_ORIGINS.get(value)
    if record is None or record[0]!=kind or type(record[1]) is not ReferenceType:
        raise BoundaryViolation('movement receiver lacks constructor provenance')
    return record[1](),record[2]


def check(boundary,value):
    boundary._check();_hooks()
    if not owns(value):raise BoundaryViolation('movement receiver is not canonical')
    _fields(value)
    if any(type(value) is cls for cls in _ROWS):
        group,_=_origin(value,'row')
        if not any(type(group) is cls for cls in _SETS) or value._owner is not group:
            raise BoundaryViolation('movement row owner changed')
        _fields(group);document,schema=_origin(group,'set')
    elif any(type(value) is cls for cls in _SETS):
        group=value;document,schema=_origin(value,'set')
    else:
        group=None;document,_=_origin(value,'collection');schema=None
    if type(document) is not BSLDocumentObject:raise BoundaryViolation('movement document expired')
    _fields(document);manager=document._manager
    if type(manager) is not BSLDocumentManager:raise BoundaryViolation('movement document manager changed')
    _fields(manager);documents=manager._documents;root=boundary.vm._catalogs;context=boundary.vm.database_context
    if type(documents) is not BSLDocuments or documents is not boundary.vm._documents or type(root) is not BSLCatalogs:
        raise BoundaryViolation('foreign movement document family')
    _fields(documents);_fields(root)
    if (manager._catalogs is not root or documents._catalogs is not root or documents._context is not context
            or root._context is not context or type(context) is not SQLiteDBContext or documents._interpreter is not boundary.vm):
        raise BoundaryViolation('foreign movement database context')
    _fields(context);backend=context._backend
    if type(backend) is not SQLiteCatalogBackend:raise BoundaryViolation('noncanonical movement backend')
    _fields(backend)
    if backend._closed is not False:raise BoundaryViolation('movement database is closed')
    metadata=documents._metadata
    if type(metadata) is not BSLDocumentMetadataCollection:raise BoundaryViolation('movement metadata family changed')
    _fields(metadata)
    metadata_root=boundary.vm._metadata
    if type(metadata_root) is not BSLMetadata:raise BoundaryViolation('movement metadata root changed')
    _fields(metadata_root)
    if metadata._context is not context or metadata is not metadata_root._documents:
        raise BoundaryViolation('foreign movement metadata snapshot')
    managers=_mapping(documents._managers);items=_mapping(metadata._items)
    meta=manager._metadata
    if type(meta) is not BSLDocumentMetadata:raise BoundaryViolation('movement document metadata changed')
    _fields(meta)
    if (type(meta._name) is not str or managers.get(meta._name.casefold()) is not manager
            or items.get(meta._name.casefold()) is not meta or manager._schema is not meta._schema):
        raise BoundaryViolation('movement document is not in current manager inventory')
    runtime=documents._posting_runtime
    if type(runtime) is not PostingRuntime:raise BoundaryViolation('movement posting profile expired')
    _fields(runtime)
    if runtime.documents is not documents:raise BoundaryViolation('movement posting owner changed')
    collection=document._movements
    collection_type=_COLLECTIONS[1] if runtime.accumulation is True else _COLLECTIONS[0]
    set_type=_SETS[1] if runtime.accumulation is True else _SETS[0]
    row_type=_ROWS[1] if runtime.accumulation is True else _ROWS[0]
    if type(collection) is not collection_type:raise BoundaryViolation('movement collection family changed')
    _fields(collection)
    if _origin(collection,'collection')[0] is not document or collection._document is not document:
        raise BoundaryViolation('movement collection owner changed')
    sets=_mapping(collection._sets)
    config=runtime.configuration
    if not any(type(config) is cls for cls in _CONFIGURATIONS):raise BoundaryViolation('movement configuration changed')
    schemas=config.registers
    key=document._key
    if type(key) is not DocumentKey or type(manager._schema) is not DocumentSchema:
        raise BoundaryViolation('movement document key changed')
    identities=(key.database_id,key.document_id,key.record_id,backend.database_id,metadata._database_id,manager._schema.identity)
    if any(type(identity) is not UUID or type(identity.int) is not int or not 0<=identity.int<2**128 for identity in identities):
        raise BoundaryViolation('movement database identity changed')
    if (key.database_id.int!=backend.database_id.int or key.database_id.int!=metadata._database_id.int
            or key.document_id.int!=manager._schema.identity.int or type(metadata._generation) is not int
            or type(backend.configuration_generation) is not int or metadata._generation!=backend.configuration_generation):
        raise BoundaryViolation('movement database generation changed')
    schema_type=AccumulationRegisterSchema if runtime.accumulation is True else RecorderRegisterSchema
    if type(schemas) is not tuple:raise BoundaryViolation('movement register schemas changed')
    for item in schemas:
        if type(item) is not schema_type or type(item.name) is not str or type(item.recorder_documents) is not tuple:
            raise BoundaryViolation('movement register schema changed')
        if any(type(identity) is not UUID or type(identity.int) is not int for identity in item.recorder_documents):
            raise BoundaryViolation('movement recorder identity changed')
    expected=tuple(s for s in schemas if any(key.document_id.int==identity.int for identity in s.recorder_documents))
    if len(sets)!=len(expected):raise BoundaryViolation('movement register inventory changed')
    rows_total=0;bytes_total=0
    for current_schema in expected:
        item=sets.get(current_schema.name.casefold())
        if type(item) is not set_type:raise BoundaryViolation('movement set family changed')
        _fields(item);original,original_schema=_origin(item,'set')
        if (original is not document or original_schema is not current_schema or item._document is not document
                or item._schema is not current_schema or type(item._rows) is not list or type(item._bytes) is not int or item._bytes<0):
            raise BoundaryViolation('movement set ownership changed')
        rows_total+=len(item._rows)
        if rows_total>recorder.MAX_MOVEMENT_ROWS:raise BoundaryViolation('movement row limit exceeded')
        schema_fields=current_schema.fields
        if type(schema_fields) is not tuple or any(type(field) is not FieldSchema or type(field.name) is not str for field in schema_fields):
            raise BoundaryViolation('movement field schema changed')
        names=frozenset(field.name.casefold() for field in schema_fields)
        seen=set();set_bytes=0
        for row in item._rows:
            if type(row) is not row_type:raise BoundaryViolation('movement row family changed')
            _fields(row)
            if id(row) in seen or row._owner is not item or _origin(row,'row')[0] is not item:
                raise BoundaryViolation('movement row ownership changed')
            seen.add(id(row))
            if type(row._bytes) is not int or row._bytes<0:raise BoundaryViolation('movement row accounting changed')
            values=_mapping(row._values)
            if values.keys()!=names or type(row._active) is not bool:raise BoundaryViolation('movement row fields changed')
            if any(not any(type(v) is cls for cls in (str,bool,Decimal,BSLDate,BSLCatalogReference,BSLDocumentReference,BSLEnumReference,type(None))) for v in values.values()):
                raise BoundaryViolation('movement row value family changed')
            expected_bytes=32+(64 if row_type is accumulation.BSLAccumulationRow else 0)
            expected_bytes+=sum(len(v.encode('utf-8')) if type(v) is str else 32 for v in values.values())
            if row._bytes!=expected_bytes:raise BoundaryViolation('movement row accounting changed')
            set_bytes+=expected_bytes
        if item._bytes!=set_bytes:raise BoundaryViolation('movement set accounting changed')
        bytes_total+=set_bytes
        if bytes_total>recorder.MAX_BUFFER_BYTES:raise BoundaryViolation('movement byte limit exceeded')
    if group is None:
        if value is not collection:raise BoundaryViolation('movement collection was replaced')
    else:
        if group._document is not document or group._schema is not schema or not any(item is group for item in sets.values()):
            raise BoundaryViolation('movement set was removed')
        if any(type(value) is cls for cls in _ROWS) and not any(row is value for row in group._rows):
            raise ValueError('detached movement row')
    return document


def namespace(boundary):
    boundary._check();_hooks()
    if type(NAMESPACE) is not accumulation._AccumulationRecordTypes or _fields(NAMESPACE):raise BoundaryViolation('movement namespace fields changed')
    documents=boundary.vm._documents
    if type(documents) is not BSLDocuments:raise BoundaryViolation('movement documents namespace changed')
    _fields(documents)
    runtime=documents.posting_runtime()
    if type(runtime) is not PostingRuntime or runtime.accumulation is not True:
        raise ValueError('accumulation posting profile required')
    return NAMESPACE


def captured(boundary,function,*,require_value=False,allow_references=False):
    if type(function) is not HostFunction:return None
    _check_hooks((_HOST_ABI,));_fields(function);callback=function.function
    if type(callback) is not MethodType or not owns(callback.__self__):return None
    receiver=callback.__self__
    if not any(callback.__func__ is method for method in _METHODS):raise BoundaryViolation('movement method is not canonical')
    def admit():
        check(boundary,receiver);_fields(function)
        if function.function is not callback or type(function.reference_parameters) is not frozenset or function.reference_parameters:
            raise BoundaryViolation('movement saved method changed')
        if require_value and function.returns_value is not True:raise TypeError('Процедура не возвращает значение: '+function.name)
    admit()
    def invoke(*args):
        admit()
        try:return callback(*args)
        finally:boundary._check()
    if allow_references:invoke.requires_reference=lambda index:False
    return invoke
