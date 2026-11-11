"""Bounded committed-snapshot reports for the exact physical15 forms grant.

This trusted host service accepts only manifest names and typed period bounds.
It never constructs/evaluates BSL or user SQL, obtains a transaction root, or
resolves a receipt. Detached uncertain receipts remain the controller's fence.
"""
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
import sqlite3
from uuid import UUID

from . import database_transactions as transactions
from .accumulation_movements import AccumulationDirection, _sum_resource_vectors
from .catalog_backend import BackendError, CatalogKey
from .configuration_inventory_application import InventoryApplicationConfiguration, PROFILE, canonical
from .document_backend import DocumentKey

MAX_INPUT_ROWS = 10000
MAX_INPUT_CELLS = 100000
MAX_TEXT = 1000000
MAX_ROWS = 1000
MAX_CELLS = 25000
MAX_LABELS = 2000
MAX_LABEL_LENGTH = 1152
UNAVAILABLE = '[Unavailable record]'


@dataclass(frozen=True, slots=True)
class InventoryReportColumn:
    name: str
    kind: str
    qualifiers: tuple = ()
    field_id: UUID | None = None
    role: str = 'standard'
    target_catalog_id: UUID | None = None


@dataclass(frozen=True, slots=True)
class InventoryReportResult:
    database_id: UUID
    configuration_generation: int
    source_digest: str
    report: str
    register_id: UUID
    register: str
    view: str
    boundaries: tuple[datetime, ...]
    columns: tuple[InventoryReportColumn, ...]
    rows: tuple[tuple, ...]
    labels: tuple[tuple[CatalogKey | DocumentKey, str], ...]


def _date(value):
    if type(value) is not datetime or value.tzinfo is not None or value.microsecond or value.fold:
        raise BackendError('invalid_input')
    return value


def _boundaries(view, at, start, end):
    if view == 'Movements' and at is start is end is None:
        return ()
    if view == 'Balance' and start is end is None:
        return (_date(at),)
    if view == 'Turnovers' and at is None:
        start, end = _date(start), _date(end)
        if start <= end:
            return start, end
    raise BackendError('invalid_input')


def _dimension(value):
    # Schema fixes each dimension's type. No arbitrary equality/presentation
    # hooks, ambient Decimal arithmetic or runtime metadata objects are used.
    if type(value) is CatalogKey:
        return value.database_id.int, value.catalog_id.int, value.record_id.int
    if type(value) is str:
        from .collation import caseless_string_key
        return caseless_string_key(value)
    if type(value) in (Decimal, bool, datetime):
        return value
    raise BackendError('integrity')


def _columns(schema, view):
    def field(f, role):
        return InventoryReportColumn(f.name, f.kind, f.qualifiers, f.identity, role, f.target_catalog_id)
    dimensions = tuple(field(f, 'dimension') for f in schema.dimensions)
    if view == 'Movements':
        return (InventoryReportColumn('Period', 'datetime', ('DateTime',)),
                InventoryReportColumn('Recorder', 'document_ref'),
                InventoryReportColumn('LineNumber', 'number', (10, 0, 'Nonnegative')),
                InventoryReportColumn('RecordType', 'accumulation_direction'),
                InventoryReportColumn('Active', 'boolean'), *dimensions,
                *(field(f, 'resource') for f in schema.resources),
                *(field(f, 'attribute') for f in schema.attributes))
    suffixes = ('Balance',) if view == 'Balance' else ('Turnover', 'Receipt', 'Expense')
    # (field_id, role) is the identity, not a potentially colliding display name.
    return dimensions + tuple(InventoryReportColumn(f.name + suffix, 'number',
        (38, f.qualifiers[1], 'Any'), f.identity, suffix.lower())
        for suffix in suffixes for f in schema.resources)


def _rows(port, schema, view, boundaries):
    from .query_sources import _check_number
    rows, groups = [], {}
    count = cells = text = 0
    for recorder, partition in port.scan(schema.identity):
        for row in partition.rows:
            count += 1
            values = row.dimensions + row.resources + row.attributes
            cells += len(values) + 5
            text += sum(len(value) for value in values if type(value) is str)
            if count > MAX_INPUT_ROWS or cells > MAX_INPUT_CELLS or text > MAX_TEXT:
                raise BackendError('unsupported')
            if row.active is not True:
                raise BackendError('unsupported')
            if view == 'Movements':
                rows.append((row.period, recorder, Decimal(row.line_number), row.direction,
                             row.active, *values))
                if len(rows) > MAX_ROWS:
                    raise BackendError('unsupported')
                continue
            if view == 'Balance':
                if row.period >= boundaries[0]:
                    continue
            elif not boundaries[0] <= row.period <= boundaries[1]:
                continue
            key = tuple(_dimension(value) for value in row.dimensions)
            group = groups.setdefault(key, (row.dimensions, [], []))
            group[1].append(row.resources)
            group[2].append(1 if row.direction is AccumulationDirection.RECEIPT else -1)
    if view == 'Movements':
        rows.sort(key=lambda r: (r[0], r[1].document_id.int, r[1].record_id.int, r[2]))
    else:
        for key in sorted(groups):
            dims, vectors, weights = groups[key]
            vectors, weights = tuple(vectors), tuple(weights)
            net = _sum_resource_vectors(schema, vectors, weights)
            if view == 'Balance' and all(value == 0 for value in net):
                continue
            totals = [net]
            if view == 'Turnovers':
                for sign in (1, -1):
                    chosen = tuple(v for v, w in zip(vectors, weights) if w == sign)
                    totals.append(_sum_resource_vectors(schema, chosen, (1,) * len(chosen)))
                # Same closed aggregate subset as accumulation_queries.load.
                if all(value == 0 for vector in totals for value in vector):
                    raise BackendError('unsupported')
            for vector in totals:
                for f, value in zip(schema.resources, vector):
                    try:
                        _check_number(value, (38, f.qualifiers[1], 'Any'))
                    except (TypeError, ValueError):
                        raise BackendError('unsupported') from None
            rows.append(dims + tuple(v for vector in totals for v in vector))
            if len(rows) > MAX_ROWS:
                raise BackendError('unsupported')
    return tuple(rows)


