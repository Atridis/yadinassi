"""One statement proves and counts physical document query rows.

A successful witness implies the existing full-source decoder would accept
even hidden values, and returns its exact global cell/text cost. Failed proofs
decline to the original reader, which owns error ordering and Unicode admission.
"""
import sqlite3

from .sqlite_catalog import _CANONICAL_UUID_GLOB, _ZERO_RECORD_ID, _boundary
from .sqlite_catalog_layout import quote_identifier
from .sqlite_document_layout import data_table, section_table
from .sqlite_single_statement import fetch_one
from .sqlite_typed_rows import attribute_column, number_check
from .sqlite_text_witness import text_check


def _uuid(column, *, zero=False):
    return (f"typeof({column})='text' AND length(CAST({column} AS BLOB))=36 "
            f"AND {column} GLOB :uuid" + ('' if zero else f' AND {column}!=:zero'))


def _date(column):
    iso = (f"substr({column},1,4)||'-'||substr({column},5,2)||'-'||substr({column},7,2)")
    return (f"typeof({column})='text' AND length(CAST({column} AS BLOB))=14 "
            f"AND length({column})=14 AND {column} NOT GLOB '*[^0-9]*' "
            f"AND substr({column},1,4)!='0000' AND date({iso},'+0 days')=({iso}) "
            f"AND substr({column},9,2)<='23' AND substr({column},11,2)<='59' "
            f"AND substr({column},13,2)<='59'")


def _boolean(column):
    return f"typeof({column})='integer' AND {column} IN(0,1)"


def _sum(terms):
    return '+'.join(terms) or '0'


def _valid(terms):
    # A NULL SQL boolean is a failed proof, not a silently skipped row.
    return 'CASE WHEN ' + ' AND '.join('('+term+')' for term in terms) + ' THEN 1 ELSE 0 END'


class _Witness:
    def __init__(self, backend, identity):
        self.backend = backend
        self.bindings = {'doc':str(identity),'uuid':_CANONICAL_UUID_GLOB,'zero':_ZERO_RECORD_ID}
        self.enums = {}

    def fields(self, prefix, definitions, *, physical_name=attribute_column, present_references=True):
        tests, text, sizes = [], [], []
        for field in definitions:
            column = prefix + quote_identifier(physical_name(field))
            kind = field.kind
            if kind == 'string':
                tests.append(text_check(column, field.qualifiers[0]))
                text.append(f'length({column})')
            elif kind == 'number':
                tests.append(number_check(column,field))
            elif kind == 'boolean':
                tests.append(_boolean(column))
            elif kind == 'datetime':
                tests.append(_date(column))
            elif kind == 'catalog_ref':
                present = _uuid(column,zero=True)
                if present_references and self.backend.format_version in (15,16):
                    target = quote_identifier(self.backend._layout.table_name(field.target_catalog_id))
                    present += (f' AND ({column}=:zero OR EXISTS(SELECT 1 FROM {target} AS target '
                                f'WHERE target.record_id={column}))')
                tests.append(f'{column} IS NULL OR ({present})')
            elif kind == 'enum_ref' and self.backend._enum_domain is not None:
                names = self.enums.get(field.target_enum_id)
                if names is None:
                    names = []
                    for value in self.backend._enum_domain._values(field.target_enum_id):
                        name = f'e{len(self.bindings)}'
                        self.bindings[name] = str(value)
                        names.append(':'+name)
                    names = self.enums[field.target_enum_id] = ','.join((':zero', *names))
                tests.append(f"typeof({column})='text' AND {column} IN({names})")
            else:
                return None
            sizes.append(f'COALESCE(length(CAST({column} AS BLOB)),0)')
        return tests, _sum(text), _sum(sizes)


