"""Private Posted storage, never automatic posting or an executable handler grant."""
from dataclasses import dataclass
from uuid import UUID
from yadinassi.db.catalog.catalog_backend import BackendError
from yadinassi.db.document.document_backend import DocumentKey

MAX_POSTED_RECORDS=10000

_POSTED_VALUES = 'r.revision,p.document_revision,p.posted'
_POSTED_ON = ' ON p.document_id=r.document_id AND p.record_id=r.record_id'
_POSTED_JOIN = ' LEFT JOIN document_posting_state p'+_POSTED_ON
_RECORD_KEY = 'r.document_id=? AND r.record_id=?'
_POINT_SQL = 'SELECT '+_POSTED_VALUES+' FROM document_record r'+_POSTED_JOIN+' WHERE '+_RECORD_KEY


POSTED_DDL='CREATE TABLE document_posting_state(document_id TEXT NOT NULL, record_id TEXT NOT NULL, document_revision INTEGER NOT NULL CHECK(document_revision>0), posted INTEGER NOT NULL CHECK(posted IN(0,1)), PRIMARY KEY(document_id,record_id), FOREIGN KEY(document_id,record_id) REFERENCES document_record(document_id,record_id))'

@dataclass(frozen=True,slots=True)
class PostedIntent:
    recorder: DocumentKey
    document_revision: int
    posted: bool


def read_posted(connection,database_id,key):
    if type(key) is not DocumentKey or key.database_id!=database_id:raise BackendError('invalid_input')
    if not connection.in_transaction:raise BackendError('closed')
    row=connection.execute(_POINT_SQL,(str(key.document_id),str(key.record_id))).fetchone()
    return None if row is None else decode_posted(*row)


def read_posted_statement(connection, database_id, key):
    """Detached host point read; the manager's stronger header gate is separate."""
    from .sqlite_single_statement import fetch_one
    if (type(key) is not DocumentKey or type(key.database_id) is not UUID
            or key.database_id != database_id or type(key.document_id) is not UUID
            or type(key.record_id) is not UUID):
        raise BackendError('invalid_input')
    row = fetch_one(connection,_POINT_SQL,(str(key.document_id),str(key.record_id)))
    return None if row is None else decode_posted(*row)


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
    """Caller owns the root transaction; no commit here.

    Requires the actual document revision already staged on the same connection.
    No revision allocation, callbacks, movement writes or mode inference occur.
    """
    if type(intent) is not PostedIntent or type(intent.document_revision) is not int or not 1<=intent.document_revision<2**63 or type(intent.posted) is not bool:raise BackendError('invalid_input')
    key=intent.recorder
    if type(key) is not DocumentKey or key.database_id!=database_id or any(type(v) is not UUID or not v.int for v in (database_id,key.document_id,key.record_id)):raise BackendError('invalid_input')
    if not connection.in_transaction:raise BackendError('closed')
    fields = (str(key.document_id),str(key.record_id))
    current, count, exists = connection.execute(
        'SELECT (SELECT revision FROM document_record WHERE document_id=? AND record_id=?),'
        '(SELECT COUNT(*) FROM document_posting_state),'
        'EXISTS(SELECT 1 FROM document_posting_state WHERE document_id=? AND record_id=?)',
        fields+fields).fetchone()
    if current!=intent.document_revision:raise BackendError('conflict')
    if count+(0 if exists else 1)>MAX_POSTED_RECORDS:raise BackendError('unsupported')
    connection.execute('INSERT INTO document_posting_state VALUES(?,?,?,?) ON CONFLICT(document_id,record_id) DO UPDATE SET document_revision=excluded.document_revision,posted=excluded.posted',(*fields,intent.document_revision,int(intent.posted)))
    return intent



def describe_posted(database_id,generation,intent):
    from .sqlite_recorder_movements import _json
    if type(intent) is not PostedIntent or type(intent.recorder) is not DocumentKey:raise BackendError('invalid_input')
    key=intent.recorder
    if key.database_id!=database_id or any(type(v) is not UUID or not v.int for v in (database_id,key.document_id,key.record_id)) or type(intent.document_revision) is not int or not 1<=intent.document_revision<2**63 or type(intent.posted) is not bool:raise BackendError('invalid_input')
    data=['posted_state_v1',str(database_id),generation,str(key.document_id),str(key.record_id),intent.document_revision,intent.posted]
    return len(_json(data).encode()),('document_posted',key.document_id,key.record_id)
