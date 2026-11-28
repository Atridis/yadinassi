"""Direct calls with omissions observed in concrete collection signatures."""
from yadinassi.syntax import ast as b
from ..direct_python_ast import attr, call, literal

_DEFAULTS = {'add': (None, '', False), 'insert': (None, None, '', False)}


def lower_omissions(emit, receiver, arguments, omitted, prefix, operation):
    # Native collection replay and ValueTree copy: Add(Name, , Title, Width).
    # Skip the type through the column method's actual Python default.
    if operation == 'add' and len(arguments) == 4 and tuple(omitted) == (1,):
        target = attr(emit.expr(receiver), prefix + 'add_column_defaults')
        return call(target, emit.expr(arguments[0]), title=emit.expr(arguments[2]),
                    width=emit.expr(arguments[3]))
    # Native table projections select columns while leaving rows at default.
    if operation == 'copy' and len(arguments) == 2 and tuple(omitted) == (0,):
        if type(receiver) is not b.Name:
            return call('_InvalidOmissions')
        target = attr(emit.expr(receiver), prefix + 'copy_columns_only')
        return call(target, columns=emit.expr(arguments[1]))
    # test_value_list_runtime: only named receivers are currently supported;
    # a required hole rejects the call before evaluating the other actuals.
    defaults = _DEFAULTS.get(operation)
    root = receiver
    while type(root) is b.Group:
        root = root.expression
    if (type(root) is not b.Name or defaults is None
            or any(i < (operation == 'insert') or i > len(defaults) for i in omitted)
            or len(arguments) > len(defaults) + (len(defaults) in omitted)):
        return call('_InvalidOmissions')

    actuals = [literal(defaults[i]) if i in omitted else emit.expr(argument)
               for i, argument in enumerate(arguments[:len(defaults)])]
    target = attr(emit.expr(receiver), prefix + operation + '_omitted')
    return call(target, *actuals)
