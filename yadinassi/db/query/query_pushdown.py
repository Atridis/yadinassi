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
    if aggregate_shape(plan) and len(plan.projections) == 1:
        expression = plan.projections[0]
        if (type(expression) is _BoundAggregate and expression.function == 'count'
                and expression.field is None and expression.distinct is False):
            return True
    if not plan.grouped:
        return False
    from .query_count import bind
    return bind(plan)


def try_count(plan,view,budget):
    """Return None for an unsupported physical shape; never hide a read error."""
    if type(plan.query) is syntax.Select and plan.query.family == 'information_register':
        from .register_queries import try_count_register
        return try_count_register(plan,view,budget)
    shape = count_eligible(plan)
    if not shape:return None
    if plan.query.family == 'document':
        from .query_count import try_document
        return try_document(plan, view, budget, shape)
    if shape is not True:
        from .query_count import owned_sqlite_query_view
        if not owned_sqlite_query_view(view, plan.catalogs._context): return None
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
    request = (CatalogAggregateRequest() if shape is True else
               CatalogAggregateRequest("count_query_headers_v1", shape.deletion_mark)
               if shape.distinct_ref or shape.deletion_mark is not None else
               CatalogAggregateRequest("count_query_keys_v1"))
    result=aggregate(manager._schema.identity,request)
    if plan.enum_scope is not None: plan.enum_scope.require_current()
    elif plan.enum_binding is not None: plan.enum_binding._live()
    if result is None:return None
    if type(result) is not CatalogAggregateResult or type(result.count) is not int or result.count<0:
        raise BackendError('integrity')
    from .queries import BSLQueryResult,_MAX_CELLS,_MAX_RESULT_TEXT
    # Only exact Ref and DeletionMark input fields are admitted. Preserve
    # both cell charges when the aggregate and WHERE refer to distinct fields.
    input_count = result.count
    if shape is not True and shape.full_input:
        input_count = result.input_count
        if type(input_count) is not int or input_count < result.count:
            raise BackendError('integrity')
    budget[0] += input_count
    if shape is not True and shape.deletion_mark is not None and len(plan.fields[0]) == 2:
        budget[0] += input_count  # Ref and DeletionMark are both bound.
    if input_count>syntax.MAX_ROWS or budget[0]>_MAX_CELLS or budget[1]>_MAX_RESULT_TEXT:
        raise ValueError('Query input resource limit exceeded')
    if shape is True:
        if _MAX_CELLS<1:raise ValueError('Query result resource limit exceeded')
        rows=((Decimal(result.count),),) if plan.query.limit else ()
    else:
        from .query_count import project
        row = project(plan, result.count if shape.include else 0)
        if len(row)>_MAX_CELLS or sum(len(value) for value in row if type(value) is str)>_MAX_RESULT_TEXT:
            raise ValueError('Query result resource limit exceeded')
        rows=(row,) if plan.query.limit else ()
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


def _numeric_constant(plan, expression):
    """Evaluate only a closed tree of exact Decimal arithmetic, once."""
    pending = [expression]
    while pending:
        node = pending.pop()
        if type(node) is Decimal:
            continue
        if (type(node) is not syntax.Expression or type(node.operator) is not str
                or type(node.arguments) is not tuple):
            return None
        if node.operator in ('unary+', 'unary-'):
            if len(node.arguments) != 1: return None
        elif node.operator in ('+', '-', '*', '/'):
            if len(node.arguments) != 2: return None
        else:
            return None
        pending.extend(node.arguments)
    try:
        value = plan.value(expression, ())
    except (ArithmeticError, ValueError):
        # The residual evaluator raises at the ordinary point, if it reaches
        # an input row at all. TOP on an empty source must not gain an error.
        return None
    return value if type(value) is Decimal else None



_REVERSED_COMPARISON = {'eq':'eq','ne':'ne','lt':'gt','le':'ge','gt':'lt','ge':'le'}


