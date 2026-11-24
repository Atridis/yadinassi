"""Exact detached ValueTree protocols, with live provenance and no DB authority."""
from yadinassi.collections import value_trees as model
from yadinassi.execution.codegen.experimental_naked_boundaries import BoundaryViolation
from decimal import Decimal
from operator import is_
from weakref import ReferenceType
from yadinassi.types.values import BSLObject, HostFunction

CONSTRUCTOR_NAMES=('valuetree','деревозначений','valuetreerow','строкадеревазначений',
                   'valuetreecolumn','колонкадеревазначений','valuetreerowcollection','коллекциястрокдеревазначений')

_CLASSES=model._DIRECT_TREE_CLASSES
_TREE,_ROWS,_ROW,_COLUMNS,_COLUMN=_CLASSES
_ABI=model._DIRECT_TREE_CLASS_ABI+model._DIRECT_TREE_ENUM_ABI
_BASE_ABI=model._DIRECT_TREE_BASE_ABI+model._DIRECT_TREE_SCHEMA_ABI
_BINDINGS=model._DIRECT_TREE_BINDINGS
_ORIGINS=model._DIRECT_TREE_ORIGINS
_SCALAR_ABI=model._DIRECT_TREE_SCALAR_ABI
_ARRAY_ABI=model._DIRECT_TREE_ARRAY_ABI
_ENUM_MEMBERS=model._DIRECT_TREE_ENUM_MEMBERS
_ENUM_MEMBER_IDS=frozenset(id(member) for member,_ in _ENUM_MEMBERS)
_LIMITS=model._DIRECT_TREE_LIMITS
_SCHEMA_BINDINGS=model._DIRECT_TREE_SCHEMA_BINDINGS+model._DIRECT_TREE_DEPENDENCY_BINDINGS
# The model owns the definition-time snapshots. Prepare their parallel
# vectors once; each check still reads the actual live class namespace.
def _identity_vectors(fields):
    return tuple(zip(*fields)) if fields else ((), ())


def _abi_vectors(classes):
    return tuple((cls,mro,*_identity_vectors(fields)) for cls,mro,fields in classes)


_CLASS_VECTORS=_abi_vectors(_ABI)
_ARRAY_VECTORS=_abi_vectors(_ARRAY_ABI)
_BASE_VECTORS=_abi_vectors(_BASE_ABI)
_SCALAR_VECTORS=tuple((cls,mro,*_identity_vectors(fields),slotnames)
                      for cls,mro,fields,slotnames in _SCALAR_ABI)
_ENUM_VECTORS=tuple((member,*_identity_vectors(fields)) for member,fields in _ENUM_MEMBERS)
_ABSENT=object()


def _matching_bindings(current,names,expected):
    # map/all avoid a Python generator frame per entry. No object equality,
    # snapshot copies or caching a successful admission.
    return all(map(is_,map(current.get,names),expected))


_QUALIFIERS=model._direct_qualifiers
_ROW_COLLECTION=object()
_ROW_READS={alias: spec for aliases,spec in (
    (('find','найти'),('_find',3,True)),
    (('findrows','найтистроки'),('_find_rows',2,True)),
    (('total','итог'),('_total',2,False)),
    (('unloadcolumn','выгрузитьколонку'),('_unload_column',1,True)),
) for alias in aliases}
_FIELDS=(frozenset(('_all_rows','columns','rows')),
         frozenset(('tree','parent','items','_columns_clear_forward')),
         frozenset(('collection','tree','parent','depth','cells','rows','_deleted')),
         frozenset(('table','items')),
         frozenset(('table','name','value_type','title','width','_deleted','default','_columns_clear_reset')))


def owns(value):return any(type(value) is cls for cls in _CLASSES)


def hooks():
    for name,value in _BINDINGS:
        if vars(model).get(name) is not value:raise BoundaryViolation('ValueTree model binding changed')
    try:model._registry_hooks()
    except ValueError as error:raise BoundaryViolation(str(error)) from None
    for cls,mro,names,expected in _ARRAY_VECTORS:
        current=vars(cls)
        if cls.__mro__ is not mro or len(current)!=len(names) or not _matching_bindings(current,names,expected):
            raise BoundaryViolation('ValueTree output array hooks changed')
        slots=current.get('__slotnames__')
        if type(slots) is not list or slots:raise BoundaryViolation('ValueTree output array copy cache changed')
    for namespace,name,value in _SCHEMA_BINDINGS:
        if namespace.get(name) is not value:raise BoundaryViolation('ValueTree schema binding changed')
    for cls,mro,names,expected in _CLASS_VECTORS:
        current=vars(cls)
        if cls.__mro__ is not mro or len(current)!=len(names) or not _matching_bindings(current,names,expected):
            raise BoundaryViolation('ValueTree class hooks changed')
        slots=current.get('__slotnames__')
        if slots is not None and (type(slots) is not list or slots):raise BoundaryViolation('ValueTree copy metadata changed')
    for member,names,expected in _ENUM_VECTORS:
        current=vars(member)
        # Inspect keys before any lookup: foreign keys may collide with the
        # canonical strings and supply an equality callback.
        if type(current) is not dict or len(current)!=len(names) or any(type(key) is not str for key in current):
            raise BoundaryViolation('ValueTree enum member fields changed')
        if not _matching_bindings(current,names,expected):
            raise BoundaryViolation('ValueTree enum member state changed')
    for cls,mro,names,expected in _BASE_VECTORS:
        current=vars(cls);slots=current.get('__slotnames__',_ABSENT)
        if (cls.__mro__ is not mro or len(current)-(slots is not _ABSENT)!=len(names)
                or not _matching_bindings(current,names,expected)):
            raise BoundaryViolation('ValueTree base hooks changed')
        if slots is not _ABSENT and (type(slots) is not list or slots):
            raise BoundaryViolation('ValueTree base copy metadata changed')
    for cls,mro,names,expected,slotnames in _SCALAR_VECTORS:
        current=vars(cls);slots=current.get('__slotnames__',_ABSENT)
        if (cls.__mro__ is not mro or len(current)-(slots is not _ABSENT)!=len(names)
                or not _matching_bindings(current,names,expected)):
            raise BoundaryViolation('ValueTree scalar hooks changed')
        if slots is not _ABSENT and slots is not None and (type(slots) is not list or any(type(name) is not str for name in slots) or tuple(slots)!=slotnames):
            raise BoundaryViolation('ValueTree scalar copy cache changed')
    for name,maximum in _LIMITS:
        value=vars(model).get(name)
        if type(value) is not int or not 0<value<=maximum:raise BoundaryViolation('ValueTree quota changed')


