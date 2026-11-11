"""Unactivated host storage primitives for recorder-owned scalar movements.

No open-time DDL, public BSL API or guessed posting handler behavior. The future
explicit profile installs DDL and binds schemas; callers supply an already
owned transaction. This port never commits, closes or creates that transaction.
"""
from dataclasses import dataclass
from hashlib import sha256
import json
import sqlite3
from uuid import UUID
from .catalog_backend import BackendError
from .document_backend import DocumentKey
from .document_movements import (RecorderMovementRow, RecorderReplacement,
    RecorderRegisterSchema, validate_replacement, mutation_identity)

MAX_BYTES=16*1024*1024
MAX_ROW_BYTES=1024*1024
RECORDER_DDL=(
    'CREATE TABLE recorder_register_schema(register_id TEXT PRIMARY KEY, definition TEXT NOT NULL)',
    'CREATE TABLE recorder_register_document(register_id TEXT NOT NULL REFERENCES recorder_register_schema(register_id), document_id TEXT NOT NULL REFERENCES document_schema(identity), PRIMARY KEY(register_id,document_id))',
    'CREATE TABLE recorder_partition(register_id TEXT NOT NULL, document_id TEXT NOT NULL, record_id TEXT NOT NULL, revision INTEGER NOT NULL CHECK(revision>0), PRIMARY KEY(register_id,document_id,record_id), FOREIGN KEY(register_id,document_id) REFERENCES recorder_register_document(register_id,document_id), FOREIGN KEY(document_id,record_id) REFERENCES document_record(document_id,record_id))',
    'CREATE TABLE recorder_movement(register_id TEXT NOT NULL, document_id TEXT NOT NULL, record_id TEXT NOT NULL, line_number INTEGER NOT NULL CHECK(line_number>0), active INTEGER NOT NULL CHECK(active IN(0,1)), values_json TEXT NOT NULL, PRIMARY KEY(register_id,document_id,record_id,line_number), FOREIGN KEY(register_id,document_id,record_id) REFERENCES recorder_partition(register_id,document_id,record_id))',
    'CREATE TABLE recorder_movement_receipt(operation_id TEXT PRIMARY KEY, request_hash TEXT NOT NULL, outcome_json TEXT NOT NULL)',
)


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
    return ['recorder_scalar_v1',str(schema.identity),sorted(str(v) for v in schema.recorder_documents),
            _storage()._fields_data(schema.fields)]


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

    def _require(self,register_id,recorder):
        if not self.connection.in_transaction:raise BackendError('closed')
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

    def _encoded(self,schema,rows):
        result=[];size=0
        for row in rows:
            data=[_storage()._encode(v,f,self.database_id) for v,f in zip(row.values,schema.fields)]
            raw=_json(data);n=len(raw.encode());size+=n
            if n>MAX_ROW_BYTES or size>MAX_BYTES:raise BackendError('unsupported')
            result.append([row.line_number,row.active,raw])
        return result

    def _snapshot(self,schema,recorder,revision,rows):
        return _hash(['recorder_partition_v1',str(self.database_id),self.generation,
            self.definitions[schema.identity],str(recorder.document_id),str(recorder.record_id),revision,rows])

    def read(self,register_id,recorder):
        schema=self._require(register_id,recorder);key=(str(register_id),str(recorder.document_id),str(recorder.record_id))
        revision_row=self.connection.execute('SELECT revision FROM recorder_partition WHERE register_id=? AND document_id=? AND record_id=?',key).fetchone()
        revision=0 if revision_row is None else revision_row[0]
        if type(revision) is not int or not 0<=revision<2**63:raise BackendError('integrity')
        count,total=self.connection.execute('SELECT COUNT(*),COALESCE(SUM(length(CAST(values_json AS BLOB))),0) FROM recorder_movement WHERE register_id=? AND document_id=? AND record_id=?',key).fetchone()
        if count>10000 or total>MAX_BYTES:raise BackendError('unsupported')
        if revision==0 and count:raise BackendError('integrity')
        rows=[]
        for line,active,raw in self.connection.execute('SELECT line_number,active,values_json FROM recorder_movement WHERE register_id=? AND document_id=? AND record_id=? ORDER BY line_number',key):
            if type(line) is not int or line!=len(rows)+1 or type(active) is not int or active not in (0,1) or type(raw) is not str or len(raw.encode())>MAX_ROW_BYTES:raise BackendError('integrity')
            try:
                data=json.loads(raw)
                if type(data) is not list or len(data)!=len(schema.fields):raise BackendError('integrity')
                values=tuple(_storage()._decode(v,f,self.database_id) for v,f in zip(data,schema.fields))
                if _json(data)!=raw:raise BackendError('integrity')
                rows.append(RecorderMovementRow(line,bool(active),values))
            except (ValueError,TypeError):raise BackendError('integrity') from None
        rows=tuple(rows)
        validate_replacement(schema,RecorderReplacement(register_id,recorder,rows,'0'*64),self.database_id)
        encoded=self._encoded(schema,rows)
        return RecorderPartition(register_id,recorder,revision,rows,self._snapshot(schema,recorder,revision,encoded))

    def describe(self,request):
        if type(request) is not RecorderReplacement:raise BackendError('invalid_input')
        schema=self._require(request.register_id,request.recorder)
        validate_replacement(schema,request,self.database_id);rows=self._encoded(schema,request.rows)
        intent=['recorder_replace_v1',str(self.database_id),self.generation,self.definitions[schema.identity],
            str(request.recorder.document_id),str(request.recorder.record_id),request.expected_snapshot,rows]
        return _hash(intent),len(_json(intent).encode()),mutation_identity(request)

    def replace(self,operation,request):
        if type(operation) is not UUID or not operation.int:raise BackendError('invalid_input')
        digest,size,_=self.describe(request)
        if size>MAX_BYTES:raise BackendError('unsupported')
        current=self.read(request.register_id,request.recorder)
        if current.snapshot!=request.expected_snapshot:raise BackendError('conflict')
        if current.revision>=2**63-1:raise BackendError('unsupported')
        schema=self.schemas[request.register_id];rows=self._encoded(schema,request.rows);revision=current.revision+1
        snapshot=self._snapshot(schema,request.recorder,revision,rows)
        result=RecorderOutcome(request.register_id,request.recorder,revision,snapshot,len(rows))
        payload=_json([str(result.register_id),str(result.recorder.document_id),str(result.recorder.record_id),revision,snapshot,len(rows)])
        key=(str(request.register_id),str(request.recorder.document_id),str(request.recorder.record_id))
        if self.connection.execute('SELECT 1 FROM recorder_movement_receipt WHERE operation_id=?',(str(operation),)).fetchone():raise BackendError('conflict')
        self.connection.execute('SAVEPOINT recorder_replace')
        try:
            self.connection.execute('DELETE FROM recorder_movement WHERE register_id=? AND document_id=? AND record_id=?',key)
            self.connection.execute('INSERT INTO recorder_partition VALUES(?,?,?,?) ON CONFLICT(register_id,document_id,record_id) DO UPDATE SET revision=excluded.revision',(*key,revision))
            self.connection.executemany('INSERT INTO recorder_movement VALUES(?,?,?,?,?,?)',[(*key,line,int(active),raw) for line,active,raw in rows])
            self.connection.execute('INSERT INTO recorder_movement_receipt VALUES(?,?,?)',(str(operation),_hash([digest,payload]),payload))
            self.connection.execute('RELEASE recorder_replace')
        except BaseException:
            self.connection.execute('ROLLBACK TO recorder_replace');self.connection.execute('RELEASE recorder_replace');raise
        return result

    def resolve(self,operation,request):
        """Recover the immutable outcome, never replay the replacement."""
        if type(operation) is not UUID or not operation.int:raise BackendError('invalid_input')
        digest,_,_=self.describe(request)
        row=self.connection.execute('SELECT request_hash,outcome_json FROM recorder_movement_receipt WHERE operation_id=?',(str(operation),)).fetchone()
        if row is None:return None
        bound,raw=row
        if type(raw) is not str or len(raw.encode())>4096:raise BackendError('integrity')
        try:data=json.loads(raw)
        except (ValueError,TypeError):raise BackendError('integrity') from None
        if type(data) is not list or len(data)!=6 or _json(data)!=raw:raise BackendError('integrity')
        if data[:3]!=[str(request.register_id),str(request.recorder.document_id),str(request.recorder.record_id)]:raise BackendError('conflict')
        if type(data[3]) is not int or not 1<=data[3]<2**63 or type(data[4]) is not str or len(data[4])!=64 or any(c not in '0123456789abcdef' for c in data[4]) or type(data[5]) is not int or data[5]!=len(request.rows):raise BackendError('integrity')
        if bound!=_hash([digest,raw]):raise BackendError('conflict')
        schema=self.schemas[request.register_id]
        if data[4]!=self._snapshot(schema,request.recorder,data[3],self._encoded(schema,request.rows)):raise BackendError('integrity')
        return RecorderOutcome(request.register_id,request.recorder,data[3],data[4],data[5])
