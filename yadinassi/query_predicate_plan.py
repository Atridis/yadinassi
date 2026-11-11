"""Conservative source filters for an already bound all-INNER query region.

This is not a second binder or a join reorderer. The original WHERE and ON remain
residuals. Any expression whose skipped evaluation might throw disables the
rewrite, including an earlier ON expression that WHERE would otherwise hide.
"""
from decimal import Decimal
from . import query_parser as syntax
from .catalog_types import BSLCatalogReference
from .document_types import BSLDocumentReference
from .dates import BSLDate

_OPERATORS = ('eq', 'ne', 'lt', 'le', 'gt', 'ge')
_REVERSE = {'eq': 'eq', 'ne': 'ne', 'lt': 'gt', 'le': 'ge', 'gt': 'lt', 'ge': 'le'}
_CONSTANTS = (str, bool, Decimal, BSLDate, BSLCatalogReference, BSLDocumentReference)


def inner_source_predicates(plan):
    """Return source-local *bound* conjunctions, or no rewrite for this region."""
    from .relational_queries import _BoundField
    empty = (None,) * len(plan.sources)
    if not plan.query.joins or any(join.kind != 'inner' for join in plan.query.joins):
        return empty
    if any(source.derived is not None or source.temporary or source.external
           or source.section is not None or source.family not in ('catalog', 'document')
           for source in plan.sources):
        return empty

    def value(expression):
        if type(expression) is Decimal:
            # Literal range checking also occurs at evaluation, not just bind.
            # Do not move it earlier or hide it on a row excluded by a filter.
            try: plan.checked_number(expression, plan.describe(expression).qualifiers[1])
            except (ValueError, TypeError): return False
        return type(expression) is _BoundField or type(expression) in _CONSTANTS

    def total(node):
        if node is None: return True
        if type(node) is syntax.Predicate:
            return node.kind == 'and' and all(total(term) for term in node.terms)
        return (type(node) is syntax.Comparison and node.operator in _OPERATORS
                and value(node.field) and value(node.value))

    if not total(plan.predicate) or any(not total(node) for node in plan.joins):
        return empty

    def terms(node):
        if type(node) is syntax.Predicate:
            for term in node.terms: yield from terms(term)
        elif node is not None:
            yield node

    output = [[] for _ in plan.sources]
    for term in terms(plan.predicate):
        left, right, operator = term.field, term.value, term.operator
        if type(left) in _CONSTANTS and type(right) is _BoundField:
            left, right, operator = right, left, _REVERSE[operator]
        if type(left) is not _BoundField or type(right) not in _CONSTANTS:
            continue
        normalized = syntax.Comparison(left, operator, right)
        # Reuse the existing closed storage translators. Unsupported fields are
        # still evaluated in the full original residual, never guessed as SQL.
        if plan.sources[left.source].family == 'document':
            supported = plan.document_storage_predicate(normalized, left.source)
        else:
            supported = plan.storage_predicate(normalized, left.source)
        # Storage counts the outer AND as one of its 64 predicate nodes.
        # A safe subset remains useful; every omitted term stays residual.
        if supported and len(output[left.source]) < 63:
            output[left.source].append(normalized)
    return tuple(None if not items else items[0] if len(items) == 1
                 else syntax.Predicate('and', tuple(items)) for items in output)
