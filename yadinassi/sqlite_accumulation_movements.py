"""Unactivated accumulation occurrence storage on a borrowed SQLite connection.

DDL is installed only by an explicit owner, never on construction/open. This
port does not begin, commit, close or own the surrounding transaction. It is
not a runtime source grant, immutable query binding or native parity claim.
There is no dimension uniqueness constraint and no balance/turnover arithmetic.
"""
from hashlib import sha256
import json
import sqlite3
from uuid import UUID

from .accumulation_movements import (
    AccumulationDirection, AccumulationMovementRow, AccumulationOutcome,
    AccumulationPartition, AccumulationReplacement, MAX_MOVEMENT_ROWS,
    mutation_identity, validate_replacement, validate_schema,
)
from .catalog_backend import BackendError, CatalogKey, CatalogSchema, FieldSchema
from .document_backend import DocumentKey

MAX_BYTES = 16 * 1024 * 1024
MAX_ROW_BYTES = 1024 * 1024
MAX_SCHEMA_BYTES = 65536
MAX_RECEIPT_BYTES = 4096
MAX_DATABASE_ROWS = 10000
MAX_DATABASE_BYTES = 16 * 1024 * 1024
MAX_DATABASE_PARTITIONS = 10000
MAX_DATABASE_RECEIPTS = 10000
_PERIOD_FIELD = FieldSchema(UUID(int=1), 'Period', 'datetime', ('DateTime',))

ACCUMULATION_DDL = (
    'CREATE TABLE accumulation_register_schema(register_id TEXT PRIMARY KEY, definition TEXT NOT NULL)',
    'CREATE TABLE accumulation_register_document(register_id TEXT NOT NULL REFERENCES accumulation_register_schema(register_id), document_id TEXT NOT NULL REFERENCES document_schema(identity), PRIMARY KEY(register_id,document_id))',
    'CREATE TABLE accumulation_partition(register_id TEXT NOT NULL, document_id TEXT NOT NULL, record_id TEXT NOT NULL, revision INTEGER NOT NULL CHECK(revision>0), PRIMARY KEY(register_id,document_id,record_id), FOREIGN KEY(register_id,document_id) REFERENCES accumulation_register_document(register_id,document_id), FOREIGN KEY(document_id,record_id) REFERENCES document_record(document_id,record_id))',
    "CREATE TABLE accumulation_movement(register_id TEXT NOT NULL, document_id TEXT NOT NULL, record_id TEXT NOT NULL, line_number INTEGER NOT NULL CHECK(line_number>0), period TEXT NOT NULL CHECK(length(period)=14), active INTEGER NOT NULL CHECK(active IN(0,1)), direction TEXT NOT NULL CHECK(direction IN('receipt','expense')), values_json TEXT NOT NULL, PRIMARY KEY(register_id,document_id,record_id,line_number), FOREIGN KEY(register_id,document_id,record_id) REFERENCES accumulation_partition(register_id,document_id,record_id))",
    'CREATE TABLE accumulation_movement_receipt(operation_id TEXT PRIMARY KEY, request_hash TEXT NOT NULL, outcome_json TEXT NOT NULL)',
)


def _storage():
    # Only the closed scalar codec is shared. No IR dimension-key codec/schema.
    from . import sqlite_catalog
    return sqlite_catalog


def _json(value):
    return json.dumps(value, ensure_ascii=True, separators=(',', ':'), allow_nan=False)


def _hash(value):
    return sha256(_json(value).encode('utf-8')).hexdigest()


def schema_data(schema, *, enum_domain=None):
    validate_schema(schema, enum_domain=enum_domain)
    groups = [[[str(f.identity), f.name, f.kind, list(f.qualifiers)] for f in group]
              for group in (schema.dimensions, schema.resources, schema.attributes)]
    if schema.value_profile == 'catalog_reference_v1':
        groups = [[[str(f.identity), f.name, f.kind, list(f.qualifiers),
                    str(f.target_catalog_id) if f.target_catalog_id is not None else None]
                   for f in group] for group in (schema.dimensions, schema.resources, schema.attributes)]
    if schema.value_profile == 'catalog_enum_reference_v1':
        groups = [[[str(f.identity), f.name, f.kind, list(f.qualifiers),
                    str(f.target_catalog_id) if f.target_catalog_id is not None else None,
                    str(f.target_enum_id) if f.target_enum_id is not None else None]
                   for f in group] for group in (schema.dimensions, schema.resources, schema.attributes)]
    tag = 'accumulation_scalar_v1' if schema.value_profile == 'scalar_v1' else 'accumulation_reference_v1'
    if schema.value_profile == 'catalog_enum_reference_v1':
        tag = 'accumulation_enum_reference_v1'
    data = [tag, str(schema.identity), schema.name,
            schema.kind.value, sorted(str(v) for v in schema.recorder_documents), *groups]
    if len(_json(data).encode('utf-8')) > MAX_SCHEMA_BYTES:
        raise BackendError('unsupported')
    return data


