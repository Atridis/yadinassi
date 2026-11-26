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


def binary(operator, left, right):
    if operator == '+' and (
            type(left) is p.Constant and type(left.value) is str
            or type(left) is p.Call and (
                getattr(left, 'bsl_utf16_units', False)
                or type(left.func) is p.Name and left.func.id == '_String')):
        return call('_String', left, right)
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
