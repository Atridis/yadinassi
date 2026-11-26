"""Scalar adaptations which differ from ordinary Python operators."""
import ast as p
from decimal import Decimal
from yadinassi.syntax import ast as b
from .direct_python_ast import call, literal

_COMPARISONS = ('=', '<>', '<', '<=', '>', '>=')


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
    return call('_Sign', emit.expr(node.operand), literal(node.operator))


def binary(operator, left, right):
    if operator == '+' and (
            type(left) is p.Constant and type(left.value) is str
            or type(left) is p.Call and type(left.func) is p.Name and left.func.id == '_String'):
        return call('_String', left, right)
    if operator in ('<', '<=', '>', '>=') and not any(
            type(value) is p.Constant and type(value.value) is not str
            for value in (left, right)):
        # Ordering for two possible strings uses BSL collation; equality never does.
        return call('_CompareOrder', left, right, literal(operator))
    if operator == '/':
        return call('_Divide', left, right)
    if operator == '%':
        return call('_Remainder', left, right)
    return None