def validate_database_budget(connection):
    """Bound all accumulation partitions, including retained empty revisions."""
    rows, size = connection.execute(
        'SELECT COUNT(*),COALESCE(SUM(length(CAST(values_json AS BLOB))'
        '+length(CAST(period AS BLOB))+length(CAST(direction AS BLOB))+64),0) '
        'FROM accumulation_movement').fetchone()
    partitions = connection.execute('SELECT COUNT(*) FROM accumulation_partition').fetchone()[0]
    receipts, receipt_bytes = connection.execute(
        'SELECT COUNT(*),COALESCE(SUM(length(CAST(outcome_json AS BLOB))+128),0) '
        'FROM accumulation_movement_receipt').fetchone()
    if (rows > MAX_DATABASE_ROWS or size > MAX_DATABASE_BYTES
            or partitions > MAX_DATABASE_PARTITIONS or receipts > MAX_DATABASE_RECEIPTS
            or receipt_bytes > MAX_DATABASE_BYTES):
        raise BackendError('unsupported')


class AccumulationMovementPort:
    """Private host primitive; the owning application supplies the transaction."""

    def __init__(self, connection, database_id, generation, schemas, *, active_only=False, reference_catalogs=()):
        if (type(connection) is not sqlite3.Connection or type(database_id) is not UUID
                or not database_id.int or type(generation) is not int
                or not 1 <= generation < 2**63 or type(schemas) is not tuple
                or not 1 <= len(schemas) <= 512 or type(active_only) is not bool):
            raise BackendError('invalid_input')
        if connection.execute('PRAGMA foreign_keys').fetchone() != (1,):
            raise BackendError('unsupported')
        data = tuple(schema_data(schema) for schema in schemas)
        identities = [item.identity for schema in schemas for item in (schema, *schema.fields)]
        if (len(set(identities)) != len(identities)
                or len({s.name.casefold() for s in schemas}) != len(schemas)):
            raise BackendError('invalid_input')
        definitions = tuple(_json(item) for item in data)
        if sum(len(item.encode('utf-8')) for item in definitions) > MAX_BYTES:
            raise BackendError('unsupported')
        self.connection = connection
        self.database_id = database_id
        self.generation = generation
        # The generic host codec can retain inactive raw occurrences. The
        # activated source-granted profile is deliberately narrower.
        self.active_only = active_only
        self.schemas = {schema.identity: schema for schema in schemas}
        self.definitions = {schema.identity: raw for schema, raw in zip(schemas, definitions)}
        if (type(reference_catalogs) is not tuple or len(reference_catalogs) > 512
                or any(type(c) is not CatalogSchema for c in reference_catalogs)):
            raise BackendError('invalid_input')
        targets = {c.identity for c in reference_catalogs}
        reference_profile = any(schema.value_profile == 'catalog_reference_v1' for schema in schemas)
        if (reference_profile != bool(reference_catalogs)
                or any(schema.value_profile != ('catalog_reference_v1' if reference_profile else 'scalar_v1')
                       for schema in schemas)
                or any(f.target_catalog_id not in targets for schema in schemas
                       for f in schema.fields if f.kind == 'catalog_ref')):
            raise BackendError('unsupported')
        self._reference_layout = (_storage().load_layout(connection, reference_catalogs)
                                  if reference_profile else None)

    def _require(self, register_id, recorder):
        if not self.connection.in_transaction:
            raise BackendError('closed')
        if type(register_id) is not UUID or not register_id.int:
            raise BackendError('invalid_input')
        schema = self.schemas.get(register_id)
        if schema is None:
            raise BackendError('unsupported')
        validate_replacement(schema, AccumulationReplacement(register_id, recorder, (), '0' * 64),
                             self.database_id)
        if self.connection.execute('PRAGMA foreign_keys').fetchone() != (1,):
            raise BackendError('unsupported')
        key = (str(register_id),)
        if self.connection.execute(
                "SELECT 1 FROM accumulation_register_schema WHERE register_id=? AND "
                "(typeof(definition)!='text' OR length(CAST(definition AS BLOB))>?)",
                (*key, MAX_SCHEMA_BYTES)).fetchone():
            raise BackendError('integrity')
        definition = self.connection.execute(
            'SELECT definition FROM accumulation_register_schema WHERE register_id=?', key).fetchone()
        if definition != (self.definitions[register_id],):
            raise BackendError('integrity')
        count = self.connection.execute(
            'SELECT COUNT(*) FROM accumulation_register_document WHERE register_id=?', key).fetchone()[0]
        if count != len(schema.recorder_documents):
            raise BackendError('integrity')
        allowed = tuple(row[0] for row in self.connection.execute(
            'SELECT document_id FROM accumulation_register_document WHERE register_id=? '
            'ORDER BY document_id', key))
        if allowed != tuple(sorted(str(v) for v in schema.recorder_documents)):
            raise BackendError('integrity')
        if self.connection.execute(
                'SELECT 1 FROM accumulation_register_document AS a '
                'LEFT JOIN document_schema AS d ON d.identity=a.document_id '
                'WHERE a.register_id=? AND d.identity IS NULL LIMIT 1', key).fetchone():
            raise BackendError('integrity')
        return schema

    def _encoded(self, schema, rows):
        result = []
        size = 0
        for row in rows:
            data = [[_storage()._encode(value, field, self.database_id)
                     for value, field in zip(values, fields)]
                    for values, fields in ((row.dimensions, schema.dimensions),
                                           (row.resources, schema.resources),
                                           (row.attributes, schema.attributes))]
            period = _storage()._encode(row.period, _PERIOD_FIELD, self.database_id)[1]
            raw = _json(data)
            # Conservative row envelope matches database-wide accounting.
            row_size = len(raw.encode('utf-8')) + len(period) + len(row.direction.value) + 64
            size += row_size
            if row_size > MAX_ROW_BYTES or size > MAX_BYTES:
                raise BackendError('unsupported')
            result.append([row.line_number, period, row.active, row.direction.value, raw])
        return result

    def _references(self, rows, *, writing):
        # JSON payloads have no SQL foreign key. Never consult a different view
        # or a memoized existence result: earlier staged catalog creates count.
        from .sqlite_catalog_layout import quote_identifier
        for row in rows:
            for value in row.dimensions + row.attributes:
                if type(value) is CatalogKey and value.record_id.int:
                    table = quote_identifier(self._reference_layout.table_name(value.catalog_id))
                    if self.connection.execute('SELECT 1 FROM ' + table + ' WHERE record_id=?',
                                               (str(value.record_id),)).fetchone() is None:
                        raise BackendError('not_found' if writing else 'integrity')

    def _snapshot(self, schema, recorder, revision, rows):
        return _hash(['accumulation_partition_v1', str(self.database_id), self.generation,
                      self.definitions[schema.identity], str(recorder.document_id),
                      str(recorder.record_id), revision, rows])

    def read(self, register_id, recorder):
        schema = self._require(register_id, recorder)
        key = (str(register_id), str(recorder.document_id), str(recorder.record_id))
        revision_row = self.connection.execute(
            'SELECT revision FROM accumulation_partition '
            'WHERE register_id=? AND document_id=? AND record_id=?', key).fetchone()
        revision = 0 if revision_row is None else revision_row[0]
        if type(revision) is not int or not (0 if revision_row is None else 1) <= revision < 2**63:
            raise BackendError('integrity')
        if revision and self.connection.execute(
                'SELECT 1 FROM document_record WHERE document_id=? AND record_id=?', key[1:]).fetchone() is None:
            raise BackendError('integrity')
        count, size, largest = self.connection.execute(
            'SELECT COUNT(*),COALESCE(SUM(length(CAST(values_json AS BLOB))'
            '+length(CAST(period AS BLOB))+length(CAST(direction AS BLOB))+64),0),'
            'COALESCE(MAX(length(CAST(values_json AS BLOB))'
            '+length(CAST(period AS BLOB))+length(CAST(direction AS BLOB))+64),0) '
            'FROM accumulation_movement WHERE register_id=? AND document_id=? AND record_id=?',
            key).fetchone()
        if count > MAX_MOVEMENT_ROWS or size > MAX_BYTES or largest > MAX_ROW_BYTES:
            raise BackendError('unsupported')
        if not revision and count:
            raise BackendError('integrity')
        from contextlib import closing
        with closing(self.connection.execute(
                'SELECT line_number,period,active,direction,values_json FROM accumulation_movement '
                'WHERE register_id=? AND document_id=? AND record_id=? ORDER BY line_number', key)) as source:
            return self._decoded_partition(schema, recorder, revision, source)

    def _decoded_partition(self, schema, recorder, revision, source):
        """Same canonical occurrence decoder for point reads and batch scans."""
        if type(revision) is not int or not 0 <= revision < 2**63:
            raise BackendError('integrity')
        rows = []
        for line, period, active, direction, raw in source:
            if len(rows) >= MAX_MOVEMENT_ROWS: raise BackendError('unsupported')
            if (type(line) is not int or line != len(rows) + 1 or type(period) is not str
                    or len(period) != 14 or type(active) is not int or active not in (0, 1)
                    or type(direction) is not str or type(raw) is not str):
                raise BackendError('integrity')
            try:
                data = json.loads(raw)
                if type(data) is not list or len(data) != 3 or _json(data) != raw:
                    raise BackendError('integrity')
                groups = []
                for values, fields in zip(data, (schema.dimensions, schema.resources, schema.attributes)):
                    if type(values) is not list or len(values) != len(fields):
                        raise BackendError('integrity')
                    groups.append(tuple(_storage()._decode(value, field, self.database_id)
                                        for value, field in zip(values, fields)))
                date = _storage()._decode(['d', period], _PERIOD_FIELD, self.database_id)
                rows.append(AccumulationMovementRow(line, date, bool(active),
                                                    AccumulationDirection(direction), *groups))
            except (ValueError, TypeError, RecursionError):
                raise BackendError('integrity') from None
        if revision == 0 and rows: raise BackendError('integrity')
        rows = tuple(rows)
        try:
            validate_replacement(schema, AccumulationReplacement(schema.identity, recorder, rows, '0' * 64),
                                 self.database_id)
        except BackendError:
            raise BackendError('integrity') from None
        if self.active_only and any(row.active is not True for row in rows):
            raise BackendError('unsupported')
        self._references(rows, writing=False)
        encoded = self._encoded(schema, rows)
        return AccumulationPartition(schema.identity, recorder, revision, rows,
                                     self._snapshot(schema, recorder, revision, encoded))

    def scan(self, register_id):
        """Bounded raw occurrences from two streams on the borrowed snapshot."""
        from contextlib import closing
        from .sqlite_partition_scan import ordered_partitions, recorder_key
        if type(register_id) is not UUID or not register_id.int:
            raise BackendError('invalid_input')
        schema = self.schemas.get(register_id)
        if schema is None:
            raise BackendError('unsupported')
        self._require(register_id, DocumentKey(self.database_id, schema.recorder_documents[0], UUID(int=1)))
        validate_database_budget(self.connection)
        args = (str(register_id),)
        # Aggregate limits before fetching any payload, preserving the point
        # port's per-partition (not per-register) configurable bounds.
        oversized = self.connection.execute(
            'SELECT 1 FROM accumulation_movement WHERE register_id=? '
            'GROUP BY document_id,record_id HAVING COUNT(*)>? OR '
            'SUM(length(CAST(values_json AS BLOB))+length(CAST(period AS BLOB))'
            '+length(CAST(direction AS BLOB))+64)>? OR '
            'MAX(length(CAST(values_json AS BLOB))+length(CAST(period AS BLOB))'
            '+length(CAST(direction AS BLOB))+64)>? LIMIT 1',
            (*args, MAX_MOVEMENT_ROWS, MAX_BYTES, MAX_ROW_BYTES)).fetchone()
        if oversized:
            raise BackendError('unsupported')
        for table in ('accumulation_register_document', 'accumulation_partition', 'accumulation_movement'):
            if self.connection.execute('PRAGMA foreign_key_check(' + table + ')').fetchone():
                raise BackendError('integrity')
        result = []
        with closing(self.connection.execute(
                'SELECT document_id,record_id,revision FROM accumulation_partition WHERE register_id=? '
                'ORDER BY document_id,record_id', args)) as metadata:
            with closing(self.connection.execute(
                    'SELECT document_id,record_id,line_number,period,active,direction,values_json '
                    'FROM accumulation_movement WHERE register_id=? '
                    'ORDER BY document_id,record_id,line_number', args)) as movements:
                for document,record,revision,raw_rows in ordered_partitions(
                        metadata,movements,max_partitions=MAX_DATABASE_PARTITIONS,max_rows=MAX_DATABASE_ROWS):
                    key = recorder_key(self.database_id,document,record)
                    if type(revision) is not int or not 1 <= revision < 2**63:
                        raise BackendError('integrity')
                    result.append((key,self._decoded_partition(schema,key,revision,raw_rows)))
        return tuple(result)

    def describe(self, request):
        if type(request) is not AccumulationReplacement:
            raise BackendError('invalid_input')
        schema = self._require(request.register_id, request.recorder)
        validate_replacement(schema, request, self.database_id)
        if self.active_only and any(row.active is not True for row in request.rows):
            raise BackendError('unsupported')
        self._references(request.rows, writing=True)
        rows = self._encoded(schema, request.rows)
        intent = ['accumulation_replace_v1', str(self.database_id), self.generation,
                  self.definitions[schema.identity], str(request.recorder.document_id),
                  str(request.recorder.record_id), request.expected_snapshot, rows]
        size = len(_json(intent).encode('utf-8'))
        if size > MAX_BYTES:
            raise BackendError('unsupported')
        return _hash(intent), size, mutation_identity(request)

    def replace(self, operation, request):
        if type(operation) is not UUID or not operation.int:
            raise BackendError('invalid_input')
        digest, _, _ = self.describe(request)
        if self.connection.execute(
                'SELECT 1 FROM accumulation_movement_receipt WHERE operation_id=?',
                (str(operation),)).fetchone():
            raise BackendError('conflict')
        current = self.read(request.register_id, request.recorder)
        if current.snapshot != request.expected_snapshot:
            raise BackendError('conflict')
        if current.revision >= 2**63 - 1:
            raise BackendError('unsupported')
        schema = self.schemas[request.register_id]
        rows = self._encoded(schema, request.rows)
        revision = current.revision + 1
        snapshot = self._snapshot(schema, request.recorder, revision, rows)
        outcome = AccumulationOutcome(request.register_id, request.recorder, revision, snapshot, len(rows))
        raw = _json(['accumulation_outcome_v1', str(request.register_id), str(request.recorder.document_id),
                     str(request.recorder.record_id), revision, snapshot, len(rows)])
        key = (str(request.register_id), str(request.recorder.document_id), str(request.recorder.record_id))
        self.connection.execute('SAVEPOINT accumulation_replace')
        try:
            self.connection.execute(
                'DELETE FROM accumulation_movement WHERE register_id=? AND document_id=? AND record_id=?', key)
            self.connection.execute(
                'INSERT INTO accumulation_partition VALUES(?,?,?,?) '
                'ON CONFLICT(register_id,document_id,record_id) DO UPDATE SET revision=excluded.revision',
                (*key, revision))
            self.connection.executemany('INSERT INTO accumulation_movement VALUES(?,?,?,?,?,?,?,?)',
                [(*key, line, period, int(active), direction, values)
                 for line, period, active, direction, values in rows])
            self.connection.execute('INSERT INTO accumulation_movement_receipt VALUES(?,?,?)',
                                    (str(operation), _hash([digest, raw]), raw))
            validate_database_budget(self.connection)
            self.connection.execute('RELEASE accumulation_replace')
        except BaseException:
            self.connection.execute('ROLLBACK TO accumulation_replace')
            self.connection.execute('RELEASE accumulation_replace')
            raise
        return outcome

    def resolve(self, operation, request):
        """Read the immutable receipt; never read or replay current movements."""
        if type(operation) is not UUID or not operation.int:
            raise BackendError('invalid_input')
        digest, _, _ = self.describe(request)
        key = (str(operation),)
        if self.connection.execute(
                "SELECT 1 FROM accumulation_movement_receipt WHERE operation_id=? AND "
                "(typeof(request_hash)!='text' OR length(request_hash)!=64 OR "
                "typeof(outcome_json)!='text' OR length(CAST(outcome_json AS BLOB))>?)",
                (*key, MAX_RECEIPT_BYTES)).fetchone():
            raise BackendError('integrity')
        row = self.connection.execute(
            'SELECT request_hash,outcome_json FROM accumulation_movement_receipt WHERE operation_id=?', key).fetchone()
        if row is None:
            return None
        bound, raw = row
        try:
            data = json.loads(raw)
            canonical = _json(data)
        except (ValueError, TypeError, RecursionError):
            raise BackendError('integrity') from None
        if type(data) is not list or len(data) != 7 or canonical != raw or data[0] != 'accumulation_outcome_v1':
            raise BackendError('integrity')
        if data[1:4] != [str(request.register_id), str(request.recorder.document_id), str(request.recorder.record_id)]:
            raise BackendError('conflict')
        revision, snapshot, row_count = data[4:]
        if (type(revision) is not int or not 1 <= revision < 2**63
                or type(snapshot) is not str or len(snapshot) != 64
                or any(c not in '0123456789abcdef' for c in snapshot)
                or type(row_count) is not int or row_count != len(request.rows)):
            raise BackendError('integrity')
        if bound != _hash([digest, raw]):
            raise BackendError('conflict')
        schema = self.schemas[request.register_id]
        if snapshot != self._snapshot(schema, request.recorder, revision, self._encoded(schema, request.rows)):
            raise BackendError('integrity')
        return AccumulationOutcome(request.register_id, request.recorder, revision, snapshot, row_count)
