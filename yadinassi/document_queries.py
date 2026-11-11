"""Read-only document query adapters over a bounded logical application view.

Document identity is not catalog identity. The query evaluator never constructs
SQL or changes document state. Scalars share existing field validation; dynamic
reference columns remain unavailable to Unload and TypeDescription codecs.
"""
from datetime import datetime
from decimal import Decimal
from uuid import UUID

from . import query_parser as syntax
from .catalog_backend import BackendError, TabularRow, TabularSectionRows
from .catalog_qualifiers import validate_string
from .dates import _date_from_datetime
from .document_backend import DocumentCard, DocumentKey, DocumentRevision, DocumentScanRequest, DocumentPage

_STANDARD = {'ref': 'ref', 'ссылка': 'ref', 'number': 'number', 'номер': 'number',
             'date': 'date', 'дата': 'date', 'deletionmark': 'deletion_mark',
             'пометкаудаления': 'deletion_mark', 'posted': 'posted',
             'проведен': 'posted', 'проведён': 'posted',
             'linenumber': 'line_number', 'номерстроки': 'line_number'}


def needs_documents(statements):
    return any(arm.family == 'document' or any(j.source.family == 'document' for j in arm.joins)
               for arm in syntax.selects(statements))


def document_field(manager, field, source_alias, section=None):
    from .queries import _Column
    if len(field.parts) == 2 and field.parts[0].casefold() != source_alias.casefold():
        raise ValueError('Unknown query source qualifier')
    name = field.parts[-1].casefold()
    standard = _STANDARD.get(name)
    allowed = ('ref', 'line_number') if section is not None else ('ref', 'number', 'date', 'deletion_mark', 'posted')
    if standard in allowed:
        kind, qualifiers = {'ref': ('document_ref', ()), 'number': ('string', (manager._schema.number_length,)),
                            'date': ('datetime', ('DateTime',)), 'deletion_mark': ('boolean', ()),
                            'posted': ('boolean', ()), 'line_number': ('number', (10, 0, 'Nonnegative'))}[standard]
        identity = (manager._documents._metadata, manager._schema.identity) if standard == 'ref' else None
        return _Column('', standard, kind, qualifiers, reference_identity=identity)
    fields = manager._schema.fields if section is None else section.fields
    matches = [item for item in fields if item.name.casefold() == name]
    if len(matches) != 1: raise ValueError('Unknown document query field')
    item = matches[0]
    identity = (manager._catalogs._metadata, item.target_catalog_id) if item.kind == 'catalog_ref' else None
    return _Column('', item.identity, item.kind, item.qualifiers, item, reference_identity=identity)


def _card_values(manager, card, view, seen, budget):
    """Validate the whole logical card, not only projected fields."""
    from .queries import _section_value, _MAX_CELLS, _MAX_RESULT_TEXT
    schema = manager._schema
    if (type(card) is not DocumentCard or type(card.key) is not DocumentKey
            or any(type(v) is not UUID for v in (card.key.database_id, card.key.document_id, card.key.record_id))
            or card.key.database_id != view.database_id or card.key.document_id != schema.identity
            or not card.key.record_id.int or card.key.record_id in seen
            or type(card.revision) is not DocumentRevision
            or any(type(v) is not UUID for v in (card.revision.database_id, card.revision.document_id, card.revision.record_id))
            or type(card.revision.configuration_generation) is not int
            or (card.revision.database_id, card.revision.configuration_generation, card.revision.document_id, card.revision.record_id)
                != (view.database_id, view.configuration_generation, schema.identity, card.key.record_id)
            or type(card.revision.token) is not str or not card.revision.token.isascii()
            or not card.revision.token.isdecimal() or not 1 <= len(card.revision.token) <= 19
            or not 1 <= int(card.revision.token) < 2**63 or str(int(card.revision.token)) != card.revision.token
            or type(card.date) is not datetime or card.date.tzinfo is not None or card.date.microsecond
            or type(card.deletion_mark) is not bool or type(card.values) is not tuple
            or len(card.values) != len(schema.fields) or type(card.tabular_sections) is not tuple
            or len(card.tabular_sections) != len(schema.tabular_sections)):
        raise BackendError('integrity')
    try: validate_string(card.number, schema.number_length)
    except (TypeError, ValueError): raise BackendError('integrity') from None
    if not card.number: raise BackendError('integrity')
    seen.add(card.key.record_id)
    values = {'ref': manager._ref(card.key.record_id), 'number': card.number,
              'date': _date_from_datetime(card.date), 'deletion_mark': card.deletion_mark, 'posted': getattr(card, 'posted', False)}
    values.update((f.identity, _section_value(manager, f, v)) for f, v in zip(schema.fields, card.values))
    sections, total_rows = {}, 0
    # Cost accounts for unprojected values too, before buffers can accumulate.
    def charge(cells):
        budget[0] += len(cells)
        budget[1] += sum(len(v) for v in cells if type(v) is str)
        if budget[0] > _MAX_CELLS or budget[1] > _MAX_RESULT_TEXT:
            raise ValueError('Query input resource limit exceeded')
    charge(tuple(values.values()))
    definitions = {s.identity: s for s in schema.tabular_sections}
    for item in card.tabular_sections:
        if (type(item) is not TabularSectionRows or type(item.section_id) is not UUID
                or item.section_id not in definitions or item.section_id in sections or type(item.rows) is not tuple):
            raise BackendError('integrity')
        section = definitions[item.section_id]
        total_rows += len(item.rows)
        if total_rows > 1000: raise BackendError('integrity')
        row_ids, rows = set(), []
        for number, row in enumerate(item.rows, 1):
            if (type(row) is not TabularRow or type(row.identity) is not UUID or not row.identity.int
                    or row.identity in row_ids or type(row.values) is not tuple or len(row.values) != len(section.fields)):
                raise BackendError('integrity')
            row_ids.add(row.identity)
            cells = {f.identity: _section_value(manager, f, v) for f, v in zip(section.fields, row.values)}
            cells.update(ref=values['ref'], line_number=Decimal(number))
            charge(tuple(cells.values()))
            rows.append(cells)
        sections[item.section_id] = rows
    return values, sections


