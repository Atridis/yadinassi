"""Bounded independent nonperiodic register managers over a logical port."""
from dataclasses import dataclass, field
from uuid import UUID, uuid4
from decimal import Decimal
from .catalogs import BSLCatalogManager
from .catalog_backend import CatalogKey
from .register_backend import RegisterKey, RegisterDraft, RegisterRecord, RegisterRevision, RegisterOutcome, RegisterSetDraft, RegisterSetOutcome
from .structures import BSLStructure
from .values import HostFunction
from .values import BSLObject
from .catalog_backend import BackendError

@dataclass(frozen=True, slots=True, eq=False)
class BSLInformationRegisterType(BSLObject):
    metadata_uuid: UUID
    type_uuid: UUID
    name: str
    snapshot: object = field(repr=False)
    family: str

    def __post_init__(self):
        if (type(self.metadata_uuid) is not UUID or not self.metadata_uuid.int
                or type(self.type_uuid) is not UUID or not self.type_uuid.int
                or type(self.name) is not str or not 1 <= len(self.name) <= 256
                or type(self.family) is not str or self.family not in ('Manager', 'Selection', 'RecordManager', 'RecordSet', 'Record')):
            raise ValueError('invalid information-register type')

    def __eq__(self, other):
        return (type(other) is BSLInformationRegisterType and self.snapshot is other.snapshot
                and self.metadata_uuid == other.metadata_uuid and self.type_uuid == other.type_uuid
                and self.family == other.family)

    def __hash__(self):
        return hash((id(self.snapshot), self.metadata_uuid, self.type_uuid, self.family))

    def __str__(self):
        return {'Manager':'Регистр сведений менеджер: ', 'Selection':'Регистр сведений выборка: ',
                'RecordSet':'Регистр сведений набор записей: ', 'Record':'Регистр сведений запись: ',
                'RecordManager':'Регистр сведений менеджер записи: '}[self.family] + self.name


class BSLInformationRegisters(BSLObject):
    def __init__(self, metadata, context, catalogs, documents):
        self._metadata, self._context = metadata, context
        self._catalogs, self._documents = catalogs, documents
        self._managers = {}
    def get_member(self, name): return self.get_index(name)
    def get_index(self, name):
        if type(name) is not str: raise TypeError('register name requires String')
        item = self._metadata._snapshot().get(name.casefold())
        if item is None: raise ValueError('information register not found')
        key = item._name.casefold()
        if key not in self._managers: self._managers[key] = BSLInformationRegisterManager(self, item)
        return self._managers[key]
    def type_by_name(self, name):
        if type(name) is str:
            prefix, separator, tail = name.partition('.')
            families = {'informationregistermanager':'_manager_type',
                'регистрсведенийменеджер':'_manager_type',
                'informationregisterselection':'_selection_type',
                'регистрсведенийвыборка':'_selection_type',
                'informationregisterrecordmanager':'_record_type',
                'регистрсведенийменеджерзаписи':'_record_type',
                'informationregisterrecordset':'_set_type','регистрсведенийнаборзаписей':'_set_type',
                'informationregisterrecord':'_row_type','регистрсведенийзапись':'_row_type'}
            if separator and prefix.casefold() in families:
                return getattr(self.get_index(tail), families[prefix.casefold()])
        return self._documents.type_by_name(name)
    def __str__(self): return 'Регистры сведений менеджер'


