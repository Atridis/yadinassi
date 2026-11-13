"""Bounded committed-snapshot reports for the exact physical15/16 forms grants.

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
from .catalog_backend import (BackendError, CatalogKey, CatalogComparison,
    CatalogPredicate, CatalogOrder, CatalogScanRequest, CatalogPage, CatalogCard, Revision,
    CatalogValuePage, CatalogValueRow, CatalogSchema)
from .configuration_inventory_application import (
    InventoryApplicationConfiguration, PROFILE, MAX_REPORT_FILTERS)
from .configuration_inventory_enum_application import (
    InventoryEnumApplicationConfiguration, PROFILE as ENUM_PROFILE)
from .configuration_main_demo import MainDemoConfiguration, PROFILE as MAIN_DEMO_PROFILE
from .inventory_host_operations import canonical
from .enum_storage_values import EnumKey
from .document_backend import DocumentKey

MAX_INPUT_ROWS = 10000
MAX_INPUT_CELLS = 100000
MAX_TEXT = 1000000
MAX_ROWS = 1000
MAX_CELLS = 25000
MAX_LABELS = 2000
MAX_LABEL_LENGTH = 1152
UNAVAILABLE = '[Unavailable record]'
MAX_CHOICES = 32
MAX_CHOICE_SNAPSHOT_ROWS = 8192
MAX_CHOICE_SNAPSHOT_BYTES = 4 * 1024 * 1024


@dataclass(frozen=True, slots=True)
class InventoryReportChoice:
    key: CatalogKey
    code: str
    description: str


@dataclass(frozen=True, slots=True)
class InventoryReportChoices:
    database_id: UUID
    configuration_generation: int
    source_digest: str
    report: str
    dimension: str
    dimension_id: UUID
    catalog_id: UUID
    code: str
    rows: tuple[InventoryReportChoice, ...]
    error: str | None = None


@dataclass(frozen=True, slots=True)
class InventoryReportChoiceSnapshot(InventoryReportChoices):
    """Полный bounded snapshot; error snapshot_limit никогда не содержит partial rows."""


@dataclass(frozen=True, slots=True)
class InventoryReportColumn:
    name: str
    kind: str
    qualifiers: tuple = ()
    field_id: UUID | None = None
    role: str = 'standard'
    target_catalog_id: UUID | None = None


@dataclass(frozen=True, slots=True)
class InventoryReportFilter:
    """Trusted host input, not a browser key or a durable selection capability."""
    dimension_id: UUID
    key: CatalogKey
    configuration_generation: int


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
    periodicity: str | None = None
    filters: tuple[InventoryReportFilter, ...] = ()


def _date(value):
    if type(value) is not datetime or value.tzinfo is not None or value.microsecond or value.fold:
        raise BackendError('invalid_input')
    return value


def _boundaries(view, at, start, end):
    if view == 'Movements' and at is start is end is None:
        return ()
    if view == 'Balance' and start is end is None:
        return (_date(at),)
    if view in ('Turnovers', 'BalanceAndTurnovers') and at is None:
        start, end = _date(start), _date(end)
        if start <= end and (view != 'BalanceAndTurnovers' or 1900 <= start.year <= end.year <= 2099):
            return start, end
    raise BackendError('invalid_input')


def _dimension(value):
    # Schema fixes each dimension's type. No arbitrary equality/presentation
    # hooks, ambient Decimal arithmetic or runtime metadata objects are used.
    if type(value) is CatalogKey:
        return value.database_id.int, value.catalog_id.int, value.record_id.int
    if type(value) is EnumKey:
        return value.database_id.int, value.enum_id.int, value.value_id.int
    if type(value) is str:
        from .collation import caseless_string_key
        return caseless_string_key(value)
    if type(value) in (Decimal, bool, datetime):
        return value
    raise BackendError('integrity')


def _columns(schema, view, periodicity=None):
    def field(f, role):
        # Reports publish plain declared names, never enum identities/capabilities.
        if f.kind == 'enum_ref':
            return InventoryReportColumn(f.name, 'string', (), f.identity, role)
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
    if view == 'BalanceAndTurnovers':
        if periodicity not in ('None', 'Day', 'Month'):
            raise BackendError('invalid_input')
        if periodicity != 'None':
            dimensions += (InventoryReportColumn('Period', 'datetime', ('DateTime',)),)
        suffixes = ('OpeningBalance', 'Receipt', 'Expense', 'ClosingBalance')
    else:
        suffixes = ('Balance',) if view == 'Balance' else ('Turnover', 'Receipt', 'Expense')
    # (field_id, role) is the identity, not a potentially colliding display name.
    return dimensions + tuple(InventoryReportColumn(f.name + suffix, 'number',
        (38, f.qualifiers[1], 'Any'), f.identity, suffix.lower())
        for suffix in suffixes for f in schema.resources)


def _source_rows(port, schema):
    """Charge all occurrences before period or catalog-dimension exclusion."""
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
            yield recorder, row


def _rows(port, schema, view, boundaries):
    from .query_sources import _check_number
    rows, groups = [], {}
    for recorder, row in _source_rows(port, schema):
        values = row.dimensions + row.resources + row.attributes
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
            net = _sum_resource_vectors(schema, vectors, weights, enum_domain=port._enum_domain)
            if view == 'Balance' and all(value == 0 for value in net):
                continue
            totals = [net]
            if view == 'Turnovers':
                for sign in (1, -1):
                    chosen = tuple(v for v, w in zip(vectors, weights) if w == sign)
                    totals.append(_sum_resource_vectors(schema, chosen, (1,) * len(chosen), enum_domain=port._enum_domain))
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


def _statement_options(grant, periodicity, filters, binding):
    if type(filters) is not tuple or len(filters) > MAX_REPORT_FILTERS:
        raise BackendError('invalid_input')
    if grant.view != 'BalanceAndTurnovers':
        if periodicity is not None or filters:
            raise BackendError('invalid_input')
        return ()
    if type(periodicity) is not str or periodicity not in grant.periodicities:
        raise BackendError('invalid_input')
    declared = {f.dimension_id: f for f in grant.filters}
    selected = {}
    for value in filters:
        if (type(value) is not InventoryReportFilter or type(value.dimension_id) is not UUID
                or type(value.key) is not CatalogKey
                or any(type(part) is not UUID for part in
                       (value.key.database_id, value.key.catalog_id, value.key.record_id))
                or type(value.configuration_generation) is not int):
            raise BackendError('invalid_input')
        field = declared.get(value.dimension_id)
        if (field is None or value.dimension_id in selected
                or value.key.catalog_id != field.catalog_id or value.key.database_id != binding[0]):
            raise BackendError('invalid_input')
        if value.configuration_generation != binding[1]:
            raise BackendError('schema_changed')
        selected[value.dimension_id] = value
    # Canonical source order, independent of caller's tuple ordering.
    return tuple(selected[f.dimension_id] for f in grant.filters if f.dimension_id in selected)


def _filter_labels(owner, filters):
    labels = {}
    for value in filters:
        if value.key in labels:
            continue
        if not value.key.record_id.int:
            labels[value.key] = UNAVAILABLE
            continue
        card = owner.read_catalog(value.key)
        if card is None:
            raise BackendError('invalid_input')
        labels[value.key] = UNAVAILABLE if card.deletion_mark else card.description or card.code
    return tuple(labels.items())


def _statement_rows(port, schema, boundaries, periodicity, filters):
    from .accumulation_periods import StatementReducer
    from .query_sources import _check_number
    reducer = StatementReducer(schema, *boundaries,
        None if periodicity == 'None' else periodicity.lower(), combined=True, enum_domain=port._enum_domain)
    indices = {field.identity: i for i, field in enumerate(schema.dimensions)}
    selected = tuple((indices[value.dimension_id], value.key) for value in filters)
    for _, row in _source_rows(port, schema):
        if any(row.dimensions[index] != key for index, key in selected):
            continue
        reducer.add(row.dimensions, tuple(_dimension(v) for v in row.dimensions), row)
    rows = []
    try:
        for dims, period, totals in reducer.rows(MAX_ROWS):
            vectors = tuple(totals[name] for name in ('openingbalance','receipt','expense','closingbalance'))
            for vector in vectors:
                for field, value in zip(schema.resources, vector):
                    _check_number(value, (38, field.qualifiers[1], 'Any'))
            row = dims + (() if period is None else (period,)) + tuple(v for vector in vectors for v in vector)
            if (len(rows) + 1) * len(row) > MAX_CELLS:
                raise BackendError('unsupported')
            rows.append(row)
    except (ValueError, TypeError):
        raise BackendError('unsupported') from None
    width = len(schema.dimensions)
    rows.sort(key=lambda row: (tuple(_dimension(v) for v in row[:width]),
                              () if periodicity == 'None' else (row[width],)))
    return tuple(rows)


def _labels(owner, configuration, rows, known=()):
    from .sqlite_documents import DocumentView
    known = dict(known)
    keys = set(known)
    if len(keys) > MAX_LABELS:
        raise BackendError('unsupported')
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
        if key in known:
            label = known[key]
        elif type(key) is CatalogKey:
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


def _enum_text(rows, configuration, domain):
    """Erase storage identity only after exact committed-snapshot validation.

    Names are deterministic authored metadata labels, not native presentation
    semantics. Empty values stay empty. Wrong database/target/value is refused
    by the same closed domain used by storage before any string is published.
    """
    if type(configuration) not in (InventoryEnumApplicationConfiguration, MainDemoConfiguration):
        raise BackendError('unsupported')
    names = {(enum.identity, value.identity): value.name
             for enum in configuration.enumerations for value in enum.values}
    def cell(value):
        if type(value) is not EnumKey:
            return value
        domain.encode(value, value.enum_id)
        if not value.value_id.int:
            return ''
        label = names[(value.enum_id, value.value_id)]
        if type(label) is not str or len(label) > MAX_LABEL_LENGTH:
            raise BackendError('unsupported')
        return label
    return tuple(tuple(cell(value) for value in row) for row in rows)


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
                or type(b.accumulation_configuration) not in (InventoryApplicationConfiguration, InventoryEnumApplicationConfiguration, MainDemoConfiguration)
                or (b.format_version, type(b.accumulation_configuration),
                    b.accumulation_configuration.profile) not in (
                        (15, InventoryApplicationConfiguration, PROFILE),
                        (16, InventoryEnumApplicationConfiguration, ENUM_PROFILE),
                        (16, MainDemoConfiguration, MAIN_DEMO_PROFILE))):
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

    def choices(self, report_name, dimension_name, code=''):
        """One admitted snapshot of exact-code choices, never a write grant.

        A continuation refuses the entire candidate list. No cursor, connection
        or persistent identity is intended for direct browser serialization.
        """
        self._admit()
        if type(report_name) is not str or type(dimension_name) is not str or type(code) is not str:
            raise BackendError('invalid_input')
        grant = next((r for r in self._configuration.reports if r.name == report_name), None)
        field = None if grant is None else next((f for f in grant.filters if f.dimension == dimension_name), None)
        if grant is None or grant.view != 'BalanceAndTurnovers' or field is None:
            raise BackendError('unsupported')
        schema = next(s for s in self._configuration.catalogs if s.identity == field.catalog_id)
        try:
            if '\x00' in code or len(code.encode('utf-16-le')) // 2 > schema.code_length:
                raise BackendError('invalid_input')
        except UnicodeError:
            raise BackendError('invalid_input') from None
        terms = (CatalogComparison('deletion_mark', 'eq', False),)
        if code:
            terms += (CatalogComparison('code', 'eq', code),)
        request = CatalogScanRequest(predicate=terms[0] if len(terms) == 1 else CatalogPredicate('and', terms),
                                     order=(CatalogOrder('code'),), page_size=MAX_CHOICES)
        if type(self._configuration) is MainDemoConfiguration:
            def admit(connection, database_id, catalogs, documents):
                return self._backend._main_demo_source_snapshot(connection)
        elif type(self._configuration) is InventoryEnumApplicationConfiguration:
            from .sqlite_inventory_enum_profile import admit
        else:
            from .sqlite_inventory_profile import admit
        owner = self._backend.begin_read()
        try:
            if (owner.database_id, owner.configuration_generation) != self._binding:
                raise BackendError('schema_changed')
            current = admit(owner._connection, owner.database_id,
                            self._configuration.catalogs, self._configuration.documents)
            if current != self._configuration:
                raise BackendError('schema_changed')
            page = owner.scan_catalog(field.catalog_id, request)
            if (type(page) is not CatalogPage or type(page.cards) is not tuple or len(page.cards) > MAX_CHOICES
                    or page.continuation is not None and (type(page.continuation) is not str
                        or len(page.continuation) != 32 or any(c not in '0123456789abcdef' for c in page.continuation))):
                raise BackendError('integrity')
            seen = set()
            for card in page.cards:
                if (type(card) is not CatalogCard or type(card.key) is not CatalogKey
                        or any(type(v) is not UUID for v in (card.key.database_id,card.key.catalog_id,card.key.record_id))
                        or (card.key.database_id,card.key.catalog_id) != (owner.database_id,field.catalog_id)
                        or not card.key.record_id.int or card.key in seen or card.deletion_mark is not False
                        or type(card.revision) is not Revision or type(card.revision.configuration_generation) is not int
                        or card.revision.configuration_generation != owner.configuration_generation
                        or type(card.code) is not str or type(card.description) is not str
                        or len(card.code.encode('utf-16-le')) // 2 > schema.code_length
                        or len(card.description.encode('utf-16-le')) // 2 > schema.description_length
                        or '\x00' in card.code or '\x00' in card.description):
                    raise BackendError('integrity')
                seen.add(card.key)
            rows = () if page.continuation is not None else tuple(
                InventoryReportChoice(card.key, card.code, card.description) for card in page.cards)
            result = InventoryReportChoices(*self._binding, current.source_digest, grant.name,
                field.dimension, field.dimension_id, field.catalog_id, code, rows,
                'too_many_matches' if page.continuation is not None else None)
        except BackendError:
            raise
        except sqlite3.Error:
            raise BackendError('storage_error') from None
        except (ValueError, TypeError, KeyError, IndexError, OverflowError):
            raise BackendError('integrity') from None
        finally:
            owner.close()
        return result

    def choice_snapshot(self, report_name, dimension_name, code=''):
        """Полный detached выбор report filter, не разрешение изменять объекты."""
        self._admit()
        if type(report_name) is not str or type(dimension_name) is not str or type(code) is not str:
            raise BackendError('invalid_input')
        grant = next((r for r in self._configuration.reports if r.name == report_name), None)
        field = None if grant is None else next((f for f in grant.filters if f.dimension == dimension_name), None)
        if grant is None or grant.view != 'BalanceAndTurnovers' or field is None:
            raise BackendError('unsupported')
        schema = next(s for s in self._configuration.catalogs if s.identity == field.catalog_id)
        if type(schema) is not CatalogSchema:
            raise BackendError('integrity')
        try:
            if '\x00' in code or len(code.encode('utf-16-le')) // 2 > schema.code_length:
                raise BackendError('invalid_input')
            code.encode('utf-8')
        except UnicodeError:
            raise BackendError('invalid_input') from None
        terms = (CatalogComparison('deletion_mark', 'eq', False),)
        if code:
            terms += (CatalogComparison('code', 'eq', code),)
        predicate = terms[0] if len(terms) == 1 else CatalogPredicate('and', terms)
        if type(self._configuration) is MainDemoConfiguration:
            def admit(connection, database_id, catalogs, documents):
                return self._backend._main_demo_source_snapshot(connection)
        elif type(self._configuration) is InventoryEnumApplicationConfiguration:
            from .sqlite_inventory_enum_profile import admit
        else:
            from .sqlite_inventory_profile import admit
        owner = self._backend.begin_read()
        try:
            def verify():
                if (type(owner.database_id) is not UUID or type(owner.configuration_generation) is not int
                        or (owner.database_id, owner.configuration_generation) != self._binding):
                    raise BackendError('schema_changed')
                if owner.catalog_schema(field.catalog_id) != schema:
                    raise BackendError('schema_changed')
                current = admit(owner._connection, owner.database_id,
                                self._configuration.catalogs, self._configuration.documents)
                if current != self._configuration:
                    raise BackendError('schema_changed')
            verify()
            rows, seen, cursors = [], set(), set()
            size, cursor, error = 0, None, None
            while True:
                request = CatalogScanRequest(predicate=predicate, order=(CatalogOrder('code'),),
                                             page_size=256, continuation=cursor)
                page = owner.scan_catalog_values(field.catalog_id, request, ('code','description','deletion_mark'))
                if type(page) is not CatalogValuePage or type(page.rows) is not tuple or len(page.rows) > 256:
                    raise BackendError('integrity')
                for row in page.rows:
                    if (type(row) is not CatalogValueRow or type(row.key) is not CatalogKey
                            or any(type(v) is not UUID for v in (row.key.database_id,row.key.catalog_id,row.key.record_id))
                            or (row.key.database_id,row.key.catalog_id) != (owner.database_id,field.catalog_id)
                            or not row.key.record_id.int or row.key in seen
                            or type(row.values) is not tuple or len(row.values) != 3):
                        raise BackendError('integrity')
                    item_code, description, deleted = row.values
                    if type(item_code) is not str or type(description) is not str or deleted is not False:
                        raise BackendError('integrity')
                    for value, bound in ((item_code,schema.code_length),(description,schema.description_length)):
                        if '\x00' in value or len(value.encode('utf-16-le'))//2 > bound:
                            raise BackendError('integrity')
                        size += len(value.encode('utf-8'))
                    if code and item_code != code:
                        raise BackendError('integrity')
                    size += 64
                    if len(rows) >= MAX_CHOICE_SNAPSHOT_ROWS or size > MAX_CHOICE_SNAPSHOT_BYTES:
                        rows, error = [], 'snapshot_limit'
                        break
                    seen.add(row.key)
                    rows.append(InventoryReportChoice(row.key,item_code,description))
                if error is not None:
                    break
                cursor = page.continuation
                if cursor is None:
                    break
                if (type(cursor) is not str or len(cursor) != 32 or any(c not in '0123456789abcdef' for c in cursor)
                        or cursor in cursors or not page.rows):
                    raise BackendError('integrity')
                cursors.add(cursor)
            verify()
            self._admit()
            result = InventoryReportChoiceSnapshot(*self._binding,self._configuration.source_digest,grant.name,
                field.dimension,field.dimension_id,field.catalog_id,code,tuple(rows),error)
        except BackendError:
            raise
        except sqlite3.Error:
            raise BackendError('storage_error') from None
        except (ValueError,TypeError,KeyError,IndexError,OverflowError):
            raise BackendError('integrity') from None
        finally:
            owner.close()
        return result

    def read(self, report_name, *, at=None, start=None, end=None, periodicity=None, filters=()):
        self._admit()
        if type(report_name) is not str:
            raise BackendError('invalid_input')
        grant = next((r for r in self._configuration.reports if r.name == report_name), None)
        if grant is None:
            raise BackendError('unsupported')
        boundaries = _boundaries(grant.view, at, start, end)
        filters = _statement_options(grant, periodicity, filters, self._binding)
        schema = next(s for s in self._configuration.registers if s.identity == grant.register_id)
        columns = _columns(schema, grant.view, periodicity)
        if type(self._configuration) is MainDemoConfiguration:
            def admit(connection, database_id, catalogs, documents):
                return self._backend._main_demo_source_snapshot(connection)
        elif type(self._configuration) is InventoryEnumApplicationConfiguration:
            from .sqlite_inventory_enum_profile import admit
        else:
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
            known = _filter_labels(owner, filters)
            port = _accumulation_port(owner)
            rows = (_statement_rows(port, schema, boundaries, periodicity, filters)
                    if grant.view == 'BalanceAndTurnovers'
                    else _rows(port, schema, grant.view, boundaries))
            if type(current) in (InventoryEnumApplicationConfiguration, MainDemoConfiguration):
                rows = _enum_text(rows, current, self._backend._enum_domain)
            if len(rows) * len(columns) > MAX_CELLS:
                raise BackendError('unsupported')
            labels = _labels(owner, self._configuration, rows, known)
            if (sum(len(v) for row in rows for v in row if type(v) is str)
                    + sum(len(label) for _, label in labels) > MAX_TEXT):
                raise BackendError('unsupported')
            result = InventoryReportResult(*self._binding, current.source_digest,
                grant.name, grant.register_id, grant.register, grant.view, boundaries, columns, rows, labels,
                periodicity, filters)
        except BackendError:
            raise
        except sqlite3.Error:
            raise BackendError('storage_error') from None
        except (ValueError, TypeError, KeyError, IndexError, OverflowError):
            raise BackendError('integrity') from None
        finally:
            owner.close()
        return result