def _load_sqlite_values(manager, section, columns, view, budget, predicate=()):
    """Use the owned SQLite port only; arbitrary backends keep full-card checks."""
    from .queries import _section_value, _MAX_CELLS, _MAX_RESULT_TEXT
    from .document_backend import DocumentValuePage, DocumentValueRow
    schema = manager._schema
    count, cells, text = view._validate_query_source(schema)
    budget[0] += cells
    budget[1] += text
    if count > syntax.MAX_ROWS: raise ValueError('Query input row limit exceeded')
    if budget[0] > _MAX_CELLS or budget[1] > _MAX_RESULT_TEXT:
        raise ValueError('Query input resource limit exceeded')
    continuation = None
    rows, cursors, seen = [], set(), set()
    while True:
        page = view.scan_document_values(schema.identity, DocumentScanRequest(1, continuation),
            tuple(c.field for c in columns), None if section is None else section.identity, predicate)
        if type(page) is not DocumentValuePage or type(page.rows) is not tuple or len(page.rows) > 1000:
            raise BackendError('integrity')
        for row in page.rows:
            if (type(row) is not DocumentValueRow or type(row.key) is not DocumentKey or
                    row.key.database_id != view.database_id or row.key.document_id != schema.identity or
                    type(row.key.record_id) is not UUID or not row.key.record_id.int or
                    type(row.values) is not tuple or len(row.values) != len(columns) or
                    type(row.line_number) is not int or
                    not (row.line_number == 0 if section is None else 1 <= row.line_number <= 1000) or
                    (row.key.record_id, row.line_number) in seen):
                raise BackendError('integrity')
            seen.add((row.key.record_id, row.line_number))
            values = []
            for column, value in zip(columns, row.values):
                if column.custom is not None: value = _section_value(manager, column.custom, value)
                elif column.field == 'ref':
                    if type(value) is not DocumentKey or value != row.key: raise BackendError('integrity')
                    value = manager._ref(value.record_id)
                elif column.field == 'date':
                    if type(value) is not datetime or value.tzinfo is not None or value.microsecond:
                        raise BackendError('integrity')
                    value = _date_from_datetime(value)
                elif column.field == 'number':
                    try: validate_string(value, schema.number_length)
                    except (TypeError, ValueError): raise BackendError('integrity') from None
                    if not value: raise BackendError('integrity')
                elif column.field in ('posted','deletion_mark'):
                    if type(value) is not bool: raise BackendError('integrity')
                elif column.field == 'line_number':
                    if type(value) is not Decimal or value != row.line_number: raise BackendError('integrity')
                values.append(value)
            rows.append(tuple(values))
            if len(rows) > syntax.MAX_ROWS: raise ValueError('Query input row limit exceeded')
        if page.continuation is None: return rows
        if type(page.continuation) is not str or len(page.continuation) != 32 or page.continuation in cursors:
            raise BackendError('integrity')
        # Empty sections may legitimately produce an empty page for an owner.
        continuation = page.continuation
        cursors.add(continuation)
        if len(cursors) > syntax.MAX_ROWS: raise BackendError('integrity')


def _owned_projection_view(view):
    from .sqlite_documents import DocumentView
    return type(view) is DocumentView and view._view._operation_id is None


def load_documents(manager, section, columns, view, budget, *, predicate=()):
    manager._check_view(view)
    if _owned_projection_view(view):
        return _load_sqlite_values(manager, section, columns, view, budget, predicate)
    rows, seen, cursors = [], set(), set()
    continuation = None
    while True:
        # A card can contain up to 1000 lines. Keep raw logical pages small;
        # projections and budgets are processed before requesting the next card.
        page = view.scan_documents(manager._schema.identity, DocumentScanRequest(1, continuation))
        if (type(page) is not DocumentPage or type(page.rows) is not tuple or len(page.rows) > 1
                or (page.continuation is not None and (type(page.continuation) is not str
                    or len(page.continuation) != 32 or page.continuation in cursors))):
            raise BackendError('integrity')
        for card in page.rows:
            values, sections = _card_values(manager, card, view, seen, budget)
            if len(seen) > syntax.MAX_ROWS: raise ValueError('Query input row limit exceeded')
            selected = (values,) if section is None else sections[section.identity]
            for values in selected:
                rows.append(tuple(values[column.field] for column in columns))
                if len(rows) > syntax.MAX_ROWS: raise ValueError('Query input row limit exceeded')
        if page.continuation is None: return rows
        if not page.rows: raise BackendError('integrity')
        continuation = page.continuation
        cursors.add(continuation)