class BSLInformationRegisterManager(BSLObject):
    _logical = BSLCatalogManager._logical
    _stored = BSLCatalogManager._stored
    _field_default = BSLCatalogManager._field_default
    _assigned = BSLCatalogManager._assigned

    def __init__(self, registers, metadata):
        self._registers, self._metadata = registers, metadata
        self._schema, self._catalogs = metadata._schema, registers._catalogs
        self._catalogs._metadata._snapshot()
        for attr, family in (('_manager_type','Manager'), ('_selection_type','Selection'),
                             ('_record_type','RecordManager'),('_set_type','RecordSet'),('_row_type','Record')):
            # The family participates in identity; no generated native UUID is claimed.
            setattr(self, attr, BSLInformationRegisterType(self._schema.identity,
                self._schema.identity, self._schema.name, registers._metadata, family))
    @property
    def _backend(self): return self._registers._context.backend
    def _key(self, unused):
        # Scalar reference conversion only needs the database identity.
        return CatalogKey(self._registers._metadata._database_id, self._schema.identity, UUID(int=0))
    def _assigned(self, field, value):
        if self._schema.periodic and field.identity==self._schema.period_field.identity:
            from .periodic_information_registers import period
            value=period(value,self._schema.periodicity)
        return BSLCatalogManager._assigned(self,field,value)
    def _record_key(self, values):
        return RegisterKey(self._registers._metadata._database_id, self._schema.identity,
            tuple(self._stored(f, values[f.name.casefold()]) for f in self._schema.key_fields))
    def _check_view(self, view):
        m = self._registers._metadata
        if (view.database_id, view.configuration_generation, view.register_schema(self._schema.identity)) != (
                m._database_id, m._generation, self._schema): raise BackendError('schema_changed')
    def _view(self):
        view = self._backend.begin_register_read()
        try: self._check_view(view)
        except BaseException as error:
            try: view.close()
            except BaseException as cleanup:
                if (not isinstance(cleanup,Exception) or isinstance(cleanup,MemoryError)) and isinstance(error,Exception) and not isinstance(error,MemoryError): raise
            raise
        return view
    def _writable(self):
        caps = self._backend.capabilities()
        return caps.atomic_transactions and caps.register_write
    def _defaults(self):
        return {f.name.casefold():self._field_default(f) for f in self._schema.fields}
    def _fields(self, record):
        if (type(record) is not RegisterRecord or type(record.key) is not RegisterKey
                or type(record.revision) is not RegisterRevision
                or record.key.database_id != self._registers._metadata._database_id
                or record.key.register_id != self._schema.identity
                or type(record.key.dimensions) is not tuple or type(record.values) is not tuple
                or len(record.key.dimensions) != len(self._schema.key_fields)
                or len(record.values) != len(self._schema.resources) + len(self._schema.attributes)):
            raise BackendError('integrity')
        return {f.name.casefold():self._logical(f,v)
            for f,v in zip(self._schema.fields,record.key.dimensions + record.values)}
    def _filter(self, value, *, complete=False):
        if value is None and not complete: return ()
        if type(value) is not BSLStructure: raise TypeError('dimension filter requires Structure')
        fields = {f.name.casefold():f for f in self._schema.dimensions}
        if any(k not in fields for k in value._items): raise ValueError('filter accepts dimensions only')
        if complete and set(value._items) != set(fields): raise ValueError('complete dimension key required')
        return tuple((f.identity,self._stored(f,self._assigned(f,value.get(f.name))))
            for f in self._schema.dimensions if f.name.casefold() in value._items)
    def create_record_set(self): return BSLInformationRegisterRecordSet(self)
    def create_record_manager(self):
        return BSLInformationRegisterRecordManager(self)
    def get(self, *args):
        if self._schema.periodic:
            if len(args)!=2: raise TypeError('Get requires Period and dimensions')
            from .periodic_information_registers import period
            when=period(args[0],self._schema.periodicity);dimensions=args[1]
        else:
            if len(args)!=1: raise TypeError('Get requires dimensions')
            dimensions=args[0]
        pairs = self._filter(dimensions, complete=True)
        key = RegisterKey(self._registers._metadata._database_id,self._schema.identity,((self._stored(self._schema.period_field,when),) if self._schema.periodic else ())+tuple(v for _,v in pairs))
        view = self._view()
        try: record = view.read_record(key)
        finally: view.close()
        values = self._defaults() if record is None else self._fields(record)
        result = BSLStructure()
        for f in (*self._schema.resources,*self._schema.attributes): result.insert(f.name,values[f.name.casefold()])
        return result
    def select(self, *args):
        if not self._schema.periodic:
            if len(args)>1: raise TypeError('Select accepts one dimension filter')
            filters=self._filter(args[0] if args else None)
            view=self._view()
            try: rows=view.select_records(self._schema.identity,filters,1000)
            finally: view.close()
        else:
            if not 2<=len(args)<=3: raise TypeError('Select requires start, end and optional dimensions')
            from .periodic_information_registers import moment
            from .dates import _parts
            start,end=map(moment,args[:2])
            if start.ticks>end.ticks: raise ValueError('reversed period range')
            filters=self._filter(args[2] if len(args)==3 else None)
            view=self._view()
            try: rows=view.periodic_records(self._schema.identity,filters,_parts(start),_parts(end),None,1000)
            finally: view.close()
        return BSLInformationRegisterSelection(self,rows)
    def _edge(self, when, dimensions, first, complete=False):
        if not self._schema.periodic: raise ValueError('periodic register required')
        from .periodic_information_registers import moment
        from .dates import _parts
        when=moment(when);filters=self._filter(dimensions,complete=complete)
        view=self._view()
        try: rows=view.periodic_records(self._schema.identity,filters,None,None,(_parts(when),first),1000)
        finally: view.close()
        if complete:
            values=self._defaults() if not rows else self._fields(rows[0])
            result=BSLStructure()
            for f in (*self._schema.resources,*self._schema.attributes): result.insert(f.name,values[f.name.casefold()])
            return result
        from .value_tables import BSLValueTable
        result=BSLValueTable()
        for f in self._schema.fields: result.columns.add(f.name)
        for record in rows:
            row=result.add()
            for name,value in self._fields(record).items(): row.set_member(name,value)
        return result
    def slice_last(self, when, dimensions=None): return self._edge(when,dimensions,False)
    def slice_first(self, when, dimensions=None): return self._edge(when,dimensions,True)
    def get_last(self, when, dimensions): return self._edge(when,dimensions,False,True)
    def get_first(self, when, dimensions): return self._edge(when,dimensions,True,True)
    def get_member(self, name):
        methods = {'createrecordset':self.create_record_set,'создатьнаборзаписей':self.create_record_set,
            'createrecordmanager':self.create_record_manager,'создатьменеджерзаписи':self.create_record_manager,
            'get':self.get,'получить':self.get,'select':self.select,'выбрать':self.select,
            'metadata':lambda:self._metadata,'метаданные':lambda:self._metadata,
            'slicelast':self.slice_last,'срезпоследних':self.slice_last,
            'slicefirst':self.slice_first,'срезпервых':self.slice_first,
            'getlast':self.get_last,'получитьпоследнее':self.get_last,
            'getfirst':self.get_first,'получитьпервое':self.get_first}
        method = methods.get(name.casefold())
        return HostFunction(name,method) if method else super().get_member(name)
    def __str__(self): return str(self._manager_type)


