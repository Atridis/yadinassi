"""Small, error-preserving simplifications of bound query conditions."""
from decimal import Decimal

from yadinassi.types.values import NULL
from . import query_parser as syntax
from .query_count import constant_condition


def without_neutral_terms(plan, node):
    """Drop only AND TRUE and OR FALSE, preserving unknown and evaluation order."""
    if type(node) is not syntax.Predicate or node.kind not in ('and', 'or'):
        return node
    identity = node.kind == 'and'
    terms = []
    for term in node.terms:
        normalized = without_neutral_terms(plan, term)
        proved, truth = constant_condition(plan, normalized)
        if not proved or truth is not identity:
            terms.append(normalized)
    if not terms:
        return node
    if len(terms) == 1:
        return terms[0]
    return syntax.Predicate(node.kind, tuple(terms))


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
