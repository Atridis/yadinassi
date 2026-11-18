"""Closed logical-to-physical query selection, with explicit residual execution.

No backend class imports, SQL fragments, caller-provided physical names, or
semantic guessing. New operator shapes require independent equivalence proofs.
"""
from decimal import Decimal
from .catalog_backend import CatalogAggregateRequest, CatalogAggregateResult, BackendError
from . import query_parser as syntax


def count_eligible(plan):
    from .relational_queries import _BoundAggregate
    q=plan.query
    if (type(q) is not syntax.Select or len(plan.sources)!=1 or len(plan.projections)!=1
            or q.family!='catalog' or q.section is not None or q.temporary or q.external
            or q.derived is not None or q.into is not None or q.virtual_condition is not None
            or q.joins or q.groups or q.predicate is not None or q.having is not None
            or q.order or q.distinct
            or plan.memberships or plan.hierarchies):return False
    expression=plan.projections[0]
    return (type(expression) is _BoundAggregate and expression.function=='count'
            and expression.field is None and expression.distinct is False)


def try_count(plan,view,budget):
    """Return None for an unsupported physical shape; never hide a read error."""
    if not count_eligible(plan):return None
    aggregate=getattr(view,'aggregate_catalog',None)
    if aggregate is None:return None
    if plan.enum_binding is not None:
        from .enum_storage_binding import EnumStorageBinding
        if type(plan.enum_binding) is not EnumStorageBinding:raise BackendError('unsupported')
        # execute() already holds the lexical read_snapshot witness. Validate
        # owner and canonical enum mappings without acquiring a second lease.
        plan.enum_binding._live()
    manager=plan.managers[0];metadata=manager._catalogs._metadata
    if ((view.database_id,view.configuration_generation)!=(metadata._database_id,metadata._generation)
            or view.catalog_schema(manager._schema.identity)!=manager._schema):
        raise BackendError('schema_changed')
    result=aggregate(manager._schema.identity,CatalogAggregateRequest())
    if plan.enum_binding is not None:plan.enum_binding._live()
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
