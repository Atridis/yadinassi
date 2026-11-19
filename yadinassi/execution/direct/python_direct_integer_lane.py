"""Compile-time proof for closed, bounded integer modules.

No value guards or runtime walks. Unsupported syntax retains Decimal lowering.
Intervals include every intermediate, not only the final result; the native
integer lane therefore does not bypass the public 38-digit Decimal precision.
"""
from decimal import Decimal, getcontext
from yadinassi.syntax import ast as bsl

_LIMIT = 10 ** 38 - 1

class _Decline(Exception):
    pass


def analyze(program):
    # Do not pay for two emitted bodies on one-off scalar statements.
    if not any(type(node) is bsl.For for node in program):
        return False
    inside_loop = False
    repeated_arithmetic = False

    def require(ok):
        if not ok:
            raise _Decline

    def bounded(lo, hi):
        require(-_LIMIT <= lo <= hi <= _LIMIT)
        return lo, hi

    def expression(node, env):
        nonlocal repeated_arithmetic
        kind = type(node)
        if inside_loop and kind in (bsl.Binary, bsl.Unary) and names(node):
            repeated_arithmetic = True
        if kind is bsl.Literal:
            value = node.value
            require(type(value) is Decimal and value.is_finite())
            require(value.as_tuple().exponent == 0 and not (value.is_zero() and value.is_signed()))
            require(-_LIMIT <= value <= _LIMIT and value == value.to_integral_value())
            return bounded(int(value), int(value))
        if kind is bsl.Name:
            require(node.name.casefold() in env)
            return env[node.name.casefold()]
        if kind is bsl.Group:
            return expression(node.expression, env)
        if kind is bsl.Unary:
            lo, hi = expression(node.operand, env)
            require(node.operator in ('+', '-'))
            require(node.operator != '-' or not (lo <= 0 <= hi))
            return bounded(lo, hi) if node.operator == '+' else bounded(-hi, -lo)
        require(kind is bsl.Binary and node.operator in ('+', '-', '*'))
        a, b = expression(node.left, env)
        c, d = expression(node.right, env)
        if node.operator == '+':
            require(not (a + c <= 0 <= b + d and (a < 0 or c < 0)))
            return bounded(a + c, b + d)
        if node.operator == '-':
            # ROUND_FLOOR preserves a negative zero on exact cancellation.
            require(not (a - d <= 0 <= b - c))
            return bounded(a - d, b - c)
        # Decimal preserves a negative zero for multiplication.
        require(not (a <= 0 <= b and c < 0) and not (c <= 0 <= d and a < 0))
        products = (a * c, a * d, b * c, b * d)
        return bounded(min(products), max(products))

    def names(node):
        if type(node) is bsl.Name:
            return {node.name.casefold()}
        if type(node) is bsl.Group:
            return names(node.expression)
        if type(node) is bsl.Unary:
            return names(node.operand)
        if type(node) is bsl.Binary:
            return names(node.left) | names(node.right)
        return set()

    env = {}
    try:
        for node in program:
            if type(node) is bsl.Assign and type(node.target) is bsl.Name:
                env[node.target.name.casefold()] = expression(node.value, env)
            elif type(node) is bsl.ExpressionStatement:
                expression(node.expression, env)
            elif type(node) is bsl.For:
                require(type(node.start) is bsl.Literal and type(node.end) is bsl.Literal)
                start = expression(node.start, env)[0]
                end = expression(node.end, env)[0]
                require(start <= end)
                bounded(start, end + 1)
                counter = node.name.casefold()
                changed = set()
                for item in node.body:
                    require(type(item) is bsl.Assign and type(item.target) is bsl.Name)
                    key = item.target.name.casefold()
                    require(key != counter and key not in changed)
                    changed.add(key)
                local = dict(env)
                local[counter] = (start, end)
                count = end - start + 1
                inside_loop = True
                for item in node.body:
                    key = item.target.name.casefold()
                    value = item.value
                    used = names(value)
                    require(not (used & (changed - {key})))
                    if key in used:
                        require(type(value) is bsl.Binary and value.operator in ('+', '-'))
                        require(type(value.left) is bsl.Name and value.left.name.casefold() == key)
                        require(key not in names(value.right) and key in env)
                        lo, hi = expression(value.right, local)
                        if value.operator == '-':
                            lo, hi = -hi, -lo
                        a, b = env[key]
                        # Union of all loop-prefix values, including the entry.
                        local[key] = bounded(a + min(0, count * lo), b + max(0, count * hi))
                        expression(value, local)  # Also prove operation intermediates.
                    else:
                        local[key] = expression(value, local)
                inside_loop = False
                env.update({key: local[key] for key in changed})
                env[counter] = (end + 1, end + 1)
            else:
                raise _Decline
        return bool(env) and repeated_arithmetic
    except _Decline:
        return False


def context_allows_integer_lane():
    """One kernel-entry decision; prepared plans may run under a new context."""
    context = getcontext()
    return (context.prec == 38 and context.Emax >= 37
            and context.Emin <= 0 and context.clamp == 0)
