"""Lightweight working ValueTable facade over Python list rows.

Native compatibility is intentionally incomplete. Receiver ownership is not
relaxed: the compiler/native boundary still admits only these exact classes.
"""
from decimal import Decimal, ROUND_DOWN
from types import MappingProxyType
from yadinassi.types.values import BSLObject, BSLArray, HostFunction
from yadinassi.types.type_descriptions import BSLTypeDescription
from .plain_table_search import SearchIndexes
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
    def __init__(self,table):self.table=table;self._items=[]
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
        # Default and coercion compatibility is deliberately not in the hot
        # path. Typed descriptors are metadata; default cells are Undefined.
        self.table._storage.add_column(name,column,None);self._items.append(column)
        return column
    def _append_materialized(self,column):
        if type(column) is not BSLValueTableColumn or column.table is not self.table:raise ValueError('foreign column')
        self.table._storage.add_column(column.name,column,None);self._items.append(column)
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
        position=self.table._storage.schema.offset(column.name)
        self.table._storage.delete_column(column.name)
        indexes=self.table.indexes
        indexes.items[:]=[tuple(i-(i>position) for i in sig) for sig in indexes.items if position not in sig]
        self.table._search.declarations=set(indexes.items)
        self.table._search.cache.clear()
        self._items.remove(column);column._deleted=True
    def clear(self):
        for column in tuple(self._items):self.delete(column)
        self.table.clear()
    def count(self):return Decimal(len(self._items))
    def index_of(self,column):return Decimal(next((i for i,c in enumerate(self._items) if c is column),-1))
    def insert(self,*args):raise NotImplementedError('column insertion is parked')
    def move(self,*args):raise NotImplementedError('column reordering is parked')
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
        _writable(self.table);return RowStorage.set_value(self,name,value)
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


class BSLCollectionIndexes(BSLObject):
    def __init__(self,table):self.table=table;self.items=[]
    def count(self):return Decimal(len(self.items))
    def add(self,names):
        _writable(self.table)
        if type(names) is not str:raise TypeError('index columns must be str')
        offsets=tuple(self.table._storage.schema.offset(n.strip()) for n in names.split(','))
        signature=self.table._search.declare(offsets)
        if signature not in self.items:self.items.append(signature)
        return signature
    def clear(self):
        _writable(self.table);self.items.clear();self.table._search.clear()
    def get_method(self,name):return _method(self,name,(
        (('count','количество'),'count',True),(('add','добавить'),'add',True),(('clear','очистить'),'clear',False)))


class BSLValueTable(BSLObject):
    def __init__(self):
        self._search=SearchIndexes()
        self._bounded_slice_read=False;self._storage=TableStorage(self,BSLValueTableRow)
        self.rows=self._storage.rows;self.columns=BSLValueTableColumnCollection(self);self.indexes=BSLCollectionIndexes(self)
    def add(self):
        _writable(self);return self._storage.add()
    def insert(self,index):
        _writable(self);return self._storage.insert(_index(index,len(self.rows),True))
    def get(self,index):return self.rows[_index(index,len(self.rows))]
    get_index=get
    def set_index(self,*args):raise ValueError('rows cannot be replaced')
    def __iter__(self):return iter(self.rows)
    def count(self):return Decimal(len(self.rows))
    def index_of(self,row):return Decimal(next((i for i,r in enumerate(self.rows) if r is row),-1))
    def _row_index(self,row):
        if type(row) is BSLValueTableRow:
            for index,item in enumerate(self.rows):
                if item is row:return index
            raise ValueError('foreign row')
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
        if comparator is not None:raise NotImplementedError('custom comparator is parked')
        if type(order) is not str:raise TypeError('sort order must be str')
        terms=[]
        for part in order.split(','):
            tokens=part.strip().split()
            if not 1<=len(tokens)<=2:raise ValueError('invalid sort order')
            direction=tokens[1].casefold() if len(tokens)==2 else 'asc'
            if direction not in ('asc','desc','возр','убыв'):raise ValueError('invalid sort direction')
            terms.append((tokens[0],direction in ('desc','убыв')))
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
    (BSLValueTable,BSLValueTableRow,BSLValueTableColumn,BSLValueTableColumnCollection,BSLCollectionIndexes,BSLObject))
_DIRECT_FUNCTIONS=tuple((fn,fn.__code__,fn.__defaults__,tuple((fn.__kwdefaults__ or {}).items()))
    for fn in [*globals().values(),*(fn for cls,_,fields in _DIRECT_CLASSES for _,v in fields
        for fn in ((v.fget,v.fset,v.fdel) if type(v) is property else (v,)) if fn is not None)]
    if type(fn) is type(lambda:None))
_DIRECT_BINDINGS=tuple((name,value) for name,value in tuple(globals().items()) if callable(value) or name.startswith("_MAX_"))

_DIRECT_NAMES=frozenset((*globals(), "_DIRECT_NAMES"))
