"""Closed logical-to-physical query selection, with explicit residual execution.

No backend class imports, SQL fragments, caller-provided physical names, or
semantic guessing. New operator shapes require independent equivalence proofs.
"""
from decimal import Decimal
from yadinassi.db.catalog.catalog_backend import CatalogAggregateRequest, CatalogAggregateResult, BackendError
from . import query_parser as syntax


def aggregate_shape(plan):
    q=plan.query
    if (type(q) is not syntax.Select or len(plan.sources)!=1
            or q.family!='catalog' or q.section is not None or q.temporary or q.external
            or q.derived is not None or q.into is not None or q.virtual_condition is not None
            or q.joins or q.groups or q.predicate is not None or q.having is not None
            or q.order or q.distinct
            or plan.memberships or plan.hierarchies):return False
    return True


def count_eligible(plan):
    from .relational_queries import _BoundAggregate
    if not aggregate_shape(plan) or len(plan.projections)!=1:return False
    expression=plan.projections[0]
    return (type(expression) is _BoundAggregate and expression.function=='count'
            and expression.field is None and expression.distinct is False)


def try_count(plan,view,budget):
    """Return None for an unsupported physical shape; never hide a read error."""
    if not count_eligible(plan):return None
    aggregate=getattr(view,'aggregate_catalog',None)
    if aggregate is None:return None
    if plan.enum_scope is not None:
        plan.enum_scope.require_current()
    elif plan.enum_binding is not None:
        from yadinassi.db.metadata.enum_storage_binding import EnumStorageBinding
        if type(plan.enum_binding) is not EnumStorageBinding:raise BackendError('unsupported')
        # execute() already holds the lexical read_snapshot witness. Validate
        # owner and canonical enum mappings without acquiring a second lease.
        plan.enum_binding._live()
    manager=plan.managers[0];metadata=manager._catalogs._metadata
    if ((view.database_id,view.configuration_generation)!=(metadata._database_id,metadata._generation)
            or view.catalog_schema(manager._schema.identity)!=manager._schema):
        raise BackendError('schema_changed')
    result=aggregate(manager._schema.identity,CatalogAggregateRequest())
    if plan.enum_scope is not None: plan.enum_scope.require_current()
    elif plan.enum_binding is not None: plan.enum_binding._live()
    if result is None:return None
    if type(result) is not CatalogAggregateResult or type(result.count) is not int or result.count<0:
        raise BackendError('integrity')
    from .queries import BSLQueryResult,_MAX_CELLS,_MAX_RESULT_TEXT
    # Canonical COUNT(*) load binds exactly Ref: one validated non-text cell per
    # input row. Preserve its input budget even without constructing BSL rows.
    budget[0]+=result.count
    if result.count>syntax.MAX_ROWS or budget[0]>_MAX_CELLS or budget[1]>_MAX_RESULT_TEXT:
        raise ValueError('Query input resource limit exceeded')
    if _MAX_CELLS<1:raise ValueError('Query result resource limit exceeded')
    rows=((Decimal(result.count),),) if plan.query.limit else ()
    return BSLQueryResult(plan.columns,rows)


def try_numeric(plan, view, budget):
    """Use the provider's exact numeric results for the closed aggregate shape."""
    from .relational_queries import _BoundAggregate, _BoundField
    from yadinassi.db.catalog.catalog_backend import CatalogNumericAggregateRequest, CatalogNumericAggregateResult
    from .queries import BSLQueryResult, _MAX_CELLS, _MAX_RESULT_TEXT
    from yadinassi.types.values import NULL
    from decimal import Context, ROUND_HALF_EVEN, InvalidOperation
    if not aggregate_shape(plan) or not 1 <= len(plan.projections) <= 64:return None
    operations=[]
    for expression in plan.projections:
        if type(expression) is not _BoundAggregate or expression.distinct:return None
        if expression.function=='count' and expression.field is None:
            operations.append(('count',None));continue
        field=expression.field
        if (expression.function not in ('sum','avg') or type(field) is not _BoundField
                or field.source!=0 or field.column.kind!='number' or field.column.custom is None):return None
        operations.append((expression.function,field.column.custom.identity))
    if not any(op!='count' for op,_ in operations):return None
    aggregate=getattr(view,'aggregate_catalog',None)
    if aggregate is None:return None
    if plan.enum_scope is not None:
        plan.enum_scope.require_current()
    elif plan.enum_binding is not None:
        from yadinassi.db.metadata.enum_storage_binding import EnumStorageBinding
        if type(plan.enum_binding) is not EnumStorageBinding:raise BackendError('unsupported')
        plan.enum_binding._live()
    manager=plan.managers[0];metadata=manager._catalogs._metadata
    if ((view.database_id,view.configuration_generation)!=(metadata._database_id,metadata._generation)
            or view.catalog_schema(manager._schema.identity)!=manager._schema):raise BackendError('schema_changed')
    result=aggregate(manager._schema.identity,CatalogNumericAggregateRequest(tuple(operations)))
    if plan.enum_scope is not None: plan.enum_scope.require_current()
    elif plan.enum_binding is not None: plan.enum_binding._live()
    if result is None:return None
    if (type(result) is not CatalogNumericAggregateResult or type(result.count) is not int or result.count<0
            or type(result.values) is not tuple or len(result.values)!=len(operations)):raise BackendError('integrity')
    budget[0]+=result.count*len(plan.fields[0])
    if result.count>syntax.MAX_ROWS or budget[0]>_MAX_CELLS or budget[1]>_MAX_RESULT_TEXT:
        raise ValueError('Query input resource limit exceeded')
    if len(operations)>_MAX_CELLS:raise ValueError('Query result resource limit exceeded')
    context=Context(prec=80,rounding=ROUND_HALF_EVEN,Emin=-999999,Emax=999999,traps=[InvalidOperation])
    values=[]
    for expression,(operation,_),raw in zip(plan.projections,operations,result.values):
        if operation=='count':
            if type(raw) is not int or raw!=result.count:raise BackendError('integrity')
            values.append(Decimal(raw));continue
        if result.count==0:
            if raw is not None:raise BackendError('integrity')
            values.append(NULL);continue
        if type(raw) is not Decimal:raise BackendError('integrity')
        number=raw;scale=plan.describe(expression).qualifiers[1]
        if not number.is_finite() or number.copy_abs()>=Decimal((0,(1,),38-scale)):
            raise ValueError('Query aggregate Number range exceeded')
        number=context.quantize(number,Decimal((0,(1,),-scale)))
        if number.copy_abs()>=Decimal((0,(1,),38-scale)):raise ValueError('Query aggregate Number range exceeded')
        values.append(number)
    return BSLQueryResult(plan.columns,(tuple(values),) if plan.query.limit else ())


