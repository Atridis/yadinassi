"""Lightweight working ValueTable facade over Python list rows.

Native compatibility is intentionally incomplete. Receiver ownership is not
relaxed: the compiler/native boundary still admits only these exact classes.
"""
from decimal import Decimal, ROUND_DOWN
from types import MappingProxyType
from yadinassi.types.values import BSLObject, BSLArray, HostFunction
from yadinassi.types.type_descriptions import BSLTypeDescription
from .plain_table_search import SearchIndexes
from .value_tables import _adjust, _default
from .plain_table_storage import RowStorage, TableStorage, Schema, scalar_equal


def _index(value,count,inserting=False):
    if type(value) is int:
        if not 0 <= value < count + inserting:raise IndexError("table index out of range")
        return value
    elif type(value) is Decimal and value.is_finite():n=value.to_integral_value(rounding=ROUND_DOWN)
    else:raise TypeError('table index must be a finite number')
    if not 0<=n<count+int(inserting):raise IndexError('table index out of range')
    return int(n)


def _writable(table):
    if table._bounded_slice_read:raise ValueError('bounded table slice is readonly')


def _query_column(description):
    return description._query_scalar is not None or description._query_reference is not None


def _array(values):
    result=BSLArray();result.items=list(values);return result


def public_cell(value):
    return Decimal(value) if type(value) is int else value


def _method(value,name,groups):
    key=name.casefold()
    for aliases,method,returns in groups:
        if key in aliases:return HostFunction(name,getattr(value,method),returns_value=returns)
    raise ValueError('Метод не найден: '+name)


class BSLValueTableColumn(BSLObject):
    def __init__(self,table,name,value_type,title='',width=Decimal(0)):
        self.table=table;self._name=name;self.value_type=value_type
        self.title=title;self.width=width;self._deleted=False
    @property
    def name(self):return self._name
    @name.setter
    def name(self,value):self.table.columns.rename(self,value)
    def get_member(self,name):
        key=name.casefold()
        if key in ('name','имя'):return self._name
        if key in ('valuetype','типзначения'):return self.value_type
        if key in ('title','заголовок'):return self.title
        if key in ('width','ширина'):return self.width
        return super().get_member(name)
    def set_member(self,name,value):
        _writable(self.table)
        key=name.casefold()
        if self._deleted:raise ValueError('column is deleted')
        if key in ('name','имя'):self.table.columns.rename(self,value)
        elif key in ('title','заголовок'):
            if type(value) is not str:raise TypeError('title must be str')
            self.title=value
        elif key in ('width','ширина'):
            if type(value) is not Decimal or not value.is_finite():raise TypeError('width must be finite number')
            self.width=value
        else:super().set_member(name,value)
    def __str__(self):return 'КолонкаТаблицыЗначений'


