"""References to already-admitted detached table fields, not new host access."""
from yadinassi.collections.value_tables import _DIRECT_ITERATION_TYPES
from .python_direct_table_iteration import owner
from yadinassi.execution.codegen.experimental_naked_boundaries import BoundaryViolation
from yadinassi.execution.codegen.experimental_naked_live_state import _ForwardReference
from yadinassi.types.values import Reference

_TABLE,_COLUMNS,_ROW,_COLUMN=_DIRECT_ITERATION_TYPES


def member(value):return type(value) is _ROW or type(value) is _COLUMN


def indexed(value):return type(value) is _ROW


def hooks(value):
    from .python_direct_plain_tables import validate
    validate(value)


def write_authority(value):
    # This family stores values directly; qualifiers are metadata, not a
    # hidden coercion engine. Keep exact owner/schema admission for writes.
    from .python_direct_plain_tables import validate
    validate(value)


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
