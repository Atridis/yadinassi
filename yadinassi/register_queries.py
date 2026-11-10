"""Typed, read-only independent register queries over a logical read snapshot.

Rows have a complete dimension key, not a fabricated Ref or owner. No virtual
period tables, recorder semantics, native parity or implicit scalar conversion.
"""
from uuid import UUID

from . import query_parser as syntax
from .catalog_backend import BackendError
from .register_backend import RegisterKey, RegisterRevision, RegisterRecord, RegisterScanRequest, RegisterPage


def needs_registers(statements):
    for statement in statements:
        if type(statement) is syntax.Destroy: continue
        for arm in statement.arms if type(statement) is syntax.Union else (statement,):
            if arm.family == 'information_register' or any(j.source.family == 'information_register' for j in arm.joins):
                return True
    return False


def register_field(manager, field, source_alias):
    from .queries import _Column
    if len(field.parts) == 2 and field.parts[0].casefold() != source_alias.casefold():
        raise ValueError('Unknown query source qualifier')
    matches = [f for f in manager._schema.fields if f.name.casefold() == field.parts[-1].casefold()]
    if len(matches) != 1: raise ValueError('Unknown information-register query field')
    item = matches[0]
    identity = (manager._catalogs._metadata, item.target_catalog_id) if item.kind == 'catalog_ref' else None
    return _Column('', item.identity, item.kind, item.qualifiers, item, reference_identity=identity)


def _record_values(manager, record, view, seen, digests, budget):
    from .queries import _section_value, _MAX_CELLS, _MAX_RESULT_TEXT
    from .relational_queries import _key
    schema = manager._schema
    if (type(record) is not RegisterRecord or type(record.key) is not RegisterKey
            or type(record.key.database_id) is not UUID or type(record.key.register_id) is not UUID
            or record.key.database_id != view.database_id or record.key.register_id != schema.identity
            or type(record.key.dimensions) is not tuple or len(record.key.dimensions) != len(schema.dimensions)
            or type(record.values) is not tuple or len(record.values) != len(schema.resources) + len(schema.attributes)
            or type(record.revision) is not RegisterRevision
            or type(record.revision.database_id) is not UUID or type(record.revision.register_id) is not UUID
            or type(record.revision.configuration_generation) is not int
            or (record.revision.database_id, record.revision.configuration_generation, record.revision.register_id)
                != (view.database_id, view.configuration_generation, schema.identity)
            or type(record.revision.key_digest) is not str or len(record.revision.key_digest) != 64
            or any(c not in '0123456789abcdef' for c in record.revision.key_digest)
            or type(record.revision.token) is not str or not 1 <= len(record.revision.token) <= 19
            or not record.revision.token.isascii() or not record.revision.token.isdecimal()
            or not 1 <= int(record.revision.token) < 2**63
            or str(int(record.revision.token)) != record.revision.token):
        raise BackendError('integrity')
    values = tuple(_section_value(manager, f, v)
                   for f, v in zip(schema.fields, record.key.dimensions + record.values))
    # Storage key identity is exact, while query string comparisons still use
    # the existing casefold policy. Case-distinct dimension keys are valid rows.
    key = tuple(('string', v) if type(v) is str else _key(v) for v in values[:len(schema.dimensions)])
    if key in seen or record.revision.key_digest in digests: raise BackendError('integrity')
    seen.add(key); digests.add(record.revision.key_digest)
    budget[0] += len(values)
    budget[1] += sum(len(v) for v in values if type(v) is str)
    if budget[0] > _MAX_CELLS or budget[1] > _MAX_RESULT_TEXT:
        raise ValueError('Query input resource limit exceeded')
    return dict(zip((f.identity for f in schema.fields), values))


def load_register(manager, columns, view, budget):
    manager._check_view(view)
    rows, seen, digests, cursors = [], set(), set(), set()
    continuation = None
    while True:
        page = view.scan_register(manager._schema.identity, RegisterScanRequest(1000, continuation))
        if (type(page) is not RegisterPage or type(page.rows) is not tuple or len(page.rows) > 1000
                or (page.continuation is not None and (type(page.continuation) is not str
                    or len(page.continuation) != 32 or page.continuation in cursors))):
            raise BackendError('integrity')
        for record in page.rows:
            values = _record_values(manager, record, view, seen, digests, budget)
            rows.append(tuple(values[column.field] for column in columns))
            if len(rows) > syntax.MAX_ROWS: raise ValueError('Query input row limit exceeded')
        if page.continuation is None: return rows
        if not page.rows: raise BackendError('integrity')
        continuation = page.continuation
        cursors.add(continuation)
