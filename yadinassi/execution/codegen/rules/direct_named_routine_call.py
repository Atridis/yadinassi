"""Names owned by a compiled BSL routine module, not the builtin resolver."""
from yadinassi.execution.direct.python_direct_routines import bind_omissions, resolve
from yadinassi.syntax import ast as b
from ..direct_python_ast import call, literal, name


def _bind(context, key, want_value, count, omissions, non_names, references):
    module = context.vm._direct_routine_modules.get(key)
    if module is None:
        raise NameError('Переменная или функция не определена: ' + key, name=key)
    on_server = key in module.server_names
    if context._verify_context or (on_server and key not in module.dual_names):
        context._check()
    local_omissions = bool(omissions and not on_server and key not in module.dual_names)
    bound = resolve(context, key, require_value=want_value, argument_count=count,
                    allow_references=references, local_omissions=local_omissions,
                    crossing_omissions=bool(omissions and on_server),
                    non_name_actuals=non_names)
    return bind_omissions(bound) if local_omissions else bound


def _bind_invocation(context, key, want_value, count):
    # The transport owns UI protocol types. A plain CLI must not import them
    # without an actual invocation (test_plain_cli_does_not_import_ui_families).
    from yadinassi.execution.invocation import resolve_direct_invocation

    # test_invocation_port: call arity is rejected before effects, and the
    # transport must own the late reads and reply checks.
    entry = context.vm._direct_invocation_ports.get(key)
    return resolve_direct_invocation(context, key, entry, require_value=want_value, argument_count=count)


def lower(emit, key, actuals, want_value):
    if key in emit.invocation_services:
        target = call('_BindInvocationPort', name('_C'), literal(key), literal(want_value), literal(len(actuals)))
        return emit.bound_call(target, actuals, emit.omissions(actuals), crossing=True)

    # Existing procedures installed into the interpreter, and a known actual
    # server declaration, are evidenced call shapes. No builtin retry.
    if key not in emit.persistent_services and key not in emit.server_services:
        return None
    omitted = emit.omissions(actuals)
    crossing = key in emit.server_services
    references = key in emit.reference_services
    non_names = []
    for i, actual in enumerate(actuals):
        while type(actual) is b.Group:
            actual = actual.expression
        if type(actual) not in (b.Name, b.OmittedArgument):
            non_names.append(i)
    target = call('_BindNamedRoutine', name('_C'), literal(key), literal(want_value),
                  literal(len(actuals)), literal(omitted), literal(tuple(non_names)), literal(references))
    return emit.bound_call(target, actuals, omitted, references=references, crossing=crossing)


HELPERS = {'_BindNamedRoutine': _bind, '_BindInvocationPort': _bind_invocation}
