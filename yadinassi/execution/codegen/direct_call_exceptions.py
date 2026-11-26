"""Standalone call differences from Python, limited to reproduced failures."""
import ast as py

from yadinassi.execution.direct.python_direct_eval import evaluate
from yadinassi.execution.direct.python_direct_fill import fill_plain
from yadinassi.syntax import ast as bsl


def _invalid_eval_call():
    raise TypeError('Вычислить ожидает 1 аргумент')


def _call(name, args=(), keywords=()):
    return py.Call(func=py.Name(id=name, ctx=py.Load()), args=list(args), keywords=list(keywords))


def lower(emit, key, arguments):
    """Return an explicit operation, or None for an ordinary Python call."""
    if key in ('eval', 'вычислить'):
        # test_eval: caller locals must stay live, and wrong arity must not
        # evaluate any argument.
        if len(arguments) != 1 or type(arguments[0]) is bsl.OmittedArgument:
            return _call('_InvalidEvalCall')
        return _call('_DynamicEval', (emit.expr(arguments[0]), *emit.fragment_arguments()))
    if key in ('fillpropertyvalues', 'заполнитьзначениясвойств'):
        # test_python_direct_fill_structure: language-native structures and
        # detached rows must use the same copy semantics as boxed structures.
        actuals = (py.Constant(value=None) if type(arg) is bsl.OmittedArgument else emit.expr(arg)
                   for arg in arguments)
        return _call('_FillProperties', actuals, (py.keyword(arg='_context', value=py.Name(id='_C', ctx=py.Load())),))
    return None


HELPERS = {
    '_DynamicEval': evaluate,
    '_InvalidEvalCall': _invalid_eval_call,
    '_FillProperties': fill_plain,
}