def fields(value):
    kind=type(value)
    for cls,allowed in zip(_CLASSES,_FIELDS):
        if kind is cls:
            data=vars(value)
            if (type(data) is not dict or any(type(k) is not str or k not in allowed for k in data)
                    or not allowed.difference(('_columns_clear_reset',)).issubset(data)):
                raise BoundaryViolation('ValueTree instance hooks changed')
            return data
    raise BoundaryViolation('foreign ValueTree receiver')


def origin(value,owners):
    saved=_ORIGINS.get(value)
    if saved is None or len(saved)!=len(owners) or any(
            (owner is not None if old is None else old() is not owner) for old,owner in zip(saved,owners)):
        raise BoundaryViolation('ValueTree provenance changed')


def local(value):
    data=fields(value);kind=type(value)
    if kind is _TREE:
        root=value;origin(value,(data['columns'],data['rows'],data['_all_rows']))
    elif kind is _ROW:
        root=data['tree'];origin(value,(root,data['collection'],data['parent'],data['rows']))
    elif kind is _ROWS:
        root=data['tree'];origin(value,(root,data['parent']))
    else:
        root=data['table'];origin(value,(root,))
        if kind is _COLUMN and (type(data['_deleted']) is not bool or
                ('_columns_clear_reset' in data and type(data['_columns_clear_reset']) is not bool)):
            raise BoundaryViolation('ValueTree column state changed')
    if type(root) is not _TREE:raise BoundaryViolation('foreign ValueTree root')
    return root


def check(boundary,value,*,graph=False):
    if getattr(boundary,'_verify_context',True) is not False:boundary._check()
    hooks()
    return admitted_receiver(boundary,value,graph=graph)


def admitted_receiver(boundary,value,*,graph=False):
    if not getattr(boundary,'_value_tree_active',False):raise BoundaryViolation('ValueTree activation expired')
    root=local(value);local(root)
    if not model._registry_owned(root._all_rows,root) or type(root.columns) is not _COLUMNS or type(root.rows) is not _ROWS:
        raise BoundaryViolation('ValueTree root storage changed')
    local(root.columns);local(root.rows)
    if type(root.columns.items) is not list or type(root.rows.items) is not list:
        raise BoundaryViolation('ValueTree root collections changed')
    _TREE._budget(len(root._all_rows),len(root.columns.items))
    # Follow only this receiver's birth links, never scan unrelated rows on a
    # Count/read/Add checkpoint. Methods traversing the graph opt in below.
    node=value;seen=set()
    while type(node) in (_ROW,_ROWS):
        if id(node) in seen or len(seen)>2*model._MAX_DEPTH+3:raise BoundaryViolation('ValueTree ancestor cycle')
        seen.add(id(node));local(node)
        if type(node) is _ROW:
            if type(node.cells) is not dict or type(node._deleted) is not bool or type(node.rows) is not _ROWS or type(node.depth) is not int or not 0<=node.depth<=model._MAX_DEPTH:
                raise BoundaryViolation('ValueTree row storage changed')
            if node.parent is None:
                if node.depth!=0:raise BoundaryViolation('ValueTree depth changed')
            elif type(node.parent) is not _ROW or type(node.parent.depth) is not int or node.depth!=node.parent.depth+1:
                raise BoundaryViolation('ValueTree depth changed')
            cell_keys(node,root)
            node=node.collection
        else:
            if type(node.items) is not list:raise BoundaryViolation('ValueTree row collection storage changed')
            node=node.parent
    if node is not None and node is not value:raise BoundaryViolation('ValueTree ancestor changed')
    if graph:
        rows=_TREE._clear_graph(root)
        for column in root.columns.items:local(column)
        for row in rows:local(row);local(row.rows);cell_keys(row,root)
    return root


# Structural reads consume only live birth links and an exact list length.
# The full model seal contains payload/enum/default/output hooks that this
# operation cannot reach. Keep the low-level provenance inputs pinned even
# when the model is first supplied by an embedding.
_INSTANCE_DICT=vars(BSLObject)['__dict__']
_STRUCTURAL_REGISTRY_TYPE=dict(model._ROW_REGISTRY_BINDINGS)['_RowRegistry']
_STRUCTURAL_REGISTRY=dict(model._ROW_REGISTRY_BINDINGS)['_ROW_REGISTRY_STATE']
_STRUCTURAL_MRO={cls:mro for cls,mro,_ in model._DIRECT_TREE_CLASS_ABI}
_STRUCTURAL_FIELDS=dict(zip(_CLASSES,_FIELDS))
_STRUCTURAL_LIMITS=tuple((name,maxval) for name,maxval in _LIMITS
                         if name in ('_MAX_ROWS','_MAX_COLUMNS','_MAX_CELLS','_MAX_DEPTH'))
_STRUCTURAL_METHODS={cls:tuple((name,method) for name,method in methods
    if name in ('get_member','get_method','count','_clear_target','_live','_budget'))
    for cls,_,methods in model._DIRECT_TREE_CLASS_ABI}
_READ_METHODS=model._DIRECT_TREE_READ_METHODS
_POSITION,_POSITION_CODE,_POSITION_DEFAULTS=model._DIRECT_TREE_READ_POSITION
_NAME_LIMIT_MODULE,_MAX_NAME_TEXT=model._DIRECT_TREE_NAME_LIMIT
_READ_UNAVAILABLE=object()
_GET_NAMES=frozenset(('get','получить'))
_COLUMN_FIELDS={'name':'name','имя':'name','title':'title','заголовок':'title',
                'width':'width','ширина':'width'}
