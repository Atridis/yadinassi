"""Weak provenance separating owning XML handles from detached XML objects."""
from weakref import ref
from yadinassi.execution.codegen.direct_boundaries import BoundaryViolation

_HANDLES={}

def mark_source_owned(value):
    identity=id(value)
    def expired(reference):
        if _HANDLES.get(identity) is reference:_HANDLES.pop(identity,None)
    _HANDLES[identity]=ref(value,expired)

def reject_source_owned(value):
    reference=_HANDLES.get(id(value))
    if reference is not None and reference() is value:
        raise BoundaryViolation('source-owned XML handle requires its owning application boundary')