def _ordered_predicate(plan):
    """Canonicalize the bound SQL candidate, never the residual predicate."""
    if plan.predicate is None: return None
    from .relational_queries import _BoundField, BSLDate, BSLCatalogReference, BSLDocumentReference
    from .query_ordered_predicates import total_number

    def constant(value):
        if type(value) is Decimal or type(value) is str or type(value) is bool:
            return value
        if type(value) is syntax.Expression:
            return _numeric_constant(plan, value)
        return None

    def normalize(node):
        if type(node) is syntax.Predicate and node.kind in ('and','or'):
            identity = node.kind == 'and'
            terms = []
            for term in node.terms:
                normalized, truth = normalize(term)
                # Neutral terms preserve both SQL unknown and the order in
                # which the remaining terms can short-circuit or raise.
                if truth is not identity: terms.append((normalized,truth))
            if not terms: return node,identity
            if len(terms) == 1: return terms[0]
            return syntax.Predicate(node.kind,tuple(term for term,_ in terms)),None
        if type(node) is not syntax.Comparison or node.operator not in _REVERSED_COMPARISON:
            return node,None
        left,right = node.field,node.value
        if type(right) is _BoundField:
            kind = type(left)
            if (kind is str or kind is bool or kind is BSLDate or kind is BSLCatalogReference
                    or kind is BSLDocumentReference or (kind is Decimal and total_number(plan,left))):
                return syntax.Comparison(right,_REVERSED_COMPARISON[node.operator],left),None
            return node,None
        if type(left) is _BoundField: return node,None
        a,b = constant(left),constant(right)
        if a is not None and b is not None:
            try:
                truth = plan.test(syntax.Comparison(a,node.operator,b),())
            except (ArithmeticError,TypeError,ValueError):
                pass  # If reached, the unchanged residual reports the error.
            else:
                if type(truth) is bool: return node,truth
        return node,None

    normalized,truth = normalize(plan.predicate)
    # Do not invent a new unfiltered or empty route for constant-only WHERE.
    return normalized if truth is None else plan.predicate

def _constant_case_arm(plan, expression):
    """Choose a row-independent, non-numeric arm without changing its result type."""
    from .query_count import constant_condition
    while type(expression) is syntax.Expression and expression.operator == 'case':
        # Numeric CASE applies its merged scale/range to the chosen value.
        # Do not skip a range error on a row beyond the physical TOP page.
        if plan.describe(expression).kind not in ('string', 'boolean', 'datetime', 'null'):
            return None
        branches, otherwise = expression.arguments
        for condition, branch in branches:
            proved, truth = constant_condition(plan, condition)
            if not proved:
                return None
            if truth is True:
                expression = branch
                break
        else:
            expression = otherwise
    return expression


def bounded_projection(plan):
    """Prove and bind the final-page projection without changing descriptors."""
    from .relational_queries import _BoundField
    from yadinassi.temporal.dates import BSLDate
    from yadinassi.types.values import NULL
    columns = []
    recipe = []
    for expression in plan.projections:
        if type(expression) is syntax.Expression and expression.operator == 'case':
            expression = _constant_case_arm(plan, expression)
            if expression is None:
                return None
        kind = type(expression)
        if kind is _BoundField:
            if expression.source != 0: return None
            recipe.append((True, None))
            columns.append(expression.column)
        else:
            if kind is syntax.Expression:
                expression = _numeric_constant(plan, expression)
                if expression is None: return None
            elif not (expression is NULL or kind is str or kind is bool or kind is Decimal or kind is BSLDate):
                return None
            recipe.append((False, expression))
    columns = tuple(columns)
    if len(columns) == len(recipe):
        return columns, tuple

    def assemble(values):
        values = iter(values)
        return tuple(next(values) if stored else literal for stored, literal in recipe)

    return columns, assemble


def _witnessed_case_projection(plan):
    from .query_simplify import total_scalar_condition
    from .relational_queries import _BoundField

    fields = []
    simplified = False
    for expression in plan.projections:
        if type(expression) is syntax.Expression and expression.operator == 'case':
            # Numeric CASE also performs its merged-scale representability
            # check on every row. It cannot be replaced by a plain field.
            if plan.describe(expression).kind not in ('string', 'boolean', 'datetime'):
                return None
            branches, otherwise = expression.arguments
            if (type(otherwise) is not _BoundField
                    or not all(type(result) is _BoundField and result == otherwise
                               and total_scalar_condition(plan, condition)
                               for condition, result in branches)):
                return None
            expression = otherwise
            simplified = True
        if (type(expression) is not _BoundField or expression.source != 0
                or expression.column.kind not in ('string', 'boolean', 'number', 'datetime')):
            return None
        fields.append(expression.column)
    return (tuple(fields), tuple) if simplified else None


