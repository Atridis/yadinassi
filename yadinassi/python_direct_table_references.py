"""References to already-admitted detached table fields, not new host access."""
from .value_tables import (_DIRECT_ITERATION_TYPES, _DIRECT_REFERENCE_ABI,
    _DIRECT_REFERENCE_WRITE_TYPES, _DIRECT_REFERENCE_WRITE_ABI, _DIRECT_REFERENCE_ADJUST,
    _DIRECT_REFERENCE_INDEX_LIMIT)
from .python_direct_table_iteration import owner, state
from .experimental_naked_boundaries import BoundaryViolation
from .experimental_naked_live_state import _ForwardReference
from .values import Reference

_TABLE,_COLUMNS,_ROW,_COLUMN=_DIRECT_ITERATION_TYPES
_INDEXES,_DESCRIPTION=_DIRECT_REFERENCE_WRITE_TYPES


def member(value):return type(value) is _ROW or type(value) is _COLUMN


def indexed(value):return type(value) is _ROW


def class_hooks(abi):
    for cls,mro,fields in abi:
        current=vars(cls)
        if cls.__mro__ is not mro or len(current)-('__slotnames__' in current)!=len(fields) or any(current.get(k) is not v for k,v in fields):
            raise BoundaryViolation('table reference receiver hooks changed')
        slots=current.get('__slotnames__')
        if slots is not None and (type(slots) is not list or slots):
            raise BoundaryViolation('table reference receiver slots changed')


def hooks(value):
    class_hooks(_DIRECT_REFERENCE_ABI)
    validate_storage(value)


def raw_fields(value,allowed):
    raw=state(value)
    if any(type(k) is not str or k not in allowed for k in raw):
        raise BoundaryViolation('table reference receiver fields changed')
    return raw


def column_state(column,root):
    if type(column) is not _COLUMN:
        raise BoundaryViolation('table reference noncanonical column')
    raw=raw_fields(column,('table','name','value_type','title','width','_deleted'))
    if (dict.get(raw,'table') is not root or type(dict.get(raw,'name')) is not str
            or type(dict.get(raw,'_deleted')) is not bool):
        raise BoundaryViolation('table reference column state changed')
    return raw


def validate_storage(value):
    raw=raw_fields(value,('table','cells','_deleted') if type(value) is _ROW else
                   ('table','name','value_type','title','width','_deleted'))
    if type(dict.get(raw,'_deleted')) is not bool:
        raise BoundaryViolation('table reference deletion state changed')
    root=dict.get(raw,'table')
    if type(root) is not _TABLE:raise BoundaryViolation('table reference owner changed')
    root_raw=raw_fields(root,('_bounded_slice_read','rows','columns','indexes'))
    if type(dict.get(root_raw,'_bounded_slice_read')) is not bool:
        raise BoundaryViolation('table reference slice state changed')
    columns=dict.get(root_raw,'columns')
    if type(columns) is not _COLUMNS:raise BoundaryViolation('table reference columns changed')
    columns_raw=raw_fields(columns,('table','items'))
    fields=dict.get(columns_raw,'items')
    if dict.get(columns_raw,'table') is not root or type(fields) is not list:
        raise BoundaryViolation('table reference column storage changed')
    # The public column lookup inspects names. Validate raw exact fields first,
    # without traversing or comparing any cell payload.
    for column in fields:column_state(column,root)
    if type(value) is _COLUMN:
        column_state(value,root);return
    cells=dict.get(raw,'cells')
    if type(cells) is not dict:raise BoundaryViolation('table reference cell storage changed')
    # A forged dictionary key can collide with a real column's identity hash.
    # No lookup may occur before keys and the hash/equality ABI are validated.
    for name,expected in (('__hash__',object.__hash__),('__eq__',object.__eq__)):
        actual=next(vars(base)[name] for base in _COLUMN.__mro__ if name in vars(base))
        if actual is not expected:raise BoundaryViolation('table reference column key hooks changed')
    for column in dict.keys(cells):column_state(column,root)


def write_authority(value):
    if type(value) is not _ROW:return
    # New byref writes deliberately stop before the unvalidated qualifier and
    # index engines. Existing ordinary assignment remains outside this adapter.
    class_hooks(_DIRECT_REFERENCE_WRITE_ABI)
    from . import value_tables as model
    if vars(model).get('_adjust') is not _DIRECT_REFERENCE_ADJUST:
        raise BoundaryViolation('table reference adjust hook changed')
    maximum=vars(model).get('_MAX_INDEX_UNITS')
    if type(maximum) is not int or not 0<=maximum<=_DIRECT_REFERENCE_INDEX_LIMIT:
        raise BoundaryViolation('table reference index budget changed')
    root=owner(value);root_raw=state(root)
    indexes=dict.get(root_raw,'indexes')
    if type(indexes) is not _INDEXES:
        raise BoundaryViolation('table reference index authority changed')
    index_raw=raw_fields(indexes,('table','items'))
    items=dict.get(index_raw,'items')
    if dict.get(index_raw,'table') is not root or type(items) is not list or items:
        raise BoundaryViolation('indexed table reference writes are not integrated')
    columns=dict.get(state(dict.get(root_raw,'columns')),'items')
    for column in columns:
        description=dict.get(state(column),'value_type')
        if type(description) is not _DESCRIPTION:
            raise BoundaryViolation('table reference type authority changed')
        description_raw=raw_fields(description,('types','number_qualifiers','string_qualifiers',
            'date_qualifiers','binary_data_qualifiers','_query_scalar'))
        kinds=dict.get(description_raw,'types')
        if type(kinds) is not tuple or kinds or dict.get(description_raw,'_query_scalar') is not None:
            raise BoundaryViolation('typed table reference writes are not integrated')


def bind(context,value,key,*,index=False):
    context._check();hooks(value);root=owner(value)
    def check():
        context._check();hooks(value)
        if owner(value) is not root:raise BoundaryViolation('table reference owner changed')
    def read():
        check()
        try:
            return (context.resolve_member(value,'__getitem__')(key) if index
                    else context.get_member(value,key))
        finally:check()
    def write(new):
        check();write_authority(value)
        try:
            if index:context.resolve_member(value,'__setitem__')(key,new)
            else:context.resolve_set_member(value,key)(new)
        finally:check()
    # Reference binding reads once, but does not require write authority until
    # the callee writes. Every later access resolves the live public protocol.
    read()
    return _ForwardReference(Reference(read,write))
