"""References to already-admitted detached table fields, not new host access."""
from decimal import Decimal, ROUND_DOWN
from yadinassi.collections import plain_table_storage as storage, plain_value_table_runtime as model, plain_table_search as search
from yadinassi.collections.value_tables import _DIRECT_ITERATION_TYPES
from yadinassi.execution.codegen.experimental_naked_collections import _Reference
from .python_direct_table_iteration import owner
from yadinassi.execution.codegen.experimental_naked_boundaries import BoundaryViolation
from yadinassi.execution.codegen.experimental_naked_live_state import _ForwardReference
from yadinassi.types.values import BSLType, Reference
from yadinassi.types import type_descriptions as descriptions, type_qualifiers as qualifiers
from . import python_direct_plain_tables as tables
from .python_direct_plain_tables import fail, raw, column_check
from .python_direct_plain_map import _scalar_map_key as _scalar_shape

_TABLE,_COLUMNS,_ROW,_COLUMN=_DIRECT_ITERATION_TYPES


def member(value):return type(value) is _ROW or type(value) is _COLUMN


def indexed(value):return type(value) is _ROW


def hooks(value):
    from .python_direct_plain_tables import validate
    validate(value,row_only=True)


def bind(context,value,key,*,index=False):
    verify=getattr(context,'_verify_context',True) is not False
    if verify:context._check()
    hooks(value);root=owner(value)
    def check(*,write=False):
        if verify:context._check()
        if verify or write:hooks(value)
        if owner(value) is not root:raise BoundaryViolation('table reference owner changed')
    def read():
        check()
        try:
            return (context.resolve_member(value,'__getitem__')(key) if index
                    else context.get_member(value,key))
        finally:check()
    def write(new):
        check(write=True)
        try:
            if type(value) is _ROW:_admit_bound_write(root,value,key,index)
            if index:context.resolve_member(value,'__setitem__')(key,new)
            else:context.resolve_set_member(value,key)(new)
        finally:check()
    # Reference binding reads once, but does not require write authority until
    # the callee writes. Every later access resolves the live public protocol.
    read()
    return _ForwardReference(Reference(read,write))


# Detached synchronous, compiler-known ByRef. The address contains only the
# receiver and key, never a column offset or the initial value.
_SCHEMA=storage._DIRECT_CLASSES[0][0]
_KERNEL=storage._DIRECT_CLASSES[-1][0]
_MODEL_BINDINGS=dict(model._DIRECT_BINDINGS)
_TYPE_DESCRIPTION=_MODEL_BINDINGS['BSLTypeDescription']
_INDEXES=_MODEL_BINDINGS['BSLCollectionIndexes']
_STORAGE_ERROR=dict(storage._DIRECT_BINDINGS)['StorageError']
_SEARCH=search._DIRECT_CLASSES[0][0]
_DECLARATIONS=dict(search._DIRECT_CLASSES[0][2])['declarations']
_KERNEL_SLOTS=dict(storage._DIRECT_CLASSES[-1][2])
_SCHEMA_SLOTS=dict(storage._DIRECT_CLASSES[0][2])
_KOWNER=_KERNEL_SLOTS['owner']
_KSCHEMA=_KERNEL_SLOTS['schema']
_KROWS=_KERNEL_SLOTS['rows']
_KEPOCH=_KERNEL_SLOTS['epoch']
_KEYS=_SCHEMA_SLOTS['_keys']
_NAMES=_SCHEMA_SLOTS['_names']
_OFFSETS=_SCHEMA_SLOTS['_offsets']
_METADATA=_SCHEMA_SLOTS['_metadata']
_DATA_EPOCH=_SCHEMA_SLOTS['data_epoch']
_INDEX_SEARCH=_SCHEMA_SLOTS['_index_search']
# The fast operation does not invoke any facade hook. Still reject changes to
# the particular public protocol it replaces, even if its function object was
# edited in place. Unrelated table methods do not participate.
_FUNCTIONS={fn:(code,defaults) for fn,code,defaults,_ in model._DIRECT_FUNCTIONS}
_METHODS={name:(fn,*_FUNCTIONS[fn]) for cls,_,attrs in model._DIRECT_CLASSES if cls is _ROW
          for name,fn in attrs if name in ('get_member','set_member','get_index','set_index','get','set','_positional_value')}


