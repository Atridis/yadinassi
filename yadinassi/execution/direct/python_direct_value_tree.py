"""Exact detached ValueTree protocols, with live provenance and no DB authority."""
from yadinassi.collections import value_trees as model
from yadinassi.execution.codegen.experimental_naked_boundaries import BoundaryViolation
from yadinassi.types.values import HostFunction

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
    for cls,mro,fields in _ARRAY_ABI:
        current=vars(cls)
        if cls.__mro__ is not mro or len(current)!=len(fields) or any(current.get(k) is not v for k,v in fields):
            raise BoundaryViolation('ValueTree output array hooks changed')
        slots=current.get('__slotnames__')
        if type(slots) is not list or slots:raise BoundaryViolation('ValueTree output array copy cache changed')
    for namespace,name,value in _SCHEMA_BINDINGS:
        if namespace.get(name) is not value:raise BoundaryViolation('ValueTree schema binding changed')
    for cls,mro,fields in _ABI:
        current=vars(cls)
        if cls.__mro__ is not mro or len(current)!=len(fields) or any(current.get(k) is not v for k,v in fields):
            raise BoundaryViolation('ValueTree class hooks changed')
        slots=current.get('__slotnames__')
        if slots is not None and (type(slots) is not list or slots):raise BoundaryViolation('ValueTree copy metadata changed')
    for member,fields in _ENUM_MEMBERS:
        current=vars(member)
        # Inspect keys before any lookup: foreign keys may collide with the
        # canonical strings and supply an equality callback.
        if type(current) is not dict or len(current)!=len(fields) or any(type(key) is not str for key in current):
            raise BoundaryViolation('ValueTree enum member fields changed')
        if any(current.get(key) is not value for key,value in fields):
            raise BoundaryViolation('ValueTree enum member state changed')
    for cls,mro,fields in _BASE_ABI:
        current={k:v for k,v in vars(cls).items() if k!='__slotnames__'}
        if cls.__mro__ is not mro or len(current)!=len(fields) or any(current.get(k) is not v for k,v in fields):
            raise BoundaryViolation('ValueTree base hooks changed')
        slots=vars(cls).get('__slotnames__',[])
        if type(slots) is not list or slots:raise BoundaryViolation('ValueTree base copy metadata changed')
    for cls,mro,fields,slotnames in _SCALAR_ABI:
        current={k:v for k,v in vars(cls).items() if k!='__slotnames__'}
        if cls.__mro__ is not mro or len(current)!=len(fields) or any(current.get(k) is not v for k,v in fields):
            raise BoundaryViolation('ValueTree scalar hooks changed')
        slots=vars(cls).get('__slotnames__')
        if slots is not None and (type(slots) is not list or any(type(name) is not str for name in slots) or tuple(slots)!=slotnames):
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
        root=check(self,value)
        kind=type(value);key=name.casefold()
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

    def resolve_member(self,value,name):
        if not owns(value):return super().resolve_member(value,name)
        return self._tree_method(value,name)

    def _tree_method(self,value,name,*,require_value=False):
        root=check(self,value)
        epoch=self._value_tree_epoch
        if name in ('__iter__','__getitem__','__setitem__') and type(value) not in (_ROWS,_ROW,_COLUMNS):
            raise ValueError('ValueTree receiver does not support indexing or iteration')
        if name=='__iter__':function=HostFunction(name,lambda:iter(value))
        elif name=='__getitem__':function=HostFunction(name,value.get_index)
        elif name=='__setitem__':function=HostFunction(name,value.set_index,returns_value=False)
        else:function=value.get_method(name)
        self._validate_host_function(function,require_value)
        key=name.casefold()
        kind=type(value)
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
