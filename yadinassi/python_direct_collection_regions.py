"""Proved callback-free collection prefixes; eager canonical objects, no replay.

This stage removes dynamic service routing and allocates eager canonical rows
and items through closed scalar leaf helpers. Unknown syntax ends a prefix.
Runtime ABI/graph mismatch selects ordinary direct operations before the loop,
never by catching or replaying a failed operation.
"""
from decimal import Decimal
from .syntax import ast


def analyze(program, *, opaque_names=()):
    opaque = set(opaque_names) | {'thisobject', 'этотобъект'}
    known = {}
    operations = {}
    loop_states = {}
    has_loop = False

    def expression(node, state):
        kind = type(node)
        if kind is ast.Literal and type(node.value) is Decimal:
            return 'number'
        if kind is ast.Name:
            key = node.name.casefold()
            if key not in opaque and key in state:
                return state[key]
        if kind is ast.Group:
            return expression(node.expression, state)
        if kind is ast.Binary and node.operator in ('+', '-', '*', '%'):
            if expression(node.left, state) == expression(node.right, state) == 'number': return 'number'
        if kind is ast.New and not node.arguments:
            key = node.name.casefold()
            if key in ('valuetable', 'таблицазначений'): return 'table'
            if key in ('valuelist', 'списокзначений'): return 'list'
        if kind is ast.Attribute:
            owner = expression(node.object, state)
            name = node.name.casefold()
            if owner == 'table' and name in ('columns', 'колонки'):
                return 'columns'
            if owner == 'row':
                operations[id(node)] = 'row_get'; return 'number'
            if owner == 'item' and name in ('value', 'значение'):
                operations[id(node)] = 'item_get'; return 'number'
        if kind is ast.Call and type(node.callee) is ast.Attribute:
            owner = expression(node.callee.object, state)
            method = node.callee.name.casefold()
            args = node.arguments
            if owner == 'columns' and method in ('add', 'добавить') and len(args) == 1 and type(args[0]) is ast.Literal and type(args[0].value) is str:
                return 'column'
            if owner == 'table' and method in ('add', 'добавить') and not args:
                operations[id(node)] = 'table_add'; return 'row'
            if owner == 'list' and method in ('add', 'добавить') and len(args) == 1 and expression(args[0], state) == 'number':
                operations[id(node)] = 'list_add'; return 'item'
            if owner in ('table', 'list') and method in ('get', 'получить') and len(args) == 1 and expression(args[0], state) == 'number':
                operations[id(node)] = owner + '_get'; return 'row' if owner == 'table' else 'item'
        return None

    def statement(node, state, *, nested=False):
        nonlocal has_loop
        if type(node) is ast.Assign:
            target = node.target
            value = expression(node.value, state)
            if not value: return False
            if type(target) is ast.Name:
                key = target.name.casefold()
                if key in opaque: return False
                # No arbitrary aliases; construction is top-level only. A row
                # binding is allowed and remains a real canonical object.
                if value in ('table', 'list') and (nested or type(node.value) is not ast.New): return False
                if value in ('columns', 'column'): return False
                if key in state and state[key] != value: return False
                state[key] = value; return True
            if type(target) is ast.Attribute and expression(target.object, state) == 'row' and value == 'number':
                operations[id(node)] = 'row_set'; return True
            return False
        if type(node) is ast.ExpressionStatement:
            return type(node.expression) is ast.Call and (not nested or not (type(node.expression.callee) is ast.Attribute and expression(node.expression.callee.object,state)=='columns')) and expression(node.expression, state) is not None
        if type(node) is ast.For:
            key = node.name.casefold()
            if key in opaque or state.get(key, 'number') != 'number': return False
            if expression(node.start, state) != 'number' or expression(node.end, state) != 'number': return False
            def writes(nodes):
                result=set()
                for child in nodes:
                    if type(child) is ast.Assign and type(child.target) is ast.Name:result.add(child.target.name.casefold())
                    elif type(child) is ast.For:result.add(child.name.casefold());result.update(writes(child.body))
                return result
            loop_states[id(node)] = (dict(state),tuple(sorted(writes(node.body)|{key})))
            inner = dict(state); inner[key] = 'number'
            if not all(statement(child, inner, nested=True) for child in node.body): return False
            # Zero iterations publish only the counter. No new body facts leak.
            state[key] = 'number'; has_loop = True; return True
        return False

    end = 0
    for index, node in enumerate(program):
        old_ops, old_states = dict(operations), dict(loop_states)
        old_has_loop = has_loop
        candidate = dict(known)
        if not statement(node, candidate):
            operations, loop_states = old_ops, old_states
            has_loop = old_has_loop
            break
        known = candidate; end = index + 1
    if not has_loop or not operations: return 0, {}, {}
    return end, operations, loop_states



