"""Read one TOP page and its complete catalog-header witness in one statement."""
import sqlite3

from yadinassi.db.catalog.catalog_backend import BackendError, CatalogValuePage

from .sqlite_catalog import _boundary
from .sqlite_document_count import _fits, catalog_header_witness
from .sqlite_single_statement import fetch_all


@_boundary
def read(view, schema, request, fields, result_fields, used):
    from yadinassi.db.query.query_parser import MAX_ROWS as QUERY_MAX_ROWS
    from yadinassi.db.query.queries import _MAX_CELLS, _MAX_RESULT_TEXT
    from .sqlite_catalog import _MAX_ROWS

    view._require()
    if view._backend._active is not view:
        raise BackendError('closed')
    proof = catalog_header_witness(view, schema, text_fields=fields)
    if proof is None:
        return None
    validity, input_text, bindings = proof
    result_proof = catalog_header_witness(view, schema, text_fields=result_fields)
    _, output_text, _ = result_proof
    view._validate_catalog_scan(schema, request, fields, _MAX_ROWS)
    order = view._scan_sql(schema, request)
    if order is None:
        return None
    table, _, _, _ = view._source(schema)
    projection = view._projection_columns(schema, fields)
    # Use the existing physical order, including the canonical UUID tie.
    # Only the proof can rule out UUID aliases; on decline the residual keeps
    # its old decoding, validation, budget checks and stability.
    outer_order = ','.join(key + (' DESC' if desc else ' ASC') for key, desc in order[3][:-1])
    binds = bindings | {'top': request.page_size}
    row_cap = min(_MAX_ROWS, QUERY_MAX_ROWS)
    fits = (f'n=valid AND n<={row_cap} AND n*{len(fields)}<={_MAX_CELLS-used[0]} '
            f'AND input_text<={_MAX_RESULT_TEXT-used[1]} '
            f'AND n*{len(result_fields)}<={_MAX_CELLS} AND output_text<={_MAX_RESULT_TEXT}')
    sql = (
        f'WITH proof AS (SELECT COUNT(*) AS n,COALESCE(SUM(valid),0) AS valid,'
        f'COALESCE(SUM(input_text),0) AS input_text,COALESCE(SUM(output_text),0) AS output_text '
        f'FROM (SELECT {validity} AS valid,{input_text} AS input_text,{output_text} AS output_text '
        f'FROM {table} LIMIT {row_cap+1})) '
        f'SELECT proof.*,page.* FROM proof LEFT JOIN '
        f'(SELECT {projection} FROM {table} WHERE (SELECT {fits} FROM proof) '
        f'ORDER BY {order[2]} LIMIT :top) AS page ON 1 ORDER BY {outer_order}'
    )
    connection = view._connection
    limits = getattr(connection, 'getlimit', None)
    if not _fits(connection, sql, schema, len(binds)):
        return None
    if limits is not None:
        # SQLite's LENGTH limit also covers the packed result row. Include
        # proof integers and conservative physical column sizes/record header.
        text_bytes = 4 * (schema.code_length + schema.description_length
                          + sum(field.qualifiers[0] for field in schema.fields if field.kind == 'string'))
        if (limits(sqlite3.SQLITE_LIMIT_COLUMN) < len(fields)+5
                or limits(sqlite3.SQLITE_LIMIT_EXPR_DEPTH) < 32 + max(len(fields), len(result_fields))
                or limits(sqlite3.SQLITE_LIMIT_LENGTH) < text_bytes + 128 + 64*len(schema.fields)):
            return None
    raw = fetch_all(connection, sql, binds)
    view._require()
    if view._backend._active is not view:
        raise BackendError('closed')
    if not raw or type(raw[0]) is not tuple or len(raw[0]) != len(fields)+5:
        raise BackendError('integrity')
    n, valid, in_units, out_units = counts = raw[0][:4]
    if any(type(value) is not int or value < 0 for value in counts) or valid > n:
        raise BackendError('integrity')
    cells = n * len(fields)
    if (n != valid or n > row_cap or cells + used[0] > _MAX_CELLS
            or in_units + used[1] > _MAX_RESULT_TEXT or n * len(result_fields) > _MAX_CELLS
            or out_units > _MAX_RESULT_TEXT):
        return None
    records = tuple(view._projection_row(schema.identity, schema, fields, row[4:])
                    for row in raw if row[4] is not None)
    if len(records) != min(n, request.page_size):
        raise BackendError('integrity')
    return CatalogValuePage(records, None), cells, in_units