def _sealed(*names):
    current=vars(_ROW)
    for name in names:
        method,code,defaults=_METHODS[name]
        if (current.get(name) is not method or method.__code__ is not code
                or method.__defaults__ is not defaults or method.__kwdefaults__ is not None):
            fail()


_WRITE=_MODEL_BINDINGS['_write_cell']
_ADJUST=_MODEL_BINDINGS['_adjust']
_WRITER_BINDINGS={name:_MODEL_BINDINGS[name] for name in ('_write_cell','_adjust','SearchIndexes')}
_CONVERTER=dict(next(attrs for cls,_,attrs in descriptions._DIRECT_LIVE_METADATA_CLASSES
                     if cls is _TYPE_DESCRIPTION))['adjust_value']
_DESCRIPTION_ACCESS=('types','number_qualifiers','string_qualifiers','date_qualifiers',
                     'binary_data_qualifiers','_query_scalar','_query_reference','adjust_value','__getattribute__')
_DESCRIPTION_CLASSES=tuple((cls,mro,dict(fields)) for cls,mro,fields in
                           (*descriptions._DIRECT_LIVE_METADATA_CLASSES,*qualifiers._DIRECT_LIVE_METADATA_CLASSES)
                           if cls is not object)
_ABSENT_MEMBER=object()
_DESCRIPTION_READER_ABI=tuple((cls,mro,fields.get('__getattribute__',_ABSENT_MEMBER),fields.get('types',_ABSENT_MEMBER))
                              for cls,mro,fields in _DESCRIPTION_CLASSES
                              if any(base is cls for base in _TYPE_DESCRIPTION.__mro__))
_TOUCH=dict(search._DIRECT_CLASSES[0][2])['touch']
_TOUCH_INNER=dict(search._DIRECT_CLASSES[0][2])['_touch']
_SEARCH_FUNCTIONS={fn:(code,defaults) for fn,code,defaults,_ in search._DIRECT_FUNCTIONS}
_DESCRIPTION_FUNCTIONS={fn:(code,defaults) for fn,code,defaults,_ in descriptions._DIRECT_REGION_FUNCTIONS}
_COLUMNS_SLOT=dict(search._DIRECT_CLASSES[0][2])['_columns']
_HISTORY_SLOT=dict(search._DIRECT_CLASSES[0][2])['_history']


def _same_code(function, specs):
    code,defaults=specs[function]
    return function.__code__ is code and function.__defaults__ is defaults and function.__kwdefaults__ is None



def _admit_bound_write(root, row, key, indexed):
    # The generic boundary has just validated the live schema and column vector.
    # Leave rejection of deleted rows, readonly slices and missing keys to the
    # public operation, which owns their diagnostics.
    state=raw(root)
    if state['_bounded_slice_read'] or raw(row)['_deleted']:return
    schema=_KSCHEMA.__get__(state['_storage'],_KERNEL)
    if type(key) is str:
        position=_OFFSETS.__get__(schema,_SCHEMA).get(key.casefold())
        if position is None:return
    elif indexed and (type(key) is int or type(key) is Decimal):
        keys=_KEYS.__get__(schema,_SCHEMA)
        position=_MODEL_BINDINGS['_index'](key,len(keys))
    else:return
    column=_METADATA.__get__(schema,_SCHEMA)[position]
    description=raw(column)['value_type']
    if type(description) is not _TYPE_DESCRIPTION:fail()
    fields=raw(description)
    if any(type(k) is not str for k in fields):fail()
    for cls,mro,getattribute,types_member in _DESCRIPTION_READER_ABI:
        current=vars(cls)
        if (cls.__mro__ is not mro or current.get('__getattribute__',_ABSENT_MEMBER) is not getattribute
                or current.get('types',_ABSENT_MEMBER) is not types_member):fail()
    types=fields.get('types')
    if type(types) is not tuple:fail()
    if types:_typed_conversion(description,fields)

