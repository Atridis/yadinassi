"""Bind an entire flat, non-throwing scalar predicate or decline it."""
from decimal import Decimal

from . import query_parser as syntax
from yadinassi.db.catalog.catalog_backend import CatalogComparison, CatalogFieldComparison, CatalogPredicate
from yadinassi.temporal.dates import BSLDate, TICKS_PER_SECOND, _parts


def total_number(plan, value):
    # The residual evaluator range-checks literals only when reached. Decline
    # here without either moving that error earlier or letting SQL hide it.
    try:
        plan.checked_number(value,plan.describe(value).qualifiers[1])
    except (ArithmeticError,ValueError):
        return False
    return True


def bind_field_comparison(node, source):
    from .relational_queries import _BoundField
    left,right = node.field,node.value
    if type(left) is not _BoundField or type(right) is not _BoundField:
        return None
    if left.source != source or right.source != source:
        return None
    if (left.column.kind != right.column.kind
            or left.column.kind not in ('string','number','datetime','boolean')
            or node.operator not in ('eq','ne','lt','le','gt','ge')):
        return None
    return CatalogFieldComparison(left.column.field,node.operator,right.column.field)


def bind_scalar_predicate(plan, condition, standard=(), *, allow_or=True, reference=None,
                          field_pairs=False, standard_leaf=None):
    from .relational_queries import _BoundField

    def bind(node):
        if type(node) is syntax.Predicate and node.kind in (('and', 'or') if allow_or else ('and',)):
            terms = tuple(bind(term) for term in node.terms)
            if terms and all(term is not None for term in terms):
                return CatalogPredicate(node.kind, terms)
            return None
        if (type(node) is not syntax.Comparison or type(node.field) is not _BoundField
                or node.field.source != 0 or node.operator not in ('eq','ne','lt','le','gt','ge')):
            return None
        column, value = node.field.column, node.value
        if field_pairs and type(value) is _BoundField:
            if any(item.custom is None and item.field not in standard
                   for item in (column,value.column)):
                return None
            return bind_field_comparison(node,0)
        if standard_leaf is not None and column.custom is None:
            result = standard_leaf(node,0)
            return result[0] if result else None
        if column.custom is None and column.field not in standard:
            return None
        if column.kind == 'string' and type(value) is str:
            try: value.encode('utf-8')
            except UnicodeEncodeError: return None
        elif column.kind == 'number' and type(value) is Decimal and (column.custom is not None or column.field == 'line_number'):
            if not value.is_finite() or (field_pairs and not total_number(plan,value)): return None
        elif column.kind == 'boolean' and type(value) is bool and node.operator in ('eq','ne'):
            pass
        elif column.kind == 'datetime' and type(value) is BSLDate:
            if value.boundary or value.ticks % TICKS_PER_SECOND: return None
            value = _parts(value)
        elif reference is not None and column.kind in ('catalog_ref', 'document_ref') and node.operator in ('eq', 'ne'):
            value = reference(node.field, value)
            if value is None: return None
        else:
            return None
        return CatalogComparison(column.field,node.operator,value)

    return bind(condition)
