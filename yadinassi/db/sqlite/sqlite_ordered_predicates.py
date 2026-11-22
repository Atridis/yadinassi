"""Closed SQL predicates for exact, provider-resolved physical scalar columns."""
from datetime import datetime
from decimal import Decimal
from uuid import UUID

from yadinassi.db.catalog.catalog_backend import BackendError, CatalogComparison, CatalogPredicate, FieldSchema
from .sqlite_catalog_numbers import comparison

_OPERATORS = {'eq':'=', 'ne':'!=', 'lt':'<', 'le':'<=', 'gt':'>', 'ge':'>='}


def ordered_where(predicate, fields):
    """Render exact scalar clauses against a provider-defined field map."""
    if type(predicate) is CatalogPredicate:
        if (type(predicate.kind) is not str or predicate.kind not in ('and','or')
                or type(predicate.terms) is not tuple or not predicate.terms):
            raise BackendError('invalid_input')
        terms = tuple(ordered_where(term, fields) for term in predicate.terms)
        joiner = ' AND ' if predicate.kind == 'and' else ' OR '
        return '(' + joiner.join(part for part,_ in terms) + ')', tuple(v for _,args in terms for v in args)
    if (type(predicate) is not CatalogComparison or type(predicate.field) not in (str, UUID)
            or type(predicate.operator) is not str or predicate.operator not in _OPERATORS
            or predicate.field not in fields):
        raise BackendError('invalid_input')
    definition, column = fields[predicate.field]
    kind = definition.kind if type(definition) is FieldSchema else definition
    operator, value = predicate.operator, predicate.value
    if kind == 'number' and type(definition) is FieldSchema and type(value) is Decimal and value.is_finite():
        return comparison(column, definition, operator, value)
    if kind == 'string' and type(value) is str:
        pass
    elif kind == 'boolean' and type(value) is bool and operator in ('eq','ne'):
        value = int(value)
    elif kind == 'datetime' and type(value) is datetime and value.tzinfo is None and not value.microsecond:
        value = '%04d%02d%02d%02d%02d%02d' % (value.year,value.month,value.day,value.hour,value.minute,value.second)
    else:
        raise BackendError('invalid_input')
    return f'({column} {_OPERATORS[operator]} ?)', (value,)
