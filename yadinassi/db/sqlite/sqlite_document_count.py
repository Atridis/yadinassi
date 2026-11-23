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


def _uuid(column, *, zero=False):
    return (f"typeof({column})='text' AND length(CAST({column} AS BLOB))=36 "
            f"AND {column} GLOB :uuid" + ('' if zero else f' AND {column}!=:zero'))


def _text(column, length, *, nonempty=False):
    # Printable ASCII has one UTF-16 unit and one SQLite character per byte.
    # Non-ASCII, NUL and controls remain valid only if the legacy decoder says so.
    return (f"typeof({column})='text' AND length(CAST({column} AS BLOB))=length({column}) "
            f"AND {column} NOT GLOB '*[^ -~]*' "
            f"AND length({column}) BETWEEN {int(nonempty)} AND {length}")


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

    def fields(self, prefix, definitions):
        tests, text, sizes = [], [], []
        for field in definitions:
            column = prefix + quote_identifier(attribute_column(field))
            kind = field.kind
            if kind == 'string':
                tests.append(_text(column, field.qualifiers[0]))
                text.append(f'length({column})')
            elif kind == 'number':
                tests.append(number_check(column,field))
            elif kind == 'boolean':
                tests.append(_boolean(column))
            elif kind == 'datetime':
                tests.append(_date(column))
            elif kind == 'catalog_ref':
                present = _uuid(column,zero=True)
                if self.backend.format_version in (15,16):
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
def count(view, schema, section):
    from .sqlite_documents import _MAX_ROW, _MAX_TOTAL

    raw = view._view
    witness = _Witness(raw._backend,schema.identity)
    fields = witness.fields('a.',schema.fields)
    if fields is None: return None
    tests, text, size = fields
    tests.extend((_uuid('r.record_id'),"typeof(r.revision)='integer' AND r.revision>0",
                  _text('r.number',min(36,schema.number_length),nonempty=True),
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
    header = (f'SELECT r.record_id,1,{int(section is None)},0,{5+len(schema.fields)} AS cells,'
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
        sql = ('SELECT COUNT(*),COUNT(*),COALESCE(SUM(cells),0),COALESCE(SUM(units),0),'
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
