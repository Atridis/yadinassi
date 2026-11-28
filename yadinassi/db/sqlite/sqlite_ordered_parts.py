"""Native ordered part selection on the existing owned query-only lease."""
from uuid import UUID

from yadinassi.db.catalog.catalog_backend import BackendError, CatalogOrder, CatalogScanRequest, FieldSchema
from .sqlite_catalog_layout import quote_identifier
from .sqlite_ordered_predicates import ordered_where
from .sqlite_typed_rows import decode_typed_columns

_LINE = FieldSchema(UUID(int=0),'LineNumber','number',(10,0,'Nonnegative'))
_EMPTY = str(UUID(int=0))


def ordered_part_rows(view, request, section, table, physical, parent, identity, *, document=False):
    """Return exact selected owner/row/ordinal and decoded physical scalars."""
    from .sqlite_catalog import _close_document_scan, _decode
    view._require()
    if not view._query_language or view._operation_id is not None: return None
    if view._backend._active is not view: raise BackendError('closed')
    if (type(request) is not CatalogScanRequest or type(request.page_size) is not int
            or not 1<=request.page_size<=10000 or request.continuation is not None
            or type(request.order) is not tuple or not 1<=len(request.order)<=16
            or type(request.string_comparison) is not str or request.string_comparison!='casefold_v1'):
        raise BackendError('invalid_input')
    owner = 's.record_id' if document else 's.owner_id'
    ordering = {'ref':owner+' COLLATE yadinassi_uuid_v1'}
    predicates = {}
    if document:
        ordering['line_number'] = 's.row_number'
        predicates['line_number'] = (_LINE,'s.row_number')
    columns = tuple('s.'+col for col in physical)
    references = []
    for field,column in zip(section.fields,columns):
        if field.kind == 'string': column += ' COLLATE yadinassi_casefold_v1'
        elif field.kind == 'catalog_ref':
            target = quote_identifier(view._backend._layout.table_name(field.target_catalog_id))
            references.append(f'({column} IS NULL OR EXISTS(SELECT 1 FROM {target} AS t WHERE t.record_id={column}))')
            column = f"COALESCE({column},'{_EMPTY}') COLLATE yadinassi_uuid_v1"
        elif field.kind not in ('number','boolean','datetime'): continue
        ordering[field.identity] = column
        if field.kind != 'catalog_ref': predicates[field.identity] = (field,column)
    order = []
    for item in request.order:
        if (type(item) is not CatalogOrder or type(item.field) not in (UUID,str)
                or type(item.descending) is not bool): raise BackendError('invalid_input')
        column = ordering.get(item.field)
        if column is None: return None
        order.append(column+(' DESC' if item.descending else ' ASC'))
    join = f'LEFT JOIN {parent} AS o ON o.record_id={owner}'
    source, args = '', ()
    parent_fields = []
    if document:
        join += ' AND o.document_id=s.document_id'
        source,args = 's.document_id=?',(str(identity),)
        parent_fields = ['o.number','o.date']
        order.extend(('o.date ASC','o.number COLLATE BINARY ASC',owner+' ASC','s.row_number ASC'))
    else:
        # The catalog residual scan uses the logical owner/row UUID ties.
        order.extend((owner+' COLLATE yadinassi_uuid_v1 ASC','s.row_id COLLATE yadinassi_uuid_v1 ASC'))
    if request.predicate is not None:
        clause, bound = ordered_where(request.predicate,predicates)
        source,args = (' AND '.join((source,clause)) if source else clause),args+bound
    _close_document_scan(view)
    view._scan_cursor = None
    projection = (owner,'s.row_id','s.row_number','o.record_id',*columns,*references,*parent_fields)
    sql = ('SELECT '+','.join(projection)+' FROM '+table+' AS s '+join
           + (' WHERE '+source if source else '')+' ORDER BY '+','.join(order)+' LIMIT ?')
    cursor = view._connection.execute(sql,args+(request.page_size,))
    result = []
    tail = 4+len(columns)
    domain = view._backend._enum_domain
    try:
        for raw in cursor:
            owner_id,row_id = UUID(raw[0]),UUID(raw[1])
            if (not owner_id.int or not row_id.int or str(owner_id)!=raw[0] or str(row_id)!=raw[1]
                    or type(raw[2]) is not int or not 1<=raw[2]<=1000 or raw[3]!=raw[0]
                    or any(type(ok) is not int or ok!=1 for ok in raw[tail:tail+len(references)])):
                raise BackendError('integrity')
            encoded = decode_typed_columns(raw[4:tail],section,enum_domain=domain)
            values = tuple(_decode(item,field,view.database_id,enum_domain=domain)
                           for item,field in zip(encoded,section.fields))
            result.append((owner_id,row_id,raw[2],values,raw[tail+len(references):]))
    finally:
        cursor.close()
    view._require()
    if view._backend._active is not view: raise BackendError('closed')
    return tuple(result)
