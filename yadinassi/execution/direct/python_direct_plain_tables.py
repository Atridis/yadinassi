"""Exact detached plain-table admission. No database or source scope grant."""
from decimal import Decimal
from yadinassi.collections import plain_table_storage as storage, plain_value_table_runtime as runtime, plain_table_search as search
from yadinassi.execution.codegen.experimental_naked_boundaries import BoundaryViolation
from yadinassi.types.values import BSLObject, BSLType

_TABLE=runtime.BSLValueTable;_ROW=runtime.BSLValueTableRow
_COLUMNS=runtime.BSLValueTableColumnCollection;_COLUMN=runtime.BSLValueTableColumn
_INDEXES=runtime.BSLCollectionIndexes;_STORAGE=storage.TableStorage;_SCHEMA=storage.Schema
_DICT=vars(BSLObject)['__dict__']
_SNAPSHOTS=tuple((vars(module),module._DIRECT_CLASSES,module._DIRECT_FUNCTIONS,module._DIRECT_BINDINGS,module._DIRECT_NAMES)
                 for module in (storage,runtime,search))


def raw(value):
    fields=_DICT.__get__(value,type(value))
    if type(fields) is not dict:fail()
    return fields


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


def row_check(row,table,schema,keys,pure=False,*,active=False,detached_iteration=False):
    if type(row) is not _ROW:fail()
    data=raw(row)
    if len(data)!=4:fail()
    for key in data:
        if type(key) is not str:fail()
    deleted=data.get('_deleted')
    if (data.get('schema') is not schema or data.get('_owner') is not table
            or data.get('table') is not table or type(deleted) is not bool):fail()
    if (active and deleted) or (list.__len__(row)!=len(keys) and not (deleted and detached_iteration)):
        fail()
    if pure and any(v is not None and type(v) is not Decimal for v in list.__iter__(row)):return False
    return True


def column_check(column,table,names,metadata,index):
    if type(column) is not _COLUMN:fail()
    col=raw(column)
    if any(type(k) is not str for k in col):fail()
    if set(col)!={'table','_name','value_type','title','width','_deleted'}:fail()
    if (col['table'] is not table or col['_deleted'] is not False
            or type(col['_name']) is not str or type(names[index]) is not str
            or col['_name']!=names[index] or metadata[index] is not column):
        fail()
    return col