class _UnprovedGraph(Exception):
    pass


def admitted(context, state, specification, writes=()):
    try:return _admitted(context,state,specification,writes)
    except _UnprovedGraph:return False


def _admitted(context, state, specification, writes):
    """Validate an eager, untyped scalar graph before a callback-free loop.

    Constructors and schema changes use the ordinary boundary. They are not
    assumed pure: this check runs AFTER them, and no transitive constructor or
    type-description methods are called inside the optimized loop.
    """
    from . import value_tables as table, value_lists as values, type_descriptions, type_values, type_qualifiers
    if context.policy is not None or any(type(key) is not str for key in state): return False
    if values.weakref.ref is not values._DIRECT_REGION_WEAKREF or values.weakref.getweakrefs is not values._DIRECT_REGION_GETWEAKREFS: return False
    if type_values._VALUE_TYPES is not type_values._DIRECT_REGION_VALUE_TYPES:return False
    for module in (table,values,type_descriptions):
        if any(type(key) is not str for key in vars(module)):return False
        if vars(module).keys()!=module._DIRECT_REGION_KEYS:return False
        if any(vars(module).get(name) is not value for name,value in module._DIRECT_REGION_GLOBALS):return False
        for fn,code,defaults,kwdefaults in module._DIRECT_REGION_FUNCTIONS:
            if fn.__code__ is not code or fn.__defaults__ is not defaults:return False
            current=fn.__kwdefaults__ or {}
            if any(type(k) is not str for k in current):return False
            if len(current)!=len(kwdefaults) or any(current.get(k) is not v for k,v in kwdefaults):return False
    for module in (table, values, type_qualifiers):
        abi=(module._DIRECT_LIVE_METADATA_CLASSES if module is type_qualifiers else module._DIRECT_REGION_ABI)
        for cls, mro, entries in abi:
            current = vars(cls)
            if any(type(key) is not str for key in current):return False
            if len(cls.__mro__)!=len(mro) or any(a is not b for a,b in zip(cls.__mro__,mro)) or len(current)!=len(entries):return False
            if any(current.get(name) is not value for name, value in entries): return False
        # These are semantic resource limits, never captured host overrides.
        if module is not type_qualifiers and any(vars(module).get(name) is not value for name,value in module._DIRECT_REGION_LIMITS): return False
    D = table._DIRECT_ITERATION_DICT
    def raw(value):
        # Destruction of a perfectly canonical old value can still invoke an
        # externally installed weakref callback. Do not admit such lifetimes.
        for ref in values._DIRECT_REGION_GETWEAKREFS(value):
            if type(ref) is not values._DIRECT_REGION_WEAKREF_TYPE or ref.__callback__ is not None:raise _UnprovedGraph()
        fields=D.__get__(value,type(value))
        if any(type(key) is not str for key in fields):raise _UnprovedGraph()
        return fields
    def scalar(value):return value is None or type(value) is Decimal
    qualifier_types=dict(type_qualifiers._DIRECT_LIVE_METADATA_BINDINGS)
    def description(value):
        if type(value) is not table.BSLTypeDescription:return False
        fields=raw(value)
        if fields.keys()!={'types','number_qualifiers','string_qualifiers','date_qualifiers','binary_data_qualifiers'}:return False
        if type(fields['types']) is not tuple or fields['types']:return False
        # The graph may belong to a previous binding being overwritten. Prove
        # its entire default descriptor payload has no hidden host finalizers.
        for name,kind in type_descriptions._QUALIFIERS:
            qualifier=fields[name]
            if type(qualifier) is not kind:return False
            q=raw(qualifier)
            if name=='number_qualifiers':
                if q.keys()!={'digits','fraction_digits','allowed_sign'} or type(q['digits']) is not Decimal or type(q['fraction_digits']) is not Decimal or type(q['allowed_sign']) is not qualifier_types['BSLAllowedSign']:return False
            elif name=='date_qualifiers':
                if q.keys()!={'date_fractions'} or type(q['date_fractions']) is not qualifier_types['BSLDateFractions']:return False
            elif q.keys()!={'length','allowed_length'} or type(q['length']) is not Decimal or type(q['allowed_length']) is not qualifier_types['BSLAllowedLength']:return False
        return True
    entries=[(state.get(name),kind) for name,kind in specification.items()]
    # Overwriting a previous host value can synchronously run __del__. That is
    # a callback even when the source expression itself is purely numeric.
    for name in writes:
        value=state.get(name)
        if value is None or any(type(value) is kind for kind in (Decimal,str,bool,int,float)):continue
        if type(value) is table.BSLValueTableRow:
            owner=raw(value).get('table')
            entries.extend(((owner,'table'),(value,'row')))
        elif type(value) is values.BSLValueListItem:
            d=raw(value);ref=d.get('_owner_ref')
            if type(ref) is not values._DIRECT_REGION_WEAKREF_TYPE or ref.__callback__ is not None:return False
            owner=ref()
            if owner is None:return False
            entries.extend(((owner,'list'),(value,'item')))
        else:return False
    tables=set(); lists=set()
    for value,kind in entries:
        if kind=='number':
            if not scalar(value):return False
        elif kind=='table':
            if type(value) is not table.BSLValueTable:return False
            data=raw(value)
            if data.keys()!={'_bounded_slice_read','rows','columns','indexes'}:return False
            if data.get('_bounded_slice_read') is not False:return False
            rows=data.get('rows'); columns=data.get('columns'); indexes=data.get('indexes')
            if type(rows) is not list or type(columns) is not table.BSLValueTableColumnCollection or type(indexes) is not table.BSLCollectionIndexes:return False
            cd=raw(columns); ix=raw(indexes)
            if cd.keys()!={'table','items'} or ix.keys()!={'table','items'}:return False
            if cd.get('table') is not value or ix.get('table') is not value:return False
            cols=cd.get('items')
            if type(cols) is not list or type(ix.get('items')) is not list or ix['items']:return False
            if len(rows)>table._MAX_ROWS or len(cols)>table._MAX_COLUMNS or len(rows)*len(cols)>table._MAX_CELLS:return False
            for col in cols:
                if type(col) is not table.BSLValueTableColumn:return False
                c=raw(col)
                if c.keys()!={'table','name','value_type','title','width','_deleted'}:return False
                if c.get('table') is not value or c.get('_deleted') is not False or type(c.get('name')) is not str:return False
                if type(c.get('title')) is not str or type(c.get('width')) is not Decimal or not description(c.get('value_type')):return False
            for row in rows:
                if type(row) is not table.BSLValueTableRow:return False
                r=raw(row); cells=r.get('cells')
                if r.keys()!={'table','cells','_deleted'}:return False
                if r.get('table') is not value or r.get('_deleted') is not False or type(cells) is not dict or len(cells)!=len(cols):return False
                if any(not any(key is c for c in cols) or not scalar(v) for key,v in cells.items()):return False
            tables.add(id(value))
        elif kind=='list':
            if type(value) is not values.BSLValueList:return False
            data=raw(value); items=data.get('items'); ids=data.get('_by_id')
            if data.keys()!={'items','_by_id','_next_id','_revision','value_type','_text_cache'}:return False
            if not description(data['value_type']):return False
            cache=data['_text_cache']
            if cache is not None and (type(cache) is not tuple or len(cache)!=2 or type(cache[0]) is not int or type(cache[1]) is not str):return False
            if type(items) is not list or type(ids) is not dict or len(ids)!=len(items) or len(items)>values._MAX_ITEMS:return False
            if type(data.get('_next_id')) is not int or data['_next_id']!=len(items) or type(data.get('_revision')) is not int or data['_revision']!=len(items):return False
            if any(type(k) is not int for k in ids):return False
            for index,item in enumerate(items):
                if type(item) is not values.BSLValueListItem:return False
                d=raw(item); ref=d.get('_owner_ref')
                if d.keys()!={'_owner_ref','_id','_detached','_decoded_standalone','value','presentation','check'}:return False
                if type(ref) is not values._DIRECT_REGION_WEAKREF_TYPE or ref.__callback__ is not None or ref() is not value:return False
                if type(d.get('_id')) is not int or d['_id']!=index or ids.get(index) is not item:return False
                if d.get('_detached') is not False or d.get('_decoded_standalone') is not False or d.get('check') is not False or type(d.get('presentation')) is not str or d['presentation']!='' or not scalar(d.get('value')):return False
            lists.add(id(value))
        elif kind not in ('row','item'):return False
    for value,kind in entries:
        if kind=='row':
            if type(value) is not table.BSLValueTableRow:return False
            owner=raw(value).get('table')
            if id(owner) not in tables or not any(row is value for row in raw(owner)['rows']):return False
        if kind=='item':
            if type(value) is not values.BSLValueListItem:return False
            ref=raw(value).get('_owner_ref')
            if type(ref) is not values._DIRECT_REGION_WEAKREF_TYPE or id(ref()) not in lists or not any(item is value for item in raw(ref())['items']):return False
    return True