def _labels(owner, configuration, rows):
    from .sqlite_documents import DocumentView
    keys = set()
    for row in rows:
        for value in row:
            if type(value) in (CatalogKey, DocumentKey):
                keys.add(value)
                if len(keys) > MAX_LABELS:
                    raise BackendError('unsupported')
    def order(key):
        return ((0, key.catalog_id.int, key.record_id.int) if type(key) is CatalogKey
                else (1, key.document_id.int, key.record_id.int))
    documents = DocumentView(owner)  # Borrows the existing lease; never closes it.
    names = {s.identity: s.name for s in configuration.documents}
    labels, size = [], 0
    for key in sorted(keys, key=order):
        if type(key) is CatalogKey:
            card = owner.read_catalog(key)
            label = UNAVAILABLE if card is None or card.deletion_mark else card.description or card.code
        else:
            card = documents.read_document_values(key, ('number', 'date', 'deletion_mark'))
            if card is None or card.values[2]:
                label = UNAVAILABLE
            else:
                label = names[key.document_id] + ' ' + card.values[0] + ' (' + card.values[1].isoformat(sep=' ') + ')'
        if len(label) > MAX_LABEL_LENGTH:
            raise BackendError('unsupported')
        size += len(label)
        if size > MAX_TEXT:
            raise BackendError('unsupported')
        labels.append((key, label))
    return tuple(labels)


class InventoryReports:
    """Pinned full grant; each read returns one detached committed snapshot.

    No receipt is accepted/resolved here. The controller must not call while
    its form/operation has pending_commit/pending_refresh, including detached
    uncertain receipts. A report is not evidence of an operation's outcome.
    """
    def __init__(self, context, configuration):
        from .database_context import SQLiteDBContext
        if type(context) is not SQLiteDBContext:
            raise BackendError('unsupported')
        self._context, self._backend = context, context.backend
        from .sqlite_catalog import SQLiteCatalogBackend
        if type(self._backend) is not SQLiteCatalogBackend:
            raise BackendError('unsupported')
        try:
            self._configuration = canonical(configuration)
        except (ValueError, TypeError):
            raise BackendError('unsupported') from None
        self._binding = (self._backend.database_id, self._backend.configuration_generation)
        self._admit()

    def _admit(self):
        from .sqlite_catalog import SQLiteCatalogBackend
        b = self._backend
        if (type(b) is not SQLiteCatalogBackend or self._context.backend is not b
                or b.format_version != 15
                or type(b.accumulation_configuration) is not InventoryApplicationConfiguration
                or b.accumulation_configuration.profile != PROFILE):
            raise BackendError('unsupported')
        if b._closed:
            raise BackendError('closed')
        transactions.require_admission()
        if (transactions._execution.get() is not None
                or transactions._execution_backend.get() is not None
                or transactions._registered(b) is not None):
            raise BackendError('unsupported')
        if (b.accumulation_configuration != self._configuration
                or (b.database_id, b.configuration_generation) != self._binding):
            raise BackendError('schema_changed')

    def read(self, report_name, *, at=None, start=None, end=None):
        self._admit()
        if type(report_name) is not str:
            raise BackendError('invalid_input')
        grant = next((r for r in self._configuration.reports if r.name == report_name), None)
        if grant is None:
            raise BackendError('unsupported')
        boundaries = _boundaries(grant.view, at, start, end)
        schema = next(s for s in self._configuration.registers if s.identity == grant.register_id)
        columns = _columns(schema, grant.view)
        from .sqlite_inventory_profile import admit
        from .sqlite_transactions import _accumulation_port
        owner = self._backend.begin_read()
        try:
            if (owner.database_id, owner.configuration_generation) != self._binding:
                raise BackendError('schema_changed')
            # Reimport actual full bytes/marker on this very lease, not export
            # through a second connection and not generation/cache alone.
            current = admit(owner._connection, owner.database_id,
                            self._configuration.catalogs, self._configuration.documents)
            if current != self._configuration:
                raise BackendError('schema_changed')
            rows = _rows(_accumulation_port(owner), schema, grant.view, boundaries)
            if len(rows) * len(columns) > MAX_CELLS:
                raise BackendError('unsupported')
            labels = _labels(owner, self._configuration, rows)
            if (sum(len(v) for row in rows for v in row if type(v) is str)
                    + sum(len(label) for _, label in labels) > MAX_TEXT):
                raise BackendError('unsupported')
            result = InventoryReportResult(*self._binding, current.source_digest,
                grant.name, grant.register_id, grant.register, grant.view, boundaries, columns, rows, labels)
        except BackendError:
            raise
        except sqlite3.Error:
            raise BackendError('storage_error') from None
        except (ValueError, TypeError, KeyError, IndexError, OverflowError):
            raise BackendError('integrity') from None
        finally:
            owner.close()
        return result
