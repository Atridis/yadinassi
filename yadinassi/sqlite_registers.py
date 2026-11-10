"""Owned SQLite v8 independent information-register records and receipts.

Register keys are canonical typed dimension tuples. A monotonically increasing
register revision prevents stale updates after a delete/reinsert cycle.
"""
import json
from hashlib import sha256
from uuid import UUID, uuid4
from .catalog_backend import BackendError, FieldSchema
from .register_backend import (InformationRegisterSchema, RegisterKey, RegisterRevision,
                               RegisterRecord, RegisterDraft, RegisterOutcome, RegisterScanRequest, RegisterPage,
                               RegisterSetDraft, RegisterSetOutcome)

REGISTER_DDL = (
    'CREATE TABLE information_register_schema(identity TEXT PRIMARY KEY, name TEXT NOT NULL UNIQUE, definition TEXT NOT NULL)',
    'CREATE TABLE information_register_record(register_id TEXT NOT NULL REFERENCES information_register_schema(identity), key_json TEXT NOT NULL, revision INTEGER NOT NULL CHECK(revision>0), values_json TEXT NOT NULL, PRIMARY KEY(register_id,key_json))',
    'CREATE TABLE information_register_sequence(register_id TEXT PRIMARY KEY REFERENCES information_register_schema(identity), next_value INTEGER NOT NULL CHECK(next_value>0))',
    'CREATE TABLE information_register_receipt(operation_id TEXT PRIMARY KEY, request_hash TEXT NOT NULL, outcome_json TEXT NOT NULL)',
)
MAX_ROW = 1024 * 1024
MAX_TOTAL = 16 * 1024 * 1024
MAX_ROWS = 10000
_RESERVED = {'read','прочитать','write','записать','delete','удалить','clear','очистить',
    'selected','выбран','metadata','метаданные','next','следующий','period','период',
    'recorder','регистратор','active','активность','linenumber','номерстроки'}


def _storage():
    from . import sqlite_catalog
    return sqlite_catalog


def _dimension(value, field, database_id):
    # Numeric key identity follows Number equality; signed zero is not a second
    # dimension value. Resource/attribute representations remain unchanged.
    if field.kind == 'number':
        from decimal import Decimal
        if type(value) is Decimal and value.is_zero(): value = value.copy_abs()
    return _storage()._encode(value, field, database_id)


def schema_data(schema):
    if (type(schema) is not InformationRegisterSchema or type(schema.dimensions) is not tuple
            or type(schema.resources) is not tuple or type(schema.attributes) is not tuple
            or not 1 <= len(schema.dimensions) <= 16 or not schema.resources):
        raise BackendError('invalid_input')
    if type(schema.periodicity) is not str or schema.periodicity not in ('Nonperiodical','WithinSecond','Day','Month','Quarter','Year'): raise BackendError('invalid_input')
    s = _storage(); s._uuid(schema.identity)
    if type(schema.name) is not str or not schema.name or len(schema.name)>128: raise BackendError('invalid_input')
    fields = s._fields_data(schema.declared_fields)
    if any(f.identity == schema.identity or f.name.casefold() in _RESERVED for f in schema.declared_fields):
        raise BackendError('invalid_input')
    data = ['independent_register_v1',str(schema.identity),schema.name,len(schema.dimensions),len(schema.resources),fields]
    if type(schema.periodicity) is not str or schema.periodicity not in ('Nonperiodical','WithinSecond','Day','Month','Quarter','Year'): raise BackendError('invalid_input')
    if schema.periodic: data = ['periodic_register_v1', *data[1:], schema.periodicity]
    if len(s._json(data))>65536: raise BackendError('invalid_input')
    return data


