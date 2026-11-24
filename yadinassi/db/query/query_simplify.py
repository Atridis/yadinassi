"""Small, error-preserving simplifications of bound query conditions."""
from decimal import Decimal
from uuid import UUID

from yadinassi.types.values import NULL
from . import query_parser as syntax
from .query_count import constant_condition


def normalize_condition(plan, node):
    """Remove neutral terms and repeats of proven-total bound conditions."""
    if type(node) is not syntax.Predicate or node.kind not in ('and', 'or'):
        return node
    identity = node.kind == 'and'
    terms = []
    seen = set()
    for term in node.terms:
        normalized = normalize_condition(plan, term)
        proved, truth = constant_condition(plan, normalized)
        if proved and truth is identity:
            continue
        key = _comparison_key(plan, normalized)
        if key is not None:
            if key in seen:
                continue
            seen.add(key)
        terms.append(normalized)
    if not terms:
        return node
    if len(terms) == 1:
        return terms[0]
    if len(terms) == len(node.terms) and all(a is b for a, b in zip(terms, node.terms)):
        return node
    return syntax.Predicate(node.kind, tuple(terms))


def _comparison_key(plan, node):
    from .relational_queries import _BoundField

    if type(node) is not syntax.Comparison or not total_scalar_condition(plan, node):
        return None

    def operand(value):
        if type(value) is _BoundField:
            field = value.column.field
            if type(field) is str or type(field) is int or type(field) is UUID:
                return ('field', value.source, value.column.kind, field)
        elif value is NULL or type(value) is str or type(value) is bool or type(value) is Decimal:
            return (type(value), value)
        return None

    left = operand(node.field)
    if left is None:
        return None
    if node.operator in ('is_null', 'is_not_null'):
        return (node.operator, left)
    right = operand(node.value)
    if right is None:
        return None
    if node.operator in ('eq', 'ne'):
        return (node.operator, frozenset((left, right)))
    return (node.operator, left, right)


def total_scalar_condition(plan, node):
    """Prove no runtime error or correlated work can be lost by skipping it."""
    from .query_ordered_predicates import total_number
    from .relational_queries import _BoundField

    if type(node) is syntax.Predicate:
        return all(total_scalar_condition(plan, term) for term in node.terms)
    if type(node) is not syntax.Comparison:
        return False
    proved, _ = constant_condition(plan, node)
    if proved:
        return True

    def total(value):
        if type(value) is _BoundField:
            return value.column.kind in ('string', 'boolean', 'number')
        if type(value) is Decimal:
            return total_number(plan, value)
        return value is NULL or type(value) in (str, bool)

    # The binder has already checked operand types and accepted operators.
    return total(node.field) and (node.operator in ('is_null', 'is_not_null')
                                  or total(node.value))