class BSLValueTableColumnCollection(BSLObject):
    def __init__(self,table):self.table=table;self._items=[];self._query_columns=0
    @property
    def items(self):return tuple(self._items)
    def __iter__(self):return iter(self._items)
    def add(self,name='',value_type=None,title='',width=Decimal(0)):
        _writable(self.table)
        if type(name) is not str or type(title) is not str:raise TypeError('column text must be str')
        if value_type is None:value_type=BSLTypeDescription()
        if type(value_type) is not BSLTypeDescription:raise TypeError('exact TypeDescription required')
        if type(width) is not Decimal or not width.is_finite():raise TypeError('width must be finite')
        column=BSLValueTableColumn(self.table,name,value_type,title,width)
        default = _default(value_type) if value_type.types else None
        self.table._storage.add_column(name,column,default);self._items.append(column)
        return column
    def _append_materialized(self,column):
        if type(column) is not BSLValueTableColumn or column.table is not self.table:raise ValueError('foreign column')
        description=column.value_type
        query_column=_query_column(description)
        default = None if query_column or not description.types else _default(description)
        self.table._storage.add_column(column.name,column,default);self._items.append(column)
        self._query_columns += query_column
    def _restore_materialized_type(self,column,description):
        # The validated snapshot already supplied every cell; a query descriptor
        # still does not supply defaults for a future blank row.
        column.value_type=description
        self._query_columns += _query_column(description)
    def find(self,name):
        if type(name) is not str:raise TypeError('column name must be str')
        offsets=self.table._storage.schema._offsets
        if type(offsets) is not dict or any(type(k) is not str for k in offsets):raise ValueError('noncanonical schema lookup')
        pos=offsets.get(name.casefold())
        if pos is not None and type(pos) is not int:raise ValueError('noncanonical schema offset')
        return None if pos is None else self._items[pos]
    def get(self,index):return self._items[_index(index,len(self._items))]
    def get_index(self,index):
        if type(index) is str:
            column=self.find(index)
            if column is None:raise ValueError('column not found: '+index)
            return column
        return self.get(index)
    def resolve(self,column):
        if type(column) is BSLValueTableColumn:
            if column.table is not self.table or column._deleted or not any(c is column for c in self._items):raise ValueError('foreign column')
            return column
        return self.get_index(column)
    def rename(self,column,name):
        _writable(self.table)
        column=self.resolve(column)
        self.table._storage.rename_column(column._name,name);column._name=name
    def delete(self,column):
        _writable(self.table)
        column=self.resolve(column)
        indexes=self.table.indexes
        plan=indexes._without_column(column)
        self.table._storage.delete_column(column.name)
        indexes._apply_column_delete(plan)
        self._items.remove(column);column._deleted=True
        self._query_columns -= _query_column(column.value_type)
    def clear(self):
        for column in tuple(self._items):self.delete(column)
        self.table.clear()
    def count(self):return Decimal(len(self._items))
    def _index_of(self,column):return next((i for i,c in enumerate(self._items) if c is column),-1)
    def index_of(self,column):return Decimal(self._index_of(column))
    def insert(self,index,name='',value_type=None,title='',width=Decimal(0)):
        _writable(self.table)
        if type(index) is int:n=index
        elif type(index) is Decimal and index.is_finite():n=index.to_integral_value(rounding=ROUND_DOWN)
        else:raise TypeError('table index must be a finite number')
        size=len(self._items)
        # The native collections fixture observes both negative and past-end
        # insertion as append. In that case retain the ordinary append path.
        if not 0<=n<size:return self.add(name,value_type,title,width)
        position=int(n)
        if type(name) is not str or type(title) is not str:raise TypeError('column text must be str')
        if value_type is None:value_type=BSLTypeDescription()
        if type(value_type) is not BSLTypeDescription:raise TypeError('exact TypeDescription required')
        if type(width) is not Decimal or not width.is_finite():raise TypeError('width must be finite')
        column=BSLValueTableColumn(self.table,name,value_type,title,width)
        default=_default(value_type) if value_type.types else None
        indexes=self.table.indexes
        if type(indexes) is not BSLCollectionIndexes or indexes.table is not self.table or type(indexes.items) is not list:
            raise ValueError('noncanonical index declarations')
        shifted=[]
        for signature in indexes.items:
            if type(signature) is not tuple or any(type(i) is not int or not 0<=i<size for i in signature):
                raise ValueError('noncanonical index declaration')
            shifted.append(tuple(i+(i>=position) for i in signature))
        declarations=set(shifted)
        self.table._storage.insert_column(position,name,column,default)
        self._items.insert(position,column)
        indexes.items[:]=shifted
        self.table._search.declarations=declarations
        self.table._search.cache.clear()
        return column
    def move(self,column,offset):
        table=self.table
        if type(table) is not BSLValueTable:raise ValueError('foreign table')
        _writable(table)
        if type(offset) is int:distance=offset
        elif type(offset) is Decimal and offset.is_finite():distance=offset.to_integral_value(rounding=ROUND_DOWN)
        else:raise TypeError('column offset must be a finite number')
        storage=table._storage
        if (type(storage) is not TableStorage or storage.owner is not table
                or storage.row_factory is not BSLValueTableRow or storage.rows is not table.rows
                or type(storage.schema) is not Schema or table.columns is not self
                or type(self._items) is not list or type(storage.schema._metadata) is not list
                or len(self._items)!=len(storage.schema._metadata)):
            raise ValueError('noncanonical column storage')
        for existing,metadata in zip(self._items,storage.schema._metadata):
            if (type(existing) is not BSLValueTableColumn or existing is not metadata
                    or existing.table is not table or existing._deleted is not False):
                raise ValueError('noncanonical column storage')
        old=self._index_of(self.resolve(column))
        size=len(self._items)
        # Check distance before converting a potentially very large Decimal.
        if not -old<=distance<size-old:raise IndexError('column index out of range')
        new=old+int(distance)
        if old==new:return
        indexes,search=table.indexes,table._search
        if (type(indexes) is not BSLCollectionIndexes or indexes.table is not table
                or type(indexes.items) is not list or type(search) is not SearchIndexes
                or type(search.cache) is not dict):
            raise ValueError('noncanonical index declarations')
        order=list(range(size))
        order.insert(new,order.pop(old))
        offsets=[0]*size
        for position,previous in enumerate(order):offsets[previous]=position
        shifted=[]
        for signature in indexes.items:
            if type(signature) is not tuple or any(type(i) is not int or not 0<=i<size for i in signature):
                raise ValueError('noncanonical index declaration')
            shifted.append(tuple(sorted(offsets[i] for i in signature)))
        declarations=set(shifted)
        storage.move_column(old,new)
        self._items.insert(new,self._items.pop(old))
        indexes.items[:]=shifted
        search.declarations=declarations
        search.cache.clear()
    def get_member(self,name):return self.get_index(name)
    def set_index(self,*args):raise ValueError('columns cannot be replaced')
    def get_method(self,name):return _method(self,name,(
        (('add','добавить'),'add',True),(('get','получить'),'get',True),
        (('find','найти'),'find',True),(('count','количество'),'count',True),
        (('indexof','индекс'),'index_of',True),(('delete','удалить'),'delete',False),
        (('clear','очистить'),'clear',False),(('insert','вставить'),'insert',True),
        (('move','сдвинуть'),'move',False)))