def _fits(connection, sql, schema, bind_count):
    from .sqlite_section_delta import _limit
    if bind_count > _limit(connection): return False
    getlimit = getattr(connection, 'getlimit', None)
    if getlimit is None: return True
    # The inner proof SELECT has eight columns, substr has three arguments,
    # and each part adds one compound arm. Each same-row field adds at most
    # one level to the left-deep conjunction/sums. The date/UUID checks,
    # enclosing CASE, aggregate and query stages all fit in the fixed margin.
    depth = 32 + max((len(schema.fields), *(len(part.fields) for part in schema.tabular_sections)))
    compound = getlimit(sqlite3.SQLITE_LIMIT_COMPOUND_SELECT)
    sql_bytes = len(sql.encode('utf-8'))
    # Leave headroom for compiler-generated CTE/aggregate loops and the
    # opcodes for optional IN members. This is an eligibility test only.
    opcode_capacity = 1024 + 8 * sql_bytes
    return (getlimit(sqlite3.SQLITE_LIMIT_COLUMN) >= 8
            and getlimit(sqlite3.SQLITE_LIMIT_FUNCTION_ARG) >= 3
            # A runtime-lowered EXPR_DEPTH of zero rejects expressions.
            and getlimit(sqlite3.SQLITE_LIMIT_EXPR_DEPTH) >= depth
            and (not compound or 1 + len(schema.tabular_sections) <= compound)
            and len(_CANONICAL_UUID_GLOB) <= getlimit(sqlite3.SQLITE_LIMIT_LIKE_PATTERN_LENGTH)
            and opcode_capacity <= getlimit(sqlite3.SQLITE_LIMIT_VDBE_OP)
            and sql_bytes <= getlimit(sqlite3.SQLITE_LIMIT_SQL_LENGTH)
            # All other bound strings are canonical ASCII UUIDs (36 bytes).
            and len(_CANONICAL_UUID_GLOB) <= getlimit(sqlite3.SQLITE_LIMIT_LENGTH))


@_boundary
def count(view, schema, section, *, deletion_mark=None):
    from .sqlite_documents import _MAX_ROW, _MAX_TOTAL

    if deletion_mark is not None and (type(deletion_mark) is not bool or section is not None):
        return None
    raw = view._view
    witness = _Witness(raw._backend,schema.identity)
    fields = witness.fields('a.',schema.fields)
    if fields is None: return None
    tests, text, size = fields
    tests.extend((_uuid('r.record_id'),"typeof(r.revision)='integer' AND r.revision>0",
                  text_check('r.number',min(36,schema.number_length),nonempty=True),
                  _date('r.date'),_boolean('r.deletion_mark'),f'({size})<={_MAX_ROW}'))
    joins, attribute_count = '', None
    if schema.fields:
        attributes = quote_identifier(data_table(schema))
        joins += f' LEFT JOIN {attributes} AS a USING(document_id,record_id)'
        tests.append('a.record_id IS NOT NULL')
        attribute_count = f'(SELECT COUNT(*) FROM {attributes})'
    if raw._backend.format_version in (13,14,15,16):
        joins += ' LEFT JOIN document_posting_state AS p USING(document_id,record_id)'
        tests.append("p.record_id IS NULL OR (typeof(p.document_revision)='integer' AND "
                     "p.document_revision BETWEEN 1 AND r.revision AND "+_boolean('p.posted')+')')
    selected = (str(int(section is None)) if deletion_mark is None else
                f'CASE WHEN r.deletion_mark={int(deletion_mark)} THEN 1 ELSE 0 END')
    header = (f'SELECT r.record_id,1,{selected} AS selected,0,{5+len(schema.fields)} AS cells,'
              f'length(r.number)+({text}) AS units,128+length(CAST(r.number AS BLOB))+({size}) AS bytes,'
              f'{_valid(tests)} AS valid FROM document_record AS r{joins} WHERE r.document_id=:doc')
    parts = []
    for part in schema.tabular_sections:
        fields = witness.fields('s.',part.fields)
        if fields is None: return None
        tests,text,size = fields
        tests.extend(('s.document_id=:doc',_uuid('s.row_id'),
                      "typeof(s.row_number)='integer' AND s.row_number>0",f'52+({size})<={_MAX_ROW}'))
        table = quote_identifier(section_table(schema,part))
        selected = 'COUNT(*)' if section is not None and section.identity==part.identity else '0'
        parts.append(f'SELECT s.record_id,0,{selected},COUNT(*),COUNT(*)*{2+len(part.fields)},'
                     f'COALESCE(SUM({text}),0),SUM(52+({size})),'
                     f'MIN({_valid(tests)}) AND MAX(s.row_number)=COUNT(*) '
                     f'FROM {table} AS s GROUP BY s.record_id')
    if parts:
        # Every group must have its owner header; track the legacy combined
        # per-owner 1,000-line quota across all declared sections.
        sql = ('WITH data(owner,headers,selected,lines,cells,units,bytes,valid) AS ('
               + ' UNION ALL '.join((header,*parts))
               + '), owners AS (SELECT SUM(headers) AS headers,SUM(selected) AS selected,'
                 'SUM(cells) AS cells,SUM(units) AS units,SUM(bytes) AS bytes,'
                 'MIN(valid) AND SUM(headers)=1 AND SUM(lines)<=1000 AS valid '
                 'FROM data GROUP BY owner) '
                 'SELECT COALESCE(SUM(headers),0),COALESCE(SUM(selected),0),'
                 'COALESCE(SUM(cells),0),COALESCE(SUM(units),0),COALESCE(SUM(bytes),0),'
                 'COALESCE(MIN(valid),1),'+(attribute_count or 'COALESCE(SUM(headers),0)')+' FROM owners')
    else:
        selected = 'COUNT(*)' if deletion_mark is None else 'COALESCE(SUM(selected),0)'
        sql = (f'SELECT COUNT(*),{selected},COALESCE(SUM(cells),0),COALESCE(SUM(units),0),'
               'COALESCE(SUM(bytes),0),COALESCE(MIN(valid),1),'+(attribute_count or 'COUNT(*)')+
               ' FROM ('+header+')')
    # Optional plans must fit the current connection before preparation.
    if not _fits(view._connection,sql,schema,len(witness.bindings)): return None
    row = fetch_one(view._connection,sql,witness.bindings)
    if (type(row) is not tuple or len(row)!=7 or
            any(type(item) is not int or item<0 for item in row)):
        return None
    count, selected, cells, text, size, valid, attrs = row
    if valid!=1 or attrs!=count or count>10000 or size>_MAX_TOTAL:
        return None
    return count,selected,cells,text