def parse_schema(raw):
    if type(raw) is not str or len(raw)>65536: raise BackendError('integrity')
    data=json.loads(raw)
    if (type(data) is not list or not ((len(data)==6 and data[0]=='independent_register_v1') or (len(data)==7 and data[0]=='periodic_register_v1'))
            or type(data[3]) is not int or type(data[4]) is not int
            or type(data[5]) is not list or len(data[5])>64): raise BackendError('integrity')
    fields=[]
    for f in data[5]:
        if type(f) is not list or len(f)!=5 or type(f[3]) is not list: raise BackendError('integrity')
        fields.append(FieldSchema(UUID(f[0]),f[1],f[2],tuple(f[3]),None if f[4] is None else UUID(f[4])))
    n,r=data[3:5]
    if not 1<=n<=16 or not 1<=r<=64 or n+r>len(fields): raise BackendError('integrity')
    result=InformationRegisterSchema(UUID(data[1]),data[2],tuple(fields[:n]),tuple(fields[n:n+r]),tuple(fields[n+r:]), 'Nonperiodical' if len(data)==6 else data[6])
    if schema_data(result)!=data: raise BackendError('integrity')
    return result


def load_schemas(connection, catalogs, documents=()):
    malformed=connection.execute("SELECT 1 FROM information_register_schema WHERE typeof(identity)!='text' OR length(CAST(identity AS BLOB))!=36 OR typeof(name)!='text' OR length(CAST(name AS BLOB))>512 OR typeof(definition)!='text' OR length(CAST(definition AS BLOB))>262144 LIMIT 1").fetchone()
    count,size=connection.execute('SELECT COUNT(*),COALESCE(SUM(length(CAST(definition AS BLOB))),0) FROM information_register_schema').fetchone()
    if malformed or not 1<=count<=512 or size>MAX_TOTAL: raise BackendError('integrity')
    rows=tuple(connection.execute('SELECT identity,name,definition FROM information_register_schema ORDER BY identity'))
    schemas=tuple(parse_schema(row[2]) for row in rows)
    if any(row[:2]!=(str(s.identity),s.name) for row,s in zip(rows,schemas)): raise BackendError('integrity')
    validate_configuration(schemas,catalogs,documents,error='integrity')
    if connection.execute('SELECT COUNT(*) FROM information_register_sequence').fetchone()[0]!=len(schemas): raise BackendError('integrity')
    sequence=tuple(connection.execute('SELECT register_id,next_value FROM information_register_sequence'))
    if (len(sequence)!=len(schemas) or {r[0] for r in sequence}!={str(s.identity) for s in schemas}
            or any(type(v) is not int or not 1<=v<2**63 for _,v in sequence)):
        raise BackendError('integrity')
    return schemas,rows


def validate_configuration(registers,catalogs,documents=(),*,error='invalid_input'):
    if type(registers) is not tuple or not registers or len(registers)+len(catalogs)+len(documents)>512:
        raise BackendError(error)
    seen=set(); names=set(); catalog_ids={s.identity for s in catalogs}
    for schema in (*catalogs,*documents,*registers):
        for item in (schema,*schema.fields,*getattr(schema,'tabular_sections',()),
                     *(f for sec in getattr(schema,'tabular_sections',()) for f in sec.fields)):
            if item.identity in seen: raise BackendError(error)
            seen.add(item.identity)
    total=0
    for schema in registers:
        data=schema_data(schema);total+=len(_storage()._json(data))
        if schema.name.casefold() in names: raise BackendError(error)
        names.add(schema.name.casefold())
        if any(f.kind=='catalog_ref' and f.target_catalog_id not in catalog_ids for f in schema.fields): raise BackendError(error)
    if total>MAX_TOTAL: raise BackendError(error)