_DELETED_ROW='Строка дерева удалена; доступ к отсоединенным строкам не поддерживается'


def _structural_fields(value,kind):
    # The weak origin lookup hashes canonical identities. Inspect the slots
    # passively before hashing so an embedding cannot supply hash/eq hooks.
    mro=_STRUCTURAL_MRO[kind]
    expected=_STRUCTURAL_FIELDS[kind]
    for cls in mro[:-1]:
        current=vars(cls)
        if ('__hash__' in current or '__eq__' in current or '__getattr__' in current
                or '__getattribute__' in current or not expected.isdisjoint(current.keys())):
            raise BoundaryViolation('ValueTree structural identity hooks changed')
    if kind.__mro__ is not mro:
        raise BoundaryViolation('ValueTree structural identity hooks changed')
    data=_INSTANCE_DICT.__get__(value,kind)
    if (type(data) is not dict or any(type(key) is not str or key not in expected for key in data)
            or len(data)!=len(expected) and not (kind is _COLUMN and len(data)==len(expected)-1
                                                and '_columns_clear_reset' not in data)):
        raise BoundaryViolation('ValueTree structural state changed')
    return data


def _structural_state(boundary,value,kind):
    if not boundary._value_tree_active:
        raise BoundaryViolation('ValueTree activation expired')
    if (model._ROW_REGISTRY_STATE is not _STRUCTURAL_REGISTRY or model._RowRegistry is not _STRUCTURAL_REGISTRY_TYPE
            or model._DIRECT_TREE_ORIGINS is not _ORIGINS):
        raise BoundaryViolation('ValueTree structural provenance changed')
    limits={}
    for name,maximum in _STRUCTURAL_LIMITS:
        current=vars(model).get(name)
        if type(current) is not int or not 0<current<=maximum:
            raise BoundaryViolation('ValueTree quota changed')
        limits[name]=current
    root=value if kind is _TREE else _structural_fields(value,kind).get('table' if kind in (_COLUMNS,_COLUMN) else 'tree')
    if type(root) is not _TREE:
        raise BoundaryViolation('foreign ValueTree root')
    root_data=_structural_fields(root,_TREE)
    root_rows=root_data.get('rows');columns=root_data.get('columns');registry=root_data.get('_all_rows')
    origin(root,(columns,root_rows,registry))
    state=_STRUCTURAL_REGISTRY.get(id(registry))
    if (type(registry) is not _STRUCTURAL_REGISTRY_TYPE or type(state) is not list or len(state)!=4
            or type(state[0]) is not ReferenceType or state[0]() is not registry
            or type(state[1]) is not ReferenceType or state[1]() is not root
            or type(state[2]) is not dict or state[3] is not False
            or type(root_rows) is not _ROWS or type(columns) is not _COLUMNS):
        raise BoundaryViolation('ValueTree root storage changed')
    root_rows_data=_structural_fields(root_rows,_ROWS);column_data=_structural_fields(columns,_COLUMNS)
    if (root_rows_data.get('tree') is not root or root_rows_data.get('parent') is not None
            or column_data.get('table') is not root):
        raise BoundaryViolation('ValueTree root collections changed')
    origin(root_rows,(root,None));origin(columns,(root,))
    column_items=column_data.get('items');root_items=root_rows_data.get('items')
    if type(column_items) is not list or type(root_items) is not list:
        raise BoundaryViolation('ValueTree root collections changed')
    rows=len(state[2]);width=len(column_items)
    if rows>limits['_MAX_ROWS'] or width>limits['_MAX_COLUMNS'] or rows*width>limits['_MAX_CELLS']:
        raise ValueError('ДеревоЗначений: превышен предел ресурсов Yadinassi')

    return root,root_rows,columns,state[2],root_rows_data,column_data,limits


def structural_count(boundary,value,projection,spelling):
    kind=type(value)
    # Only the effective receiver/projection semantics may be consulted.
    # Stable private operations are never invoked from this fast lane.
    checked=(kind,) if projection is None else (kind,_ROWS if projection=='rows' else _COLUMNS)
    for cls in checked:
        current=vars(cls)
        if any(current.get(name) is not method for name,method in _STRUCTURAL_METHODS[cls]):
            raise BoundaryViolation('ValueTree structural methods changed')
    root,root_rows,columns,_,root_rows_data,column_data,limits=_structural_state(boundary,value,kind)
    root_items=root_rows_data['items']
    width=len(column_data['items'])

    if (kind is _TREE and projection=='columns') or value is columns:return Decimal(width)
    if (kind is _TREE and projection=='rows') or value is root_rows:
        if root_rows_data['_columns_clear_forward'] is not False:
            return boundary._tree_method(root_rows,spelling)()
        return Decimal(len(root_items))
    if kind is _COLUMNS:
        extra=_structural_fields(value,_COLUMNS)
        origin(value,(root,))
        items=extra.get('items')
        if type(items) is not list:raise BoundaryViolation('ValueTree column collection storage changed')
        return Decimal(len(items))

    if kind is _ROW:
        data=_structural_fields(value,_ROW)
        collection=data.get('rows')
        if type(collection) is not _ROWS:
            raise BoundaryViolation('foreign ValueTree child collection')
        projected_parent=value
    else:collection=value;projected_parent=None
    current=collection;direct_parent=None;items=None;depth=0
    first_deleted=False;forward=False
    while current is not root_rows:
        if type(current) is not _ROWS or depth>limits['_MAX_DEPTH']:
            raise BoundaryViolation('ValueTree ancestor changed')
        current_data=_structural_fields(current,_ROWS)
        parent=current_data.get('parent')
        if current_data.get('tree') is not root or (parent is not None and type(parent) is not _ROW):
            raise BoundaryViolation('foreign ValueTree child collection')
        origin(current,(root,parent))
        if parent is None:
            # The public constructor is not exposed to BSL. Keep the prior
            # disposition of other model-born, parentless host wrappers.
            return boundary._tree_method(collection,spelling)()
        data=_structural_fields(parent,_ROW);up=data.get('collection')
        if data.get('tree') is not root:
            raise BoundaryViolation('ValueTree ancestor changed')
        deleted=data.get('_deleted');parent_depth=data.get('depth')
        if type(deleted) is not bool or type(parent_depth) is not int or not 0<=parent_depth<=limits['_MAX_DEPTH'] or type(up) is not _ROWS:
            raise BoundaryViolation('ValueTree row storage changed')
        origin(parent,(root,up,data.get('parent'),data.get('rows')))
        current_items=current_data.get('items')
        if type(current_items) is not list:
            raise BoundaryViolation('ValueTree row collection storage changed')
        if items is None:
            if projected_parent is not None and (parent is not projected_parent or data.get('rows') is not current):
                raise BoundaryViolation('foreign ValueTree child collection')
            first_deleted=deleted;forward=current_data.get('_columns_clear_forward') is not False
            items=current_items
        elif direct_parent != parent_depth+1:
            raise BoundaryViolation('ValueTree depth changed')
        direct_parent=parent_depth;current=up;depth+=1
    if direct_parent is not None and direct_parent!=0:
        raise BoundaryViolation('ValueTree depth changed')
    # Row.Rows itself is invalid after deletion even when a previously
    # retained Rows wrapper can redirect Count to a live root.
    if first_deleted and projected_parent is not None:raise ValueError(_DELETED_ROW)
    if forward:return boundary._tree_method(collection,spelling)()
    if first_deleted:raise ValueError(_DELETED_ROW)
    return Decimal(len(root_items if items is None else items))


