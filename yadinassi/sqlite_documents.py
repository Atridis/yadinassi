"""SQLite v7 non-posting documents using the owned application's transaction.

Distinct document tables/keys; catalog layouts and receipt bytes are unchanged.
The closed tagged scalar codec is shared, never exposed as a native codec.
"""
from hashlib import sha256
import json
from uuid import UUID

from .catalog_backend import BackendError, CatalogSchema, FieldSchema, CatalogKey, TabularRow, TabularSectionRows
from .catalog_qualifiers import normalize_field, normalize_string, validate_string
from .document_backend import (DocumentSchema, DocumentKey, DocumentRevision, DocumentCard,
                               DocumentDraft, DocumentWriteOutcome, DocumentSelection)

DOCUMENT_DDL = (
    'CREATE TABLE document_schema(identity TEXT PRIMARY KEY, name TEXT NOT NULL UNIQUE, definition TEXT NOT NULL)',
    'CREATE TABLE document_record(document_id TEXT NOT NULL REFERENCES document_schema(identity), record_id TEXT NOT NULL, revision INTEGER NOT NULL CHECK(revision>0), number TEXT NOT NULL, date TEXT NOT NULL, deletion_mark INTEGER NOT NULL CHECK(deletion_mark IN(0,1)), values_json TEXT NOT NULL, sections_json TEXT NOT NULL, PRIMARY KEY(document_id,record_id), UNIQUE(document_id,number))',
    'CREATE TABLE document_sequence(document_id TEXT PRIMARY KEY REFERENCES document_schema(identity), next_value INTEGER NOT NULL CHECK(next_value>0))',
    'CREATE TABLE document_commit_receipt(operation_id TEXT PRIMARY KEY, request_hash TEXT NOT NULL, document_id TEXT NOT NULL, record_id TEXT NOT NULL, revision INTEGER NOT NULL CHECK(revision>0), number TEXT NOT NULL)',
)
_MAX_ROW = 1024 * 1024
_MAX_TOTAL = 16 * 1024 * 1024
_DATE_FIELD = FieldSchema(UUID(int=1), 'Date', 'datetime', ('DateTime',))
_RESERVED = {'number','номер','date','дата','posted','проведен','проведён','ref','ссылка',
             'deletionmark','пометкаудаления','write','записать','isnew','этоновый',
             'metadata','метаданные','getobject','получитьобъект','setnewobjectref','установитьссылкунового'}


def _storage():
    # Lazy import keeps the shared application admission/import graph acyclic.
    from . import sqlite_catalog
    return sqlite_catalog


def schema_data(schema):
    if type(schema) is not DocumentSchema or type(schema.number_length) is not int or not 1 <= schema.number_length <= 9:
        raise BackendError('invalid_input')
    surrogate = CatalogSchema(schema.identity, schema.name, schema.number_length, 0,
                              schema.fields, schema.tabular_sections, schema.numbering)
    data = _storage()._schema_data(surrogate)
    names = _RESERVED.copy(); ids = {schema.identity}
    for item in (*schema.fields, *schema.tabular_sections):
        if item.identity in ids or item.name.casefold() in names: raise BackendError('invalid_input')
        ids.add(item.identity); names.add(item.name.casefold())
        if hasattr(item, 'fields'):
            for field in item.fields:
                if field.identity in ids or field.name.casefold() in ('linenumber','номерстроки'):
                    raise BackendError('invalid_input')
                ids.add(field.identity)
    # This is a versioned local schema encoding, not a catalog registration.
    return ['nonposting_document_v1', data]


def parse_schema(raw):
    if type(raw) is not str or len(raw) > 65536: raise BackendError('integrity')
    data = json.loads(raw)
    if type(data) is not list or len(data) != 2 or data[0] != 'nonposting_document_v1': raise BackendError('integrity')
    old = _storage()._schema(_storage()._json(data[1]), allow_numbering=True)
    schema = DocumentSchema(old.identity, old.name, old.code_length, old.fields, old.tabular_sections, old.numbering)
    if schema_data(schema) != data: raise BackendError('integrity')
    return schema


