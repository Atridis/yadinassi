"""Scalar adaptations which differ from ordinary Python operators."""
import ast as p
from decimal import Decimal
from yadinassi.syntax import ast as b
from ..direct_python_ast import call, literal, name

_COMPARISONS = ('=', '<>', '<', '<=', '>', '>=')
_ORDER = {'<': '_Less', '<=': '_LessEqual', '>': '_Greater', '>=': '_GreaterEqual'}

# These native calls can return a lone UTF-16 surrogate. Tag only calls already
# bound to the builtin implementation, never a user or runtime-dispatched call.
_UTF16_UNIT_PRODUCERS = frozenset((
    'char', 'символ', 'left', 'лев', 'right', 'прав', 'mid', 'сред',
))


def builtin_result(key, invocation):
    if key in _UTF16_UNIT_PRODUCERS:
        invocation.bsl_utf16_units = True
    return invocation


def condition(self,x):
    root=x
    while type(root) is b.Group:root=root.expression
    value=self.expr(x)
    if (type(root) is b.Binary and root.operator in (*_COMPARISONS,'AND','OR')
            or type(root) is b.Unary and root.operator=='NOT'
            or type(root) is b.Literal and type(root.value) in (bool,Decimal)):
        return value
    return call('_Truth',value)



def unary(emit, node):
    if node.operator == 'NOT':
        return p.UnaryOp(op=p.Not(), operand=emit.condition(node.operand))
    if type(node.operand) is b.Literal and type(node.operand.value) is Decimal:
        value = node.operand.value
        return emit.literal(value.copy_negate() if node.operator == '-' else value)
    operand = emit.temp()
    capture = p.NamedExpr(target=name(operand, True), value=emit.expr(node.operand))
    integer = p.Compare(left=call('_ValueType', capture), ops=[p.Is()], comparators=[name('_IntegerType')])
    negative = node.operator == '-'
    direct = p.UnaryOp(op=p.USub() if negative else p.UAdd(), operand=name(operand))
    if negative:
        # Unary minus on the whole number zero must retain its reported sign.
        direct = p.IfExp(test=name(operand), body=direct, orelse=name('_NegativeZero'))
    # test_context_independent_sign_and_division: Decimal unary operators
    # round in Python's active context. Its exact sign change must not.
    return p.IfExp(test=integer, body=direct,
                   orelse=call('_DecimalSign', name(operand), literal(node.operator)))


def _text_literal(node):
    return type(node) is p.Constant and type(node.value) is str


def _text_suffix(node):
    # In the native DOM captures (DM-19/DM-31), the ordinary prefix
    # S(value) + ":" is text. Only the following addition needs BSL
    # presentation of a missing attribute, not another field rule.
    return type(node) is p.BinOp and type(node.op) is p.Add and _text_literal(node.right)


def binary(operator, left, right):
    if operator == '+' and (
            _text_literal(left)
            or _text_suffix(left) and not _text_literal(right)
            or type(left) is p.Call and (
                getattr(left, 'bsl_utf16_units', False)
                or type(left.func) is p.Name and left.func.id == '_String')):
        return call('_String', left, right)
    # test_python_direct_array_equality: a pair of lists only exists when
    # neither emitted operand is a Python literal. Keep literal sites direct.
    if operator in ('=', '<>') and not any(type(value) is p.Constant for value in (left, right)):
        return call('_EqualArrays' if operator == '=' else '_UnequalArrays', left, right)
    if operator in _ORDER and not any(
            type(value) is p.Constant and type(value.value) is not str
            for value in (left, right)):
        # A prepared comparison may see a pair of strings on a later run.
        # Keep one small operator-specific call, never an operator lookup in a loop.
        return call(_ORDER[operator], left, right)
    if operator == '/':
        return call('_Divide', left, right)
    if operator == '%':
        return call('_Remainder', left, right)
    return None