def catalog_header_witness(view, schema, *, alias='', text_fields=()):
    """Validity CASE, exact projected character counts, and named bindings.

    The caller must apply these expressions to the complete physical source;
    filter/LIMIT belongs outside that witness. Unsupported encodings decline.
    """
    if view._backend.storage_version < 2 or schema.hierarchy != 'none': return None
    witness = _Witness(view._backend, schema.identity)
    prefix = quote_identifier(alias) + '.' if alias else ''
    layout = view._catalog_layout
    def physical_name(field):
        return layout.field_name(schema.identity, field.identity)
    fields = witness.fields(prefix, schema.fields, physical_name=physical_name,
                            present_references=False)
    if fields is None: return None
    tests = fields[0]
    tests.extend((_uuid(prefix+'record_id'), f"typeof({prefix}revision)='integer' AND {prefix}revision>0",
                  text_check(prefix+'code', schema.code_length),
                  text_check(prefix+'description', schema.description_length),
                  _boolean(prefix+'deletion_mark')))
    units = '0'
    if text_fields:
        text_columns = {'code':'code', 'description':'description'}
        text_columns.update((field.identity, physical_name(field))
                            for field in schema.fields if field.kind == 'string')
        units = _sum(f'length({prefix}{quote_identifier(text_columns[field])})'
                     for field in text_fields if field in text_columns)
    del witness.bindings['doc']
    return _valid(tests), units, witness.bindings


def count_catalog_headers(view, schema, table, deletion_mark):
    """Validate all header scalars in the same statement, before counting matches."""
    from yadinassi.db.catalog.catalog_backend import BackendError, CatalogAggregateResult
    from .sqlite_catalog import _MAX_ROWS

    witness = catalog_header_witness(view, schema)
    if witness is None: return None
    validity, _, bindings = witness
    # The TEXT primary key and the canonical UUID witness prove logical
    # uniqueness without allocating a DISTINCT set or decoding Python rows.
    selected = 'COUNT(*)'
    if deletion_mark is not None:
        selected = 'COUNT(CASE WHEN deletion_mark=:marked THEN 1 END)'
        bindings['marked'] = int(deletion_mark)
    sql = f'SELECT COUNT(*),COALESCE(SUM({validity}),0),{selected} FROM {table}'
    if not _fits(view._connection, sql, schema, len(bindings)): return None
    row = fetch_one(view._connection, sql, bindings)
    if (type(row) is not tuple or len(row) != 3
            or any(type(item) is not int or item < 0 for item in row)
            or row[1] > row[0] or row[2] > row[0]):
        raise BackendError('integrity')
    if row[0] != row[1]: return None
    if row[0] > _MAX_ROWS: raise BackendError('unsupported')
    return CatalogAggregateResult(row[2], row[0])
