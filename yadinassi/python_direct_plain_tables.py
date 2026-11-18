"""Exact detached plain-table admission. No database or source scope grant."""
from decimal import Decimal
from . import plain_table_storage as storage, plain_value_table_runtime as runtime
from .experimental_naked_boundaries import BoundaryViolation
from .values import BSLObject

_TABLE=runtime.BSLValueTable;_ROW=runtime.BSLValueTableRow
_COLUMNS=runtime.BSLValueTableColumnCollection;_COLUMN=runtime.BSLValueTableColumn
_INDEXES=runtime.BSLCollectionIndexes;_STORAGE=storage.TableStorage;_SCHEMA=storage.Schema
_DICT=vars(BSLObject)['__dict__']
_SNAPSHOTS=tuple((vars(module),module._DIRECT_CLASSES,module._DIRECT_FUNCTIONS,module._DIRECT_BINDINGS,module._DIRECT_NAMES)
                 for module in (storage,runtime))


def raw(value):return _DICT.__get__(value,type(value))


def fail():raise BoundaryViolation('plain table ownership or storage changed')


def hooks():
    for namespace,classes,functions,bindings,names in _SNAPSHOTS:
        if any(type(k) is not str for k in namespace):fail()
        if namespace.keys()!=names:fail()
        if any(namespace.get(k) is not v for k,v in bindings):fail()
        for cls,mro,fields in classes:
            current=vars(cls)
            if cls.__mro__ is not mro:fail()
            # copyreg's harmless bookkeeping can appear on these nonslotted
            # facade classes; it must remain an empty exact list.
            extra='__slotnames__' in current and not any(k=='__slotnames__' for k,_ in fields)
            if len(current)!=len(fields)+int(extra):fail()
            if extra and (type(current['__slotnames__']) is not list or current['__slotnames__']):fail()
            if any(current.get(k) is not v for k,v in fields):fail()
        for fn,code,defaults,kwdefaults in functions:
            if fn.__code__ is not code or fn.__defaults__ is not defaults:fail()
            current=fn.__kwdefaults__
            if current is not None and type(current) is not dict:fail()
            current={} if current is None else current
            if any(type(k) is not str for k in current):fail()
            if len(current)!=len(kwdefaults) or any(current.get(k) is not v for k,v in kwdefaults):fail()


def row_check(row,table,schema,keys,pure=False):
    if type(row) is not _ROW:fail()
    data=raw(row)
    if any(type(k) is not str for k in data):fail()
    if set(data)!= {'schema','_owner','_deleted','table'}:fail()
    if data['schema'] is not schema or data['_owner'] is not table or data['table'] is not table or type(data['_deleted']) is not bool:fail()
    if list.__len__(row)!=len(keys):fail()
    if pure and any(v is not None and type(v) is not Decimal for v in list.__iter__(row)):return False
    return True


def validate(value,pure=False):
    hooks()
    kind=type(value)
    if kind is _TABLE:table=value
    elif any(kind is cls for cls in (_ROW,_COLUMN,_COLUMNS)):
        table=dict.get(raw(value),'table')
    else:fail()
    if type(table) is not _TABLE:fail()
    data=raw(table)
    if any(type(k) is not str for k in data):fail()
    if set(data)!={'_bounded_slice_read','_storage','rows','columns','indexes'}:fail()
    if type(data['_bounded_slice_read']) is not bool:fail()
    if pure and data['_bounded_slice_read']:return False
    kernel=data['_storage'];rows=data['rows'];columns=data['columns'];indexes=data['indexes']
    if type(kernel) is not _STORAGE or type(rows) is not list or type(columns) is not _COLUMNS or type(indexes) is not _INDEXES:fail()
    if kernel.owner is not table or kernel.rows is not rows or kernel.row_factory is not _ROW or type(kernel.schema) is not _SCHEMA:fail()
    schema=kernel.schema
    if type(schema.version) is not int or schema.version<0:fail()
    # Exact key types before any hashing, comparison, or user dictionary lookup.
    if type(schema._keys) is not list or any(type(k) is not str for k in schema._keys):fail()
    if type(schema._names) is not list or any(type(k) is not str for k in schema._names):fail()
    if type(schema._offsets) is not dict or type(schema._defaults) is not list or type(schema._metadata) is not list:fail()
    if any(type(k) is not str for k in schema._offsets):fail()
    keys=schema._keys
    if [n.casefold() for n in schema._names]!=keys or len(set(keys))!=len(keys):fail()
    if set(schema._offsets)!=set(keys) or len(schema._defaults)!=len(keys) or len(schema._metadata)!=len(keys):fail()
    if any(type(schema._offsets[k]) is not int or schema._offsets[k]!=i for i,k in enumerate(keys)):fail()
    cols=raw(columns);ix=raw(indexes)
    if any(type(k) is not str for k in cols) or any(type(k) is not str for k in ix):fail()
    if set(cols)!={'table','_items'} or cols['table'] is not table or type(cols['_items']) is not list:fail()
    if set(ix)!={'table','items'} or ix['table'] is not table or type(ix['items']) is not list or ix['items']:fail()
    if len(cols['_items'])!=len(keys):fail()
    for i,column in enumerate(cols['_items']):
        if type(column) is not _COLUMN:fail()
        col=raw(column)
        if any(type(k) is not str for k in col):fail()
        if set(col)!={'table','_name','value_type','title','width','_deleted'}:fail()
        if col['table'] is not table or col['_deleted'] is not False or type(col['_name']) is not str or col['_name']!=schema._names[i]:fail()
        if schema._metadata[i] is not column:fail()
    if pure and any(v is not None and type(v) is not Decimal for v in schema._defaults):return False
    for row in rows:
        if not row_check(row,table,schema,keys,pure):return False
    if kind is _ROW and not any(row is value for row in rows):
        if not row_check(value,table,schema,keys,pure):return False
    if kind is _COLUMN and not any(column is value for column in cols['_items']):fail()
    return True