def load_schemas(connection, catalogs):
    invalid = connection.execute("SELECT 1 FROM document_schema WHERE typeof(identity)!='text' OR length(CAST(identity AS BLOB))!=36 OR typeof(name)!='text' OR length(CAST(name AS BLOB))>512 OR typeof(definition)!='text' OR length(CAST(definition AS BLOB))>262144 LIMIT 1").fetchone()
    count, size = connection.execute('SELECT COUNT(*),COALESCE(SUM(length(CAST(definition AS BLOB))),0) FROM document_schema').fetchone()
    if invalid or not 1 <= count <= 512 or size > _MAX_TOTAL: raise BackendError('integrity')
    rows = tuple(connection.execute('SELECT identity,name,definition FROM document_schema ORDER BY identity'))
    schemas = tuple(parse_schema(row[2]) for row in rows)
    if any(row[:2] != (str(s.identity),s.name) for row,s in zip(rows,schemas)):
        raise BackendError('integrity')
    catalog_ids = {s.identity for s in catalogs}
    identities = set()
    for s in (*catalogs, *schemas):
        for item in (s, *s.fields, *s.tabular_sections, *(f for section in s.tabular_sections for f in section.fields)):
            if item.identity in identities: raise BackendError('integrity')
            identities.add(item.identity)
    if len({s.name.casefold() for s in schemas}) != len(schemas): raise BackendError('integrity')
    if sum(len(s.tabular_sections) for s in (*catalogs,*schemas)) > 512: raise BackendError('unsupported')
    if any(f.target_catalog_id not in catalog_ids for s in schemas for f in (*s.fields, *(f for section in s.tabular_sections for f in section.fields)) if f.kind == 'catalog_ref'):
        raise BackendError('integrity')
    expected = {str(s.identity): 10 ** s.number_length for s in schemas if s.numbering == 'decimal_v1'}
    if connection.execute('SELECT COUNT(*) FROM document_sequence').fetchone()[0] != len(expected): raise BackendError('integrity')
    for identity, value in connection.execute('SELECT document_id,next_value FROM document_sequence'):
        if identity not in expected or type(value) is not int or not 1 <= value <= expected[identity]: raise BackendError('integrity')
    return schemas, rows


def _receipt_hash(intent_hash, outcome):
    revision = outcome.revision
    payload = ['document_outcome_v1', intent_hash, str(revision.database_id),
               revision.configuration_generation, str(revision.document_id),
               str(revision.record_id), revision.token, outcome.number]
    return sha256(_storage()._json(payload).encode('utf-8')).hexdigest()


