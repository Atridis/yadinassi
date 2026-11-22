"""Unactivated host storage primitives for recorder-owned scalar movements.

No open-time DDL, public BSL API or guessed posting handler behavior. The future
explicit profile installs DDL and binds schemas; callers supply an already
owned transaction. This port never commits, closes or creates that transaction.
"""
from dataclasses import dataclass
from hashlib import sha256
import sqlite3
from uuid import UUID
from yadinassi.db.catalog.catalog_backend import BackendError
from yadinassi.db.document.document_backend import DocumentKey
from yadinassi.db.document.document_movements import (RecorderMovementRow, RecorderReplacement,
    RecorderRegisterSchema, validate_replacement, mutation_identity)

from . import sqlite_movement_layout as movement
from .sqlite_typed_rows import encode_typed_columns, decode_typed_columns

MAX_BYTES=16*1024*1024
MAX_ROW_BYTES=1024*1024
MAX_DATABASE_ROWS=10000
MAX_DATABASE_BYTES=16*1024*1024
MAX_DATABASE_PARTITIONS=10000
RECORDER_DDL=(
    'CREATE TABLE recorder_register_schema(register_id TEXT PRIMARY KEY, definition TEXT NOT NULL)',
    'CREATE TABLE recorder_register_document(register_id TEXT NOT NULL REFERENCES recorder_register_schema(register_id), document_id TEXT NOT NULL REFERENCES document_schema(identity), PRIMARY KEY(register_id,document_id))',
    'CREATE TABLE recorder_partition(register_id TEXT NOT NULL, document_id TEXT NOT NULL, record_id TEXT NOT NULL, revision INTEGER NOT NULL CHECK(revision>0), PRIMARY KEY(register_id,document_id,record_id), FOREIGN KEY(register_id,document_id) REFERENCES recorder_register_document(register_id,document_id), FOREIGN KEY(document_id,record_id) REFERENCES document_record(document_id,record_id))',
)


def recorder_movement_ddls(schemas):
    return movement.data_ddls('recorder', schemas)


def validate_database_budget(connection, schemas):
    """Same aggregate bounds for writer savepoints and fresh admission."""
    movement.database_budget(connection, 'recorder', schemas, max_rows=MAX_DATABASE_ROWS,
                             max_bytes=MAX_DATABASE_BYTES, max_partitions=MAX_DATABASE_PARTITIONS)


def _canonical_rows(rows):
    return [list(row[:-1]) for row in rows]


def _storage():
    from . import sqlite_catalog
    return sqlite_catalog


def _json(value):return _storage()._json(value)
def _hash(value):return sha256(_json(value).encode()).hexdigest()


@dataclass(frozen=True, slots=True)
class RecorderPartition:
    register_id: UUID
    recorder: DocumentKey
    revision: int
    rows: tuple[RecorderMovementRow,...]
    snapshot: str


@dataclass(frozen=True, slots=True)
class RecorderOutcome:
    register_id: UUID
    recorder: DocumentKey
    revision: int
    snapshot: str
    row_count: int


def schema_data(schema,database_id):
    if type(schema) is not RecorderRegisterSchema:raise BackendError('invalid_input')
    if type(schema.recorder_documents) is not tuple or not schema.recorder_documents:raise BackendError('invalid_input')
    key=DocumentKey(database_id,schema.recorder_documents[0],UUID(int=1))
    validate_replacement(schema,RecorderReplacement(schema.identity,key,(),'0'*64),database_id)
    if type(schema.name) is not str or type(schema.dimension_count) is not int or not 0<=schema.dimension_count<=len(schema.fields):raise BackendError('invalid_input')
    if bool(schema.name)!=(schema.dimension_count>0):raise BackendError('invalid_input')
    return ['recorder_scalar_v1',str(schema.identity),sorted(str(v) for v in schema.recorder_documents),
            _storage()._fields_data(schema.fields),schema.name,schema.dimension_count]


def decode_movement_row(schema, database_id, raw):
    line, active, byte_count, *physical = raw
    if (type(line) is not int or not 1 <= line <= MAX_DATABASE_ROWS or type(active) is not int
            or active not in (0,1) or type(byte_count) is not int or not 0 <= byte_count <= MAX_ROW_BYTES):
        raise BackendError('integrity')
    try:
        data = decode_typed_columns(physical, schema)
        if len(_json(data).encode()) != byte_count:
            raise BackendError('integrity')
        values = tuple(_storage()._decode(value, field, database_id)
                       for value, field in zip(data, schema.fields))
        return RecorderMovementRow(line, bool(active), values)
    except (ValueError,TypeError):
        raise BackendError('integrity') from None


