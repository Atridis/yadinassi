"""Bind an entire flat, non-throwing scalar predicate or decline it."""
from decimal import Decimal

from . import query_parser as syntax
from yadinassi.db.catalog.catalog_backend import CatalogComparison, CatalogPredicate
from yadinassi.temporal.dates import BSLDate, TICKS_PER_SECOND, _parts


def bind_scalar_predicate(plan, standard=()):
    from .relational_queries import _BoundField

    def bind(node):
        if type(node) is syntax.Predicate and node.kind in ('and', 'or'):
            terms = tuple(bind(term) for term in node.terms)
            if terms and all(term is not None for term in terms):
                return CatalogPredicate(node.kind, terms)
            return None
        if (type(node) is not syntax.Comparison or type(node.field) is not _BoundField
                or node.field.source != 0 or node.operator not in ('eq','ne','lt','le','gt','ge')):
            return None
        column, value = node.field.column, node.value
        if column.custom is None and column.field not in standard:
            return None
        if column.kind == 'string' and type(value) is str:
            try: value.encode('utf-8')
            except UnicodeEncodeError: return None
        elif column.kind == 'number' and type(value) is Decimal and (column.custom is not None or column.field == 'line_number'):
            if not value.is_finite(): return None
        elif column.kind == 'boolean' and type(value) is bool and node.operator in ('eq','ne'):
            pass
        elif column.kind == 'datetime' and type(value) is BSLDate:
            if value.boundary or value.ticks % TICKS_PER_SECOND: return None
            value = _parts(value)
        else:
            return None
        return CatalogComparison(column.field,node.operator,value)

    return bind(plan.predicate)