def _ordinary_read(boundary):
    return (getattr(boundary,'_known_method_local',False)
            and not boundary._verify_context and boundary.policy is None)


def _read_methods(kind,*names):
    current=vars(kind);methods=_READ_METHODS[kind]
    slots=current.get('__slotnames__')
    if type(slots) is not list or slots:
        raise BoundaryViolation('ValueTree structural copy metadata changed')
    for name in names:
        fn,code=methods[name]
        if current.get(name) is not fn or fn.__code__ is not code:
            raise BoundaryViolation('ValueTree structural methods changed')


def _read_position(index,size):
    namespace=vars(model)
    if (namespace.get('_position') is not _POSITION or _POSITION.__code__ is not _POSITION_CODE
            or _POSITION.__defaults__ is not _POSITION_DEFAULTS or namespace.get('Decimal') is not Decimal
            or any(name in namespace for name in ('type','int','IndexError','TypeError'))):
        raise BoundaryViolation('ValueTree positional conversion changed')
    return _POSITION(index,size)


def _row_state(state,row):
    root,_,_,entries,_,_,limits=state
    if type(row) is not _ROW:raise BoundaryViolation('foreign ValueTree result')
    data=_structural_fields(row,_ROW)
    collection=data['collection'];parent=data['parent'];children=data['rows'];depth=data['depth']
    if (data['tree'] is not root or type(collection) is not _ROWS or type(children) is not _ROWS
            or type(depth) is not int or not 0<=depth<=limits['_MAX_DEPTH']
            or type(data['_deleted']) is not bool or type(data['cells']) is not dict):
        raise BoundaryViolation('ValueTree row storage changed')
    origin(row,(root,collection,parent,children))
    if data['_deleted'] is False:
        entry=entries.get(id(row))
        if type(entry) is not ReferenceType or entry() is not row:
            raise BoundaryViolation('ValueTree row is not registered')
    return data


def _rows_state(state,collection,*,binding=False):
    root,root_rows,_,_,root_data,_,limits=state
    if type(collection) is not _ROWS:raise BoundaryViolation('foreign ValueTree row collection')
    current=collection;child_data=None;child_depth=None;depth=0
    while current is not root_rows:
        if type(current) is not _ROWS or depth>limits['_MAX_DEPTH']:
            raise BoundaryViolation('ValueTree ancestor changed')
        data=_structural_fields(current,_ROWS);parent=data['parent']
        if data['tree'] is not root or type(data['items']) is not list:
            raise BoundaryViolation('ValueTree row collection storage changed')
        origin(current,(root,parent))
        if parent is None:return _READ_UNAVAILABLE
        parent_data=_row_state(state,parent)
        if (parent_data['rows'] is not current or child_depth is not None
                and child_depth!=parent_data['depth']+1):
            raise BoundaryViolation('ValueTree ancestor changed')
        child_depth=parent_data['depth']
        if child_data is None:
            if data['_columns_clear_forward'] is not False:return _READ_UNAVAILABLE
            if parent_data['_deleted'] and not binding:raise ValueError(_DELETED_ROW)
            child_data=data
        current=parent_data['collection'];depth+=1
    if child_depth is not None and child_depth!=0:
        raise BoundaryViolation('ValueTree depth changed')
    if child_data is not None:return child_data
    if root_data['_columns_clear_forward'] is not False:return _READ_UNAVAILABLE
    return root_data


def _column_state(root,column):
    if type(column) is not _COLUMN:raise BoundaryViolation('foreign ValueTree result')
    data=_structural_fields(column,_COLUMN)
    if (data['table'] is not root or type(data['_deleted']) is not bool
            or ('_columns_clear_reset' in data and type(data['_columns_clear_reset']) is not bool)):
        raise BoundaryViolation('ValueTree column storage changed')
    origin(column,(root,))
    return data


def _column_items(root,collection):
    data=_structural_fields(collection,_COLUMNS)
    origin(collection,(root,))
    items=data['items']
    if type(items) is not list:raise BoundaryViolation('ValueTree column collection storage changed')
    return items