def validate(value,pure=False,*,row_only=False,iteration=False,fresh=False):
    hooks()
    kind=type(value)
    if kind is _TABLE:table=value
    elif any(kind is cls for cls in (_ROW,_COLUMN,_COLUMNS)):
        fields=raw(value)
        if any(type(k) is not str for k in fields):fail()
        table=dict.get(fields,'table')
    else:fail()
    if type(table) is not _TABLE:fail()
    data=raw(table)
    if any(type(k) is not str for k in data):fail()
    if set(data)!={'_bounded_slice_read','_storage','rows','columns','indexes','_search'}:fail()
    if type(data['_bounded_slice_read']) is not bool:fail()
    if pure and data['_bounded_slice_read']:return False
    kernel=data['_storage'];rows=data['rows'];columns=data['columns'];indexes=data['indexes']
    if type(kernel) is not _STORAGE or type(rows) is not list or type(columns) is not _COLUMNS or type(indexes) is not _INDEXES:fail()
    if kernel.owner is not table or kernel.rows is not rows or kernel.row_factory is not _ROW or type(kernel.schema) is not _SCHEMA:fail()
    if type(kernel.epoch) is not int or kernel.epoch<0:fail()
    if fresh:
        # Decline nonempty or reused origin state without a graph traversal.
        schema=kernel.schema
        if kind is not _TABLE or rows or kernel.epoch:return False
        for group,expected in ((schema._keys,list),(schema._names,list),
                               (schema._metadata,list),(schema._defaults,list),(schema._offsets,dict)):
            if type(group) is not expected or group:return False
    if iteration:
        # A read-only iterator need not admit indexes, names or row contents
        # it will never consume. Bind the owners and shared storage here; each
        # emitted item is checked against those identities at its read.
        schema=kernel.schema
        cols=raw(columns)
        if (any(type(k) is not str for k in cols)
                or set(cols)!={'table','_items','_query_columns'}
                or cols['table'] is not table or type(cols['_items']) is not list
                or type(schema._keys) is not list or type(schema._names) is not list
                or type(schema._metadata) is not list
                or len(cols['_items'])!=len(schema._keys)
                or len(schema._names)!=len(schema._keys)
                or len(schema._metadata)!=len(schema._keys)):
            fail()
        return table,schema,rows,columns,cols['_items']
    cache=data['_search']
    if type(cache) is not search.SearchIndexes:fail()
    if type(cache.declarations) is not set or type(cache.cache) is not dict or type(cache.builds) is not int:fail()
    schema=kernel.schema
    if schema._index_search is not (cache if cache.declarations else None):fail()
    # Raw collection-region writes deliberately omit facade index history.
    if pure and schema._index_search is not None:return False
    if fresh and (cache.declarations or cache.cache or cache.builds):return False
    for signature in cache.declarations:
        if type(signature) is not tuple or any(type(i) is not int or i<0 for i in signature):fail()
    # Derived cache is private implementation state, not a receiver graph.
    # Search returns rows from the already validated table, never cached refs.
    # Raw host writes to cache internals are outside the supported API.
    if type(schema.version) is not int or schema.version<0:fail()
    if type(schema.data_epoch) is not int or schema.data_epoch<0:fail()
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
    if set(cols)!={'table','_items','_query_columns'} or cols['table'] is not table or type(cols['_items']) is not list:fail()
    if type(cols['_query_columns']) is not int or not 0<=cols['_query_columns']<=len(keys):fail()
    if pure and cols['_query_columns']:return False
    if set(ix)!={'table','items','_handles'} or ix['table'] is not table or type(ix['items']) is not list or type(ix['_handles']) is not list:fail()
    if fresh and (cols['_items'] or cols['_query_columns'] or ix['items'] or ix['_handles']):return False
    if any(type(sig) is not tuple or any(type(i) is not int or i<0 for i in sig) for sig in ix['items']):fail()
    if set(ix['items'])!=cache.declarations:fail()
    if len(cols['_items'])!=len(keys):fail()
    for i,column in enumerate(cols['_items']):
        col=column_check(column,table,schema._names,schema._metadata,i)
        # Raw region stores are valid only for untyped cells. Typed tables
        # continue through the ordinary direct facade, never another engine.
        if pure:
            description=col['value_type']
            if type(description) is not runtime.BSLTypeDescription:return False
            kinds=raw(description).get('types')
            if type(kinds) is not tuple or len(kinds):return False
    if pure and any(v is not None and type(v) is not Decimal for v in schema._defaults):return False
    if row_only and kind is _ROW:
        # A field reference never traverses the table's row inventory.
        # Check the addressed row even when it is detached; its public
        # accessors enforce deletion and readonly behavior.
        return row_check(value,table,schema,keys,pure)
    for row in rows:
        if not row_check(row,table,schema,keys,pure):return False
    if kind is _ROW and not any(row is value for row in rows):
        if not row_check(value,table,schema,keys,pure):return False
    if kind is _COLUMN and not any(column is value for column in cols['_items']):fail()
    return True


def fresh_closed_table(context,value,configured=False):
    # This value has just passed the normal constructor. The true branch can
    # touch only this empty graph and data allocated by the closed source.
    # Never check previously published tables or release their references here.
    if (type(value) is not _TABLE or context.policy is not None or context.loop_budget is not None
            or context._verify_context):return False
    try:
        if not configured:
            return validate(value,pure=True,fresh=True)
        # All ordinary constructor/column effects already ran and published.
        # The continuation needs a fresh, exact, rowless numeric table, not
        # proof of the original identity or of other pre-bound locals.
        data=raw(value)
        if any(type(key) is not str for key in data):
            return False
        rows=data.get('rows')
        if type(rows) is not list or rows:
            return False
        if not validate(value) or data['_bounded_slice_read']:
            return False
        schema=data['_storage'].schema
        columns=raw(data['columns'])
        if schema._index_search is not None or columns['_query_columns']:
            return False
        from .python_direct_plain_map import _scalar_map_key
        for column,default in zip(schema._metadata,schema._defaults):
            descriptor=raw(column)['value_type']
            if type(descriptor) is not runtime.BSLTypeDescription:
                return False
            fields=raw(descriptor)
            if any(type(key) is not str for key in fields):
                return False
            kinds=fields.get('types')
            if type(kinds) is not tuple or (kinds and (len(kinds)!=1 or kinds[0] is not BSLType.NUMBER)):
                return False
            try:
                _scalar_map_key(descriptor)
            except TypeError:
                return False
            if default is not None and type(default) is not Decimal:
                return False
        return True
    except BoundaryViolation:
        return False