class BSLInformationRegisterRecordManager(BSLObject):
    def __init__(self, manager):
        self._manager = manager; self._record_type = manager._record_type
        self._pending = None; self.clear()
    def clear(self):
        if self._pending is not None: raise BackendError('uncertain_commit')
        self._values = self._manager._defaults(); self._revision = None
        self._operation_id = uuid4()
    def selected(self): return self._revision is not None
    def read(self):
        if self._pending is not None: raise BackendError('uncertain_commit')
        m = self._manager; key = m._record_key(self._values)
        view = m._view()
        try: record = view.read_record(key)
        finally: view.close()
        values = m._defaults() if record is None else m._fields(record)
        if record is None:
            for f in m._schema.key_fields: values[f.name.casefold()] = self._values[f.name.casefold()]
        self._values, self._revision = values, None if record is None else record.revision
    def _accept(self, outcome):
        if type(outcome) is not RegisterOutcome or type(outcome.revision) is not RegisterRevision:
            raise BackendError('uncertain_commit')
        draft, expected, operation, deleted = self._pending
        r = outcome.revision; m = self._manager
        if (type(outcome.deleted) is not bool or outcome.deleted != deleted or
                (r.database_id,r.configuration_generation,r.register_id) !=
                (draft.key.database_id,m._registers._metadata._generation,draft.key.register_id)
                or type(r.token) is not str or not r.token.isascii() or not r.token.isdecimal()
                or not 0 < int(r.token) < 2**63 or type(r.key_digest) is not str or len(r.key_digest)!=64
                or any(c not in '0123456789abcdef' for c in r.key_digest)
                or (expected is not None and (r.key_digest!=expected.key_digest or int(r.token)<=int(expected.token)))): raise BackendError('uncertain_commit')
        next_operation = uuid4()
        self._revision = None if deleted else r
        self._operation_id = next_operation; self._pending = None
    def _write(self, deleted):
        m = self._manager
        if not m._writable(): raise BackendError('unsupported')
        if self._pending is not None:
            draft, expected, operation, pending_delete = self._pending
            if deleted != pending_delete: raise BackendError('uncertain_commit')
            outcome = m._backend.resolve_register_write(operation,draft,expected,deleted)
            if outcome is not None: self._accept(outcome); return
        else:
            if deleted and self._revision is None: raise ValueError('Read an existing record before Delete')
            draft = RegisterDraft(m._record_key(self._values),tuple(m._stored(f,self._values[f.name.casefold()])
                for f in (*m._schema.resources,*m._schema.attributes)))
            expected, operation = self._revision, self._operation_id
        tx = m._backend.begin_register_write(operation); committing = False
        try:
            m._check_view(tx)
            if deleted: tx.delete(draft,expected)
            else: tx.write(draft,expected)
            self._pending = (draft,expected,operation,deleted); committing = True
            outcome = tx.commit(); tx.close(); self._accept(outcome)
        except BaseException as error:
            if not committing: self._pending = None
            for cleanup in (tx.rollback,tx.close):
                try: cleanup()
                except BaseException as cleanup_error:
                    if (not isinstance(cleanup_error,Exception) or isinstance(cleanup_error,MemoryError)) and isinstance(error,Exception) and not isinstance(error,MemoryError): error=cleanup_error
            if committing and isinstance(error,Exception) and not isinstance(error,MemoryError): raise BackendError('uncertain_commit') from None
            raise error
    def write(self): return self._write(False)
    def delete(self): return self._write(True)
    def get_method(self, name):
        methods={'read':self.read,'прочитать':self.read,'write':self.write,'записать':self.write,
            'delete':self.delete,'удалить':self.delete,'selected':self.selected,'выбран':self.selected,
            'clear':self.clear,'очистить':self.clear,'metadata':lambda:self._manager._metadata,
            'метаданные':lambda:self._manager._metadata}
        method=methods.get(name.casefold())
        return HostFunction(name,method) if method else BSLObject.get_member(self,name)
    def get_member(self, name):
        key='period' if name.casefold()=='период' and self._manager._schema.periodic else name.casefold()
        if key not in self._values: return self.get_method(name)
        return self._values[key]
    def set_member(self, name, value):
        if self._pending is not None: raise BackendError('uncertain_commit')
        key=('period' if name.casefold()=='период' and self._manager._schema.periodic else name.casefold()); m=self._manager
        field=next((f for f in m._schema.fields if f.name.casefold()==key),None)
        if field is None: raise ValueError('register field not found')
        value=m._assigned(field,value)
        if self._revision is not None and field in m._schema.key_fields:
            raise ValueError('Clear before changing a selected record key')
        self._values[key]=value
    def __str__(self): raise ValueError('register record presentation unsupported')


