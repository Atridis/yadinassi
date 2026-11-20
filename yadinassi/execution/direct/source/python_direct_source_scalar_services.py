"""Canonical local text operations with no Python callback on exact strings."""
from yadinassi.execution.codegen.experimental_naked_boundaries import BoundaryViolation
from yadinassi.execution.direct.python_direct_services import builtin_binding
from yadinassi.execution.direct.python_direct_pure_builtins import _ABI
from yadinassi.types.values import HostFunction
from . import python_direct_source_xdto_local as local


def resolve(boundary, key, *, require_value=False, allow_references=False, argument_count=None):
    spec = _ABI.get(key)
    if spec is None or spec[1] != 1 or argument_count not in (None, 1) or not boundary._local_scalars():
        return None
    impl = spec[0]
    vm = boundary.vm
    # Local BSL declarations keep precedence; misses retain the normal path.
    routines = vm.server_routines if boundary.side == 'server' else vm.routines
    if type(routines) is not dict or key in routines:
        return None
    registry = boundary._services
    snapshot = vm._builtin_functions
    if type(registry) is not dict or type(snapshot) is not dict:
        return None
    function = registry.get(key)
    entry = snapshot.get(key)
    if type(function) is not HostFunction:return None
    local._host_hooks()
    local._fields(function)
    if (type(entry) is not tuple or len(entry) != 5 or entry[1] is not impl
            or type(entry[3]) is not frozenset or entry[3] or entry[4] is not True or not builtin_binding(function, entry)):
        return None

    def canonical():
        local._host_hooks()
        local._fields(function)
        if (vm.functions is not registry or vm._builtin_functions is not snapshot
                or registry.get(key) is not function or snapshot.get(key) is not entry
                or not builtin_binding(function, entry)):
            raise BoundaryViolation('source scalar built-in binding changed')

    def invoke(*values):
        if (boundary._local_scalars() and len(values) == 1 and type(values[0]) is str):
            boundary._check_local_lifetime()
            canonical()
            return impl(values[0])
        boundary._check()
        canonical()
        # Preserve the normal service-policy dispatch before opaque coercion
        # or if argument evaluation installed a policy after binding.
        boundary._before('call', key)
        canonical()
        try:
            return function(*values)
        except PermissionError as error:
            raise BoundaryViolation(str(error)) from error
        finally:
            boundary._check()

    if allow_references:
        invoke.requires_reference = lambda index: False
    return invoke
