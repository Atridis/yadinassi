"""Closed query-order index specifications; creation is explicit migration only."""
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
