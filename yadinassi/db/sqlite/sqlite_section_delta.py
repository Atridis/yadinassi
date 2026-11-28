"""Set-based writes for owner-local, UUID-addressed SQLite tabular sections."""
import sqlite3

from yadinassi.db.catalog.catalog_backend import BackendError
from .sqlite_typed_rows import bounded_attribute_sql, bounded_value_sql


def _limit(connection):
    getlimit = getattr(connection, 'getlimit', None)
    # The Python 3.10 connection does not expose getlimit().
    return getlimit(sqlite3.SQLITE_LIMIT_VARIABLE_NUMBER) if getlimit is not None else 999


def _batches(items, variables, width):
    size = variables // width
    if size < 1 and items:
        raise BackendError('unsupported')
    if size:
        for start in range(0, len(items), size):
            yield items[start:start+size]


def _marks(n):
    return ','.join('?' for _ in range(n))


def _execute(connection, sql, parameters, count=None):
    cursor = connection.execute(sql, parameters)
    try:
        if count is not None and cursor.rowcount != count:
            raise BackendError('integrity')
    finally:
        cursor.close()


def _where(columns):
    return ' AND '.join(column + '=?' for column in columns)


def read_physical_rows(connection, table, owner_columns, owner, columns, fields, max_rows):
    """Stream only the selected owner's old payload, in the locked writer."""
    fields_sql = [bounded_value_sql('row_id',36),
                  "CASE WHEN typeof(row_number)='integer' THEN row_number END"]
    fields_sql.extend(bounded_attribute_sql(column,field) for column,field in zip(columns,fields))
    cursor = connection.execute('SELECT '+','.join(fields_sql)+' FROM '+table+
                                ' WHERE '+_where(owner_columns)+' LIMIT ?', (*owner,max_rows+1))
    try:
        for index,row in enumerate(cursor,1):
            if index > max_rows:
                raise BackendError('unsupported')
            yield row[0],row[1],row[2:]
    finally:
        cursor.close()


def _same_physical_fields(old, new):
    # SQLite corruption may present a different storage class with the
    # same Python numeric value. Do not treat it as an unchanged field.
    return all(type(before) is type(after) and before == after
               for before,after in zip(old,new))


def _same_tagged_fields(old, new):
    if old == new:
        return True
    # Fixed-scale columns have a single physical zero; decoded historical
    # rows always carry its unsigned spelling. The draft may carry -0.
    return all(before == after or
               (before[0] == 'n' and after[1] == '-'+before[1] and not before[1].strip('0.'))
               for before,after in zip(old,new))


def write_section(connection, table, owner_columns, owner, columns, rows,
                  *, create, max_rows, previous=(), encode=None):
    """Persist the validated owner's changed UUIDs; the caller owns rollback.

    Catalog rows are physical; documents can reuse the already validated
    tagged snapshot used for their revision check, and encode only the delta.
    None/omitted sections are handled by the callers, not by this helper.
    """
    where = _where(owner_columns)
    if not rows:
        if not create:
            _execute(connection,'DELETE FROM '+table+' WHERE '+where,owner)
        return
    variables = _limit(connection)
    desired = {identity:(position,values) for position,(identity,values) in enumerate(rows,1)}
    removed, moved, changed = [], [], []
    if not create:
        same_fields = _same_physical_fields if encode is None else _same_tagged_fields
        # All stored and final positions are in 1..max_rows. Park the changed
        # survivors once above that range so arbitrary swaps and cycles work,
        # even when later bindings must be split across SQLite's limit.
        try:
            for identity,position,old in previous:
                if type(identity) is not str or len(identity)!=36 or type(position) is not int or not 1<=position<=max_rows:
                    raise BackendError('integrity')
                target = desired.pop(identity,None)
                if target is None:
                    removed.append(identity)
                elif position != target[0]:
                    moved.append(identity)
                    changed.append((identity,*target))
                elif not same_fields(old,target[1]):
                    changed.append((identity,*target))
        finally:
            # A streamed catalog SELECT must finish before DML can change
            # its table. A document's in-memory generator follows the same API.
            previous.close()
        for chunk in _batches(removed, variables-len(owner), 1):
            _execute(connection,'DELETE FROM '+table+' WHERE '+where+' AND row_id IN ('+
                     _marks(len(chunk))+')',(*owner,*chunk),len(chunk))
        for chunk in _batches(moved, variables-len(owner)-1, 1):
            _execute(connection,'UPDATE '+table+' SET row_number=row_number+? WHERE '+where+
                     ' AND row_id IN ('+_marks(len(chunk))+')',(max_rows,*owner,*chunk),len(chunk))

    changed.extend((identity,*target) for identity,target in desired.items())
    if not changed:
        return
    column_list = (*owner_columns,'row_id','row_number',*columns)
    insert = 'INSERT INTO '+table+'('+','.join(column_list)+') VALUES'
    row_sql = '('+_marks(len(column_list))+')'
    if not create:
        update = (' ON CONFLICT('+','.join((*owner_columns,'row_id'))+') DO UPDATE SET '+
                  ','.join(column+'=excluded.'+column for column in ('row_number',*columns)))
    else:
        update = ''
    for chunk in _batches(changed,variables,len(column_list)):
        parameters = tuple(value for identity,position,fields in chunk for value in
                           (*owner,identity,position,*(fields if encode is None else encode(fields))))
        _execute(connection,insert+','.join(row_sql for _ in chunk)+update,parameters,len(chunk))