class BSLInformationRegisterSelection(BSLObject):
    def __init__(self, manager, rows):
        if type(rows) is not tuple or len(rows)>1000: raise BackendError('integrity')
        self._manager=manager; self._selection_type=manager._selection_type
        self._rows=tuple(manager._fields(row) for row in rows); self._position=-1
    def next(self):
        if self._position<len(self._rows): self._position+=1
        return self._position<len(self._rows)
    def get_method(self, name):
        if name.casefold() in ('next','следующий'): return HostFunction(name,self.next)
        return super().get_method(name)
    def get_member(self, name):
        key=name.casefold()
        if key not in self._manager._defaults(): raise ValueError('register field not found')
        if not 0<=self._position<len(self._rows): return None
        return self._rows[self._position][key]
    def __str__(self): return str(self._selection_type)


def _register_buffer_bytes(values):
    return 64 + sum(len(v.encode('utf-8')) if type(v) is str else 128 for v in values.values())


class _RegisterFilterItem(BSLObject):
    def __init__(self, owner, field): self._owner,self._field=owner,field; self._used=False; self._value=None
    def set(self,value):
        value=self._owner._manager._assigned(self._field,value)
        self._owner._change_filter();self._value=value;self._used=True
    def clear(self): self._owner._change_filter();self._used=False;self._value=None
    def get_member(self,name):
        key=name.casefold()
        if key in ('set','установить'): return HostFunction(name,self.set)
        if key in ('clear','очистить'): return HostFunction(name,self.clear)
        if key in ('use','использование'): return self._used
        if key in ('value','значение'): return self._value
        return super().get_member(name)
    def set_member(self,name,value):
        key=name.casefold()
        if key in ('value','значение'): self.set(value);return
        if key in ('use','использование'):
            if type(value) is not bool: raise TypeError('Use requires Boolean')
            if value and self._value is None: raise ValueError('Set a filter value first')
            self._owner._change_filter();self._used=value;return
        return super().set_member(name,value)


