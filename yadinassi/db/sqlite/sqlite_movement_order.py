"""Bounded managed reads of physical movement occurrences."""
from contextlib import closing

from yadinassi.db.catalog.catalog_backend import BackendError
from .sqlite_catalog_layout import quote_identifier
from .sqlite_movement_layout import references
from .sqlite_partition_scan import recorder_key

_ZERO = '00000000-0000-0000-0000-000000000000'


def ordered_movements(view, family, schema, predicate, order, limit):
    """Use the admitted source descriptor; validate the resulting page, not the source."""
    from .sqlite_documents import DocumentView
    from .sqlite_ordered_predicates import ordered_where
    if type(view) is not DocumentView:
        return None
    owner = view._view
    owner._require()
    if not owner._query_language or owner._operation_id is not None:
        return None
    if owner._backend._active is not owner:
        raise BackendError('closed')
    backend = owner._backend
    accumulation = family == 'accumulation'
    if accumulation:
        from .sqlite_accumulation_movements import MAX_BYTES, decode_movement_row
        admitted = backend._accumulation_schemas
        cells = ('line_number', 'period', 'active', 'direction', 'payload_bytes')
        enum_domain = backend._enum_domain
    elif family == 'recorder':
        from .sqlite_recorder_movements import MAX_BYTES, decode_movement_row
        admitted = backend._recorder_schemas
        cells = ('line_number', 'active', 'payload_bytes')
    else:
        raise BackendError('invalid_input')
    if not any(schema is item for item in admitted):
        raise BackendError('schema_changed')

    table, columns = references(family, schema)
    fields = {'active': ('boolean', 'm.active')}
    if accumulation:
        fields['period'] = ('datetime', 'm.period')
    sorting = {key: sql for key, (_, sql) in fields.items()}
    sorting.update(recorder='m.record_id', line_number='m.line_number')
    targets = []
    for definition, column in zip(schema.fields, columns):
        column = 'm.' + column
        if definition.kind == 'catalog_ref':
            sorting[definition.identity] = f"COALESCE({column},'{_ZERO}')"
            target = quote_identifier(backend._layout.table_name(definition.target_catalog_id))
            targets.append(f'({column} IS NULL OR EXISTS(SELECT 1 FROM {target} AS t WHERE t.record_id={column}))')
        elif definition.kind in ('string', 'number', 'datetime', 'boolean'):
            if definition.kind == 'string':
                column += ' COLLATE yadinassi_casefold_v1'
            sorting[definition.identity] = column
            fields[definition.identity] = definition, column
    if any(field not in sorting for field in order):
        return None
    where, args = ('1', ()) if predicate is None else ordered_where(predicate, fields)
    terms = [sorting[field] + (' DESC' if desc else ' ASC') for field, desc in order.items()]
    terms.extend(('m.document_id ASC', 'm.record_id ASC', 'm.line_number ASC'))

    # Resolve only the returned movement's parent links, in the same statement.
    # LEFT JOIN keeps an orphan visible to the decoder instead of dropping it.
    key = 'p.register_id=m.register_id AND p.document_id=m.document_id AND p.record_id=m.record_id'
    source = (f'chosen AS m LEFT JOIN {family}_partition AS p ON {key} '
              'LEFT JOIN document_record AS d ON d.document_id=m.document_id AND d.record_id=m.record_id '
              f'LEFT JOIN {family}_register_document AS r ON r.register_id=m.register_id AND r.document_id=m.document_id')
    values = ','.join('m.' + column for column in (*cells, *columns))
    live_targets = (' AND '.join(targets)) if targets else '1'
    result, byte_count = [], 0
    size_index = len(cells) - 1
    order_sql = ','.join(terms)
    sql = (f'WITH chosen AS (SELECT m.* FROM {table} AS m '
           f'WHERE m.register_id=? AND ({where}) ORDER BY {order_sql} LIMIT ?) '
           f'SELECT m.document_id,m.record_id,p.revision,d.record_id,r.document_id,({live_targets}),{values} '
           f'FROM {source} ORDER BY {order_sql}')
    with closing(owner._connection.execute(sql, (str(schema.identity), *args, limit))) as cursor:
        for document, record, revision, live_record, live_document, live_refs, *raw in cursor:
            recorder = recorder_key(view.database_id, document, record)
            if (type(revision) is not int or not 1 <= revision < 2**63 or live_record != record
                    or live_document != document or live_refs != 1
                    or recorder.document_id not in schema.recorder_documents):
                raise BackendError('integrity')
            if accumulation:
                row = decode_movement_row(schema, view.database_id, raw, enum_domain=enum_domain)
                if not row.active:
                    raise BackendError('unsupported')
            else:
                row = decode_movement_row(schema, view.database_id, raw)
            # This count has been verified against the decoded canonical row.
            byte_count += raw[size_index]
            if byte_count > MAX_BYTES:
                raise BackendError('unsupported')
            result.append((recorder, row))
    owner._require()
    if backend._active is not owner:
        raise BackendError('closed')
    return result