class BSLValueTableRow(RowStorage,BSLObject):
    __hash__=object.__hash__
    __eq__=object.__eq__
    __ne__=object.__ne__
    def __init__(self,owner,schema,values=None):
        RowStorage.__init__(self,owner,schema,values);self.table=owner
    def get_member(self,name):
        value = RowStorage.get_value(self,name)
        return Decimal(value) if type(value) is int else value
    def set_member(self,name,value):
        _writable(self.table)
        if self._deleted:raise ValueError("row is deleted")
        position = self.schema.offset(name)
        description = self.schema._metadata[position].value_type
        if description.types:value = _adjust(description,value)
        self.schema.data_epoch += 1
        list.__setitem__(self,position,value)
    def _positional_value(self,index):
        if self._deleted:raise ValueError("row is deleted")
        return list.__getitem__(self,_index(index,len(self.schema._keys)))
    def get(self,index):
        value = self._positional_value(index)
        return Decimal(value) if type(value) is int else value
    def set(self,index,value):
        if self._deleted:raise ValueError("row is deleted")
        _writable(self.table)
        position = _index(index,len(self.schema._keys))
        description = self.schema._metadata[position].value_type
        if description.types:value = _adjust(description,value)
        self.table._storage.epoch += 1
        list.__setitem__(self,position,value)
    def get_index(self,index):return self.get_member(index) if type(index) is str else self.get(index)
    def set_index(self,index,value):return self.set_member(index,value) if type(index) is str else self.set(index,value)
    def owner(self):
        if self._deleted:raise ValueError('row is deleted')
        return self.table
    @property
    def cells(self):
        # Readonly cold snapshot for inspection; not a second authoritative map.
        return MappingProxyType({c:public_cell(list.__getitem__(self,i)) for i,c in enumerate(self.table.columns._items)})
    @cells.setter
    def cells(self,values):
        if type(values) is not dict:raise TypeError('materialized cells must be dict')
        prepared={}
        for column,value in values.items():
            if type(column) is not BSLValueTableColumn or column.table is not self.table:raise ValueError('foreign column')
            prepared[column.name.casefold()]=value
        if set(prepared)!=set(self.schema._keys):raise ValueError('materialized schema mismatch')
        _writable(self.table)
        self.table._storage.epoch += 1
        list.__setitem__(self,slice(None),[prepared[k] for k in self.schema._keys])
    def __iter__(self):return map(public_cell,list.__iter__(self))
    def get_method(self,name):return _method(self,name,(
        (('get','получить'),'get',True),(('set','установить'),'set',False),(('owner','владелец'),'owner',True)))
    def __str__(self):return 'СтрокаТаблицыЗначений'