def _named_column(root,columns,name):
    limit=vars(_NAME_LIMIT_MODULE).get('_MAX_TEXT')
    if type(limit) is not int or not 0<limit<=_MAX_NAME_TEXT:
        raise BoundaryViolation('ValueTree name quota changed')
    if len(name)>limit:raise ValueError('ТаблицаЗначений: превышен предел ресурсов Yadinassi')
    key=name.casefold()
    for column in columns:
        data=_column_state(root,column);spelling=data['name']
        if type(spelling) is not str:raise BoundaryViolation('ValueTree column name changed')
        if spelling.casefold()==key:return column
    raise ValueError(f'Колонка не найдена: {name}')


def _row_cells(state,data):
    # Seal all keys before lookup, including an exact canonical column's
    # identity hash. Only the reached row's dictionary is inspected.
    cells=data['cells']
    if len(cells)>state[-1]['_MAX_COLUMNS']:raise BoundaryViolation('ValueTree cell budget changed')
    for column in cells:_column_state(state[0],column)
    return cells


def _read_row_item(state,collection,data,item):
    raw=_row_state(state,item);parent=data['parent']
    if (raw['collection'] is not collection or raw['parent'] is not parent or raw['_deleted']
            or raw['depth']!=(0 if parent is None else _row_state(state,parent)['depth']+1)):
        raise BoundaryViolation('foreign ValueTree row result')
    _row_cells(state,raw)
    return item


def _read_column_item(root,item):
    if _column_state(root,item)['_deleted']:raise BoundaryViolation('deleted ValueTree column result')
    return item


def _structural_member(boundary,value,kind,key,name):
    boundary._check_effect()
    _read_methods(kind,'get_member')
    state=_structural_state(boundary,value,kind);root,root_rows,columns,_,_,column_data,_=state
    if kind is _TREE:return root_rows if key in ('rows','строки') else columns
    if kind is _COLUMN:
        data=_column_state(root,value);field=_COLUMN_FIELDS[key]
        if data['_deleted']:
            if data.get('_columns_clear_reset') is True:return Decimal(0) if field=='width' else ''
            raise ValueError('Колонка дерева удалена')
        # Non-text fields still follow their ordinary exact representations.
        result=data[field]
        if type(result) is not (Decimal if field=='width' else str):
            raise BoundaryViolation('ValueTree column metadata changed')
        return result
    _read_methods(_ROW,'_live','get_index')
    data=_row_state(state,value)
    parent_collection=_rows_state(state,data['collection'])
    if parent_collection is _READ_UNAVAILABLE:return _READ_UNAVAILABLE
    cells=_row_cells(state,data)
    if data['_deleted']:raise ValueError(_DELETED_ROW)
    if key in ('rows','строки'):
        child=data['rows']
        child_data=_structural_fields(child,_ROWS)
        if child_data['tree'] is not root or child_data['parent'] is not value or type(child_data['items']) is not list:
            raise BoundaryViolation('foreign ValueTree child collection')
        origin(child,(root,value))
        return child
    if key in ('parent','родитель'):return data['parent']
    _read_methods(_COLUMNS,'get_index','find')
    return cells[_named_column(root,column_data['items'],name)]


def _positional_read(boundary,value,kind,key,name):
    boundary._check_effect()
    subscript=key=='__getitem__'
    selected=_READ_METHODS[kind]['get_index' if subscript else 'get'][0]
    _read_methods(kind,*('get_index','get') if subscript else ('get_method','get'))
    state=_structural_state(boundary,value,kind);root=state[0]
    if kind is _ROWS:
        _read_methods(_ROWS,'_clear_target','_live')
        # A deleted parent is a model error at invocation, after arguments.
        if _rows_state(state,value,binding=True) is _READ_UNAVAILABLE:return None
    else:
        _column_items(root,value)
    epoch=boundary._value_tree_epoch
    def invoke(*args):
        boundary._check_effect()
        if epoch is not boundary._value_tree_epoch or not _ordinary_read(boundary):
            raise BoundaryViolation('ValueTree structural call activation changed')
        _read_methods(kind,*('get_index','get') if subscript else ('get_method','get'))
        live=_structural_state(boundary,value,kind)
        if live[0] is not root:raise BoundaryViolation('ValueTree owner changed')
        if len(args)!=1 or owns(args[0]):
            # Preserve ordinary callable arity and validation of tree-valued
            # improper indices on their existing checked dispatch.
            return boundary._tree_method(value,name,_canonical=selected)(*args)
        index=args[0]
        if kind is _ROWS:
            _read_methods(_ROWS,'_clear_target','_live')
            data=_rows_state(live,value)
            if data is _READ_UNAVAILABLE:
                # A legal column clear can change forwarding during argument
                # evaluation. Keep the already captured receiver and actuals.
                return boundary._tree_method(value,name,_canonical=selected)(*args)
            items=data['items']
            return _read_row_item(live,value,data,items[_read_position(index,len(items))])
        items=_column_items(root,value)
        if subscript and type(index) is str:
            _read_methods(_COLUMNS,'find')
            return _named_column(root,items,index)
        return _read_column_item(root,items[_read_position(index,len(items))])
    return invoke


def _structural_iter(boundary,value,kind):
    boundary._check_effect()
    names=('__iter__','_live') if kind is _ROWS else ('__iter__',)
    selected=_READ_METHODS[kind]['__iter__'][0]
    _read_methods(kind,*names)
    state=_structural_state(boundary,value,kind);root=state[0]
    if kind is _ROWS:
        if _rows_state(state,value,binding=True) is _READ_UNAVAILABLE:return None
    else:_column_items(root,value)
    epoch=boundary._value_tree_epoch

    def admit():
        if epoch is not boundary._value_tree_epoch or not _ordinary_read(boundary):
            raise BoundaryViolation('ValueTree iterator activation expired')
        boundary._check_effect()
        _read_methods(kind,*names)
        live=_structural_state(boundary,value,kind)
        if live[0] is not root:raise BoundaryViolation('ValueTree iterator owner changed')
        return live

    def start(*args):
        live=admit()
        if args:return boundary._tree_method(value,'__iter__',_canonical=selected)(*args)
        if kind is _ROWS:
            data=_rows_state(live,value)
            if data is _READ_UNAVAILABLE:
                # The captured receiver may have changed before invocation;
                # its native iterator still uses _live, never Get forwarding.
                return boundary._tree_method(value,'__iter__',_canonical=selected)()
            items=data['items']
        else:items=_column_items(root,value)
        cursor=list.__iter__(items)

        def iterator():
            # Preserve Python's live list position and sticky exhaustion.
            # No admission result is carried across a yield or into BSL.
            for item in cursor:
                current=admit()
                if kind is _ROWS:
                    data=_rows_state(current,value)
                    if data is _READ_UNAVAILABLE:
                        raise BoundaryViolation('ValueTree iterator row collection changed')
                    _read_row_item(current,value,data,item)
                    del data
                else:
                    _column_items(root,value)
                    _read_column_item(root,item)
                del current
                yield item
        return iterator()
    return start