class _RegisterFilter(BSLObject):
    def __init__(self,owner): self._items={f.name.casefold():_RegisterFilterItem(owner,f) for f in owner._manager._schema.key_fields}
    def get_member(self,name):
        if name.casefold() not in self._items: raise ValueError('register dimension not found')
        return self._items[name.casefold()]
    def get_index(self,name):
        if type(name) is not str: raise TypeError('dimension name requires String')
        return self.get_member(name)


class BSLInformationRegisterRecord(BSLObject):
    def __init__(self,owner,values): self._owner=owner;self._values=values;self._row_type=owner._manager._row_type
    def _require(self):
        if not any(self is row for row in self._owner._rows): raise ValueError('record no longer belongs to set')
    def get_member(self,name):
        self._require()
        if name.casefold() not in self._values: raise ValueError('register field not found')
        return self._values[name.casefold()]
    def set_member(self,name,value):
        self._require();self._owner._editable();key=name.casefold();m=self._owner._manager
        field=next((f for f in m._schema.fields if f.name.casefold()==key),None)
        if field is None: raise ValueError('register field not found')
        assigned=m._assigned(field,value)
        proposed=dict(self._values);proposed[key]=assigned
        size=_register_buffer_bytes(proposed)
        if size>1024*1024 or sum(_register_buffer_bytes(r._values) for r in self._owner._rows if r is not self)+size>16*1024*1024:
            raise ValueError('register record set buffer limit exceeded')
        self._values=proposed