def bounded_projection(plan):
    """Bind selected fields and the constant projection once for the final page."""
    from .relational_queries import _BoundField
    columns = []
    recipe = []
    for expression in plan.projections:
        if type(expression) is _BoundField:
            recipe.append((True, None))
            columns.append(expression.column)
        else:
            recipe.append((False, expression))
    columns = tuple(columns)
    if len(columns) == len(recipe):
        return columns, tuple

    def assemble(values):
        values = iter(values)
        return tuple(next(values) if stored else literal for stored, literal in recipe)

    return columns, assemble


def try_ordered_select(plan, view, budget=None):
    """Select a bounded physical page, then project only proven safe values."""
    from .relational_queries import _BoundField
    from yadinassi.temporal.dates import BSLDate
    from yadinassi.types.values import NULL
    q = plan.query
    if (type(q) is not syntax.Select or not 0 < q.limit < syntax.MAX_ROWS
            or len(plan.sources) != 1 or q.family not in ('catalog','document','information_register','accumulation_register')
            or q.temporary or q.external or q.derived is not None or q.into is not None
            or q.virtual_condition is not None or q.joins or plan.grouped or q.having is not None
            or plan.memberships or plan.hierarchies):
        return None
    if not q.order:
        # One proven key equality can produce a bounded point page. Other
        # unordered sources retain their existing input budgets.
        keys = ('code','ref') if q.family=='catalog' else ('ref',) if q.family=='document' else ()
        point = plan.predicate
        if (not keys or q.section is not None or type(point) is not syntax.Comparison
                or point.operator != 'eq' or type(point.field) is not _BoundField
                or point.field.source != 0 or point.field.column.field not in keys):
            return None
    for expression in plan.projections:
        kind = type(expression)
        if kind is _BoundField:
            if expression.source != 0: return None
        elif not (expression is NULL or kind is str or kind is bool or kind is Decimal or kind is BSLDate):
            # Dynamic expressions may fail on a row discarded by TOP.
            return None
    if any(type(field) is not _BoundField or field.source != 0 for field, _ in plan.orders):
        return None
    if q.distinct:
        # With TOP 1, all instances of each distinct result must have the
        # same sort key. Stable source ties then pick its first original
        # representative, even when two spellings compare equal by casefold.
        # A hidden ORDER field could otherwise select a later duplicate.
        projected = {expression.column.field for expression in plan.projections
                     if type(expression) is _BoundField}
        if q.limit != 1 or any(field.column.field not in projected for field, _ in plan.orders):
            return None
    if q.section is not None:
        if q.family not in ('catalog','document'): return None
        from .query_ordered_parts import try_ordered_parts
        return try_ordered_parts(plan,view,budget)
    if q.family in ('accumulation_register', 'information_register'):
        from .recorder_queries import RecorderQueryManager
        accumulation = q.family == 'accumulation_register'
        if accumulation or type(plan.managers[0]) is RecorderQueryManager:
            from .query_movement_order import try_ordered_movements
            return try_ordered_movements(plan, view, budget, 'accumulation' if accumulation else 'recorder')
    if q.family == 'information_register':
        from .register_queries import try_ordered_register
        return try_ordered_register(plan,view,budget)
    document = q.family == 'document'
    select = getattr(view, 'ordered_document_values' if document else 'ordered_catalog_values', None)
    if select is None: return None
    from uuid import UUID
    from yadinassi.db.catalog.catalog_backend import (
        CatalogKey, CatalogOrder, CatalogPredicate, CatalogScanRequest, CatalogValuePage, CatalogValueRow,
    )
    filtered = False
    if document:
        from yadinassi.db.document.document_backend import DocumentKey, DocumentValuePage, DocumentValueRow
        from .document_queries import _ordered_header_value
        predicates = plan.document_storage_predicate(plan.predicate, 0)
        if predicates is None:
            from yadinassi.db.sqlite.sqlite_documents import DocumentView
            from .query_ordered_predicates import bind_scalar_predicate
            if (type(view) is not DocumentView or not view._view._query_language
                    or view._view._operation_id is not None
                    or any(c.kind in ('catalog_ref','document_ref','enum_ref') for c in plan.fields[0])):
                return None
            predicate = bind_scalar_predicate(plan, ('number','date','deletion_mark'))
            if predicate is None: return None
            filtered = True
        else:
            predicate = CatalogPredicate('and', predicates) if predicates else None
        page_type, row_type, key_type = DocumentValuePage, DocumentValueRow, DocumentKey
    else:
        predicate = plan.storage_predicate(plan.predicate, 0, allow_or=True)
        if plan.predicate is not None and predicate is None: return None
        page_type, row_type, key_type = CatalogValuePage, CatalogValueRow, CatalogKey
    from .queries import BSLQueryResult, _logical, _section_value, _MAX_CELLS, _MAX_RESULT_TEXT

    # All used fields are included so the provider validates selected sort and
    # filter values too. Only the requested projection enters the BSL result.
    fields = tuple(dict.fromkeys(column.field for column in plan.fields[0]))
    ordered = {}
    for field, descending in plan.orders:
        ordered.setdefault(field.column.field, descending)
    if len(fields) > 128 or len(ordered) > 16: return None
    order = tuple(CatalogOrder(field, descending) for field, descending in ordered.items())
    manager = plan.managers[0]
    if plan.enum_scope is not None: plan.enum_scope.require_current()
    elif plan.enum_binding is not None: plan.enum_binding._live()
    if document:
        manager._check_view(view)
    else:
        metadata = manager._catalogs._metadata
        if ((view.database_id,view.configuration_generation) != (metadata._database_id,metadata._generation)
                or view.catalog_schema(manager._schema.identity) != manager._schema):
            raise BackendError('schema_changed')
    request = CatalogScanRequest(predicate,order,q.limit,string_comparison='casefold_v1')
    page = (select(manager._schema.identity, request, fields, scalar_filter=True) if filtered
            else select(manager._schema.identity, request, fields))
    if plan.enum_scope is not None: plan.enum_scope.require_current()
    elif plan.enum_binding is not None: plan.enum_binding._live()
    if page is None: return None
    if (type(page) is not page_type or type(page.rows) is not tuple
            or len(page.rows) > q.limit or page.continuation is not None):
        raise BackendError('integrity')
    ordinals = {field: i for i, field in enumerate(fields)}
    columns, project = bounded_projection(plan)
    positions = tuple(ordinals[column.field] for column in columns)
    rows, seen, text_units = [], set(), 0
    input_text = 0
    for record in page.rows:
        if type(record) is not row_type or type(record.key) is not key_type:
            raise BackendError('integrity')
        key = record.key
        identity = key.document_id if document else key.catalog_id
        if (type(key.database_id) is not UUID or type(identity) is not UUID or type(key.record_id) is not UUID
                or key.database_id != view.database_id or identity != manager._schema.identity
                or (document and (type(record.line_number) is not int or record.line_number != 0))
                or not key.record_id.int or key.record_id in seen or type(record.values) is not tuple
                or len(record.values) != len(fields)):
            raise BackendError('integrity')
        if 'ref' in ordinals:
            ref = record.values[ordinals['ref']]
            if (type(ref) is not key_type or type(ref.database_id) is not UUID
                    or type(ref.document_id if document else ref.catalog_id) is not UUID
                    or type(ref.record_id) is not UUID or ref != key):
                raise BackendError('integrity')
        seen.add(key.record_id)
        if budget is not None:
            input_text += sum(len(value) for value in record.values if type(value) is str)
        values = (_section_value(manager,column.custom,record.values[index]) if column.custom is not None
                  else _ordered_header_value(manager,column.field,record.values[index]) if document
                  else _logical(manager,column,record.values[index])
                  for column, index in zip(columns,positions))
        row = project(values)
        text_units += sum(len(value) for value in row if type(value) is str)
        rows.append(row)
        if len(rows)*len(plan.columns) > _MAX_CELLS or text_units > _MAX_RESULT_TEXT:
            raise ValueError('Query result resource limit exceeded')
    if budget is not None:
        budget[0] += len(rows)*len(fields)
        budget[1] += input_text
        if budget[0] > _MAX_CELLS or budget[1] > _MAX_RESULT_TEXT:
            raise ValueError('Query input resource limit exceeded')
    return BSLQueryResult(plan.columns,tuple(rows))