class RecorderMovementPort:
    """Private borrowed-connection port. Admission/activation is not installed."""
    def __init__(self,connection,database_id,generation,schemas):
        if type(connection) is not sqlite3.Connection or type(database_id) is not UUID or not database_id.int:
            raise BackendError('invalid_input')
        if type(generation) is not int or not 1<=generation<2**63 or type(schemas) is not tuple or not 1<=len(schemas)<=512:
            raise BackendError('invalid_input')
        if connection.execute('PRAGMA foreign_keys').fetchone()!=(1,):raise BackendError('unsupported')
        self.connection=connection;self.database_id=database_id;self.generation=generation
        data=tuple(schema_data(s,database_id) for s in schemas)
        if len({s.identity for s in schemas})!=len(schemas):raise BackendError('invalid_input')
        self.schemas={s.identity:s for s in schemas};self.definitions={s.identity:_json(d) for s,d in zip(schemas,data)}

    def _require(self,register_id,recorder,*,_query_view=None):
        from .sqlite_transactions import _require_movement_scan
        _require_movement_scan(self.connection, _query_view)
        schema=self.schemas.get(register_id)
        if schema is None:raise BackendError('unsupported')
        validate_replacement(schema,RecorderReplacement(register_id,recorder,(),'0'*64),self.database_id)
        if self.connection.execute('SELECT 1 FROM recorder_register_schema WHERE register_id=? AND (typeof(definition)!=\'text\' OR length(CAST(definition AS BLOB))>65536)',(str(register_id),)).fetchone():raise BackendError('integrity')
        row=self.connection.execute('SELECT definition FROM recorder_register_schema WHERE register_id=?',(str(register_id),)).fetchone()
        if row!=(self.definitions[register_id],):raise BackendError('integrity')
        if self.connection.execute('SELECT COUNT(*) FROM recorder_register_document WHERE register_id=?',(str(register_id),)).fetchone()[0]>256:raise BackendError('integrity')
        allowed=tuple(r[0] for r in self.connection.execute('SELECT document_id FROM recorder_register_document WHERE register_id=? ORDER BY document_id',(str(register_id),)))
        if allowed!=tuple(sorted(str(v) for v in schema.recorder_documents)):raise BackendError('integrity')
        return schema

    def _encoded(self, schema, rows):
        result = []
        size = 0
        for row in rows:
            data = [_storage()._encode(movement.canonical_number(value, field), field, self.database_id)
                    for value, field in zip(row.values, schema.fields)]
            raw = _json(data)
            n = len(raw.encode())
            size += n
            if n > MAX_ROW_BYTES or size > MAX_BYTES:
                raise BackendError('unsupported')
            result.append([row.line_number, row.active, raw, encode_typed_columns(data, schema)])
        return result

    def _dimension_key(self, schema, row):
        from .sqlite_registers import _dimension
        return tuple(tuple(_dimension(value, field, self.database_id))
                     for value, field in zip(row.values[:schema.dimension_count],
                                             schema.fields[:schema.dimension_count]))

    def _snapshot(self,schema,recorder,revision,rows):
        return _hash(['recorder_partition_v1',str(self.database_id),self.generation,
            self.definitions[schema.identity],str(recorder.document_id),str(recorder.record_id),revision,_canonical_rows(rows)])

    def _decoded_partition(self, schema, recorder, revision, source):
        """Shared logical decoder; no declaration lookups or transaction changes."""
        if type(revision) is not int or not 0 <= revision < 2**63:
            raise BackendError('integrity')
        rows=[]
        for raw in source:
            if raw[0] != len(rows)+1: raise BackendError('integrity')
            if len(rows) >= MAX_DATABASE_ROWS: raise BackendError('unsupported')
            rows.append(decode_movement_row(schema,self.database_id,raw))
        if revision == 0 and rows: raise BackendError('integrity')
        rows=tuple(rows)
        validate_replacement(schema,RecorderReplacement(schema.identity,recorder,rows,'0'*64),self.database_id)
        encoded=self._encoded(schema,rows)
        return RecorderPartition(schema.identity,recorder,revision,rows,self._snapshot(schema,recorder,revision,encoded))

    def scan(self, register_id, *, _query_view=None):
        """One declaration check and two bounded streams, never partition N+1."""
        from contextlib import closing
        from .sqlite_partition_scan import ordered_partitions, recorder_key
        schema = self.schemas.get(register_id)
        if schema is None: raise BackendError('unsupported')
        self._require(register_id,DocumentKey(self.database_id,schema.recorder_documents[0],UUID(int=1)), _query_view=_query_view)
        args = (str(register_id),)
        count = self.connection.execute('SELECT COUNT(*) FROM recorder_partition WHERE register_id=?',args).fetchone()[0]
        if count > MAX_DATABASE_PARTITIONS: raise BackendError('unsupported')
        table, columns = movement.references('recorder', schema)
        movement.scoped_budget(self.connection, table, columns, ' WHERE register_id=?', args,
                               max_rows=MAX_DATABASE_ROWS, max_bytes=MAX_BYTES, max_row_bytes=MAX_ROW_BYTES,
                                       oversize_code='integrity')
        if self.connection.execute('PRAGMA foreign_key_check').fetchone():raise BackendError('integrity')
        # Cursor acquisition is nested so even a failure opening the second
        # stream cannot retain the first cursor on the borrowed connection.
        result=[];dimensions=set()
        with closing(self.connection.execute(
                'SELECT document_id,record_id,revision FROM recorder_partition '
                'WHERE register_id=? ORDER BY document_id,record_id', args)) as metadata:
            projection = ','.join(('document_id','record_id','line_number','active','payload_bytes',*columns))
            with closing(self.connection.execute('SELECT ' + projection + ' FROM ' + table
                    + ' WHERE register_id=? ORDER BY document_id,record_id,line_number', args)) as movements:
                for doc,record,revision,raw_rows in ordered_partitions(
                        metadata,movements,max_partitions=MAX_DATABASE_PARTITIONS,max_rows=MAX_DATABASE_ROWS):
                    key=recorder_key(self.database_id,doc,record)
                    partition=self._decoded_partition(schema,key,revision,raw_rows)
                    if schema.dimension_count:
                        for row in partition.rows:
                            dimension=self._dimension_key(schema,row)
                            if dimension in dimensions: raise BackendError('integrity')
                            dimensions.add(dimension)
                    result.append((key,partition))
        return tuple(result)

    def read(self,register_id,recorder):
        from contextlib import closing
        schema=self._require(register_id,recorder);key=(str(register_id),str(recorder.document_id),str(recorder.record_id))
        revision_row=self.connection.execute('SELECT revision FROM recorder_partition WHERE register_id=? AND document_id=? AND record_id=?',key).fetchone()
        revision=0 if revision_row is None else revision_row[0]
        if type(revision) is not int or not 0<=revision<2**63:raise BackendError('integrity')
        table, columns = movement.references('recorder', schema)
        where = ' WHERE register_id=? AND document_id=? AND record_id=?'
        count = movement.scoped_budget(self.connection, table, columns, where, key, max_rows=10000,
                                       max_bytes=MAX_BYTES, max_row_bytes=MAX_ROW_BYTES,
                                       oversize_code='integrity')
        if revision == 0 and count: raise BackendError('integrity')
        projection = ','.join(('line_number','active','payload_bytes',*columns))
        with closing(self.connection.execute('SELECT ' + projection + ' FROM ' + table + where + ' ORDER BY line_number',key)) as source:
            return self._decoded_partition(schema,recorder,revision,source)

    def _prepare_replacement(self,request):
        if type(request) is not RecorderReplacement:raise BackendError('invalid_input')
        schema=self._require(request.register_id,request.recorder)
        validate_replacement(schema,request,self.database_id);rows=self._encoded(schema,request.rows)
        intent=['recorder_replace_v1',str(self.database_id),self.generation,self.definitions[schema.identity],
            str(request.recorder.document_id),str(request.recorder.record_id),request.expected_snapshot,_canonical_rows(rows)]
        size=len(_json(intent).encode())
        if size>MAX_BYTES:raise BackendError('unsupported')
        return schema,rows,size

    def describe(self,request):
        _,_,size=self._prepare_replacement(request)
        return size,mutation_identity(request)

    def replace(self,request):
        schema,rows,_=self._prepare_replacement(request)
        current=self.read(request.register_id,request.recorder)
        if current.snapshot!=request.expected_snapshot:raise BackendError('conflict')
        if current.revision>=2**63-1:raise BackendError('unsupported')
        revision=current.revision+1
        snapshot=self._snapshot(schema,request.recorder,revision,rows)
        result=RecorderOutcome(request.register_id,request.recorder,revision,snapshot,len(rows))
        key=(str(request.register_id),str(request.recorder.document_id),str(request.recorder.record_id))
        table, columns = movement.references('recorder', schema)
        self.connection.execute('SAVEPOINT recorder_replace')
        try:
            self.connection.execute('DELETE FROM ' + table + ' WHERE register_id=? AND document_id=? AND record_id=?', key)
            self.connection.execute('INSERT INTO recorder_partition VALUES(?,?,?,?) ON CONFLICT(register_id,document_id,record_id) DO UPDATE SET revision=excluded.revision',(*key,revision))
            names = ','.join(('register_id','document_id','record_id','line_number','active','payload_bytes',*columns))
            marks = ','.join('?' for _ in range(6 + len(columns)))
            self.connection.executemany('INSERT INTO ' + table + '(' + names + ') VALUES(' + marks + ')',
                [(*key,line,int(active),len(raw.encode()),*values) for line,active,raw,values in rows])
            validate_database_budget(self.connection, tuple(self.schemas.values()))
            self.connection.execute('RELEASE recorder_replace')
        except BaseException:
            self.connection.execute('ROLLBACK TO recorder_replace');self.connection.execute('RELEASE recorder_replace');raise
        return result