class BSLInformationRegisterRecordSet(BSLObject):
    def __init__(self,manager):
        self._manager=manager;self._set_type=manager._set_type
        self._rows=[];self._snapshot=None;self._pending=None;self._operation_id=uuid4()
        self._filter=_RegisterFilter(self)
    def _editable(self):
        if self._pending is not None: raise BackendError('uncertain_commit')
    def _change_filter(self):
        self._editable()
        if self._rows: raise ValueError('Clear the record set before changing its filter')
        self._snapshot=None
    def _filters(self):
        m=self._manager
        return tuple((f.identity,m._stored(f,self._filter._items[f.name.casefold()]._value))
            for f in m._schema.key_fields if self._filter._items[f.name.casefold()]._used)
    def add(self):
        self._editable()
        if len(self._rows)>=1000: raise ValueError('register record set limit exceeded')
        values=self._manager._defaults()
        for key,item in self._filter._items.items():
            if item._used: values[key]=item._value
        if sum(_register_buffer_bytes(r._values) for r in self._rows)+_register_buffer_bytes(values)>16*1024*1024:
            raise ValueError('register record set buffer limit exceeded')
        row=BSLInformationRegisterRecord(self,values);self._rows.append(row);return row
    def clear(self): self._editable();self._rows=[]
    def count(self): return Decimal(len(self._rows))
    def get(self,index):
        if type(index) is not Decimal or not index.is_finite() or index!=index.to_integral_value(): raise TypeError('integer index required')
        i=int(index)
        if not 0<=i<len(self._rows): raise IndexError('record index out of range')
        return self._rows[i]
    get_index=get
    def set_index(self,index,value): raise ValueError('record set row replacement is unsupported')
    def __iter__(self):
        rows=tuple(self._rows)
        for row in rows:
            row._require();yield row
    def read(self):
        self._editable();m=self._manager;view=m._view()
        try: records,snapshot=view.read_set(m._schema.identity,self._filters())
        finally: view.close()
        if type(records) is not tuple or len(records)>1000 or type(snapshot) is not str or len(snapshot)!=64: raise BackendError('integrity')
        rows=[BSLInformationRegisterRecord(self,m._fields(r)) for r in records]
        self._rows=rows;self._snapshot=snapshot
    def _accept(self,outcome):
        if (type(outcome) is not RegisterSetOutcome or outcome.register_id!=self._manager._schema.identity
                or type(outcome.snapshot) is not str or len(outcome.snapshot)!=64
                or any(c not in '0123456789abcdef' for c in outcome.snapshot)
                or type(outcome.count) is not int or not 0<=outcome.count<=10000): raise BackendError('uncertain_commit')
        operation=uuid4();self._snapshot=outcome.snapshot;self._operation_id=operation;self._pending=None
    def write(self,replace=True):
        if type(replace) is not bool: raise TypeError('Replace requires Boolean')
        m=self._manager
        if not m._writable(): raise BackendError('unsupported')
        if self._pending is not None:
            draft,operation=self._pending
            if draft.replace!=replace: raise BackendError('uncertain_commit')
            outcome=m._backend.resolve_register_set(operation,draft)
            if outcome is not None: self._accept(outcome);return
        else:
            rows=tuple(RegisterDraft(m._record_key(row._values),tuple(m._stored(f,row._values[f.name.casefold()])
                for f in (*m._schema.resources,*m._schema.attributes))) for row in self._rows)
            draft=RegisterSetDraft(m._schema.identity,self._filters(),rows,replace,self._snapshot)
            operation=self._operation_id
        tx=m._backend.begin_register_write(operation);committing=False
        try:
            m._check_view(tx);tx.write_set(draft)
            self._pending=(draft,operation);committing=True
            outcome=tx.commit();tx.close();self._accept(outcome)
        except BaseException as error:
            if not committing: self._pending=None
            for cleanup in (tx.rollback,tx.close):
                try: cleanup()
                except BaseException as cleanup_error:
                    if (not isinstance(cleanup_error,Exception) or isinstance(cleanup_error,MemoryError)) and isinstance(error,Exception) and not isinstance(error,MemoryError): error=cleanup_error
            if committing and isinstance(error,Exception) and not isinstance(error,MemoryError): raise BackendError('uncertain_commit') from None
            raise error
    def get_member(self,name):
        if name.casefold() in ('filter','отбор'): return self._filter
        methods={'add':self.add,'добавить':self.add,'clear':self.clear,'очистить':self.clear,
            'count':self.count,'количество':self.count,'get':self.get,'получить':self.get,
            'read':self.read,'прочитать':self.read,'write':self.write,'записать':self.write,
            'metadata':lambda:self._manager._metadata,'метаданные':lambda:self._manager._metadata}
        method=methods.get(name.casefold())
        return HostFunction(name,method) if method else super().get_member(name)
    def __str__(self): return str(self._set_type)
