"""An explicit notification invocation, not a generic builtin fallback."""
from yadinassi.execution.direct.python_direct_callback import NAMES, bind
from .direct_python_ast import call, literal, name


def _bind(context, key, count):
    return bind(context, key, context._services.get(key), argument_count=count)


def lower(emit, key, arguments):
    # test_json_handlers_interoperate_with_normal_callbacks and callback
    # runtime tests need the actual registered notification owner.
    if key not in NAMES:
        return None
    target = call('_BindNotification', name('_C'), literal(key), literal(len(arguments)))
    return emit.bound_call(target, arguments, emit.omissions(arguments))


HELPERS = {'_BindNotification': _bind}