def _typed_conversion(description,fields):
    # Unowned or nullable query descriptors have their own resolver. For an
    # ordinary scalar description, validate exactly the qualifier data shared
    # with typed native Map keys before invoking canonical scalar conversion.
    if '_query_scalar' in fields or '_query_reference' in fields:
        return False
    if any(type(kind) is not BSLType for kind in fields['types']):
        return False
    if not _same_code(_ADJUST,_FUNCTIONS) or not _same_code(_CONVERTER,_DESCRIPTION_FUNCTIONS):fail()
    for cls,mro,expected in _DESCRIPTION_CLASSES:
        # Only descriptor/qualifier/host base hooks used in the conversion.
        current=vars(cls)
        names=_DESCRIPTION_ACCESS if cls is _TYPE_DESCRIPTION else ('__getattribute__','digits','fraction_digits','allowed_sign','length','allowed_length','date_fractions')
        if cls.__mro__ is not mro or any(current.get(name) is not expected.get(name) for name in names):fail()
    _scalar_shape(description)
    return True


def _index_listener(root, schema, indexes, index, declarations, position):
    listener=_INDEX_SEARCH.__get__(schema,_SCHEMA)
    if not declarations:
        if listener is not None:fail()
        return None
    if listener is not index:fail()
    state=raw(indexes)
    if any(type(key) is not str for key in state) or state.get('table') is not root:fail()
    offsets=_COLUMNS_SLOT.__get__(index,_SEARCH)
    if type(offsets) is not tuple:fail()
    if not 0<=position<len(offsets):return None
    handles=offsets[position]
    if type(handles) is not tuple or any(type(handle) is not int for handle in handles):fail()
    if not handles:return None
    histories=_HISTORY_SLOT.__get__(index,_SEARCH)
    if type(histories) is not dict or any(type(handle) is not int for handle in histories):fail()
    current=vars(_SEARCH)
    if (current.get('touch') is not _TOUCH or current.get('_touch') is not _TOUCH_INNER
            or '__getattribute__' in current or current.get('_columns') is not _COLUMNS_SLOT
            or current.get('_history') is not _HISTORY_SLOT
            or not _same_code(_TOUCH,_SEARCH_FUNCTIONS) or not _same_code(_TOUCH_INNER,_SEARCH_FUNCTIONS)):
        fail()
    for handle in handles:
        history=histories.get(handle)
        if history is not None and type(history) is not dict:fail()
    return listener


