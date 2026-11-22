"""Detached canonical table iteration, without invoking receiver or payload hooks."""
from yadinassi.collections.value_tables import _DIRECT_ITERATION_TYPES, _DIRECT_ITERATION_DICT
from yadinassi.collections.plain_value_table_runtime import public_cell
from yadinassi.collections.plain_table_storage import _DIRECT_CLASSES
from yadinassi.execution.codegen.experimental_naked_boundaries import BoundaryViolation

_TABLE, _COLUMNS, _ROW, _COLUMN = _DIRECT_ITERATION_TYPES
_SCHEMA, _, _schema_members = _DIRECT_CLASSES[0]
_schema_slots = dict(_schema_members)
_KEYS, _NAMES, _METADATA = (_schema_slots[name] for name in ('_keys','_names','_metadata'))


def owns(value):
    kind=type(value)
    return kind is _TABLE or kind is _COLUMNS or kind is _ROW


def state(value):
    fields=_DIRECT_ITERATION_DICT.__get__(value,type(value))
    if type(fields) is not dict:invalid()
    for key in fields:
        if type(key) is not str:invalid()
    return fields


def invalid():raise BoundaryViolation('noncanonical value table iteration state')


def owner(value):
    if type(value) is _TABLE:return value
    fields=state(value)
    root=dict.get(fields,'table')
    if type(root) is not _TABLE:invalid()
    return root


def resolve(boundary,value):
    verify=getattr(boundary,'_verify_context',True) is not False
    if verify:boundary._check()
    root=owner(value)
    kind=type(value)
    def check():
        if verify:boundary._check()
        if kind is not _TABLE and owner(value) is not root:invalid()
    def invoke():
        from .python_direct_plain_tables import validate, row_check, column_check
        check()
        bound,schema,rows,columns,column_items=validate(value,iteration=True)
        if bound is not root:invalid()
        keys=_KEYS.__get__(schema,_SCHEMA)
        if kind is _ROW:
            row_check(value,root,schema,keys,detached_iteration=True)
        if kind is _COLUMNS:
            if value is not columns:invalid()
            items=column_items
            expected=_COLUMN
        elif kind is _TABLE or state(value)['_deleted']:
            items=rows
            expected=_ROW
        else:
            # Row values retain their invocation-time snapshot. No unrelated
            # rows or column objects are read to create it.
            items=list(list.__iter__(value))
            expected=None
        check()
        def iterator():
            index=0
            while True:
                check()
                if index>=len(items):return
                item=items[index]
                if expected is _ROW:
                    keys_now=_KEYS.__get__(schema,_SCHEMA)
                    if type(keys_now) is not list:invalid()
                    row_check(item,root,schema,keys_now,active=True)
                elif expected is _COLUMN:
                    names=_NAMES.__get__(schema,_SCHEMA)
                    metadata=_METADATA.__get__(schema,_SCHEMA)
                    if (type(names) is not list or type(metadata) is not list
                            or index>=len(names) or index>=len(metadata)):
                        invalid()
                    column_check(item,root,names,metadata,index)
                index+=1
                yield public_cell(item) if expected is None else item
        return iterator()
    return invoke
