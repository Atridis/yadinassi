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
    root=dict.get(state(value),'table')
    if type(root) is not _TABLE:invalid()
    return root


def resolve(boundary,value):
    boundary._check();root=owner(value)
    def check():
        boundary._check()
        if owner(value) is not root:invalid()
    def invoke():
        check();kind=type(value);raw=state(value);expected=None
        if kind is _TABLE:
            items=dict.get(raw,'rows');expected=_ROW
        elif kind is _COLUMNS:
            items=dict.get(raw,'items');expected=_COLUMN
        else:
            deleted=dict.get(raw,'_deleted')
            if type(deleted) is not bool:invalid()
            if deleted:
                # Native deleted rows enumerate their still-live owner's rows.
                items=dict.get(state(root),'rows');expected=_ROW
            else:
                columns=dict.get(state(root),'columns');cells=dict.get(raw,'cells')
                if type(columns) is not _COLUMNS or owner(columns) is not root or type(cells) is not dict:invalid()
                fields=dict.get(state(columns),'items')
                if type(fields) is not list:invalid()
                # Dict lookup must not reach a forged key's equality callback.
                for name,expected_hook in (('__hash__',object.__hash__),('__eq__',object.__eq__)):
                    actual=next(vars(base)[name] for base in _COLUMN.__mro__ if name in vars(base))
                    if actual is not expected_hook:invalid()
                for column in dict.keys(cells):
                    if type(column) is not _COLUMN or owner(column) is not root:invalid()
                items=[]
                for column in fields:
                    if type(column) is not _COLUMN or owner(column) is not root:invalid()
                    items.append(dict.__getitem__(cells,column))
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
