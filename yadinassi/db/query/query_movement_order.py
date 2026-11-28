"""Lower one flat, raw movement source to a bounded native provider read."""
from decimal import Decimal

from yadinassi.db.catalog.catalog_backend import BackendError


def try_ordered_movements(plan, view, budget, family, projection, condition):
    from .query_ordered_predicates import bind_scalar_predicate
    from .queries import BSLQueryResult, _section_value, _MAX_CELLS, _MAX_RESULT_TEXT
    from yadinassi.db.sqlite.sqlite_movement_order import ordered_movements

    manager = plan.managers[0]
    accumulation = family == 'accumulation'
    schema = manager._schema if accumulation else manager.recorder_schema
    standard = ('active', 'period') if accumulation else ('active',)
    predicate = bind_scalar_predicate(plan, condition, standard=standard)
    if condition is not None and predicate is None:
        return None
    order = {}
    for field, descending in plan.orders:
        order.setdefault(field.column.field, descending)
    if len(order) > 16:
        return None
    if view is None:
        return None
    from yadinassi.db.sqlite.sqlite_documents import DocumentView
    if type(view) is not DocumentView:
        return None
    if manager.documents._context.backend is not view._view._backend:
        raise BackendError('schema_changed')
    if plan.enum_scope is not None:
        plan.enum_scope.require_current()
    elif plan.enum_binding is not None:
        plan.enum_binding._live()
    selected = ordered_movements(view, family, schema, predicate, order, plan.query.limit)
    if plan.enum_scope is not None:
        plan.enum_scope.require_current()
    elif plan.enum_binding is not None:
        plan.enum_binding._live()
    if selected is None:
        return None

    if budget is None:
        budget = [0, 0]
    from yadinassi.temporal.dates import _from_parts
    rows, text = [], 0
    columns, project = projection
    has_recorder = any(column.field == 'recorder' for column in columns)
    has_period = any(column.field == 'period' for column in columns)
    for key, row in selected:
        raw = row.dimensions + row.resources + row.attributes if accumulation else row.values
        values = {field.identity: _section_value(manager, field, value)
                  for field, value in zip(schema.fields, raw)}
        budget[0] += len(values) + (5 if accumulation else 3)
        budget[1] += sum(len(value) for value in values.values() if type(value) is str)
        if budget[0] > _MAX_CELLS or budget[1] > _MAX_RESULT_TEXT:
            raise ValueError('Query input resource limit exceeded')
        values.update(active=row.active, line_number=Decimal(row.line_number))
        if accumulation and has_period:
            date = row.period
            values['period'] = _from_parts((date.year, date.month, date.day, date.hour, date.minute, date.second))
        if has_recorder:
            values['recorder'] = manager._documents_by_id[key.document_id]._ref(key.record_id)
        projected = project(values[column.field] for column in columns)
        rows.append(projected)
        text += sum(len(value) for value in projected if type(value) is str)
        if len(rows) * len(plan.columns) > _MAX_CELLS or text > _MAX_RESULT_TEXT:
            raise ValueError('Query result resource limit exceeded')
    return BSLQueryResult(plan.columns, tuple(rows))
