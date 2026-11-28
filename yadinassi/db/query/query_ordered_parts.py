"""Shared bound dispatch for one selected typed part."""
from decimal import Decimal
from uuid import UUID

from yadinassi.db.catalog.catalog_backend import BackendError, CatalogOrder, CatalogScanRequest, CatalogSectionPage
from yadinassi.db.document.document_backend import DocumentKey, DocumentValuePage, DocumentValueRow
from .query_ordered_predicates import bind_scalar_predicate


def try_ordered_parts(plan, view, budget, projection, condition):
    from .queries import BSLQueryResult, _MAX_CELLS, _MAX_RESULT_TEXT, _section_row, _section_value
    columns, project = projection
    document = plan.query.family == 'document'
    select = getattr(view,'ordered_document_part' if document else 'ordered_catalog_part',None)
    if select is None: return None
    manager,part = plan.managers[0],plan.sections[0]
    if part is None: return None
    predicate = bind_scalar_predicate(plan,condition,('line_number',) if document else ())
    if condition is not None and predicate is None: return None
    fields = tuple(dict.fromkeys(column.field for column in plan.fields[0]))
    order = {}
    for field, descending in plan.orders: order.setdefault(field.column.field,descending)
    if len(fields)>128 or len(order)>16: return None
    if plan.enum_scope is not None: plan.enum_scope.require_current()
    elif plan.enum_binding is not None: plan.enum_binding._live()
    if document:
        manager._check_view(view)
    else:
        meta = manager._catalogs._metadata
        if ((view.database_id,view.configuration_generation)!=(meta._database_id,meta._generation)
                or view.catalog_schema(manager._schema.identity)!=manager._schema):
            raise BackendError('schema_changed')
    request = CatalogScanRequest(predicate,tuple(CatalogOrder(field,descending) for field,descending in order.items()),
                                 plan.query.limit,string_comparison='casefold_v1')
    page = select(manager._schema.identity,part.identity,request,fields)
    if plan.enum_scope is not None: plan.enum_scope.require_current()
    elif plan.enum_binding is not None: plan.enum_binding._live()
    if page is None: return None
    if (type(page) is not (DocumentValuePage if document else CatalogSectionPage)
            or type(page.rows) is not tuple or len(page.rows)>plan.query.limit or page.continuation is not None):
        raise BackendError('integrity')
    indexes = {field:i for i,field in enumerate(fields)}
    rows,seen,result_text,input_text = [],set(),0,0
    input_width = len(fields) if document else len(part.fields)
    for record in page.rows:
        if not document:
            row = _section_row(manager,part,record,columns,view,seen)
            input_text += sum(len(value) for value in record.row.values if type(value) is str)
        else:
            if type(record) is not DocumentValueRow or type(record.key) is not DocumentKey:
                raise BackendError('integrity')
            key = record.key
            if (type(key.database_id) is not UUID or type(key.document_id) is not UUID
                    or type(key.record_id) is not UUID or not key.record_id.int or key.database_id!=view.database_id
                    or key.document_id!=manager._schema.identity or type(record.line_number) is not int
                    or not 1<=record.line_number<=1000 or type(record.values) is not tuple
                    or len(record.values)!=len(fields) or (key.record_id,record.line_number) in seen):
                raise BackendError('integrity')
            seen.add((key.record_id,record.line_number))
            decoded = []
            for column in columns:
                value = record.values[indexes[column.field]]
                if column.field=='ref':
                    if (type(value) is not DocumentKey or type(value.database_id) is not UUID
                            or type(value.document_id) is not UUID or type(value.record_id) is not UUID or value!=key):
                        raise BackendError('integrity')
                    value = manager._ref(value.record_id)
                elif column.field=='line_number':
                    if type(value) is not Decimal or value!=record.line_number: raise BackendError('integrity')
                else: value = _section_value(manager,column.custom,value)
                decoded.append(value)
            row = tuple(decoded)
            input_text += sum(len(value) for value in record.values if type(value) is str)
        row = project(row)
        rows.append(row)
        result_text += sum(len(value) for value in row if type(value) is str)
        if len(rows)*len(plan.columns)>_MAX_CELLS or result_text>_MAX_RESULT_TEXT:
            raise ValueError('Query result resource limit exceeded')
    if budget is not None:
        budget[0] += len(rows)*input_width
        budget[1] += input_text
        if budget[0]>_MAX_CELLS or budget[1]>_MAX_RESULT_TEXT:
            raise ValueError('Query input resource limit exceeded')
    return BSLQueryResult(plan.columns,tuple(rows))