def cell_keys(row,root):
    # Iteration does not hash or compare adversarial keys. Never do a canonical
    # dict lookup until every key has passed the exact identity gate.
    if len(row.cells)>model._MAX_COLUMNS:raise BoundaryViolation('ValueTree cell budget changed')
    for key in row.cells:
        if type(key) is not _COLUMN or local(key) is not root:
            raise BoundaryViolation('ValueTree cell key changed')


def row_read_admission(root, start, *, track_rows=True):
    """A post-arguments seal for exactly the prefix the row reader consumes."""
    entries = model._registry_owned_entries(root._all_rows, root)
    weakref_type = model.ref
    if entries is None:
        raise BoundaryViolation('ValueTree registry changed')
    start_data = fields(start)
    parent = start_data['parent']
    if parent is None:
        attached = start is root.rows
        start_depth = 0
    else:
        data = fields(parent)
        saved = entries.get(id(parent))
        attached = (type(saved) is weakref_type and saved() is parent
                    and data['rows'] is start and data['_deleted'] is False)
        start_depth = data['depth'] + 1
    if not attached:
        raise BoundaryViolation('ValueTree read receiver is not attached')
    columns = root.columns.items
    column_ids = {id(column) for column in columns}
    if len(column_ids) != len(columns) or any(column._deleted is not False for column in columns):
        raise BoundaryViolation('ValueTree read schema changed')
    seen = set() if track_rows else None

    def admit(collection, depth, row=_ROW_COLLECTION):
        if row is _ROW_COLLECTION:
            # Called only when the canonical DFS is about to descend.
            if type(collection) is not _ROWS or local(collection) is not root:
                raise BoundaryViolation('foreign ValueTree read child collection')
            if (collection._columns_clear_forward is not False
                    or type(collection.items) is not list or len(collection.items) > model._MAX_ROWS):
                raise BoundaryViolation('ValueTree read child collection changed')
            return
        if type(row) is not _ROW or local(row) is not root:
            raise BoundaryViolation('foreign ValueTree read row')
        identity = id(row)
        saved = entries.get(identity)
        if (type(saved) is not weakref_type or saved() is not row
                or (seen is not None and identity in seen)
                or row.collection is not collection or row.parent is not collection.parent
                or row._deleted is not False or type(row.depth) is not int
                or row.depth != start_depth + depth or row.depth > model._MAX_DEPTH):
            raise BoundaryViolation('ValueTree read row is not attached')
        cells = row.cells
        if (type(cells) is not dict or len(cells) != len(column_ids)
                or any(type(key) is not _COLUMN or id(key) not in column_ids for key in cells)):
            raise BoundaryViolation('ValueTree read cell keys changed')
        if seen is not None:
            seen.add(identity)

    admit(start, 0)
    return admit


def admit_copy_row(row):
    # Copy itself verifies the complete graph, schema keys and registry before
    # allocating its result. Only add the direct boundary's instance/origin seal.
    if type(row) is not _ROW:
        raise BoundaryViolation('foreign ValueTree copy row')
    local(row)
    children = row.rows
    if type(children) is not _ROWS:
        raise BoundaryViolation('foreign ValueTree copy child collection')
    local(children)
    if children._columns_clear_forward is not False:
        raise BoundaryViolation('detached ValueTree copy child collection')


def description(value):
    if type(value) is not model.BSLTypeDescription:
        raise BoundaryViolation('ValueTree description changed')
    expected={'types','number_qualifiers','string_qualifiers','date_qualifiers','binary_data_qualifiers'}
    if not model._clear_fields(value,expected):raise BoundaryViolation('ValueTree description fields changed')
    q=_QUALIFIERS
    from decimal import Decimal
    specs=(('number_qualifiers',q.BSLNumberQualifiers,{'digits':Decimal,'fraction_digits':Decimal,'allowed_sign':q.BSLAllowedSign}),
           ('string_qualifiers',q.BSLStringQualifiers,{'length':Decimal,'allowed_length':q.BSLAllowedLength}),
           ('binary_data_qualifiers',q.BSLBinaryDataQualifiers,{'length':Decimal,'allowed_length':q.BSLAllowedLength}),
           ('date_qualifiers',q.BSLDateQualifiers,{'date_fractions':q.BSLDateFractions}))
    if type(value.types) is not tuple or len(value.types)>6 or any(type(t) is not model.BSLType or id(t) not in _ENUM_MEMBER_IDS for t in value.types):
        raise BoundaryViolation('ValueTree description types changed')
    for name,cls,shape in specs:
        qualifier=vars(value)[name]
        if type(qualifier) is not cls or not model._clear_fields(qualifier,set(shape)):
            raise BoundaryViolation('ValueTree qualifier fields changed')
        if any(type(vars(qualifier)[key]) is not kind or (kind is not Decimal and id(vars(qualifier)[key]) not in _ENUM_MEMBER_IDS) for key,kind in shape.items()):
            raise BoundaryViolation('ValueTree qualifier value changed')


def columns(root):
    for column in root.columns.items:
        if type(column) is not _COLUMN or local(column) is not root:
            raise BoundaryViolation('ValueTree column provenance changed')
        if type(column.name) is not str or type(column.title) is not str:
            raise BoundaryViolation('ValueTree column name changed')
        description(column.value_type)
    _ROWS._clear_defaults(root.rows)