class BSLCollectionIndex(BSLObject):
    """A public definition, not a bucket owner or a retained row inventory."""
    def __init__(self, table, columns):
        self.table = table
        self._columns = columns
        self._detached = self._cleared = False

    def _name(self, position):
        column = self._columns[position]
        if column is None:
            return ''
        if type(column) is not BSLValueTableColumn or column.table is not self.table:
            raise ValueError('foreign index column')
        if column._deleted is True:
            return ''
        if column._deleted is not False or type(column._name) is not str:
            raise ValueError('invalid index column')
        return column._name

    def __iter__(self):
        columns = self._columns
        if type(columns) is not tuple:
            raise ValueError('invalid index columns')
        return iter(tuple(self._name(i) for i in range(len(columns))))

    def get_index(self, index):
        if type(self._columns) is not tuple:
            raise ValueError('invalid index columns')
        return self._name(_index(index, len(self._columns)))

    def set_index(self, *args):
        raise ValueError('index definition is readonly')

    def __str__(self):
        if self._cleared:
            raise ValueError('Индекс коллекции очищен')
        return ', '.join(self)


class BSLCollectionIndexes(BSLObject):
    def __init__(self, table):
        self.table = table
        self.items = []  # unique sorted offset signatures, not public handles
        self._handles = []

    def __str__(self):return 'ИндексыКоллекции'
    def __iter__(self):return iter(tuple(self._active()))
    def count(self):
        if type(self._handles) is not list:raise ValueError('invalid index handles')
        return Decimal(len(self._handles))
    def get_index(self,index):
        handles = self._handles
        if type(handles) is not list:raise ValueError('invalid index handles')
        return self._handle(handles[_index(index,len(handles))])
    def set_index(self,*args):raise ValueError('index collection is readonly')

    def _add_positions(self, positions):
        columns = tuple(self.table.columns._items[i] for i in positions)
        handle = BSLCollectionIndex(self.table, columns)
        signature = self._signature(positions)
        if signature and signature not in self.items:
            self.table._search.declare(signature)
            self.items.append(signature)
        self._handles.append(handle)
        return handle

    def add(self,names=None):
        _writable(self.table)
        if names is None:
            return self._add_positions(())
        if type(names) is not str:raise TypeError('index columns must be str')
        schema = self.table._storage.schema
        return self._add_positions(tuple(schema.offset(name) for part in names.split(',')
                                         if (name := part.strip())))

    def _positions(self, columns, positions):
        if type(columns) is not tuple:
            raise ValueError('invalid index columns')
        result = []
        for column in columns:
            if (type(column) is not BSLValueTableColumn or column.table is not self.table
                    or column._deleted is not False or id(column) not in positions):
                raise ValueError('foreign index column')
            result.append(positions[id(column)])
        return tuple(result)

    def _handle(self, handle):
        if (type(handle) is not BSLCollectionIndex or handle.table is not self.table
                or handle._detached is not False or handle._cleared is not False
                or type(handle._columns) is not tuple):
            raise ValueError('foreign index handle')
        return handle

    def _active(self):
        if type(self._handles) is not list:
            raise ValueError('invalid index handles')
        for handle in self._handles:self._handle(handle)
        return self._handles

    @staticmethod
    def _signature(positions):
        if len(set(positions)) != len(positions):
            return ()
        return tuple(sorted(positions))

    def _replace_signatures(self, signatures, *, preserve_cache=False):
        self.items[:] = signatures
        search = self.table._search
        search.declarations = set(signatures)
        if preserve_cache:
            for dropped in search.cache.keys() - search.declarations:
                del search.cache[dropped]
        else:
            search.cache.clear()

    def _without_column(self, removed):
        columns = [col for col in self.table.columns._items if col is not removed]
        positions = {id(col): i for i,col in enumerate(columns)}
        plans = [(handle, tuple(col for col in handle._columns if col is not removed))
                 for handle in self._active()]
        signatures = [self._signature(self._positions(columns, positions)) for _,columns in plans]
        return plans, list(dict.fromkeys(sig for sig in signatures if sig))

    def _apply_column_delete(self, plan):
        plans, signatures = plan
        for handle,columns in plans:
            handle._columns = columns
        self._replace_signatures(signatures)

    def delete(self, index):
        _writable(self.table)
        handles = self._active()
        if type(index) is str:
            from decimal import InvalidOperation
            try:index = Decimal(index)
            except InvalidOperation:raise ValueError('expected numeric index') from None
        if type(index) is not BSLCollectionIndex:
            index = self.get_index(index)
        if index.table is not self.table or not any(handle is index for handle in handles):
            raise ValueError('foreign or detached index')
        remaining = [handle for handle in handles if handle is not index]
        positions = {id(col): i for i,col in enumerate(self.table.columns._items)}
        signatures = [self._signature(self._positions(handle._columns, positions)) for handle in remaining]
        self._replace_signatures(list(dict.fromkeys(sig for sig in signatures if sig)), preserve_cache=True)
        self._handles[:] = remaining
        index._detached = True

    def clear(self):
        _writable(self.table)
        plans = [(handle, (None,) * len(handle._columns)) for handle in self._active()]
        for handle,columns in plans:
            handle._columns = columns
            handle._detached = handle._cleared = True
        self._handles.clear()
        self.items.clear()
        self.table._search.clear()

    def get_method(self,name):return _method(self,name,(
        (('count','количество'),'count',True),(('add','добавить'),'add',True),
        (('delete','удалить'),'delete',False),(('clear','очистить'),'clear',False)))


