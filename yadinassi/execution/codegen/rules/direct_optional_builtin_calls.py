"""Non-Python call shapes for StrFind defaults and named JSON converters."""
from yadinassi.execution.direct import python_direct_json_handlers as handlers
from yadinassi.execution.codegen.direct_boundaries import BoundaryViolation
from yadinassi.syntax import ast as b
from yadinassi.types.values import HostFunction
from ..direct_python_ast import attr, call, literal, name


_SEARCH_PARAMETERS = ('value', 'needle', 'direction', 'start', 'occurrence')


def _bind_json(context, key):
    implementation, _, _ = handlers.JSON_CALLBACKS[key]
    service = context._services.get(key)
    if type(service) is not HostFunction or service.function is not implementation:
        raise BoundaryViolation('canonical JSON handler binding changed')
    return handlers.bind(context, key, service, implementation, implementation)


def lower(emit, key, arguments):
    if key in ('strfind', 'стрнайти'):
        omitted = emit.omissions(arguments)
        if not omitted or len(arguments) > len(_SEARCH_PARAMETERS):
            return None
        # test_omitted_slots_are_not_explicit_undefined: keep Python's
        # defaults for holes, not for actual BSL Undefined arguments.
        prefix = omitted[0]
        node = emit.plain_target(key)
        return call(node, *(emit.expr(arg) for arg in arguments[:prefix]),
                    **{_SEARCH_PARAMETERS[i]: emit.expr(arguments[i])
                       for i in range(prefix, len(arguments)) if i not in omitted})
    match = handlers.JSON_CALLBACKS.get(key)
    if match is None:
        return None
    _, owner_slot, maximum = match
    if not owner_slot <= len(arguments) <= maximum:
        return None
    # test_json_conversion: a named BSL converter needs its actual owner.
    actuals = []
    for i, arg in enumerate(arguments):
        if type(arg) is b.OmittedArgument:
            actuals.append(literal(None))
            continue
        imported = emit.import_path(arg) if i == owner_slot else None
        actuals.append(call(attr(name('_C'), 'import_callback_module'), literal(imported))
                       if imported is not None else emit.expr(arg))
    return call(call('_BindJsonConverters', name('_C'), literal(key)), *actuals)


HELPERS = {'_BindJsonConverters': _bind_json}
