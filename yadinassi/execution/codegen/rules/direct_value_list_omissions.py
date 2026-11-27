"""Omitted optional positions in the native ValueList Add/Insert signatures."""
from yadinassi.syntax import ast as b
from ..direct_python_ast import attr, call, literal

_DEFAULTS = {'add': (None, '', False), 'insert': (None, None, '', False)}


def lower_omissions(emit, receiver, arguments, omitted, prefix, operation):
    # test_value_list_runtime: only named receivers are currently supported;
    # a required hole rejects the call before evaluating the other actuals.
    defaults = _DEFAULTS.get(operation)
    if (type(receiver) is not b.Name or defaults is None
            or any(i < (operation == 'insert') or i > len(defaults) for i in omitted)
            or len(arguments) > len(defaults) + (len(defaults) in omitted)):
        return call('_InvalidOmissions')

    actuals = [literal(defaults[i]) if i in omitted else emit.expr(argument)
               for i, argument in enumerate(arguments[:len(defaults)])]
    target = attr(emit.expr(receiver), prefix + operation + '_omitted')
    return call(target, *actuals)
