"""Owned SQLite v8 independent information-register records.

Register keys are canonical typed dimension tuples. A monotonically increasing
register revision prevents stale updates after a delete/reinsert cycle.
"""
import json
from hashlib import sha256
from uuid import UUID, uuid4
from yadinassi.db.catalog.catalog_backend import BackendError, FieldSchema, CatalogOrder
from yadinassi.db.registers.register_backend import (InformationRegisterSchema, RegisterKey, RegisterRevision,
                               RegisterRecord, RegisterDraft, RegisterOutcome, RegisterScanRequest, RegisterPage,
                               RegisterSetDraft, RegisterSetOutcome)

from .sqlite_typed_rows import encode_typed_columns, decode_typed_columns
from .sqlite_register_layout import RegisterLayout

REGISTER_DDL = (
    'CREATE TABLE information_register_schema(identity TEXT PRIMARY KEY, name TEXT NOT NULL UNIQUE, definition TEXT NOT NULL)',
    'CREATE TABLE information_register_sequence(register_id TEXT PRIMARY KEY REFERENCES information_register_schema(identity), next_value INTEGER NOT NULL CHECK(next_value>0))',
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


def load_schemas(connection, catalogs, documents=(), *, allow_empty=False):
    malformed=connection.execute("SELECT 1 FROM information_register_schema WHERE typeof(identity)!='text' OR length(CAST(identity AS BLOB))!=36 OR typeof(name)!='text' OR length(CAST(name AS BLOB))>512 OR typeof(definition)!='text' OR length(CAST(definition AS BLOB))>262144 LIMIT 1").fetchone()
    count,size=connection.execute('SELECT COUNT(*),COALESCE(SUM(length(CAST(definition AS BLOB))),0) FROM information_register_schema').fetchone()
    if malformed or not (0 if allow_empty else 1)<=count<=512 or size>MAX_TOTAL: raise BackendError('integrity')
    rows=tuple(connection.execute('SELECT identity,name,definition FROM information_register_schema ORDER BY identity'))
    schemas=tuple(parse_schema(row[2]) for row in rows)
    if any(row[:2]!=(str(s.identity),s.name) for row,s in zip(rows,schemas)): raise BackendError('integrity')
    if schemas: validate_configuration(schemas,catalogs,documents,error='integrity')
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
        self._outcome=None;self._scan=None;self._layouts={}
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
    def _layout(self,schema):
        layout = self._layouts.get(schema.identity)
        if layout is None:
            layout = self._layouts[schema.identity] = RegisterLayout(schema)
        return layout
    def _key_columns(self,key):
        if type(key) is not RegisterKey or type(key.database_id) is not UUID or key.database_id!=self.database_id: raise BackendError('invalid_input')
        schema=self.register_schema(key.register_id)
        if type(key.dimensions) is not tuple or len(key.dimensions)!=len(schema.key_fields): raise BackendError('invalid_input')
        if schema.periodic:
            from yadinassi.db.registers.periodic_information_registers import storage_period
            if storage_period(key.dimensions[0],schema.periodicity) != key.dimensions[0]: raise BackendError('invalid_input')
        encoded=[_dimension(v,f,self.database_id) for f,v in zip(schema.key_fields,key.dimensions)]
        raw=_storage()._json(encoded)
        if len(raw)>MAX_ROW: raise BackendError('invalid_input')
        return schema,raw,encode_typed_columns(encoded,self._layout(schema).dimensions)
    def _key(self,key):
        schema,raw,_=self._key_columns(key)
        return schema,raw
    def _preflight(self,schema):
        layout=self._layout(schema)
        invalid,count,size=self._connection.execute(
            f"SELECT COALESCE(MAX(typeof(revision)!='integer' OR revision<1 OR ({layout.bytes})>?),0),"
            f"COUNT(*),COALESCE(SUM({layout.bytes}+64),0) FROM {layout.table}",(MAX_ROW,)).fetchone()
        if invalid: raise BackendError('integrity')
        if count>MAX_ROWS or size>MAX_TOTAL: raise BackendError('unsupported')
        return count
    def _record(self,schema,row):
        layout=self._layout(schema)
        revision=row[0]
        if type(revision) is not int or not 1<=revision<2**63: raise BackendError('integrity')
        split=1+len(layout.keys)
        keys,raw_values=row[1:split],row[split:]
        dimensions=decode_typed_columns(keys,layout.dimensions)
        values=decode_typed_columns(raw_values,layout.payload)
        s=_storage()
        key=RegisterKey(self.database_id,schema.identity,tuple(s._decode(v,f,self.database_id) for f,v in zip(schema.key_fields,dimensions)))
        stored=tuple(s._decode(v,f,self.database_id) for f,v in zip(layout.payload.fields,values))
        _,raw,canonical=self._key_columns(key)
        if keys!=canonical or raw_values!=encode_typed_columns(values,layout.payload): raise BackendError('integrity')
        return RegisterRecord(key,RegisterRevision(self.database_id,self.configuration_generation,
            schema.identity,sha256(raw.encode()).hexdigest(),str(revision)),stored)
    def _lookup(self,schema,keys):
        layout=self._layout(schema)
        row=self._connection.execute(f'SELECT {layout.columns} FROM {layout.table} WHERE {layout.where}',keys).fetchone()
        return None if row is None else self._record(schema,row)
    def read_record(self,key):
        self._view._require();schema,_,keys=self._key_columns(key);self._preflight(schema)
        return self._lookup(schema,keys)
    def _ordered_rows(self,schema):
        layout=self._layout(schema)
        return self._connection.execute(f'SELECT {layout.columns} FROM {layout.table} ORDER BY {layout.key_order}')
    def select_records(self,identity,filters=(),limit=1000):
        schema=self.register_schema(identity)
        if type(limit) is not int or not 1<=limit<=1000: raise BackendError('invalid_input')
        admitted,wanted=self._filter_values(schema,filters)
        self._preflight(schema);result=[]
        # Keep strict full-source validation on the general read port.
        for row in self._ordered_rows(schema):
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
        layout=self._layout(schema)
        if request.continuation is None:
            self._scan=None;self._preflight(schema)
            # Validate the full bounded source once before releasing the first page.
            for row in self._ordered_rows(schema): self._record(schema,row)
            where,params='',()
        else:
            if self._scan is None or self._scan[:2]!=(request.continuation,identity): raise BackendError('invalid_input')
            where,params=layout.seek(self._scan[2]);self._scan=None
        rows=tuple(self._connection.execute(f'SELECT {layout.columns} FROM {layout.table}{where} ORDER BY {layout.key_order} LIMIT ?',
            params+(request.page_size+1,)))
        records=tuple(self._record(schema,row) for row in rows[:request.page_size])
        token=None
        if len(rows)>request.page_size:
            token=uuid4().hex;self._scan=(token,identity,rows[request.page_size-1][1:1+len(layout.keys)])
        return RegisterPage(records,token)

    def ordered_register_records(self, identity, order, limit, *, predicate=None):
        """Closed query-only TOP over physical columns, never the raw/tx port."""
        self._view._require()
        if not self._view._query_language or self._view._operation_id is not None:
            return None
        if self._view._backend._active is not self._view: raise BackendError('closed')
        if (type(order) is not tuple or not 1<=len(order)<=16
                or type(limit) is not int or not 1<=limit<MAX_ROWS):
            raise BackendError('invalid_input')
        schema=self.register_schema(identity);layout=self._layout(schema)
        admitted={field.identity:(field,col) for field,col in zip(schema.fields,(*layout.keys,*layout.values))}
        terms=[];seen=set()
        for item in order:
            if (type(item) is not CatalogOrder or type(item.field) is not UUID
                    or type(item.descending) is not bool or item.field in seen or item.field not in admitted):
                raise BackendError('invalid_input')
            seen.add(item.field)
            field,col=admitted[item.field]
            if field.kind=='string': col+=' COLLATE yadinassi_casefold_v1'
            elif field.kind=='catalog_ref':
                # Empty reference precedes nonempty UUID, as in logical _key.
                col=f"COALESCE({col},'00000000-0000-0000-0000-000000000000')"
            elif field.kind not in ('number','datetime','boolean'): return None
            terms.append(col+(' DESC' if item.descending else ' ASC'))
        order_sql=','.join((*terms,layout.key_order))
        self._scan=None
        where, args = '', ()
        if predicate is not None:
            from .sqlite_ordered_predicates import ordered_where
            fields = {identity:(field,col+' COLLATE yadinassi_casefold_v1' if field.kind=='string' else col)
                      for identity,(field,col) in admitted.items()
                      if field.kind in ('string','number','boolean','datetime')}
            expression,args = ordered_where(predicate, fields)
            where = ' WHERE ' + expression
        cursor=self._connection.execute(
            f'SELECT {layout.columns} FROM {layout.table}{where} ORDER BY {order_sql} LIMIT ?',(*args,limit))
        try: rows=tuple(self._record(schema,row) for row in cursor)
        finally: cursor.close()
        self._view._require()
        if self._view._backend._active is not self._view: raise BackendError('closed')
        return RegisterPage(rows,None)

    def periodic_records(self, identity, filters=(), start=None, end=None, edge=None, limit=1000):
        schema=self.register_schema(identity)
        if not schema.periodic or type(limit) is not int or not 1<=limit<=10000: raise BackendError('invalid_input')
        # Public edge/range filters are dimension-only; Period belongs to bounds.
        if any(type(pair) is not tuple or len(pair)!=2 or pair[0]==schema.period_field.identity for pair in filters): raise BackendError('invalid_input')
        from yadinassi.db.registers.periodic_information_registers import storage_moment,edge_records
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
                from yadinassi.db.registers.periodic_information_registers import storage_period
                if storage_period(pair[1],schema.periodicity)!=pair[1]: raise BackendError('invalid_input')
            wanted[pair[0]]=_dimension(pair[1],f,self.database_id)
        return admitted,wanted

    def _scope(self,schema,filters):
        admitted,wanted=self._filter_values(schema,filters)
        self._preflight(schema);result=[]
        for row in self._ordered_rows(schema):
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
        seen=set();rows=[];physical=[]
        for record in draft.rows:
            rs,raw,values,keys=self._intent(record,None,False)
            if rs.identity!=schema.identity or raw in seen: raise BackendError('invalid_input')
            seen.add(raw)
            if any(_dimension(record.key.dimensions[admitted[k][0]],admitted[k][1],self.database_id)!=v for k,v in wanted.items()): raise BackendError('invalid_input')
            rows.append((raw,values))
            physical.append((keys,encode_typed_columns(values,self._layout(schema).payload)))
        intent=['register_set_v1',str(schema.identity),[[str(f.identity),wanted[f.identity]] for f in schema.key_fields if f.identity in wanted],rows,draft.replace,draft.expected_snapshot]
        raw=_storage()._json(intent)
        if len(raw)>MAX_TOTAL: raise BackendError('invalid_input')
        return schema,rows,physical

    def write_set(self,draft):
        self._view._require(True)
        if self._outcome is not None: raise BackendError('unsupported')
        schema,rows,physical=self._set_intent(draft)
        layout=self._layout(schema)
        self._scan=None
        old,snapshot=self._scope(schema,draft.filters)
        if draft.expected_snapshot is not None and draft.expected_snapshot!=snapshot: raise BackendError('conflict')
        old_keys={self._key(r.key)[1] for r in old}
        if not draft.replace and any(raw in old_keys for raw,_ in rows): raise BackendError('duplicate_identity')
        with self._view._atomic_record():
            if draft.replace:
                self._connection.executemany(f'DELETE FROM {layout.table} WHERE {layout.where}',
                    (self._key_columns(record.key)[2] for record in old))
            revision=self._connection.execute('SELECT next_value FROM information_register_sequence WHERE register_id=?',(str(schema.identity),)).fetchone()[0]
            if type(revision) is not int or not 1<=revision<2**63-len(rows)-1: raise BackendError('integrity')
            if old and revision<=max(int(r.revision.token) for r in old): raise BackendError('integrity')
            for keys,values in physical:
                self._connection.execute(f'INSERT INTO {layout.table}({layout.columns}) VALUES({layout.insert_params})',(revision,*keys,*values));revision+=1
            self._connection.execute('UPDATE information_register_sequence SET next_value=? WHERE register_id=?',(revision,str(schema.identity)))
            # _scope already checks post-write bounds before reading the
            # new snapshot, on this same locked writer/savepoint.
            result_rows,result_snapshot=self._scope(schema,draft.filters)
            outcome=RegisterSetOutcome(schema.identity,result_snapshot,len(result_rows))
        self._outcome=outcome

    def _intent(self,draft,expected,deleted):
        if type(draft) is not RegisterDraft or type(deleted) is not bool: raise BackendError('invalid_input')
        schema,raw,keys=self._key_columns(draft.key)
        fields=(*schema.resources,*schema.attributes)
        if type(draft.values) is not tuple or len(draft.values)!=len(fields): raise BackendError('invalid_input')
        values=[_storage()._encode(v,f,self.database_id) for f,v in zip(fields,draft.values)]
        key_digest=sha256(raw.encode()).hexdigest()
        if expected is not None:
            if (type(expected) is not RegisterRevision or type(expected.database_id) is not UUID
                    or type(expected.register_id) is not UUID or type(expected.configuration_generation) is not int
                    or type(expected.key_digest) is not str or (expected.database_id,expected.configuration_generation,expected.register_id,expected.key_digest)!=(self.database_id,self.configuration_generation,schema.identity,key_digest)
                    or type(expected.token) is not str or not expected.token.isascii() or not expected.token.isdecimal()
                    or not 0<int(expected.token)<2**63): raise BackendError('invalid_input')
        if deleted and expected is None: raise BackendError('invalid_input')
        intent=['register_write_v1',str(schema.identity),raw,values,None if expected is None else expected.token,deleted]
        encoded=_storage()._json(intent)
        if len(encoded)>MAX_ROW: raise BackendError('invalid_input')
        return schema,raw,values,keys
    def write(self,draft,expected=None): self._write(draft,expected,False)
    def delete(self,draft,expected): self._write(draft,expected,True)
    def _write(self,draft,expected,deleted):
        self._view._require(True)
        if self._outcome is not None: raise BackendError('unsupported')
        schema,raw,values,keys=self._intent(draft,expected,deleted)
        layout=self._layout(schema)
        self._scan=None
        count=self._preflight(schema)
        old=self._lookup(schema,keys)
        if expected is None:
            if old is not None: raise BackendError('duplicate_identity')
            if count>=MAX_ROWS: raise BackendError('unsupported')
        elif old is None or old.revision!=expected: raise BackendError('conflict')
        with self._view._atomic_record():
            revision=self._connection.execute('SELECT next_value FROM information_register_sequence WHERE register_id=?',(str(schema.identity),)).fetchone()[0]
            if type(revision) is not int or not 1<=revision<2**63-1: raise BackendError('integrity')
            if old is not None and revision<=int(old.revision.token): raise BackendError('integrity')
            self._connection.execute('UPDATE information_register_sequence SET next_value=? WHERE register_id=?',(revision+1,str(schema.identity)))
            if deleted: self._connection.execute(f'DELETE FROM {layout.table} WHERE {layout.where}',keys)
            else:
                stored=encode_typed_columns(values,layout.payload)
                if old is None: self._connection.execute(f'INSERT INTO {layout.table}({layout.columns}) VALUES({layout.insert_params})',(revision,*keys,*stored))
                else: self._connection.execute(f'UPDATE {layout.table} SET revision=?,{layout.set_values} WHERE {layout.where}',(revision,*stored,*keys))
            self._preflight(schema)
            outcome=RegisterOutcome(RegisterRevision(self.database_id,self.configuration_generation,schema.identity,sha256(raw.encode()).hexdigest(),str(revision)),deleted)
        self._outcome=outcome
    def _confirm_commit(self):
        self._view._require(True)
        if self._outcome is None: raise BackendError('invalid_input')
        # Caller publishes this acknowledged outcome, then closes its view.
        _storage()._confirm_sqlite_commit(self._connection)
        self._view._committed = True
        return self._outcome

    def commit(self):
        try:
            result = self._confirm_commit()
            self.close()
        except BaseException as error:
            try: self.close()
            except BaseException as cleanup:
                if _storage()._interruption(cleanup) and not _storage()._interruption(error): raise
            raise
        return result


# Apply the same narrow error translation as the owning catalog application.
# Installed by sqlite_catalog after its boundary helper has been defined.
def install_boundaries(boundary):
    for name in ('registers','register_schema','read_record','select_records','scan_register','ordered_register_records','periodic_records','read_set','write_set','write','delete','commit'):
        setattr(RegisterView,name,boundary(getattr(RegisterView,name)))
