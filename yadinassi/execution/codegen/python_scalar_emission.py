"""Emit ordinary expressions as their Python syntax, adapting BSL differences.

Intrinsic result types describe syntax, regardless of whether an unrelated
statement prevents a closed-module proof. Existing proven scalar facts can
still describe references; references with unknown values need the BSL
operator boundary where Python's native behavior differs.
"""
import ast as py
from decimal import Decimal

from yadinassi.syntax import ast as bsl
from . import experimental_naked_scalar_semantics as scalar


_EQ = {'=': py.Eq, '<>': py.NotEq}
_ORDER = {'<': py.Lt, '<=': py.LtE, '>': py.Gt, '>=': py.GtE}
_ARITH = {'+': py.Add, '-': py.Sub, '*': py.Mult, '%': py.Mod}


def _leaf(node):
    while type(node) is bsl.Group:
        node = node.expression
    return node


def _literal_kind(value):
    kind = type(value)
    if kind is Decimal:
        return 'number'
    if kind is bool:
        return 'bool'
    if kind is str:
        return 'string'
    if value is None:
        return 'undefined'
    return None


class ScalarEmitter:
    def literal(self, value, token):
        kind = type(value)
        if kind is bool or kind is str or value is None:
            return self.const(value, token)
        if (self.integer_lane and kind is Decimal and value.is_finite()
                and value.as_tuple().exponent == 0
                and not (value.is_zero() and value.is_signed())):
            return self.const(int(value), token)
        index = len(self.constants)
        self.constants.append(value)
        return self.node(py.Subscript, token, value=self.name('_constants', token),
                         slice=self.const(index, token), ctx=py.Load())

    def scalar_kind(self, node, leaf=None):
        if leaf is None:
            leaf = _leaf(node)
        kind = type(leaf)
        if kind is bsl.Literal:
            return _literal_kind(leaf.value)
        if kind is bsl.Unary:
            return 'bool' if leaf.operator == 'NOT' else 'number'
        if kind is bsl.Binary:
            op = leaf.operator
            if op in ('AND', 'OR') or op in _ORDER:
                return 'bool'
            if op == '/':
                return 'number'
        facts = self.scalar_kinds
        return facts.get(id(leaf)) or (facts.get(id(node)) if node is not leaf else None)

    def truth(self, node, token):
        if self.catalog_bounds:
            # Keep metered source evaluation unchanged.
            if type(node) is bsl.Literal and type(node.value) is bool:
                return self.expr(node)
            kind = self.scalar_kinds.get(id(node))
        else:
            leaf = _leaf(node)
            if type(leaf) is bsl.Literal and type(leaf.value) is Decimal:
                return self.const(leaf.value != 0, token)
            kind = self.scalar_kind(node)
        value = self.expr(node)
        if kind == 'bool':
            return value
        if (not self.catalog_bounds and type(value) is py.Compare
                and type(leaf) is bsl.Binary and leaf.operator in _EQ):
            # The native comparison path admits only exact primitive
            # operands, so unlike the hosted equality adapter it returns bool.
            return value
        if kind == 'number':
            return self.node(py.Compare, token, left=value, ops=[py.NotEq()],
                             comparators=[self.const(0, token)])
        # Python's generic bool() would admit strings, collections and host hooks.
        return self.call('_truth', [value], token)

    def scalar_conditional(self, node):
        t = node.token
        return self.node(py.IfExp, t, test=self.truth(node.condition, t),
                         body=self.expr(node.when_true), orelse=self.expr(node.when_false))

    def scalar_unary(self, node):
        t, op = node.token, node.operator
        if op == 'NOT':
            return self.node(py.UnaryOp, t, op=py.Not(), operand=self.truth(node.operand, t))
        operand = _leaf(node.operand)
        if not self.catalog_bounds and type(operand) is bsl.Literal and type(operand.value) is Decimal:
            if not self.integer_lane or operand.value.is_zero() or operand.value.as_tuple().exponent != 0:
                # Decimal unary Python +/- may round. BSL's sign changes no precision.
                value = operand.value.copy_negate() if op == '-' else operand.value
                return self.literal(value, t)
            return self.node(py.UnaryOp, t, op=py.USub() if op == '-' else py.UAdd(),
                             operand=self.expr(node.operand))
        return self.call('_dynamic_sign' if self.integer_lane else '_sign',
                         [self.expr(node.operand), self.const(op, t)], t)

    def scalar_binary(self, node):
        t, op = node.token, node.operator
        if op in ('AND', 'OR'):
            return self.node(py.BoolOp, t, op=py.And() if op == 'AND' else py.Or(),
                             values=[self.truth(node.left, t), self.truth(node.right, t)])

        if op == '+':
            lhs, rhs = _leaf(node.left), _leaf(node.right)
            if (not self.catalog_bounds and type(lhs) is bsl.Literal
                    and type(rhs) is bsl.Literal and type(lhs.value) is str
                    and _literal_kind(rhs.value) is not None):
                return self.literal(scalar.concatenate(lhs.value, rhs.value), t)
            left, right = self.expr(node.left), self.expr(node.right)
            kind = (self.scalar_kinds.get(id(node.left)) if self.catalog_bounds
                    else self.scalar_kind(node.left, lhs))
            return self.scalar_add(node, lhs, kind, left, right)

        left, right = self.expr(node.left), self.expr(node.right)
        if op in _ARITH and not (op == '%' and self.integer_lane):
            return self.node(py.BinOp, t, left=left, op=_ARITH[op](), right=right)
        if op == '%':
            # Python's integer remainder differs for mixed signs; exact BSL zero
            # and quotient-overflow failures also belong to the decimal operation.
            return self.call('_dynamic_remainder', [left, right], t)
        if op == '/':
            return self.call('_dynamic_divide' if self.integer_lane else '_divide', [left, right], t)

        if self.catalog_bounds:
            left_kind = self.scalar_kinds.get(id(node.left))
            right_kind = self.scalar_kinds.get(id(node.right))
        else:
            left_kind = self.scalar_kind(node.left)
            right_kind = self.scalar_kind(node.right)

        if op in _EQ:
            native = (left_kind in ('number', 'bool', 'string', 'undefined')
                      and right_kind in ('number', 'bool', 'string', 'undefined'))
            if self.catalog_bounds:
                native = id(node) in self.scalar_kinds and left_kind == right_kind and left_kind in ('number', 'bool')
            if native:
                return self.node(py.Compare, t, left=left, ops=[_EQ[op]()], comparators=[right])
            return self.call('_equal' if op == '=' else '_not_equal', [left, right], t)
        if op in _ORDER:
            native = left_kind in ('number', 'bool') and right_kind in ('number', 'bool')
            if self.catalog_bounds:
                native = id(node) in self.scalar_kinds and left_kind == right_kind and left_kind in ('number', 'bool')
            if native:
                return self.node(py.Compare, t, left=left, ops=[_ORDER[op]()], comparators=[right])
            return self.call('_order', [left, right, self.const(op, t)], t)
        from .experimental_direct_ast import _reject
        _reject('unsupported expression Binary')

    def scalar_add(self, node, lhs, kind, left, right):
        t = node.token
        closed = self.static_module_kinds.get(id(node))
        if kind == 'string' or closed == 'string' or type(lhs) is bsl.Literal and type(lhs.value) is str:
            # The BSL string operator coerces the RHS and rejoins surrogate halves.
            return self.call('_concatenate', [left, right], t)
        if kind in ('number', 'bool') or closed == 'number' or type(lhs) is bsl.Literal:
            return self.node(py.BinOp, t, left=left, op=py.Add(), right=right)
        # The only adaptation is the BSL string operator. Keep one
        # occurrence of each operand in the emitted tree and execute +.
        temporary = self.temp()
        bound = self.node(py.NamedExpr, t, target=self.name(temporary, t, True), value=left)
        test = self.node(py.Compare, t, left=self.call('type', [bound], t), ops=[py.Is()],
                         comparators=[self.name('str', t)])
        saved = self.name(temporary, t)
        left = self.node(py.IfExp, t, test=test,
                         body=self.call('_TextAddend', [saved], t), orelse=saved)
        return self.node(py.BinOp, t, left=left, op=py.Add(), right=right)
