"""Exact application-owned source temporary markers with early authorization."""
import weakref
from .experimental_naked_boundaries import BoundaryViolation
from .values import HostFunction
from . import temporary_storage as temporary


def captured(boundary, function, *, require_value=False, allow_references=False,
             argument_count=None):
    if type(function) is not HostFunction or type(function.function) is not temporary.SourceTemporaryCall:
        return None
    marker = function.function
    owner = marker.owner
    operation = marker.operation

    def authorize(count=None):
        boundary._check()
        if (function.function is not marker or marker.owner is not owner
                or marker.operation is not operation
                or type(owner) is not temporary.SourceTemporaryStorage
                or owner is not boundary.app.temporary_storage
                or not any(operation is value for value in temporary.MARKERS)):
            raise BoundaryViolation('source temporary marker binding changed')
        for cls, name, expected in temporary._DIRECT_TEMPORARY_ABI:
            instance = marker if cls is temporary.SourceTemporaryCall else owner
            if (name in vars(instance) or getattr(cls, name) is not expected
                    or cls is temporary.ApplicationTemporaryStorage and name != '_capture'
                    and getattr(type(owner), name) is not expected):
                raise BoundaryViolation('custom source temporary hooks are not integrated')
        if (type(owner._application) is not weakref.ReferenceType
                or owner._application() is not boundary.app
                or type(owner._closed) is not bool or type(owner._entries) is not dict
                or type(owner._units) is not int or type(owner._nodes) is not int):
            raise BoundaryViolation('source temporary owner state changed')
        for address, entry in owner._entries.items():
            if (type(address) is not str or type(entry) is not tuple or len(entry) != 4
                    or type(entry[1]) is not int or type(entry[2]) is not int
                    or type(entry[3]) is not str):
                raise BoundaryViolation('source temporary bookkeeping changed')
        # Use the canonical path only after exact owner/hook validation.
        owner.authorize(boundary.vm)
        boundary._validate_host_function(function, require_value, allow_references)
        if count is not None:
            marker.authorize_call(boundary.vm, count)

    authorize(argument_count)
    def call(*values):
        authorize(len(values))
        try:
            return marker.invoke(boundary.vm, list(values))
        finally:
            authorize()
    if allow_references:
        call.requires_reference = lambda index: False
    return call
