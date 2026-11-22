"""Private Posted storage, never automatic posting or an executable handler grant."""
from dataclasses import dataclass
from uuid import UUID
from yadinassi.db.catalog.catalog_backend import BackendError
from yadinassi.db.document.document_backend import DocumentKey

MAX_POSTED_RECORDS=10000

_POSTED_VALUES = 'r.revision,p.document_revision,p.posted'
_POSTED_ON = ' ON p.document_id=r.document_id AND p.record_id=r.record_id'
_POSTED_JOIN = ' LEFT JOIN document_posting_state p'+_POSTED_ON
_HEADER_JOIN = ' LEFT JOIN main.document_posting_state p'+_POSTED_ON
_RECORD_KEY = 'r.document_id=? AND r.record_id=?'
_POINT_SQL = 'SELECT '+_POSTED_VALUES+' FROM document_record r'+_POSTED_JOIN+' WHERE '+_RECORD_KEY


def _header_sql(key, has_attributes):
    from .sqlite_catalog_layout import quote_identifier
    from .sqlite_document_layout import document_data_table
    from .sqlite_typed_rows import bounded_value_sql as bounded

    attributes = '1'
    if has_attributes:
        attributes = ('EXISTS(SELECT 1 FROM main.'+quote_identifier(document_data_table(key.document_id))+
                      ' a WHERE a.document_id=r.document_id AND a.record_id=r.record_id)')
    fields = (bounded('i.database_uuid',36),'i.generation','i.activated',
              bounded('r.record_id',36),bounded('r.number',36),bounded('r.date',14),
              'r.deletion_mark',bounded('p.record_id',36),_POSTED_VALUES,attributes,
              'EXISTS(SELECT 1 FROM main.document_schema d WHERE d.identity=? AND d.name=? AND d.definition=?)')
    return ('SELECT '+','.join(fields)+' FROM main.database_info i'
            ' LEFT JOIN main.document_record r ON '+_RECORD_KEY+
            _HEADER_JOIN+" WHERE i.singleton=1 AND i.activation_issues='[]' LIMIT 2")


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


def read_posted_statement(connection, database_id, key, *, header=None):
    """A detached point read on an admitted ordinary data connection."""
    from .sqlite_single_statement import fetch_all, fetch_one
    if (type(key) is not DocumentKey or type(key.database_id) is not UUID
            or key.database_id != database_id or type(key.document_id) is not UUID
            or type(key.record_id) is not UUID):
        raise BackendError('invalid_input')
    params = (str(key.document_id),str(key.record_id))
    if header is None:
        row = fetch_one(connection,_POINT_SQL,params)
        return None if row is None else decode_posted(*row)
    generation,number_length,has_attributes,manifest = header
    # A missing document is False, but a stale/missing database singleton
    # is not a missing record. Check both in the same SQLite statement.
    rows = fetch_all(connection,_header_sql(key,has_attributes),manifest+params)
    if len(rows)!=1: raise BackendError('schema_changed')
    database,current,active,record,number,date,mark,state,revision,state_revision,posted,attrs,declared = rows[0]
    if ((database,current,active)!=(str(database_id),generation,1)
            or type(current) is not int or type(active) is not int or declared!=1):
        raise BackendError('schema_changed')
    if record is None: return None
    if (type(record) is not str or record!=str(key.record_id) or not key.record_id.int
            or type(mark) is not int or mark not in (0,1) or not number
            or attrs!=1 or (state is not None and (state!=record or state_revision is None or posted is None))):
        raise BackendError('integrity')
    from yadinassi.db.catalog.catalog_qualifiers import validate_string
    from .sqlite_documents import _DATE_FIELD
    from .sqlite_catalog import _decode
    validate_string(number,number_length)
    _decode(['d',date],_DATE_FIELD,database_id)
    return decode_posted(revision,state_revision,posted)


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
