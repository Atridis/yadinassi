"""Closed scalar projections over a single structural COUNT result."""
from dataclasses import dataclass
from decimal import Decimal

from yadinassi.db.catalog.catalog_backend import BackendError
from yadinassi.temporal.dates import BSLDate
from yadinassi.types.values import NULL
from . import query_parser as syntax

_ARITHMETIC = frozenset(('+', '-', '*', '/', 'unary+', 'unary-'))
_SCALAR_LITERAL_TYPES = frozenset(map(id, (str, bool, Decimal, BSLDate)))


def constant_condition(plan, node):
    """Prove a row-independent truth, including SQL unknown; never run effects."""
    from .query_pushdown import _numeric_constant

    def inert(value):
        return (value is NULL or type(value) is str or type(value) is bool or type(value) is Decimal
                or type(value) is syntax.Expression and _numeric_constant(plan, value) is not None)

    def closed(condition):
        if type(condition) is syntax.Predicate:
            return all(closed(term) for term in condition.terms)
        return (type(condition) is syntax.Comparison and inert(condition.field)
                and (condition.operator in ('is_null', 'is_not_null') or inert(condition.value)))

    if not closed(node): return False, None
    try:
        return True, plan.test(node, ())
    except (ArithmeticError, TypeError, ValueError):
        # The existing residual decides whether the expression is reached.
        return False, None


@dataclass(frozen=True, slots=True)
class CountShape:
    include: bool
    deletion_mark: bool | None = None
    distinct_ref: bool = False
    full_input: bool = False


def bind(plan):
    from .relational_queries import _BoundAggregate, _BoundField

    q = plan.query
    if (type(q) is not syntax.Select or len(plan.sources) != 1
            or q.temporary or q.external or q.derived is not None or q.into is not None
            or q.joins or q.groups or q.having is not None or q.distinct
            or q.virtual_condition is not None or plan.memberships or plan.hierarchies):
        return None
    # Catalog flat headers have a payload-independent row count; SQLite
    # document counts can supply a separate whole-source budget witness.
    if q.family not in ('catalog','document') or (q.family=='catalog' and q.section is not None):
        return None
    if any(not any(order is item for item in plan.projections) for order, _ in plan.orders):
        return None

    counted = distinct_ref = False
    def closed(value):
        nonlocal counted, distinct_ref
        kind = type(value)
        if kind is _BoundAggregate:
            field = value.field
            identity = (type(field) is _BoundField and field.source == 0
                        and field.column.field == 'ref' and field.column.custom is None)
            if (value.function != 'count' or field is not None and not identity
                    or value.distinct and (not identity or q.section is not None)):
                return False
            counted = True
            distinct_ref |= value.distinct
            return True
        if kind is syntax.Expression:
            return value.operator in _ARITHMETIC and all(closed(item) for item in value.arguments)
        return value is NULL or id(kind) in _SCALAR_LITERAL_TYPES

    if not all(closed(item) for item in plan.projections) or not counted:
        return None
    from .query_simplify import normalize_condition
    predicate = normalize_condition(plan, plan.predicate)
    if predicate is None: return CountShape(True, distinct_ref=distinct_ref)
    if q.section is None and type(predicate) is syntax.Comparison and predicate.operator == 'eq':
        field, value = predicate.field, predicate.value
        if (type(field) is _BoundField and field.source == 0
                and field.column.field == 'deletion_mark' and field.column.custom is None
                and type(value) is bool):
            # The residual scanned all headers when its original predicate
            # could not be sent to storage. Normalizing must keep that input
            # budget, not charge only the rows surviving the normalized filter.
            full_input = (q.family == 'catalog' and predicate is not plan.predicate
                          and plan.storage_predicate(plan.predicate, 0) is None)
            return CountShape(True, value, distinct_ref, full_input)
    proved, truth = constant_condition(plan, predicate)
    if not proved: return None
    return CountShape(truth is True, distinct_ref=distinct_ref)


def owned_sqlite_query_view(view, context):
    from yadinassi.db.sqlite.sqlite_catalog import SQLiteCatalogBackend, _View
    from yadinassi.db.sqlite.sqlite_documents import DocumentView

    # Other ports and views, including explicit writers, retain their existing
    # raw projection/validation behavior. Native record_id is defined NOT NULL.
    if type(view) is not DocumentView or type(view._view) is not _View:
        return False
    raw = view._view
    backend = raw._backend
    if (type(backend) is not SQLiteCatalogBackend or not raw._query_language
            or raw._operation_id is not None):
        return False
    if backend is not context.backend:
        raise BackendError('schema_changed')
    return backend.storage_version >= 2


def project(plan, count):
    from .relational_queries import _BoundAggregate
    number = Decimal(count)
    def replace(expression):
        if type(expression) is _BoundAggregate: return number
        if type(expression) is syntax.Expression:
            return syntax.Expression(expression.operator, tuple(replace(item) for item in expression.arguments))
        return expression
    return tuple(plan.value(replace(item), ()) for item in plan.projections)


def try_document(plan, view, budget, shape):
    from yadinassi.db.sqlite.sqlite_document_count import count
    from .queries import BSLQueryResult, _MAX_CELLS, _MAX_RESULT_TEXT

    if not owned_sqlite_query_view(view, plan.catalogs._context): return None
    manager, section = plan.managers[0], plan.sections[0]
    manager._check_view(view)
    proof = count(view, manager._schema, section, deletion_mark=shape.deletion_mark)
    if proof is None: return None
    holders, selected, cells, text = proof
    budget[0] += cells
    budget[1] += text
    if max(holders,selected)>syntax.MAX_ROWS: raise ValueError('Query input row limit exceeded')
    if budget[0]>_MAX_CELLS or budget[1]>_MAX_RESULT_TEXT:
        raise ValueError('Query input resource limit exceeded')
    row = project(plan, selected if shape.include else 0)
    if len(row)>_MAX_CELLS or sum(len(value) for value in row if type(value) is str)>_MAX_RESULT_TEXT:
        raise ValueError('Query result resource limit exceeded')
    return BSLQueryResult(plan.columns, (row,) if plan.query.limit else ())
