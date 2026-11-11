"""Closed query-order index specifications; creation is explicit maintenance or fresh creation only."""
from decimal import Decimal
from uuid import UUID

from .catalog_backend import BackendError, CatalogSchema
from .sqlite_catalog_layout import quote_identifier


def register_query_collations(connection):
    """Install versioned comparators on readers, writers and migration handles."""
    def compare(a, b): return (a > b) - (a < b)
    connection.create_collation('yadinassi_casefold_v1', lambda a, b: compare(a.casefold(), b.casefold()))
    connection.create_collation('yadinassi_decimal_v1', lambda a, b: compare(Decimal(a), Decimal(b)))
    connection.create_collation('yadinassi_uuid_v1', lambda a, b: compare(UUID(a).int, UUID(b).int))


def catalog_query_index_ddls(schemas, layout):
    """One index per admitted catalog for the default logical UUID/rowid order.

    SQLite appends rowid to nonunique indexes, preserving the reader's physical
    tie-break for accepted textual UUID aliases. No user-provided DDL or fields.
    """
    if type(schemas) is not tuple or len(schemas) > 512:
        raise BackendError('invalid_input')
    identities = set()
    for schema in schemas:
        if type(schema) is not CatalogSchema or type(schema.identity) is not UUID or not schema.identity.int:
            raise BackendError('invalid_input')
        if schema.identity in identities: raise BackendError('invalid_input')
        identities.add(schema.identity)
    return tuple('CREATE INDEX ' + quote_identifier('query_catalog_' + identity.hex + '_v1') +
                 ' ON ' + quote_identifier(layout.table_name(identity)) +
                 '(record_id COLLATE yadinassi_uuid_v1)'
                 for identity in sorted(identities, key=str))


def _index_name(ddl):
    """Names in our closed declaration vocabulary, not a generic SQL parser."""
    import re
    if type(ddl) is not str:
        raise BackendError('invalid_input')
    match = re.match(r'^CREATE INDEX (?:"([A-Za-z0-9_]+)"|([A-Za-z0-9_]+)) ON ', ddl)
    if match is None:
        raise BackendError('invalid_input')
    return match.group(1) or match.group(2)


def canonical_index_ddls(ddls):
    if type(ddls) is not tuple or len(ddls) > 4096:
        raise BackendError('invalid_input')
    named = [(_index_name(ddl), ddl) for ddl in ddls]
    if len({name for name, _ in named}) != len(named):
        raise BackendError('invalid_input')
    return tuple(ddl for _, ddl in sorted(named))


def read_index_bundle_ddls(storage_version, schemas, layout, *, format_version):
    """Optional exact-read bundle; no format change and no DDL execution.

    Existing mandatory UUID-order index declarations are deliberately unchanged.
    Casefold indexes are nonunique: logically equal codes remain ambiguous, not
    forbidden, and rowid remains SQLite's final physical tie-break.
    """
    if (type(storage_version) is not int or type(format_version) is not int
            or storage_version not in range(1, 11) or format_version not in range(1, 15)):
        raise BackendError('invalid_input')
    if storage_version in (1, 5):
        return ()
    # Reuse the existing exact schema/identity validation, without changing its
    # baseline return value or introducing caller-specified index expressions.
    catalog_query_index_ddls(schemas, layout)
    result = list(catalog_query_index_ddls(schemas, layout)) if format_version not in (11, 12, 13, 14) else []
    for schema in sorted(schemas, key=lambda item: str(item.identity)):
        table = quote_identifier(layout.table_name(schema.identity))
        for field in ('code', 'description'):
            name = 'query_exact_' + schema.identity.hex + '_' + field + '_v1'
            result.append('CREATE INDEX ' + quote_identifier(name) + ' ON ' + table +
                          '(' + field + ' COLLATE yadinassi_casefold_v1,'
                          'record_id COLLATE yadinassi_uuid_v1)')
            # Public exact lookups retain codepoint equality. Code already has
            # its UNIQUE BINARY autoindex; only Description needs this addition.
            if field == 'description':
                binary = 'query_exact_binary_' + schema.identity.hex + '_' + field + '_v1'
                result.append('CREATE INDEX ' + quote_identifier(binary) + ' ON ' + table +
                              '(' + field + ' COLLATE BINARY,record_id COLLATE yadinassi_uuid_v1)')
    if storage_version >= 7:
        if format_version not in (11, 12, 13, 14):
            result.append('CREATE INDEX document_query_order_v1 ON document_record(document_id,date,number,record_id)')
        result.append('CREATE INDEX document_query_number_casefold_v1 ON document_record'
                      '(document_id,number COLLATE yadinassi_casefold_v1,date,record_id)')
    return canonical_index_ddls(tuple(result))


def admit_query_indexes(connection, baseline_ddls, optional_ddls):
    """Admit exactly the old baseline or the complete declared optional bundle.

    An absent bundle remains readable. A partial, renamed, modified or unknown
    index is not an implicit request for repair and remains unsupported.
    """
    baseline = canonical_index_ddls(baseline_ddls)
    complete = canonical_index_ddls(baseline_ddls + optional_ddls)
    actual = tuple(connection.execute(
        "SELECT name,sql FROM sqlite_master WHERE type='index' AND sql IS NOT NULL ORDER BY name"))
    def declarations(ddls):
        return tuple((_index_name(ddl), ddl) for ddl in ddls)
    if actual == declarations(baseline): return False
    if optional_ddls and actual == declarations(complete): return True
    raise BackendError('unsupported')


def check_index_bundle_budget(connection, additions):
    """Refuse an installation that the bounded schema admission cannot reopen."""
    additions=canonical_index_ddls(additions)
    count,size=connection.execute("SELECT COUNT(*),COALESCE(SUM(length(CAST(name AS BLOB))+length(CAST(COALESCE(sql,'') AS BLOB))),0) FROM sqlite_master").fetchone()
    if (count+len(additions)>4096 or size+sum(len(_index_name(ddl).encode())+len(ddl.encode()) for ddl in additions)>64*1024*1024):
        raise BackendError('unsupported')