def helpers():
    from . import value_tables as t, value_lists as v
    # Pinned exact builtin weak-reference construction cannot execute a host
    # replacement of weakref.ref. All public rows/items remain canonical.
    ref=v._DIRECT_REGION_WEAKREF
    table_type,row_type,column_type,columns_type=t._DIRECT_ITERATION_TYPES[0],t._DIRECT_ITERATION_TYPES[2],t._DIRECT_ITERATION_TYPES[3],t._DIRECT_ITERATION_TYPES[1]
    list_type,item_type=v._DIRECT_REGION_TYPES
    table_limits=dict(t._DIRECT_REGION_LIMITS); list_limits=dict(v._DIRECT_REGION_LIMITS)
    def table_add(value):
        count=len(value.rows)+1; columns=value.columns.items
        if count>table_limits['_MAX_ROWS'] or len(columns)>table_limits['_MAX_COLUMNS'] or count*len(columns)>table_limits['_MAX_CELLS']:
            raise ValueError('ТаблицаЗначений: превышен предел ресурсов Yadinassi')
        row=object.__new__(row_type)
        row.table=value;row.cells={col:None for col in columns};row._deleted=False
        value.rows.append(row)
        return row
    def table_get(value,index):
        if type(index) is not Decimal or not index.is_finite():raise TypeError('ТаблицаЗначений: ожидается конечное число')
        if index.copy_abs()>2**32:raise ValueError('ТаблицаЗначений: число вне поддерживаемых границ')
        position=int(index)
        if not 0<=position<len(value.rows):raise IndexError('Индекс таблицы вне границ')
        return value.rows[position]
    def column(row,name):
        # Schema and row liveness were proved at entry and cannot change inside
        # the island: no Delete, Columns.Add, aliases escaping, or callbacks.
        key=name.casefold()
        for col in row.table.columns.items:
            if col.name.casefold()==key:return col
        raise ValueError('Колонка не найдена: '+name)
    def row_get(row,name):return row.cells[column(row,name)]
    def row_set(row,name,value):row.cells[column(row,name)]=value
    def list_add(value,number):
        count=len(value.items)
        if count+1>list_limits['_MAX_ITEMS']:raise ValueError('СписокЗначений: превышен предел ресурсов Yadinassi')
        if value._next_id+1>list_limits['_MAX_ID']:raise ValueError('СписокЗначений: превышен предел идентификаторов Yadinassi')
        if type(number) is Decimal:
            if not number.is_finite():raise ValueError('СписокЗначений: ожидается конечное число')
            if len(number.as_tuple().digits)>list_limits['_MAX_NUMBER_DIGITS']:raise ValueError('СписокЗначений: превышен предел ресурсов Yadinassi')
        item=object.__new__(item_type)
        item._owner_ref=ref(value);item._id=value._next_id;item._detached=False;item._decoded_standalone=False
        item.value=number;item.presentation='';item.check=False
        value.items.append(item);value._by_id[value._next_id]=item;value._next_id+=1;value._revision+=1
        return item
    def list_get(value,index):
        if type(index) is not Decimal:raise TypeError('СписокЗначений: ожидается число')
        if not index.is_finite():raise ValueError('СписокЗначений: ожидается конечное число')
        if len(index.as_tuple().digits)>list_limits['_MAX_NUMBER_DIGITS'] or index.copy_abs()>2**32:raise ValueError('СписокЗначений: превышен предел ресурсов Yadinassi')
        if index<0 and index!=index.to_integral_value():raise ValueError('СписокЗначений: отрицательный дробный числовой аргумент пока не поддерживается в Yadinassi')
        position=int(index)
        if not 0<=position<len(value.items):raise IndexError('Индекс списка значений вне границ')
        return value.items[position]
    def boundary(function):
        def invoke(context,*arguments):
            context._check()
            try:return function(*arguments)
            finally:context._check()
        return invoke
    return {name:boundary(function) for name,function in dict(
        table_add=table_add,table_get=table_get,row_get=row_get,row_set=row_set,
        list_add=list_add,list_get=list_get,item_get=lambda item:item.value).items()}