class _RowAddress(_Reference):
    __slots__=('context','row','root','kernel','schema','key','name','indexed')

    def __init__(self,context,row,key,indexed):
        self.context,self.row,self.key,self.indexed=context,row,key,indexed
        self.name=key.casefold() if type(key) is str else None
        self.root=owner(row)
        data=raw(self.root)
        if any(type(k) is not str for k in data):fail()
        self.kernel=data.get('_storage')
        if type(self.kernel) is not _KERNEL:fail()
        self.schema=_KSCHEMA.__get__(self.kernel,_KERNEL)
        if type(self.schema) is not _SCHEMA:fail()
        self._locate()  # Validate the address before later actuals, not its value.

    def _locate(self,*,writing=False):
        if self.context.vm._family_closed:
            raise BoundaryViolation('python-direct interpreter was closed during execution')
        row,root,kernel,schema=self.row,self.root,self.kernel,self.schema
        data=raw(root)
        if any(type(k) is not str for k in data):fail()
        rows=data.get('rows')
        if (data.get('_storage') is not kernel or _KOWNER.__get__(kernel,_KERNEL) is not root
                or _KSCHEMA.__get__(kernel,_KERNEL) is not schema or type(rows) is not list
                or _KROWS.__get__(kernel,_KERNEL) is not rows):
            fail()
        keys=_KEYS.__get__(schema,_SCHEMA)
        if type(keys) is not list:fail()
        tables.row_check(row,root,schema,keys)
        if raw(row)['_deleted']:
            raise ValueError('row is deleted' if self.name is None else 'row is detached')
        if self.indexed:_sealed('set_index' if writing else 'get_index')
        if self.name is None:
            if writing:_sealed('set')
            else:_sealed('get','_positional_value')
            index=self.key
            if type(index) is Decimal:
                if not index.is_finite():raise TypeError('table index must be a finite number')
                index=index.to_integral_value(rounding=ROUND_DOWN)
            if not 0<=index<len(keys):raise IndexError('table index out of range')
            position=int(index)
        else:
            _sealed('set_member' if writing else 'get_member')
            position=self._named_position(schema,keys)
        columns=data.get('columns')
        if type(columns) is not _COLUMNS:fail()
        fields=raw(columns)
        for k in fields:
            if type(k) is not str:fail()
        items=fields.get('_items')
        names=_NAMES.__get__(schema,_SCHEMA);metadata=_METADATA.__get__(schema,_SCHEMA)
        if (fields.get('table') is not root or type(items) is not list or type(names) is not list
                or type(metadata) is not list or len(items)!=len(keys)
                or len(names)!=len(keys) or len(metadata)!=len(keys)):fail()
        column=column_check(items[position],root,names,metadata,position)
        key=keys[position]
        if type(key) is not str or names[position].casefold()!=key:fail()
        return position,column

    def _named_position(self,schema,keys):
        offsets=_OFFSETS.__get__(schema,_SCHEMA)
        if type(offsets) is not dict:fail()
        # The existing schema exposes a raw mutable dict. A foreign collision
        # key must fail before lookup invokes its equality; no cached offsets.
        for k in offsets:
            if type(k) is not str:fail()
        position=offsets.get(self.name)
        if position is None and self.name not in offsets:raise _STORAGE_ERROR('column not found: '+self.key)
        if type(position) is not int:fail()
        if not 0<=position<len(keys) or type(keys[position]) is not str or keys[position]!=self.name:fail()
        return position

    @property
    def value(self):
        position,_=self._locate()
        try:
            value=list.__getitem__(self.row,position)
            return Decimal(value) if type(value) is int else value
        finally:
            if owner(self.row) is not self.root:fail()

    @value.setter
    def value(self,new):
        row,root,kernel,schema=self.row,self.root,self.kernel,self.schema
        position,column=self._locate(writing=True)
        data=raw(root)  # Exact keys already checked; no arbitrary callbacks since.
        readonly=data.get('_bounded_slice_read')
        if type(readonly) is not bool:fail()
        if readonly:raise ValueError('bounded table slice is readonly')
        description=column['value_type']
        if type(description) is not _TYPE_DESCRIPTION:fail()
        desc=raw(description)
        if any(type(k) is not str for k in desc):fail()
        if 'types' in vars(_TYPE_DESCRIPTION):fail()
        types=desc.get('types')
        if type(types) is not tuple:fail()
        indexes=data.get('indexes')
        if type(indexes) is not _INDEXES:fail()
        index=data.get('_search')
        if type(index) is not _SEARCH:fail()
        declarations=_DECLARATIONS.__get__(index,_SEARCH)
        if type(declarations) is not set:fail()
        try:
            obj,cls,stamp=((kernel,_KERNEL,_KEPOCH) if self.name is None
                           else (schema,_SCHEMA,_DATA_EPOCH))
            epoch=stamp.__get__(obj,cls)
            if type(epoch) is not int or epoch<0:fail()
            if types or declarations:
                if any(vars(model).get(k) is not v for k,v in _WRITER_BINDINGS.items()) or not _same_code(_WRITE,_FUNCTIONS):fail()
                if types and not _typed_conversion(description,desc):
                    # Nullable/query/reference descriptors retain their own
                    # admitted conversion rather than gaining scalar authority.
                    hooks(row)
                    if self.indexed:self.context.resolve_member(row,'__setitem__')(self.key,new)
                    else:self.context.resolve_set_member(row,self.key)(new)
                    return
                if types:new=_ADJUST(description,new)
                listener=_index_listener(root,schema,indexes,index,declarations,position)
                _WRITE(row,obj,stamp,position,new,listener)
            else:
                if _INDEX_SEARCH.__get__(schema,_SCHEMA) is not None:fail()
                stamp.__set__(obj,epoch+1)
                list.__setitem__(row,position,new)
        finally:
            if owner(row) is not root:fail()



def local_member(context,row,name):
    if not context._known_method_local or context._verify_context or context.policy is not None:
        return context.reference_member(row,name)
    return _RowAddress(context,row,name,False)


def local_index(context,row,key):
    if (not context._known_method_local or context._verify_context or context.policy is not None
            or (type(key) is not int and type(key) is not Decimal and type(key) is not str)):
        return context.reference_index(row,key)
    return _RowAddress(context,row,key,True)
