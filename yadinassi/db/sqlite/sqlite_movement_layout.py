"""Typed SQLite movement tables keyed to the shared persisted document identity."""
from decimal import Decimal
from uuid import UUID

from yadinassi.db.catalog.catalog_backend import BackendError
from .sqlite_catalog_layout import quote_identifier
from .sqlite_typed_rows import attribute_column, attribute_definitions


def canonical_number(value, field):
    # Fixed scaled numeric storage has one zero. Use that representation for
    # both the persisted value and the logical mutation/snapshot digest.
    if field.kind == 'number' and type(value) is Decimal and value.is_zero():
        return value.copy_abs()
    return value


def table_name(family, schema):
    if family not in ('accumulation', 'recorder') or type(schema.identity) is not UUID or not schema.identity.int:
        raise BackendError('invalid_input')
    return ('amove_' if family == 'accumulation' else 'rmove_') + schema.identity.hex


def data_ddls(family, schemas, catalog_layout=None, *, enum_domain=None):
    if type(schemas) is not tuple or len({schema.identity for schema in schemas}) != len(schemas):
        raise BackendError('invalid_input')
    result = []
    for schema in sorted(schemas, key=lambda item: item.identity.hex):
        table = quote_identifier(table_name(family, schema))
        columns = [
            f"register_id TEXT NOT NULL CHECK(register_id='{schema.identity}')",
            'document_id TEXT NOT NULL',
            'record_id TEXT NOT NULL',
            'line_number INTEGER NOT NULL CHECK(line_number>0)',
            'active INTEGER NOT NULL CHECK(active IN(0,1))',
        ]
        if family == 'accumulation':
            columns.extend(('period TEXT NOT NULL CHECK(length(period)=14)',
                            "direction TEXT NOT NULL CHECK(direction IN('receipt','expense'))"))
        # Exact canonical logical payload cost, not an encoded data column.
        columns.append('payload_bytes INTEGER NOT NULL CHECK(payload_bytes>=0)')
        columns.extend(attribute_definitions(schema.fields, catalog_layout, enum_domain=enum_domain))
        columns.extend(('PRIMARY KEY(register_id,document_id,record_id,line_number)',
                        f'FOREIGN KEY(register_id,document_id,record_id) REFERENCES {family}_partition(register_id,document_id,record_id)'))
        result.append(f'CREATE TABLE {table}(' + ', '.join(columns) + ')')
        if family == 'recorder' and schema.dimension_count:
            keys = tuple(quote_identifier(attribute_column(field))
                         for field in schema.fields[:schema.dimension_count])
            index = quote_identifier('rmove_dimensions_' + schema.identity.hex)
            result.append(f'CREATE UNIQUE INDEX {index} ON {table}(' + ', '.join(keys) + ')')
    return tuple(result)


def references(family, schema):
    """Trusted quoted physical table and ordered typed field identifiers."""
    return quote_identifier(table_name(family, schema)), tuple(
        quote_identifier(attribute_column(field)) for field in schema.fields)


def database_budget(connection, family, schemas, *, max_rows, max_bytes, max_partitions):
    tables = [quote_identifier(table_name(family, schema)) for schema in schemas]
    rows = size = 0
    # Stay below SQLite's default compound-select limit for wide configurations.
    for offset in range(0, len(tables), 128):
        sql = ' UNION ALL '.join('SELECT COUNT(*),COALESCE(SUM(payload_bytes),0) FROM ' + table
                                 for table in tables[offset:offset+128])
        for count, total in connection.execute(sql):
            rows += count
            size += total
            if rows > max_rows or size > max_bytes:
                raise BackendError('unsupported')
    partitions = connection.execute(f'SELECT COUNT(*) FROM {family}_partition').fetchone()[0]
    if partitions > max_partitions:
        raise BackendError('unsupported')


def payload_cost(columns):
    # Recheck actual bytes before materializing typed values from an external
    # database. Wide numbers occupy 16 bytes even if their logical tag is
    # shorter, so allow that bounded physical representation overhead.
    physical = '+'.join('COALESCE(length(CAST(' + name + ' AS BLOB)),0)' for name in columns)
    return f'MAX(payload_bytes,({physical})-{16 * len(columns)})'


def scoped_budget(connection, table, columns, where, args, *, max_rows, max_bytes,
                  max_row_bytes, oversize_code='unsupported'):
    cost = payload_cost(columns)
    count, size, largest = connection.execute(
        f'SELECT COUNT(*),COALESCE(SUM({cost}),0),COALESCE(MAX({cost}),0) FROM '
        + table + where, args).fetchone()
    if count > max_rows or size > max_bytes:
        raise BackendError('unsupported')
    if largest > max_row_bytes:
        raise BackendError(oversize_code)
    return count
