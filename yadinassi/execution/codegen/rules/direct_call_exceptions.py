"""Standalone call differences from Python, limited to reproduced failures."""
from yadinassi.execution.direct.python_direct_eval import evaluate
from yadinassi.execution.direct.python_direct_fill import fill_plain
from yadinassi.execution.direct.python_direct_names import CHARS_ALIASES
from yadinassi.syntax import ast as bsl
from ..direct_python_ast import call, literal, name


def _not_callable(key):
    raise TypeError('Значение не является функцией: ' + key)


def _invalid_eval_call():
    raise TypeError('Вычислить ожидает 1 аргумент')


# The tests below distinguish a required hole from an explicitly supplied
# Undefined: reject the hole before evaluating the other actuals.
_REQUIRED_POSITIONS = {
    'strfind': 2, 'стрнайти': 2,               # test_str_find_extended
    'readjson': 1, 'прочитатьjson': 1,         # test_json_conversion
    'writejson': 2, 'записатьjson': 2,         # test_json_conversion
}


def lower(emit, key, arguments):
    """Return an explicit operation, or None for an ordinary Python call."""
    # test_direct_namespace_rejections_are_catchable_without_calling_arguments:
    # this field-only namespace rejects a call while binding its target.
    # Local and published routines have already had precedence.
    if key in CHARS_ALIASES:
        return call('_NotCallable', literal(key))
    # Dates reject omitted components (native date.construct.omitted).
    # Message rejects holes before any actual can write to the output.
    required = (len(arguments) if key in ('date', 'дата', 'message', 'сообщить')
                else _REQUIRED_POSITIONS.get(key))
    if required is not None and any(type(arg) is bsl.OmittedArgument for arg in arguments[:required]):
        return call('_InvalidOmissions')
    if key in ('eval', 'вычислить'):
        # test_eval: caller locals must stay live, and wrong arity must not
        # evaluate any argument.
        if len(arguments) != 1 or type(arguments[0]) is bsl.OmittedArgument:
            return call('_InvalidEvalCall')
        return call('_DynamicEval', emit.expr(arguments[0]), *emit.fragment_arguments())
    if key in ('fillpropertyvalues', 'заполнитьзначениясвойств'):
        # test_python_direct_fill_structure: language-native structures and
        # detached rows must use the same copy semantics as boxed structures.
        actuals = (literal(None) if type(arg) is bsl.OmittedArgument else emit.expr(arg)
                   for arg in arguments)
        return call('_FillProperties', *actuals, _context=name('_C'))
    return None


HELPERS = {
    '_DynamicEval': evaluate,
    '_NotCallable': _not_callable,
    '_InvalidEvalCall': _invalid_eval_call,
    '_FillProperties': fill_plain,
}