def try_ordered_select(plan, view, budget=None):
    """Select a bounded physical page, then project only proven safe values."""
    from .relational_queries import _BoundField
    q = plan.query
    if (type(q) is not syntax.Select or not 0 < q.limit < syntax.MAX_ROWS
            or len(plan.sources) != 1 or q.family not in ('catalog','document','information_register','accumulation_register')
            or q.temporary or q.external or q.derived is not None or q.into is not None
            or q.virtual_condition is not None or q.joins or plan.grouped or q.having is not None
            or plan.memberships or plan.hierarchies):
        return None
    if not q.order and (q.family not in ('catalog','document') or q.section is not None):
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
    projection = bounded_projection(plan)
    witnessed = projection is None
    if witnessed:
        if (q.family != 'catalog' or q.section is not None or q.distinct or budget is None or any(field.column.kind not in ('string','boolean','number','datetime')
                                         for field, _ in plan.orders)):
            return None
        projection = _witnessed_case_projection(plan)
        if projection is None: return None
        if plan.predicate is not None:
            from .query_count import constant_condition
            proved, truth = constant_condition(plan, plan.predicate)
            if not proved or truth is not True: return None
        from yadinassi.db.sqlite.sqlite_catalog import SQLiteCatalogBackend, _View
        from yadinassi.db.sqlite.sqlite_documents import DocumentView
        raw = view._view if type(view) is DocumentView else view
        if (type(raw) is not _View or type(raw._backend) is not SQLiteCatalogBackend
                or raw._backend is not plan.managers[0]._backend or not raw._query_language
                or raw._operation_id is not None):
            return None
    condition = None if witnessed else _ordered_predicate(plan)
    if q.section is not None:
        if q.family not in ('catalog','document'): return None
        from .query_ordered_parts import try_ordered_parts
        return try_ordered_parts(plan,view,budget,projection,condition)
    if q.family in ('accumulation_register', 'information_register'):
        from .recorder_queries import RecorderQueryManager
        accumulation = q.family == 'accumulation_register'
        if accumulation or type(plan.managers[0]) is RecorderQueryManager:
            from .query_movement_order import try_ordered_movements
            return try_ordered_movements(plan, view, budget, 'accumulation' if accumulation else 'recorder', projection, condition)
    if q.family == 'information_register':
        from .register_queries import try_ordered_register
        return try_ordered_register(plan,view,budget,projection,condition)
    document = q.family == 'document'
    select = getattr(view, 'ordered_document_values' if document else 'ordered_catalog_values', None)
    if select is None: return None
    from uuid import UUID
    from yadinassi.db.catalog.catalog_backend import (
        CatalogKey, CatalogOrder, CatalogPredicate, CatalogScanRequest, CatalogValuePage, CatalogValueRow, _point_predicate,
    )
    filtered = False
    if document:
        from yadinassi.db.document.document_backend import DocumentKey, DocumentValuePage, DocumentValueRow
        from .document_queries import _ordered_header_value
        predicates = plan.document_storage_predicate(condition, 0)
        if predicates is None:
            from yadinassi.db.sqlite.sqlite_documents import DocumentView
            from .query_ordered_predicates import bind_scalar_predicate
            if (type(view) is not DocumentView or not view._view._query_language
                    or view._view._operation_id is not None
                    or any(c.kind in ('catalog_ref','document_ref','enum_ref') and c.field != 'ref'
                           for c in plan.fields[0])):
                return None
            predicate = bind_scalar_predicate(plan, condition, ('number','date','deletion_mark'), field_pairs=True,
                                              standard_leaf=plan.document_storage_predicate)
            if predicate is None: return None
            filtered = True
        else:
            predicate = CatalogPredicate('and', predicates) if predicates else None
        page_type, row_type, key_type = DocumentValuePage, DocumentValueRow, DocumentKey
    else:
        predicate = plan.storage_predicate(condition, 0, allow_or=True, field_pairs=True)
        if condition is not None and predicate is None: return None
        page_type, row_type, key_type = CatalogValuePage, CatalogValueRow, CatalogKey
    if not q.order and not _point_predicate(predicate, ('ref',) if document else ('code','ref')):
        return None
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
    full_cost = None
    if witnessed:
        if len(fields) != len(plan.fields[0]):
            return None
        from yadinassi.db.sqlite.sqlite_case_page import read
        admitted = read(raw, manager._schema, request, fields,
                        tuple(column.field for column in projection[0]), tuple(budget[:2]))
        if admitted is None:
            return None
        page, cells, units = admitted
        full_cost = cells, units
    else:
        page = (select(manager._schema.identity, request, fields, scalar_filter=True) if filtered
                else select(manager._schema.identity, request, fields))
    if plan.enum_scope is not None: plan.enum_scope.require_current()
    elif plan.enum_binding is not None: plan.enum_binding._live()
    if page is None: return None
    if (type(page) is not page_type or type(page.rows) is not tuple
            or len(page.rows) > q.limit or page.continuation is not None):
        raise BackendError('integrity')
    ordinals = {field: i for i, field in enumerate(fields)}
    columns, project = projection
    positions = tuple(ordinals[column.field] for column in columns)
    rows, seen, text_units = [], set(), 0
    input_text = 0
    measure_input = budget is not None and full_cost is None
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
        if measure_input:
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
        cells, units = (len(rows)*len(fields), input_text) if full_cost is None else full_cost
        budget[0] += cells
        budget[1] += units
        if budget[0] > _MAX_CELLS or budget[1] > _MAX_RESULT_TEXT:
            raise ValueError('Query input resource limit exceeded')
    return BSLQueryResult(plan.columns,tuple(rows))