class DocumentView:
    """One pinned application transaction; one document write per transaction."""
    def __init__(self, view):
        self._view = view
        self.database_id = view.database_id
        self.configuration_generation = view.configuration_generation
        self._outcome = None; self._hash = None
        if view._backend.storage_version != 7:
            self._schemas = ()
        else:
            self._schemas = view._backend._document_schemas
        if view._operation_id is not None and self._connection.execute(
                'SELECT 1 FROM document_commit_receipt WHERE operation_id=?', (str(view._operation_id),)).fetchone():
            raise BackendError('conflict')

    @property
    def _connection(self): return self._view._connection
    def close(self): self._view.close()
    def rollback(self): self._view.rollback()
    def documents(self): self._view._require(); return self._schemas
    def document_schema(self, identity):
        self._view._require(); _storage()._uuid(identity)
        schema = next((s for s in self._schemas if s.identity == identity), None)
        if schema is None: raise BackendError('not_found')
        return schema

    def _key(self, key):
        if type(key) is not DocumentKey or key.database_id != self.database_id: raise BackendError('invalid_input')
        _storage()._uuid(key.record_id, empty=True)
        return self.document_schema(key.document_id)

    def _preflight(self, schema):
        args = (str(schema.identity),)
        invalid = self._connection.execute("SELECT 1 FROM document_record WHERE document_id=? AND (typeof(record_id)!='text' OR length(CAST(record_id AS BLOB))!=36 OR typeof(revision)!='integer' OR revision<1 OR typeof(number)!='text' OR length(CAST(number AS BLOB))>36 OR typeof(date)!='text' OR length(date)!=14 OR typeof(deletion_mark)!='integer' OR deletion_mark NOT IN(0,1) OR typeof(values_json)!='text' OR typeof(sections_json)!='text' OR length(CAST(values_json AS BLOB))+length(CAST(sections_json AS BLOB))>?) LIMIT 1", args+(_MAX_ROW,)).fetchone()
        count, size = self._connection.execute('SELECT COUNT(*),COALESCE(SUM(length(CAST(values_json AS BLOB))+length(CAST(sections_json AS BLOB))+128),0) FROM document_record WHERE document_id=?', args).fetchone()
        if invalid: raise BackendError('integrity')
        if count > 10000 or size > _MAX_TOTAL: raise BackendError('unsupported')
        return count

    def _values(self, fields, values, *, writing=False):
        s = _storage()
        if type(values) is not (tuple if writing else list) or len(values) != len(fields): raise BackendError('invalid_input' if writing else 'integrity')
        if writing:
            result = []; size = 0
            for field,value in zip(fields,values):
                encoded = s._encode(normalize_field(value,field),field,self.database_id)
                size += len(s._json(encoded)) + 1
                if size > _MAX_ROW: raise BackendError('invalid_input')
                result.append(encoded)
            for value in values:
                if type(value) is CatalogKey and value.record_id.int and not self._view._reference_exists(value): raise BackendError('not_found')
            return result
        return tuple(s._decode(v,f,self.database_id) for f,v in zip(fields,values))

    def _sections(self, schema, contents, *, writing=False):
        if type(contents) is not (tuple if writing else list) or len(contents) > 16: raise BackendError('invalid_input' if writing else 'integrity')
        definitions = {s.identity:s for s in schema.tabular_sections}
        supplied = {}; total = 0; size = 0
        for item in contents:
            if writing:
                if type(item) is not TabularSectionRows or type(item.rows) is not tuple: raise BackendError('invalid_input')
                identity, rows = item.section_id, item.rows
            else:
                if type(item) is not list or len(item) != 2 or type(item[1]) is not list: raise BackendError('integrity')
                identity, rows = UUID(item[0]), item[1]
                if str(identity) != item[0]: raise BackendError('integrity')
            if identity not in definitions or identity in supplied: raise BackendError('integrity')
            total += len(rows)
            if total > 1000: raise BackendError('unsupported')
            result = []; seen = set()
            for row in rows:
                if writing:
                    if type(row) is not TabularRow: raise BackendError('invalid_input')
                    row_id, values = row.identity, row.values
                else:
                    if type(row) is not list or len(row) != 2: raise BackendError('integrity')
                    row_id, values = UUID(row[0]), row[1]
                    if str(row_id) != row[0]: raise BackendError('integrity')
                _storage()._uuid(row_id)
                if row_id in seen: raise BackendError('integrity')
                seen.add(row_id)
                values = self._values(definitions[identity].fields, values, writing=writing)
                encoded = [str(row_id),values] if writing else TabularRow(row_id,values)
                if writing:
                    size += len(_storage()._json(encoded)) + 1
                    if size > _MAX_ROW: raise BackendError('invalid_input')
                result.append(encoded)
            supplied[identity] = result
        if not writing and set(supplied) != set(definitions): raise BackendError('integrity')
        return ([[str(identity),supplied.get(identity,[])] for identity in sorted(definitions,key=str)] if writing else
                tuple(TabularSectionRows(section.identity,tuple(supplied[section.identity])) for section in schema.tabular_sections))

    def _card(self, schema, row):
        record, revision, number, date, mark, values, sections = row
        identity = UUID(record); _storage()._uuid(identity)
        if str(identity) != record or type(revision) is not int or not 1 <= revision < 2**63: raise BackendError('integrity')
        validate_string(number,schema.number_length)
        if not number or type(mark) is not int or mark not in (0,1): raise BackendError('integrity')
        return DocumentCard(DocumentKey(self.database_id,schema.identity,identity),
            DocumentRevision(self.database_id,self.configuration_generation,schema.identity,identity,str(revision)),
            number,_storage()._decode(['d',date],_DATE_FIELD,self.database_id),bool(mark),
            self._values(schema.fields,json.loads(values)),self._sections(schema,json.loads(sections)))

    def read_document(self, key):
        schema = self._key(key); self._preflight(schema)
        row = self._connection.execute('SELECT record_id,revision,number,date,deletion_mark,values_json,sections_json FROM document_record WHERE document_id=? AND record_id=?', (str(schema.identity),str(key.record_id))).fetchone()
        return None if row is None else self._card(schema,row)

    def select_documents(self, identity, request):
        schema = self.document_schema(identity)
        if type(request) is not DocumentSelection or type(request.limit) is not int or not 1 <= request.limit <= 1000: raise BackendError('invalid_input')
        for value in (request.start,request.end):
            if value is not None: _storage()._encode(value,_DATE_FIELD,self.database_id)
        if request.start is not None and request.end is not None and request.start > request.end: raise BackendError('invalid_input')
        self._preflight(schema)
        cards = []
        for row in self._connection.execute('SELECT record_id,revision,number,date,deletion_mark,values_json,sections_json FROM document_record WHERE document_id=? ORDER BY date,number,record_id', (str(identity),)):
            card = self._card(schema,row)
            if (request.start is None or card.date >= request.start) and (request.end is None or card.date <= request.end):
                cards.append(card)
                if len(cards) > request.limit: raise BackendError('unsupported')
        return tuple(cards)

    def find_document_number(self, identity, number):
        schema = self.document_schema(identity); validate_string(number,schema.number_length)
        self._preflight(schema)
        row = self._connection.execute('SELECT record_id,revision,number,date,deletion_mark,values_json,sections_json FROM document_record WHERE document_id=? AND number=?', (str(identity),number)).fetchone()
        return None if row is None else self._card(schema,row).key

    def _intent(self, draft, expected):
        if type(draft) is not DocumentDraft or type(draft.auto_number) is not bool or type(draft.deletion_mark) is not bool: raise BackendError('invalid_input')
        schema = self._key(draft.key); _storage()._uuid(draft.key.record_id)
        number = normalize_string(draft.number,schema.number_length)
        if draft.auto_number:
            if expected is not None or schema.numbering != 'decimal_v1' or number != '': raise BackendError('invalid_input')
        elif not number: raise BackendError('invalid_input')
        if expected is not None:
            if type(expected) is not DocumentRevision or (expected.database_id,expected.configuration_generation,expected.document_id,expected.record_id) != (self.database_id,self.configuration_generation,schema.identity,draft.key.record_id): raise BackendError('conflict')
            _storage()._revision_number(expected.token)
        values = self._values(schema.fields,draft.values,writing=True)
        sections = None if draft.tabular_sections is None else self._sections(schema,draft.tabular_sections,writing=True)
        date = _storage()._encode(draft.date,_DATE_FIELD,self.database_id)[1]
        intent = ['document_write_v1',str(schema.identity),str(draft.key.record_id),number,date,draft.deletion_mark,values,sections,draft.auto_number,None if expected is None else expected.token]
        encoded = _storage()._json(intent)
        if len(encoded.encode('utf-8')) > _MAX_ROW: raise BackendError('invalid_input')
        return schema,intent,sha256(encoded.encode('utf-8')).hexdigest()

    def create(self, draft): self._write(draft,None)
    def update(self, draft, expected):
        if expected is None: raise BackendError('invalid_input')
        self._write(draft,expected)

    def _write(self, draft, expected):
        self._view._require(True)
        if self._outcome is not None: raise BackendError('unsupported')
        schema,intent,digest = self._intent(draft,expected)
        _,document,record,number,date,mark,values,sections,auto,_ = intent
        count = self._preflight(schema)
        old = self.read_document(draft.key)
        if expected is None:
            if old is not None: raise BackendError('duplicate_identity')
            if count >= 10000: raise BackendError('unsupported')
            revision = 1
        else:
            if old is None or old.revision != expected: raise BackendError('conflict')
            revision = int(expected.token)+1
        with self._view._atomic_record():
            if auto:
                next_value = self._connection.execute('SELECT next_value FROM document_sequence WHERE document_id=?',(document,)).fetchone()[0]
                while next_value < 10**schema.number_length:
                    number = str(next_value).zfill(schema.number_length); next_value += 1
                    if not self._connection.execute('SELECT 1 FROM document_record WHERE document_id=? AND number=?',(document,number)).fetchone(): break
                else: raise BackendError('number_exhausted')
                self._connection.execute('UPDATE document_sequence SET next_value=? WHERE document_id=?',(next_value,document))
            if self._connection.execute('SELECT 1 FROM document_record WHERE document_id=? AND number=? AND record_id!=?',(document,number,record)).fetchone(): raise BackendError('duplicate_number')
            if sections is None:
                sections = self._sections(schema,() if old is None else old.tabular_sections,writing=True)
            args = (revision,number,date,int(mark),_storage()._json(values),_storage()._json(sections),document,record)
            if len(args[4])+len(args[5]) > _MAX_ROW: raise BackendError('invalid_input')
            if old is None:
                self._connection.execute('INSERT INTO document_record(revision,number,date,deletion_mark,values_json,sections_json,document_id,record_id) VALUES(?,?,?,?,?,?,?,?)',args)
            else:
                self._connection.execute('UPDATE document_record SET revision=?,number=?,date=?,deletion_mark=?,values_json=?,sections_json=? WHERE document_id=? AND record_id=?',args)
            self._preflight(schema)
            # Allocate all receipt state while rollback still covers this row
            # and its sequence. After RELEASE install only existing references.
            outcome = DocumentWriteOutcome(DocumentRevision(self.database_id,self.configuration_generation,schema.identity,draft.key.record_id,str(revision)),number)
        self._outcome = outcome
        self._hash = digest

    def commit(self):
        self._view._require(True)
        if self._outcome is None: raise BackendError('invalid_input')
        result = self._outcome; revision = result.revision
        try:
            self._connection.execute('INSERT INTO document_commit_receipt VALUES(?,?,?,?,?,?)',
                (str(self._view._operation_id),_receipt_hash(self._hash,result),str(revision.document_id),str(revision.record_id),int(revision.token),result.number))
            self._connection.execute('COMMIT')
            self.close()
        except BaseException as error:
            try: self.close()
            except BaseException as cleanup:
                if _storage()._interruption(cleanup) and not _storage()._interruption(error): raise
            if _storage()._interruption(error): raise
            raise BackendError('uncertain_commit') from None
        return result

    def resolve(self, operation_id, draft, expected):
        self._view._require(); _storage()._uuid(operation_id)
        schema,intent,digest = self._intent(draft,expected)
        if self._connection.execute("SELECT 1 FROM document_commit_receipt WHERE operation_id=? AND (typeof(request_hash)!='text' OR length(CAST(request_hash AS BLOB))!=64 OR typeof(document_id)!='text' OR length(CAST(document_id AS BLOB))!=36 OR typeof(record_id)!='text' OR length(CAST(record_id AS BLOB))!=36 OR typeof(revision)!='integer' OR typeof(number)!='text' OR length(CAST(number AS BLOB))>36)", (str(operation_id),)).fetchone(): raise BackendError('integrity')
        row = self._connection.execute('SELECT request_hash,document_id,record_id,revision,number FROM document_commit_receipt WHERE operation_id=?',(str(operation_id),)).fetchone()
        if row is None: return None
        if (row[1],row[2],row[3]) != (str(schema.identity),str(draft.key.record_id),1 if expected is None else int(expected.token)+1): raise BackendError('integrity')
        validate_string(row[4],schema.number_length)
        if draft.auto_number:
            if len(row[4]) != schema.number_length or not row[4].isascii() or not row[4].isdecimal() or int(row[4]) == 0: raise BackendError('integrity')
        elif row[4] != intent[3]: raise BackendError('integrity')
        outcome = DocumentWriteOutcome(DocumentRevision(self.database_id,self.configuration_generation,schema.identity,draft.key.record_id,str(row[3])),row[4])
        if row[0] != _receipt_hash(digest,outcome): raise BackendError('conflict')
        return outcome
