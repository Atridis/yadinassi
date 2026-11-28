"""A single SQLite statement proving one independent register count."""
import sqlite3
import sys
from decimal import Decimal

from yadinassi.db.catalog.catalog_backend import BackendError
from .sqlite_catalog import _boundary
from .sqlite_single_statement import fetch_one
from .sqlite_typed_rows import number_check


def _scalar_fields(schema, layout):
    if schema.periodic:
        # Periodic reads additionally prove that the stored date is normalized
        # to the exact declared period (even without a virtual table).
        return None
    checks, text = [], []
    for field, column in zip(schema.fields,layout.keys+layout.values):
        if field.kind=='number':
            if sys.implementation.name!='cpython' or Decimal.__sizeof__ is object.__sizeof__:
                return None  # The original Number resource accounting must agree.
            checks.append(number_check(column,field))
        elif field.kind=='boolean':
            checks.append(f"typeof({column})='integer' AND {column} IN (0,1)")
        elif field.kind=='string':
            # Exact printable ASCII gives byte count == Python length == UTF-16
            # units; the blob-length condition also excludes embedded NUL.
            # Anything else goes through the original strict Unicode decoder.
            length=f'length(CAST({column} AS BLOB))'
            checks.append(f"typeof({column})='text' AND {length}=length({column}) "
                          f"AND {length}<={field.qualifiers[0]} AND {column} NOT GLOB '*[^ -~]*'")
            text.append(length)
        else:
            return None  # Dates and references have additional logical checks.
    return ' AND '.join(f'({check})' for check in checks), '+'.join(text) or '0'


@_boundary
def count_register(reader, schema):
    """Return (rows, input_text), or decline to the strict full-source reader."""
    from .sqlite_registers import MAX_ROWS, MAX_ROW, MAX_TOTAL
    layout=reader._layout(schema)
    proof=_scalar_fields(schema,layout)
    if proof is None:return None
    checks,text=proof
    # The strict port bounds the compact tagged JSON key separately from
    # physical row bytes. Printable ASCII quotes/backslashes can double; a
    # Number needs at most precision plus its sign, radix and leading zero.
    # Each field's 12-byte envelope covers its tag, quotes and separators.
    key_bytes=2+sum(12+(2*field.qualifiers[0] if field.kind=='string'
                          else field.qualifiers[0] if field.kind=='number' else 0)
                    for field in schema.key_fields)
    if key_bytes>MAX_ROW:return None
    # Validated NUMBER coefficients, Boolean 0/1 and ASCII TEXT are injective
    # under the logical key identity. Group the full dimension tuple, not the
    # individual fields, so an altered/dropped unique index cannot hide dupes.
    # The row limit is a fixed provider constant. This statement has no user
    # values and no bind parameters, including on SQLite with a zero limit.
    statement=(
        'SELECT COALESCE(SUM(n),0),COUNT(*),COALESCE(SUM(bytes),0),'
        'COALESCE(SUM(text_units),0),COALESCE(MAX(invalid),0) FROM ('
        f'SELECT COUNT(*) AS n,SUM(({layout.bytes})+64) AS bytes,'
        f'SUM({text}) AS text_units,MAX(CASE WHEN typeof(revision)=\'integer\' '
        f'AND revision>=1 AND ({layout.bytes})<={MAX_ROW} AND {checks} THEN 0 ELSE 1 END) AS invalid '
        f'FROM {layout.table} GROUP BY {layout.key_order})')
    connection=reader._connection
    getlimit=getattr(connection,'getlimit',None)
    if getlimit is not None:
        depth=getlimit(sqlite3.SQLITE_LIMIT_EXPR_DEPTH)
        # Generated SQL is ASCII. The expression grows by at most two left-
        # nested terms per field, plus the fixed scalar/aggregate envelope.
        if (len(statement)>getlimit(sqlite3.SQLITE_LIMIT_SQL_LENGTH)
                or (depth and depth<16+2*len(schema.fields))
                or getlimit(sqlite3.SQLITE_LIMIT_COLUMN)<5):
            return None
    result=fetch_one(connection,statement)
    if (type(result) is not tuple or len(result)!=5
            or any(type(item) is not int or item<0 for item in result)):
        raise BackendError('integrity')
    rows,keys,size,units,invalid=result
    if invalid or keys!=rows or rows>MAX_ROWS or size>MAX_TOTAL:
        return None  # Preserve the original decoder's error and precedence.
    return rows,units
