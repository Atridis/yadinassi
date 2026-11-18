"""Detached canonical table iteration, without invoking receiver or payload hooks."""
from .value_tables import _DIRECT_ITERATION_TYPES, _DIRECT_ITERATION_DICT
from .experimental_naked_boundaries import BoundaryViolation

_TABLE, _COLUMNS, _ROW, _COLUMN = _DIRECT_ITERATION_TYPES


def owns(value):
    kind=type(value)
    return kind is _TABLE or kind is _COLUMNS or kind is _ROW


def state(value):
    return _DIRECT_ITERATION_DICT.__get__(value,type(value))


def invalid():
    raise BoundaryViolation('noncanonical value table iteration state')


def owner(value):
    if type(value) is _TABLE:return value
    fields=state(value)
    if any(type(k) is not str for k in fields):invalid()
    root=dict.get(fields,'table')
    if type(root) is not _TABLE:invalid()
    return root


def resolve(boundary,value):
    boundary._check();root=owner(value)
    def check():
        boundary._check()
        if owner(value) is not root:invalid()
    def invoke():
        from .python_direct_plain_tables import validate
        check();validate(value);kind=type(value);expected=None
        if kind is _TABLE:
            items=state(root)['rows'];expected=_ROW
        elif kind is _COLUMNS:
            items=state(value)['_items'];expected=_COLUMN
        elif state(value)['_deleted']:
            items=state(root)['rows'];expected=_ROW
        else:
            schema=state(value)['schema']
            items=list(list.__iter__(value))
        if type(items) is not list:invalid()
        check()
        def iterator():
            index=0
            while True:
                check()
                if index>=len(items):return
                item=items[index];index+=1
                if expected is not None and (type(item) is not expected or owner(item) is not root):invalid()
                yield item
        return iterator()
    return invoke