class BSLValueTable(BSLObject):
    def __init__(self):
        self._search=SearchIndexes()
        self._bounded_slice_read=False;self._storage=TableStorage(self,BSLValueTableRow)
        self.rows=self._storage.rows;self.columns=BSLValueTableColumnCollection(self);self.indexes=BSLCollectionIndexes(self)
    def add(self):
        _writable(self)
        if self.columns._query_columns:raise ValueError('default row values for query columns are not supported')
        return self._storage.add()
    def insert(self,index):
        _writable(self)
        if self.columns._query_columns:raise ValueError('default row values for query columns are not supported')
        return self._storage.insert(_index(index,len(self.rows),True))
    def get(self,index):return self.rows[_index(index,len(self.rows))]
    get_index=get
    def set_index(self,*args):raise ValueError('rows cannot be replaced')
    def __iter__(self):return iter(self.rows)
    def count(self):return Decimal(len(self.rows))
    def _index_of(self,row):
        for index,item in enumerate(self.rows):
            if item is row:return index
        return -1
    def index_of(self,row):return Decimal(self._index_of(row))
    def _row_index(self,row):
        if type(row) is BSLValueTableRow:
            index=self._index_of(row)
            if index<0:raise ValueError('foreign row')
            return index
        return _index(row,len(self.rows))
    def delete(self,row):
        _writable(self);self._storage.delete(self._row_index(row))
    def clear(self):
        _writable(self);self._storage.clear()
    def move(self,row,offset):
        _writable(self)
        if type(offset) is int:distance=offset
        elif type(offset) is Decimal and offset.is_finite():distance=int(offset.to_integral_value(rounding=ROUND_DOWN))
        else:raise TypeError('row offset must be a finite number')
        self._storage.move(self._row_index(row),distance)
    def _selection(self,names):
        if names is None:return tuple(self._storage.schema._names)
        if type(names) is not str:raise TypeError('column selection must be str')
        if not names:return tuple(self._storage.schema._names)
        result=tuple(x.strip() for x in names.split(','))
        for name in result:self._storage.schema.resolve(name)
        return result
    def find(self,value,columns=None):
        schema=self._storage.schema
        selected=tuple(schema.offset(name) for name in self._selection(columns))
        for row in self.rows:
            for position in selected:
                if scalar_equal(list.__getitem__(row,position),value):return row
        return None
    def find_rows(self,filters):
        from .structures import BSLStructure
        from yadinassi.execution.codegen.experimental_naked_structure import _DirectStructure
        if type(filters) is BSLStructure:
            fields = filters._items.values()
        elif type(filters) is _DirectStructure:
            fields = dict.values(filters)
        else:
            raise TypeError('Structure filter required')
        selected = tuple((self._storage.schema.offset(name), value) for name, value in fields)
        result = []
        # Historical FindRows(empty Structure) is empty, not all rows.
        if selected:
            rows = self._search.candidates(self.rows, selected, (self._storage.epoch,self._storage.schema.version,self._storage.schema.data_epoch), True)
            for row in rows:
                for offset, value in selected:
                    if not scalar_equal(list.__getitem__(row, offset), value):
                        break
                else:
                    result.append(row)
        return _array(result)
    def fill_values(self,value,columns=None):
        _writable(self);self._storage.fill(value,self._selection(columns))
    def unload_column(self,column):
        name=self.columns.resolve(column).name
        return _array(row.get_member(name) for row in self.rows)
    def load_column(self,values,column):
        _writable(self)
        if type(values) is not BSLArray:raise TypeError('Array required')
        name=self.columns.resolve(column).name
        for row,value in zip(self.rows,values.items):row.set_member(name,value)
    def total(self,column):
        position=self._storage.schema.offset(self.columns.resolve(column).name)
        result=sum((v for row in self.rows if type(v:=list.__getitem__(row,position)) in (int,Decimal)),0)
        return public_cell(result)
    def sort(self,order,comparator=None):
        _writable(self)
        if comparator is not None:
            kind = type(comparator)
            if kind is int or kind is Decimal:
                raise TypeError('numeric sort comparator is invalid')
            raise NotImplementedError('custom comparator is parked')
        if type(order) is not str:raise TypeError('sort order must be str')
        terms=[]
        for part in order.split(','):
            tokens=part.strip().split()
            if not tokens:continue
            if len(tokens)>2:raise ValueError('invalid sort order')
            direction=tokens[1].casefold() if len(tokens)==2 else 'asc'
            terms.append((tokens[0],direction in ('desc','убыв')))
        if not terms:raise ValueError('invalid sort order')
        self._storage.sort(terms)
    def copy_columns(self,columns=None):
        result=BSLValueTable()
        for name in self._selection(columns):
            c=self.columns.find(name);result.columns.add(c.name,c.value_type,c.title,c.width)
        return result
    def copy(self,rows=None,columns=None):
        selected=self._selection(columns);result=self.copy_columns(columns)
        if rows is None:source=self.rows
        elif type(rows) is BSLArray:source=rows.items
        else:source=self.find_rows(rows).items
        for row in source:
            if type(row) is not BSLValueTableRow or row.table is not self:raise ValueError('foreign copy row')
            copied=result.add()
            for name in selected:copied.set_member(name,row.get_member(name))
        return result
    def group_by(self,*args):raise NotImplementedError('ValueTable grouping is parked')
    def get_member(self,name):
        if name.casefold() in ('columns','колонки'):return self.columns
        if name.casefold() in ('indexes','индексы'):return self.indexes
        return super().get_member(name)
    def get_method(self,name):return _method(self,name,(
        (('add','добавить'),'add',True),(('insert','вставить'),'insert',True),(('get','получить'),'get',True),
        (('count','количество'),'count',True),(('delete','удалить'),'delete',False),(('clear','очистить'),'clear',False),
        (('move','сдвинуть'),'move',False),(('indexof','индекс'),'index_of',True),(('find','найти'),'find',True),
        (('findrows','найтистроки'),'find_rows',True),(('fillvalues','заполнитьзначения'),'fill_values',False),
        (('loadcolumn','загрузитьколонку'),'load_column',False),(('unloadcolumn','выгрузитьколонку'),'unload_column',True),
        (('total','итог'),'total',True),(('sort','сортировать'),'sort',False),(('copy','скопировать'),'copy',True),
        (('copycolumns','скопироватьколонки'),'copy_columns',True),(('groupby','свернуть'),'group_by',False)))
    def __str__(self):return 'ТаблицаЗначений'

_DIRECT_CLASSES=tuple((cls,cls.__mro__,tuple(vars(cls).items())) for cls in
    (BSLValueTable,BSLValueTableRow,BSLValueTableColumn,BSLValueTableColumnCollection,BSLCollectionIndexes,BSLCollectionIndex,BSLObject))
_DIRECT_FUNCTIONS=tuple((fn,fn.__code__,fn.__defaults__,tuple((fn.__kwdefaults__ or {}).items()))
    for fn in [*globals().values(),*(fn for cls,_,fields in _DIRECT_CLASSES for _,v in fields
        for fn in ((v.fget,v.fset,v.fdel) if type(v) is property else (v,)) if fn is not None)]
    if type(fn) is type(lambda:None))
_DIRECT_BINDINGS=tuple((name,value) for name,value in tuple(globals().items()) if callable(value) or name.startswith("_MAX_"))

_DIRECT_NAMES=frozenset((*globals(), "_DIRECT_NAMES"))