class RegisterView:
    def __init__(self, view):
        self._view=view;self.database_id=view.database_id
        self.configuration_generation=view.configuration_generation
        self._schemas=view._backend._register_schemas
        self._outcome=None;self._digest=None;self._scan=None
        if view._operation_id is not None and self._connection.execute(
                'SELECT 1 FROM information_register_receipt WHERE operation_id=?',(str(view._operation_id),)).fetchone():
            raise BackendError('conflict')
    @property
    def _connection(self): return self._view._connection
    def close(self):
        self._scan=None;self._view.close()
    def rollback(self): self._view.rollback()
    def registers(self): self._view._require(); return self._schemas
    def register_schema(self, identity):
        self._view._require(); _storage()._uuid(identity)
        schema=next((s for s in self._schemas if s.identity==identity),None)
        if schema is None: raise BackendError('not_found')
        return schema
    def _key(self,key):
        if type(key) is not RegisterKey or type(key.database_id) is not UUID or key.database_id!=self.database_id: raise BackendError('invalid_input')
        schema=self.register_schema(key.register_id)
        if type(key.dimensions) is not tuple or len(key.dimensions)!=len(schema.key_fields): raise BackendError('invalid_input')
        if schema.periodic:
            from .periodic_information_registers import storage_period
            if storage_period(key.dimensions[0],schema.periodicity) != key.dimensions[0]: raise BackendError('invalid_input')
        encoded=[_dimension(v,f,self.database_id) for f,v in zip(schema.key_fields,key.dimensions)]
        raw=_storage()._json(encoded)
        if len(raw)>MAX_ROW: raise BackendError('invalid_input')
        return schema,raw
    def _preflight(self,schema):
        args=(str(schema.identity),)
        invalid=self._connection.execute("SELECT 1 FROM information_register_record WHERE register_id=? AND (typeof(key_json)!='text' OR typeof(values_json)!='text' OR typeof(revision)!='integer' OR revision<1 OR length(CAST(key_json AS BLOB))+length(CAST(values_json AS BLOB))>?) LIMIT 1",args+(MAX_ROW,)).fetchone()
        count,size=self._connection.execute('SELECT COUNT(*),COALESCE(SUM(length(CAST(key_json AS BLOB))+length(CAST(values_json AS BLOB))+64),0) FROM information_register_record WHERE register_id=?',args).fetchone()
        if invalid: raise BackendError('integrity')
        if count>MAX_ROWS or size>MAX_TOTAL: raise BackendError('unsupported')
        return count
    def _record(self,schema,row):
        raw,revision,values_raw=row
        dimensions=json.loads(raw);values=json.loads(values_raw)
        if (type(dimensions) is not list or len(dimensions)!=len(schema.key_fields)
                or type(values) is not list or len(values)!=len(schema.resources)+len(schema.attributes)):
            raise BackendError('integrity')
        s=_storage()
        key=RegisterKey(self.database_id,schema.identity,tuple(s._decode(v,f,self.database_id) for f,v in zip(schema.key_fields,dimensions)))
        stored=tuple(s._decode(v,f,self.database_id) for f,v in zip((*schema.resources,*schema.attributes),values))
        if self._key(key)[1]!=raw or s._json(values)!=values_raw: raise BackendError('integrity')
        return RegisterRecord(key,RegisterRevision(self.database_id,self.configuration_generation,
            schema.identity,sha256(raw.encode()).hexdigest(),str(revision)),stored)
    def read_record(self,key):
        self._view._require();schema,raw=self._key(key);self._preflight(schema)
        row=self._connection.execute('SELECT key_json,revision,values_json FROM information_register_record WHERE register_id=? AND key_json=?',(str(schema.identity),raw)).fetchone()
        return None if row is None else self._record(schema,row)
    def select_records(self,identity,filters=(),limit=1000):
        schema=self.register_schema(identity)
        if type(filters) is not tuple or type(limit) is not int or not 1<=limit<=1000: raise BackendError('invalid_input')
        admitted={f.identity:(i,f) for i,f in enumerate(schema.key_fields)};wanted={}
        for pair in filters:
            if type(pair) is not tuple or len(pair)!=2 or type(pair[0]) is not UUID or pair[0] not in admitted or pair[0] in wanted:
                raise BackendError('invalid_input')
            _,f=admitted[pair[0]]
            if schema.periodic and f.identity==schema.period_field.identity:
                from .periodic_information_registers import storage_period
                if storage_period(pair[1],schema.periodicity)!=pair[1]: raise BackendError('invalid_input')
            wanted[pair[0]]=_dimension(pair[1],f,self.database_id)
        self._preflight(schema);result=[]
        # Validate the bounded entire source, even rows excluded by the filter.
        for row in self._connection.execute('SELECT key_json,revision,values_json FROM information_register_record WHERE register_id=? ORDER BY key_json',(str(identity),)):
            record=self._record(schema,row)
            if all(_dimension(record.key.dimensions[admitted[k][0]],admitted[k][1],self.database_id)==v for k,v in wanted.items()):
                if len(result)>=limit: raise BackendError('unsupported')
                result.append(record)
        return tuple(result)
    def scan_register(self,identity,request):
        schema=self.register_schema(identity)
        if self._view._operation_id is not None: raise BackendError('unsupported')
        if (type(request) is not RegisterScanRequest or type(request.page_size) is not int
                or not 1<=request.page_size<=1000
                or (request.continuation is not None and type(request.continuation) is not str)):
            raise BackendError('invalid_input')
        if request.continuation is None:
            self._scan=None;self._preflight(schema)
            # Validate the full bounded source once before releasing the first page.
            for row in self._connection.execute('SELECT key_json,revision,values_json FROM information_register_record WHERE register_id=? ORDER BY key_json',(str(identity),)):
                self._record(schema,row)
            after=''
        else:
            if self._scan is None or self._scan[:2]!=(request.continuation,identity): raise BackendError('invalid_input')
            after=self._scan[2];self._scan=None
        rows=tuple(self._connection.execute('SELECT key_json,revision,values_json FROM information_register_record WHERE register_id=? AND key_json>? ORDER BY key_json LIMIT ?',
            (str(identity),after,request.page_size+1)))
        records=tuple(self._record(schema,row) for row in rows[:request.page_size])
        token=None
        if len(rows)>request.page_size:
            token=uuid4().hex;self._scan=(token,identity,rows[request.page_size-1][0])
        return RegisterPage(records,token)

    def periodic_records(self, identity, filters=(), start=None, end=None, edge=None, limit=1000):
        schema=self.register_schema(identity)
        if not schema.periodic or type(limit) is not int or not 1<=limit<=10000: raise BackendError('invalid_input')
        # Public edge/range filters are dimension-only; Period belongs to bounds.
        if any(type(pair) is not tuple or len(pair)!=2 or pair[0]==schema.period_field.identity for pair in filters): raise BackendError('invalid_input')
        from .periodic_information_registers import storage_moment,edge_records
        if start is not None: storage_moment(start)
        if end is not None: storage_moment(end)
        if start is not None and end is not None and start>end: raise BackendError('invalid_input')
        rows,_=self._scope(schema,filters)
        if edge is not None:
            if type(edge) is not tuple or len(edge)!=2 or type(edge[1]) is not bool: raise BackendError('invalid_input')
            rows=edge_records(rows,schema,*edge)
        else:
            rows=tuple(r for r in rows if (start is None or r.key.dimensions[0]>=start)
                       and (end is None or r.key.dimensions[0]<=end))
        if len(rows)>limit: raise BackendError('unsupported')
        return rows

    def _filter_values(self,schema,filters):
        if type(filters) is not tuple: raise BackendError('invalid_input')
        admitted={f.identity:(i,f) for i,f in enumerate(schema.key_fields)};wanted={}
        for pair in filters:
            if type(pair) is not tuple or len(pair)!=2 or type(pair[0]) is not UUID or pair[0] not in admitted or pair[0] in wanted:
                raise BackendError('invalid_input')
            _,f=admitted[pair[0]]
            if schema.periodic and f.identity==schema.period_field.identity:
                from .periodic_information_registers import storage_period
                if storage_period(pair[1],schema.periodicity)!=pair[1]: raise BackendError('invalid_input')
            wanted[pair[0]]=_dimension(pair[1],f,self.database_id)
        return admitted,wanted

    def _scope(self,schema,filters):
        admitted,wanted=self._filter_values(schema,filters)
        self._preflight(schema);result=[]
        for row in self._connection.execute('SELECT key_json,revision,values_json FROM information_register_record WHERE register_id=? ORDER BY key_json',(str(schema.identity),)):
            record=self._record(schema,row)
            if all(_dimension(record.key.dimensions[admitted[k][0]],admitted[k][1],self.database_id)==v for k,v in wanted.items()):
                result.append(record)
        snapshot=sha256(_storage()._json([[self._key(r.key)[1],r.revision.token] for r in result]).encode()).hexdigest()
        return tuple(result),snapshot

    def read_set(self,identity,filters=()):
        schema=self.register_schema(identity);records,snapshot=self._scope(schema,filters)
        if len(records)>1000: raise BackendError('unsupported')
        return records,snapshot

    def _set_intent(self,draft):
        if (type(draft) is not RegisterSetDraft or type(draft.rows) is not tuple or len(draft.rows)>1000
                or type(draft.replace) is not bool
                or (draft.expected_snapshot is not None and (type(draft.expected_snapshot) is not str
                    or len(draft.expected_snapshot)!=64 or any(c not in '0123456789abcdef' for c in draft.expected_snapshot)))):
            raise BackendError('invalid_input')
        schema=self.register_schema(draft.register_id)
        admitted,wanted=self._filter_values(schema,draft.filters)
        # An unfiltered replacement must first observe the whole scope.
        if draft.replace and not wanted and draft.expected_snapshot is None: raise BackendError('invalid_input')
        seen=set();rows=[]
        for record in draft.rows:
            rs,raw,values,_=self._intent(record,None,False)
            if rs.identity!=schema.identity or raw in seen: raise BackendError('invalid_input')
            seen.add(raw)
            if any(_dimension(record.key.dimensions[admitted[k][0]],admitted[k][1],self.database_id)!=v for k,v in wanted.items()): raise BackendError('invalid_input')
            rows.append((raw,values))
        intent=['register_set_v1',str(schema.identity),[[str(f.identity),wanted[f.identity]] for f in schema.key_fields if f.identity in wanted],rows,draft.replace,draft.expected_snapshot]
        raw=_storage()._json(intent)
        if len(raw)>MAX_TOTAL: raise BackendError('invalid_input')
        return schema,rows,sha256(raw.encode()).hexdigest()

    def write_set(self,draft):
        self._view._require(True)
        if self._outcome is not None: raise BackendError('unsupported')
        schema,rows,digest=self._set_intent(draft)
        self._scan=None
        old,snapshot=self._scope(schema,draft.filters)
        if draft.expected_snapshot is not None and draft.expected_snapshot!=snapshot: raise BackendError('conflict')
        old_keys={self._key(r.key)[1] for r in old}
        if not draft.replace and any(raw in old_keys for raw,_ in rows): raise BackendError('duplicate_identity')
        with self._view._atomic_record():
            if draft.replace:
                self._connection.executemany('DELETE FROM information_register_record WHERE register_id=? AND key_json=?',((str(schema.identity),raw) for raw in old_keys))
            revision=self._connection.execute('SELECT next_value FROM information_register_sequence WHERE register_id=?',(str(schema.identity),)).fetchone()[0]
            if type(revision) is not int or not 1<=revision<2**63-len(rows)-1: raise BackendError('integrity')
            if old and revision<=max(int(r.revision.token) for r in old): raise BackendError('integrity')
            for raw,values in rows:
                self._connection.execute('INSERT INTO information_register_record VALUES(?,?,?,?)',(str(schema.identity),raw,revision,_storage()._json(values)));revision+=1
            self._connection.execute('UPDATE information_register_sequence SET next_value=? WHERE register_id=?',(revision,str(schema.identity)))
            self._preflight(schema)
            result_rows,result_snapshot=self._scope(schema,draft.filters)
            outcome=RegisterSetOutcome(schema.identity,result_snapshot,len(result_rows))
        self._outcome=outcome;self._digest=digest

    def _intent(self,draft,expected,deleted):
        if type(draft) is not RegisterDraft or type(deleted) is not bool: raise BackendError('invalid_input')
        schema,raw=self._key(draft.key)
        fields=(*schema.resources,*schema.attributes)
        if type(draft.values) is not tuple or len(draft.values)!=len(fields): raise BackendError('invalid_input')
        values=[_storage()._encode(v,f,self.database_id) for f,v in zip(fields,draft.values)]
        digest=sha256(raw.encode()).hexdigest()
        if expected is not None:
            if (type(expected) is not RegisterRevision or type(expected.database_id) is not UUID
                    or type(expected.register_id) is not UUID or type(expected.configuration_generation) is not int
                    or type(expected.key_digest) is not str or (expected.database_id,expected.configuration_generation,expected.register_id,expected.key_digest)!=(self.database_id,self.configuration_generation,schema.identity,digest)
                    or type(expected.token) is not str or not expected.token.isascii() or not expected.token.isdecimal()
                    or not 0<int(expected.token)<2**63): raise BackendError('invalid_input')
        if deleted and expected is None: raise BackendError('invalid_input')
        intent=['register_write_v1',str(schema.identity),raw,values,None if expected is None else expected.token,deleted]
        encoded=_storage()._json(intent)
        if len(encoded)>MAX_ROW: raise BackendError('invalid_input')
        return schema,raw,values,sha256(encoded.encode()).hexdigest()
    def write(self,draft,expected=None): self._write(draft,expected,False)
    def delete(self,draft,expected): self._write(draft,expected,True)
    def _write(self,draft,expected,deleted):
        self._view._require(True)
        if self._outcome is not None: raise BackendError('unsupported')
        schema,raw,values,digest=self._intent(draft,expected,deleted)
        self._scan=None
        old=self.read_record(draft.key)
        if expected is None:
            if old is not None: raise BackendError('duplicate_identity')
            if self._preflight(schema)>=MAX_ROWS: raise BackendError('unsupported')
        elif old is None or old.revision!=expected: raise BackendError('conflict')
        with self._view._atomic_record():
            revision=self._connection.execute('SELECT next_value FROM information_register_sequence WHERE register_id=?',(str(schema.identity),)).fetchone()[0]
            if type(revision) is not int or not 1<=revision<2**63-1: raise BackendError('integrity')
            if old is not None and revision<=int(old.revision.token): raise BackendError('integrity')
            self._connection.execute('UPDATE information_register_sequence SET next_value=? WHERE register_id=?',(revision+1,str(schema.identity)))
            if deleted: self._connection.execute('DELETE FROM information_register_record WHERE register_id=? AND key_json=?',(str(schema.identity),raw))
            elif old is None: self._connection.execute('INSERT INTO information_register_record VALUES(?,?,?,?)',(str(schema.identity),raw,revision,_storage()._json(values)))
            else: self._connection.execute('UPDATE information_register_record SET revision=?,values_json=? WHERE register_id=? AND key_json=?',(revision,_storage()._json(values),str(schema.identity),raw))
            self._preflight(schema)
            outcome=RegisterOutcome(RegisterRevision(self.database_id,self.configuration_generation,schema.identity,sha256(raw.encode()).hexdigest(),str(revision)),deleted)
        self._outcome=outcome;self._digest=digest
    def _outcome_data(self,outcome):
        if type(outcome) is RegisterSetOutcome:
            return ['register_set_v1',str(outcome.register_id),outcome.snapshot,outcome.count]
        r=outcome.revision
        return [str(r.database_id),r.configuration_generation,str(r.register_id),r.key_digest,r.token,outcome.deleted]
    def commit(self):
        self._view._require(True)
        if self._outcome is None: raise BackendError('invalid_input')
        result=self._outcome;payload=_storage()._json(self._outcome_data(result))
        bound=sha256((self._digest+payload).encode()).hexdigest()
        try:
            self._connection.execute('INSERT INTO information_register_receipt VALUES(?,?,?)',(str(self._view._operation_id),bound,payload))
            self._connection.execute('COMMIT');self.close()
        except BaseException as error:
            try: self.close()
            except BaseException as cleanup:
                if _storage()._interruption(cleanup) and not _storage()._interruption(error): raise
            if _storage()._interruption(error): raise
            raise BackendError('uncertain_commit') from None
        return result
    def resolve(self,operation,draft,expected,deleted=False):
        self._view._require();_storage()._uuid(operation)
        schema,raw,values,digest=self._intent(draft,expected,deleted)
        if self._connection.execute("SELECT 1 FROM information_register_receipt WHERE operation_id=? AND (typeof(request_hash)!='text' OR length(CAST(request_hash AS BLOB))!=64 OR typeof(outcome_json)!='text' OR length(CAST(outcome_json AS BLOB))>1024)",(str(operation),)).fetchone(): raise BackendError('integrity')
        row=self._connection.execute('SELECT request_hash,outcome_json FROM information_register_receipt WHERE operation_id=?',(str(operation),)).fetchone()
        if row is None: return None
        if type(row[0]) is not str or len(row[0])!=64 or type(row[1]) is not str or len(row[1])>1024: raise BackendError('integrity')
        p=json.loads(row[1]);key_digest=sha256(raw.encode()).hexdigest()
        if (type(p) is not list or len(p)!=6 or type(p[1]) is not int or type(p[5]) is not bool
                or p[:4]!=[str(self.database_id),self.configuration_generation,str(schema.identity),key_digest]
                or p[5]!=deleted or type(p[4]) is not str or not p[4].isascii() or not p[4].isdecimal()
                or not 0<int(p[4])<2**63 or (expected is not None and int(p[4])<=int(expected.token))): raise BackendError('integrity')
        if _storage()._json(p)!=row[1] or sha256((digest+row[1]).encode()).hexdigest()!=row[0]: raise BackendError('conflict')
        return RegisterOutcome(RegisterRevision(self.database_id,self.configuration_generation,schema.identity,key_digest,p[4]),deleted)

    def resolve_set(self,operation,draft):
        self._view._require();_storage()._uuid(operation)
        schema,rows,digest=self._set_intent(draft)
        if self._connection.execute("SELECT 1 FROM information_register_receipt WHERE operation_id=? AND (typeof(request_hash)!='text' OR length(CAST(request_hash AS BLOB))!=64 OR typeof(outcome_json)!='text' OR length(CAST(outcome_json AS BLOB))>1024)",(str(operation),)).fetchone(): raise BackendError('integrity')
        row=self._connection.execute('SELECT request_hash,outcome_json FROM information_register_receipt WHERE operation_id=?',(str(operation),)).fetchone()
        if row is None: return None
        if type(row[0]) is not str or len(row[0])!=64 or type(row[1]) is not str or len(row[1])>1024: raise BackendError('integrity')
        p=json.loads(row[1])
        if (type(p) is not list or len(p)!=4 or p[:2]!=['register_set_v1',str(schema.identity)]
                or type(p[2]) is not str or len(p[2])!=64 or any(c not in '0123456789abcdef' for c in p[2])
                or type(p[3]) is not int or not 0<=p[3]<=MAX_ROWS): raise BackendError('integrity')
        if _storage()._json(p)!=row[1] or sha256((digest+row[1]).encode()).hexdigest()!=row[0]: raise BackendError('conflict')
        return RegisterSetOutcome(schema.identity,p[2],p[3])


# Apply the same narrow error translation as the owning catalog application.
# Installed by sqlite_catalog after its boundary helper has been defined.
def install_boundaries(boundary):
    for name in ('registers','register_schema','read_record','select_records','scan_register','periodic_records','read_set','write_set','resolve_set','write','delete','commit','resolve'):
        setattr(RegisterView,name,boundary(getattr(RegisterView,name)))
