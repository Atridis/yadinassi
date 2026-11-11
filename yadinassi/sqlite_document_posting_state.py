"""Private Posted storage, never automatic posting or an executable handler grant."""
from dataclasses import dataclass
from uuid import UUID
from .catalog_backend import BackendError
from .document_backend import DocumentKey

MAX_POSTED_RECORDS=10000

POSTED_DDL='CREATE TABLE document_posting_state(document_id TEXT NOT NULL, record_id TEXT NOT NULL, document_revision INTEGER NOT NULL CHECK(document_revision>0), posted INTEGER NOT NULL CHECK(posted IN(0,1)), PRIMARY KEY(document_id,record_id), FOREIGN KEY(document_id,record_id) REFERENCES document_record(document_id,record_id))'

@dataclass(frozen=True,slots=True)
class PostedIntent:
    recorder: DocumentKey
    document_revision: int
    posted: bool


def read_posted(connection,database_id,key):
    if type(key) is not DocumentKey or key.database_id!=database_id:raise BackendError('invalid_input')
    if not connection.in_transaction:raise BackendError('closed')
    row=connection.execute('SELECT r.revision,p.document_revision,p.posted FROM document_record r LEFT JOIN document_posting_state p ON p.document_id=r.document_id AND p.record_id=r.record_id WHERE r.document_id=? AND r.record_id=?',(str(key.document_id),str(key.record_id))).fetchone()
    if row is None:return None
    return decode_posted(*row)


def decode_posted(revision, state_revision, posted):
    """Same validation for a point read and an owned batch LEFT JOIN."""
    if type(revision) is not int or not 1<=revision<2**63:raise BackendError('integrity')
    if state_revision is None and posted is None:return False
    if type(state_revision) is not int or not 1<=state_revision<=revision or type(posted) is not int or posted not in (0,1):raise BackendError('integrity')
    return bool(posted)




def validate_database_budget(connection):
    if connection.execute('SELECT COUNT(*) FROM document_posting_state').fetchone()[0]>MAX_POSTED_RECORDS:
        raise BackendError('unsupported')


def stage_posted(connection,database_id,intent):
    """Caller owns the root transaction and durable receipt; no commit here.

    Requires the actual document revision already staged on the same connection.
    No revision allocation, callbacks, movement writes or mode inference occur.
    """
    if type(intent) is not PostedIntent or type(intent.document_revision) is not int or not 1<=intent.document_revision<2**63 or type(intent.posted) is not bool:raise BackendError('invalid_input')
    key=intent.recorder
    if type(key) is not DocumentKey or key.database_id!=database_id or any(type(v) is not UUID or not v.int for v in (database_id,key.document_id,key.record_id)):raise BackendError('invalid_input')
    if not connection.in_transaction:raise BackendError('closed')
    current=connection.execute('SELECT revision FROM document_record WHERE document_id=? AND record_id=?',(str(key.document_id),str(key.record_id))).fetchone()
    if current!=(intent.document_revision,):raise BackendError('conflict')
    count=connection.execute('SELECT COUNT(*) FROM document_posting_state').fetchone()[0]
    exists=connection.execute('SELECT 1 FROM document_posting_state WHERE document_id=? AND record_id=?',(str(key.document_id),str(key.record_id))).fetchone()
    if count+(0 if exists else 1)>MAX_POSTED_RECORDS:raise BackendError('unsupported')
    connection.execute('INSERT INTO document_posting_state VALUES(?,?,?,?) ON CONFLICT(document_id,record_id) DO UPDATE SET document_revision=excluded.document_revision,posted=excluded.posted',(str(key.document_id),str(key.record_id),intent.document_revision,int(intent.posted)))
    return intent

POSTED_RECEIPT_DDL='CREATE TABLE document_posting_receipt(operation_id TEXT PRIMARY KEY, request_hash TEXT NOT NULL, outcome_json TEXT NOT NULL)'


def describe_posted(database_id,generation,intent):
    from .sqlite_recorder_movements import _hash,_json
    if type(intent) is not PostedIntent or type(intent.recorder) is not DocumentKey:raise BackendError('invalid_input')
    key=intent.recorder
    if key.database_id!=database_id or any(type(v) is not UUID or not v.int for v in (database_id,key.document_id,key.record_id)) or type(intent.document_revision) is not int or not 1<=intent.document_revision<2**63 or type(intent.posted) is not bool:raise BackendError('invalid_input')
    data=['posted_state_v1',str(database_id),generation,str(key.document_id),str(key.record_id),intent.document_revision,intent.posted]
    return _hash(data),len(_json(data).encode()),('document_posted',key.document_id,key.record_id)


def write_posted_receipt(connection,database_id,generation,operation,intent):
    from .sqlite_recorder_movements import _json,_hash
    if type(operation) is not UUID or not operation.int:raise BackendError('invalid_input')
    digest,_,_=describe_posted(database_id,generation,intent)
    stage_posted(connection,database_id,intent)
    payload=_json([str(intent.recorder.document_id),str(intent.recorder.record_id),intent.document_revision,intent.posted])
    bound=_hash([digest,payload])
    connection.execute('INSERT INTO document_posting_receipt VALUES(?,?,?)',(str(operation),bound,payload))
    return intent,bound,payload


def resolve_posted_receipt(connection,database_id,generation,operation,intent):
    from .sqlite_recorder_movements import _json,_hash
    digest,_,_=describe_posted(database_id,generation,intent)
    payload=_json([str(intent.recorder.document_id),str(intent.recorder.record_id),intent.document_revision,intent.posted])
    row=connection.execute('SELECT request_hash,outcome_json FROM document_posting_receipt WHERE operation_id=?',(str(operation),)).fetchone()
    if row is None:return None
    if row!=(_hash([digest,payload]),payload):raise BackendError('conflict')
    return intent