class ValueTreeBoundary:
    def enter(self):
        self._value_tree_active=True;self._value_tree_epoch=object()
        try:return super().enter()
        except BaseException:
            self._value_tree_active=False;raise
    def leave(self):
        self._value_tree_active=False
        return super().leave()
    def resolve_service(self,name,*args,**kwargs):
        if not name.casefold().startswith('new:') or name[4:].casefold() not in CONSTRUCTOR_NAMES:
            return super().resolve_service(name,*args,**kwargs)
        if getattr(self,'_verify_context',True) is not False:self._check()
        hooks();key=name.split(':',1)[1].casefold()
        if key not in ('valuetree','деревозначений'):raise ValueError('Тип дерева не имеет конструктора: '+key)
        factory=self.vm.types.get(key)
        if type(factory) is not HostFunction or factory.function is not _TREE:
            raise BoundaryViolation('ValueTree constructor requires canonical registration')
        epoch=self._value_tree_epoch
        def construct(*values):
            if getattr(self,'_verify_context',True) is not False:self._check()
            hooks()
            if not self._value_tree_active or self._value_tree_epoch is not epoch:raise BoundaryViolation('ValueTree constructor activation expired')
            if self.vm.types.get(key) is not factory or factory.function is not _TREE:
                raise BoundaryViolation('ValueTree constructor changed during arguments')
            try:return _TREE(*values)
            finally:
                if getattr(self,'_verify_context',True) is not False:self._check()
        return construct

    def get_member(self,value,name):
        if not owns(value):return super().get_member(value,name)
        kind=type(value);key=name.casefold()
        if (kind is _ROW or kind is _TREE and key in ('rows','строки','columns','колонки')
                or kind is _COLUMN and key in _COLUMN_FIELDS) and _ordinary_read(self):
            result=_structural_member(self,value,kind,key,name)
            if result is not _READ_UNAVAILABLE:return result
        root=check(self,value)
        structural=(
            kind is _TREE and key in ('rows','строки','columns','колонки')
            or kind is _ROW and key in ('rows','строки','parent','родитель')
            or kind is _ROWS and key in ('parent','родитель')
        )
        if not structural:columns(root)
        try:return value.get_member(name)
        finally:
            if getattr(self,'_verify_context',True) is not False:self._check()

    def resolve_set_member(self,value,name):
        if not owns(value):return super().resolve_set_member(value,name)
        check(self,value)
        epoch=self._value_tree_epoch
        def write(new_value):
            if self._value_tree_epoch is not epoch:raise BoundaryViolation('ValueTree reference activation expired')
            root=check(self,value);columns(root)
            try:value.set_member(name,new_value)
            finally:
                if getattr(self,'_verify_context',True) is not False:self._check()
        return write

    def resolve_member_call(self,value,name,*,require_value=False,omitted=()):
        if not owns(value):return super().resolve_member_call(value,name,require_value=require_value,omitted=omitted)
        defaults=()
        if type(value) is _COLUMNS:
            from decimal import Decimal
            if name.casefold() in ('add','добавить'):defaults=('',None,'',Decimal(0))
            elif name.casefold() in ('insert','вставить'):defaults=(None,'',None,'',Decimal(0))
        first=1 if name.casefold() in ('insert','вставить') else 0
        if any(index not in range(first,len(defaults)) for index in omitted):
            raise TypeError('ValueTree method argument omissions are not integrated')
        method=self._tree_method(value,name,require_value=require_value)
        if not omitted:return method
        def invoke(*arguments):
            values=list(arguments)
            for index in omitted:values[index]=defaults[index]
            return method(*values)
        return invoke

    def call_member(self,value,name,*arguments):
        if not owns(value):return super().call_member(value,name,*arguments)
        return self._tree_method(value,name)(*arguments)

    def reference_member(self,value,name):
        if not owns(value):return super().reference_member(value,name)
        self.get_member(value,name)
        epoch=self._value_tree_epoch
        def read():
            if self._value_tree_epoch is not epoch:raise BoundaryViolation('ValueTree reference activation expired')
            return self.get_member(value,name)
        from yadinassi.types.values import Reference
        from yadinassi.execution.codegen.experimental_naked_live_state import _ForwardReference
        return _ForwardReference(Reference(read,self.resolve_set_member(value,name)))

    def reference_index(self,value,index):
        if type(value) is not _ROW:return super().reference_index(value,index)
        self.call_member(value,'__getitem__',index)
        epoch=self._value_tree_epoch
        def current():
            if self._value_tree_epoch is not epoch:raise BoundaryViolation('ValueTree reference activation expired')
        def read():
            current();return self.call_member(value,'__getitem__',index)
        def write(new):
            current();self.call_member(value,'__setitem__',index,new)
        # Local native cells adapt the private reference ABI, not the generic
        # host-address object. Keep the original key live through schema edits.
        from yadinassi.types.values import Reference
        from yadinassi.execution.codegen.experimental_naked_live_state import _ForwardReference
        return _ForwardReference(Reference(read,write))

    def resolve_member(self,value,name):
        if not owns(value):return super().resolve_member(value,name)
        return self._tree_method(value,name)

    def _tree_method(self,value,name,*,require_value=False,_canonical=None):
        key=name.casefold();kind=type(value)
        if (_canonical is None and (kind is _ROWS or kind is _COLUMNS)
                and (key in _GET_NAMES or name in ('__getitem__','__iter__')) and _ordinary_read(self)):
            method=_structural_iter(self,value,kind) if name=='__iter__' else _positional_read(self,value,kind,key,name)
            if method is not None:return method
        root=check(self,value)
        epoch=self._value_tree_epoch
        if name in ('__iter__','__getitem__','__setitem__') and type(value) not in (_ROWS,_ROW,_COLUMNS):
            raise ValueError('ValueTree receiver does not support indexing or iteration')
        if _canonical is not None:function=HostFunction(name,_canonical.__get__(value,kind))
        elif name=='__iter__':function=HostFunction(name,lambda:iter(value))
        elif name=='__getitem__':function=HostFunction(name,value.get_index)
        elif name=='__setitem__':function=HostFunction(name,value.set_index,returns_value=False)
        else:function=value.get_method(name)
        self._validate_host_function(function,require_value)
        positional_child = (
            kind is _ROWS and key in ('get','получить','__getitem__')
            or kind is _COLUMNS and key in ('get','получить')
        )
        scalar_read=key in ('count','количество','owner','владелец','level','уровень')
        row_read=_ROW_READS.get(key) if kind is _ROWS else None
        copying=kind is _TREE and key in ('copy','скопировать')
        row_index=kind is _ROWS and key in ('indexof','индекс')
        column_lookup=(kind is _COLUMNS and value is root.columns
                       and key in ('find','найти','indexof','индекс'))
        local_call=(scalar_read or row_read is not None or copying or row_index or column_lookup or key in ('get','получить','__getitem__','__iter__')
                    or kind is _ROWS and key in ('add','добавить','insert','вставить'))
        def invoke(*arguments):
            if check(self,value,graph=not local_call) is not root or self._value_tree_epoch is not epoch:
                raise BoundaryViolation('ValueTree owner changed')
            if not scalar_read and not positional_child:columns(root)
            if column_lookup:
                ids=set()
                for column in value.items:
                    if column._deleted or id(column) in ids:
                        raise BoundaryViolation('ValueTree column lookup schema changed')
                    ids.add(id(column))
            # Public operations validate wrong-collection arguments; preflight all
            # exact tree receivers first so host hooks cannot run inside them.
            for argument in arguments:
                if owns(argument):check(self,argument)
            if type(value) is _ROWS and arguments:
                arguments=self._tree_arguments(key,arguments)
            if type(value) is _COLUMNS and key in ('add','добавить','insert','вставить'):
                position=1 if key in ('add','добавить') else 2
                if len(arguments)>position and arguments[position] is not None:description(arguments[position])
            try:
                if row_read is not None and 1 <= len(arguments) <= row_read[1]:
                    if value.parent is not None and value.parent._deleted is True:
                        # A retained child of a deleted row is still an exact
                        # receiver. Preserve the model's catchable _live error
                        # before any scan, not a bridge corruption exception.
                        result=function(*arguments)
                    else:
                        method, _, track_rows = row_read
                        result=getattr(_ROWS,method)(value,*arguments,
                            admit=row_read_admission(root,value,track_rows=track_rows))
                elif row_index and len(arguments)==1:
                    # Nonmatching siblings are only compared by identity. Seal
                    # the matching row before exposing its position.
                    result=_ROWS._index_of(value,arguments[0],
                        admit=lambda row:row_read_admission(root,value)(value,0,row))
                elif copying and not arguments:
                    if root.rows._columns_clear_forward is not False:
                        raise BoundaryViolation('detached ValueTree copy root')
                    result=_TREE._copy(value,admit=admit_copy_row)
                else:
                    result=function(*arguments)
                if name=='__iter__':
                    def iterator():
                        for item in result:
                            if self._value_tree_epoch is not epoch:raise BoundaryViolation('ValueTree iterator activation expired')
                            check(self,value)
                            expected=_ROW if type(value) is _ROWS else _COLUMN if type(value) is _COLUMNS else None
                            if expected is not None and type(item) is not expected:raise BoundaryViolation('foreign ValueTree iteration item')
                            # This resume already admitted the model ABI; only
                            # the item's distinct birth links remain to check.
                            if owns(item) and admitted_receiver(self,item) is not root:
                                raise BoundaryViolation('foreign ValueTree iteration item')
                            yield item
                        if getattr(self,'_verify_context',True) is not False:self._check()
                    return iterator()
                if key in ('get','получить','__getitem__') and type(value) in (_ROWS,_COLUMNS):
                    expected=_ROW if type(value) is _ROWS else _COLUMN
                    if type(result) is not expected:raise BoundaryViolation('foreign ValueTree result')
                if owns(result) and key not in ('copy','скопировать'):
                    # These exact scalar readers cannot call user code after
                    # admission. Check the returned receiver's own provenance
                    # without auditing all Python classes a second time.
                    validate=(admitted_receiver if scalar_read or positional_child or row_read is not None or column_lookup else check)
                    if validate(self,result) is not root:
                        raise BoundaryViolation('foreign ValueTree result')
                return result
            finally:
                if getattr(self,'_verify_context',True) is not False:self._check()
        return invoke

    def _tree_arguments(self,key,arguments):
        from yadinassi.execution.codegen.experimental_naked_structure import _DirectStructure
        if key in ('loadcolumn','загрузитьколонку') and type(arguments[0]) is list:
            from yadinassi.types.values import _DIRECT_COLLECTION_CLASS_ABI as abi
            source=arguments[0]
            if len(source)>model._MAX_ROWS:raise ValueError('ValueTree load source exceeds row budget')
            canonical=abi[2][0];field='items'
        elif key in ('findrows','найтистроки') and type(arguments[0]) is _DirectStructure:
            from yadinassi.collections.structures import _DIRECT_COLLECTION_CLASS_ABI as abi
            source=arguments[0]
            if len(source)>model._MAX_COLUMNS:raise ValueError('ValueTree filters exceed column budget')
            canonical=abi[1][0];field='_items'
        else:return arguments
        for cls,mro,fields in abi:
            current={k:v for k,v in vars(cls).items() if k!='__slotnames__'}
            expected=tuple((k,v) for k,v in fields if k!='__slotnames__')
            if cls.__mro__ is not mro or len(current)!=len(expected) or any(current.get(k) is not v for k,v in expected):
                raise BoundaryViolation('ValueTree argument adapter hooks changed')
            slots=vars(cls).get('__slotnames__',[])
            if type(slots) is not list or slots:raise BoundaryViolation('ValueTree argument copy cache changed')
        view=object.__new__(canonical)
        setattr(view,field,source)
        if field=='_items':view._version=0
        return (view,*arguments[1:])
