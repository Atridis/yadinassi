"""Exact application-owned source temporary markers with early authorization."""
import weakref
from yadinassi.execution.codegen.experimental_naked_boundaries import BoundaryViolation
from yadinassi.types.values import HostFunction
from yadinassi.application import temporary_storage as temporary
from yadinassi.types.unique_identifiers import BSLUUID

_UUID_TEXT = vars(BSLUUID)['text']
_UUID_INIT = vars(BSLUUID)['__init__']


def _copy_to_server(vm, marker, operation, values, check_client):
    from yadinassi.configuration.configuration_source_runtime import _DIRECT_SOURCE_FACTORY_ABI, _SourceInterpreter
    from yadinassi.execution.direct.python_direct_source import check_owner
    from yadinassi.runtime import Interpreter
    from ..python_direct_server import transfer

    if operation is temporary.put_marker:
        value, owner = values
        if type(owner) is not BSLUUID:
            raise ValueError('client temporary storage requires an explicit UUID owner')
        # Transport the bounded UUID scalar only in the owner slot; do not
        # broaden the generic server packet or copy opaque client objects.
        packet = transfer([value, _UUID_TEXT.__get__(owner, BSLUUID)])
    else:
        packet = transfer(list(values))
    check_client()
    if any(getattr(Interpreter, name) is not expected
           or (name != '__init__' and getattr(_SourceInterpreter, name) is not expected)
           for name, expected in _DIRECT_SOURCE_FACTORY_ABI):
        raise BoundaryViolation('source temporary server factory hooks changed')

    server = vm._activation_interpreter()
    try:
        check_client()
        server._logical_side = 'server'
        server._transaction_activation_allowed = False
        side_stack = server._context_stack
        module_stack = server._module_context_stack
        side_stack.append('server')
        try:
            module_stack.append(True)
            try:
                from yadinassi.db.database_transactions import admission
                with admission(False):
                    check_owner(server)
                    if operation is temporary.put_marker:
                        # Exact constructor and a fresh object, never the client UUID.
                        owner = object.__new__(BSLUUID)
                        _UUID_INIT(owner, packet[1])
                        packet[1] = owner
                    result = marker.invoke(server, packet)
                    check_owner(server)
                    return transfer([result])[0]
            finally:
                module_stack.pop()
        finally:
            side_stack.pop()
    finally:
        server.close()


def captured(boundary, function, *, require_value=False, allow_references=False,
             argument_count=None):
    if type(function) is not HostFunction or type(function.function) is not temporary.SourceTemporaryCall:
        return None
    marker = function.function
    owner = marker.owner
    operation = marker.operation
    from yadinassi.execution.direct.python_direct_source import SourceBoundary
    client = (type(boundary) is SourceBoundary and boundary.side == boundary.logical_side == 'client'
              and (operation is temporary.put_marker or operation is temporary.get_marker))

    def check_binding():
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

    def check_transfer():
        from yadinassi.db.database_transactions import forbid_transfer
        from yadinassi.execution.safe_mode import require_transfer
        if owner._closed:
            raise ValueError('temporary storage belongs to another or closed source application')
        require_transfer('cross-context or asynchronous calls')
        forbid_transfer(boundary.vm._transaction_backend())

    def check_client():
        # The extra checks around packet copying/factory do not scan entries.
        check_binding()
        check_transfer()

    def authorize(count=None):
        check_binding()
        if client:
            check_transfer()
        else:
            # Preserve the old server lane. For the client crossing, the
            # store itself owns its entries and performs existing quota work.
            for address, entry in owner._entries.items():
                if (type(address) is not str or type(entry) is not tuple or len(entry) != 4
                        or type(entry[1]) is not int or type(entry[2]) is not int
                        or type(entry[3]) is not str):
                    raise BoundaryViolation('source temporary bookkeeping changed')
            owner.authorize(boundary.vm)
        boundary._validate_host_function(function, require_value, allow_references)
        if count is not None:
            if client:
                if count != (2 if operation is temporary.put_marker else 1):
                    raise TypeError('temporary storage function arity')
            else:
                marker.authorize_call(boundary.vm, count)

    authorize(argument_count)
    def call(*values):
        authorize(len(values))
        try:
            if client:
                return _copy_to_server(boundary.vm, marker, operation, values, check_client)
            return marker.invoke(boundary.vm, list(values))
        finally:
            authorize()
    if allow_references:
        call.requires_reference = lambda index: False
    return call
