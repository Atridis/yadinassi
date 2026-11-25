"""Bounded source-owned XDTO trees and lists, with finite descriptor reads."""
from weakref import WeakKeyDictionary
from types import MappingProxyType, MethodType
from decimal import Decimal
from . import python_direct_source_xdto as shared
from yadinassi.types.values import HostFunction
from yadinassi.execution.codegen.experimental_naked_boundaries import BoundaryViolation

_OBJECT=shared.values.BSLXDTODataObject
_TYPE=shared.values.BSLXDTOObjectType
_LIST=shared.values.BSLXDTOList
_PROPERTY=shared.values.BSLXDTOProperty
_PROPERTIES=shared.values.BSLXDTOPropertyCollection
_RECORDS=WeakKeyDictionary()
_METHODS={}
for _method,_arity,_returns,_names in (
    ('count',(0,),True,('count','количество')),('get',(1,),True,('get','получить')),
    ('get_xdto',(1,),True,('getxdto','получитьxdto')),('add',(1,),True,('add','добавить')),
    ('insert',(2,),True,('insert','вставить')),('set',(2,),True,('set','установить')),
    ('delete',(0,1),True,('delete','удалить')),('clear',(0,),False,('clear','очистить'))):
    for _name in _names:_METHODS[_name]=(getattr(_LIST,_method),_arity,_returns,_method)
_UNSET=_OBJECT.unset
_GET_LIST=_OBJECT.get_list
_OBJECT_READS={}
for _operation,_arity,_returns,_aliases in (
    ('type',(0,),True,('type','тип')),
    ('factory',(0,),True,('factory','фабрика')),
    ('owner',(0,),True,('owner','владелец')),
    ('owning_property',(0,),True,('owningproperty','владеющеесвойство')),
    ('is_set',(1,),True,('isset','установлено')),
    ('get_list',(1,),True,('getlist','получитьсписок')),
    ('get_xdto',(1,),True,('getxdto','получитьxdto')),
    ('validate',(0,),False,('validate','проверить')),
):
    for _name in _aliases:
        _OBJECT_READS[_name]=(getattr(_OBJECT,_operation),_arity,_returns,_operation)
_SET=_OBJECT.set
_MUTATIONS=frozenset(('add','insert','set','delete','clear','unset'))


def release_application(app):_RECORDS.pop(app,None)
def owns(value):return type(value) is _OBJECT or type(value) is _LIST


def _fields(value):
    result=vars(value)
    if type(result) is not dict or len(result)>10000 or any(type(k) is not str for k in result):
        raise BoundaryViolation('source XDTO object fields changed')
    return result


def _hooks():
    if shared.values.NULL is not shared.values._DIRECT_SOURCE_XDTO_NULL:
        raise BoundaryViolation('source XDTO Null binding changed')


def admit_type(factory,kind):
    pending=[(kind,0)];seen=set();root=None;total=0
    while pending:
        current,depth=pending.pop()
        if id(current) in seen:continue
        seen.add(id(current))
        if type(current) is not _TYPE or depth>min(shared.values.MAX_DEPTH,shared.io.MAX_DEPTH) or len(seen)>shared.values.MAX_TYPES:
            raise BoundaryViolation('source XDTO object type graph exceeds bounds')
        _fields(current)
        if (current._factory is not factory or type(current._uri) is not str or type(current._name) is not str
                or factory._types.get((current._uri,current._name)) is not current or current._base is not None):
            raise BoundaryViolation('source XDTO object type ownership changed')
        collection=current._properties
        if type(collection) is not _PROPERTIES:raise BoundaryViolation('source XDTO property collection changed')
        _fields(collection);items=collection._items
        if type(items) is not tuple:raise BoundaryViolation('source XDTO property inventory changed')
        total+=len(items)
        if total>shared.values.MAX_TYPES*shared.values.MAX_PROPERTIES or len(items)>shared.values.MAX_PROPERTIES:
            raise BoundaryViolation('source XDTO property inventory exceeds bounds')
        if current is kind:root=items
        names=set()
        for prop in items:
            if type(prop) is not _PROPERTY:raise BoundaryViolation('source XDTO property changed')
            _fields(prop)
            if (prop._owner is not current or type(prop._name) is not str or type(prop._uri) is not str
                    or type(prop._upper) is not int or type(prop._lower) is not int
                    or type(prop._nil) is not bool or type(prop._attribute) is not bool):
                raise BoundaryViolation('source XDTO property ownership/shape changed')
            if (prop._lower<0 or prop._lower>shared.values.MAX_LIST or prop._upper==0 or prop._upper < -1
                    or (prop._upper!=-1 and prop._lower>prop._upper) or prop._name in names):
                raise ValueError('source XDTO property bounds unavailable')
            names.add(prop._name)
            if type(prop._type) is _TYPE:pending.append((prop._type,depth+1))
            elif type(prop._type) is shared._TYPE:
                _fields(prop._type);shared._kind(factory,prop._type)
            else:raise ValueError('source XDTO property type not integrated')
    return root


def _snapshot(value):
    fields=tuple(_fields(value).items())
    if type(value) is _OBJECT:return value,fields,value._values,tuple(value._values.items()),None
    if type(value) is _LIST:
        entries=tuple(value._items)
        # Mint from a canonical write/reader, never from an observed raw list.
        # Repeated scalar/None values are legal; a repeated object is not.
        positions={}
        for index,child in enumerate(entries):
            if type(child) is _OBJECT:
                key=id(child)
                positions[key]=index if key not in positions else -1
        return value,fields,value._items,entries,MappingProxyType(positions)
    return value,fields,None,(),None


def _record(boundary,*values):
    records=_RECORDS.setdefault(boundary.app,{})
    for value in values:
        if value is None:continue
        if not any(type(value) is cls for cls in (_OBJECT,_LIST,shared._VALUE)):
            raise BoundaryViolation('source XDTO canonical result changed')
        records[value]=_snapshot(value)
        if type(value) is shared._VALUE:shared._VALUES[value]=tuple(_fields(value).items())


def _scope(boundary,target):
    owner,factory=shared._owner(boundary);_hooks()
    if not owns(target):raise BoundaryViolation('source XDTO receiver changed')
    records=_RECORDS.get(boundary.app)
    if type(records) is not dict or target not in records:raise BoundaryViolation('source XDTO receiver not produced here')
    if len(records)>shared.values.MAX_NODES:raise BoundaryViolation('source XDTO value inventory exceeds bounds')
    return owner,factory,records


def _check(boundary,target):
    owner,factory,records=_scope(boundary,target)
    types=_validate_records(factory,records)
    return owner,factory,types.get(target._type) if type(target) is _OBJECT else target._prop


def _graph_records(records,*roots):
    # Find the connected ownership graphs using previously admitted edges,
    # not current raw containers. A modified live edge must fail validation,
    # not widen the set of values we traverse or get minted into a new seal.
    selected={}
    pending=list(roots)
    while pending:
        value=pending.pop()
        if value is None:continue
        kind=type(value)
        if kind is not _OBJECT and kind is not _LIST and kind is not shared._VALUE:
            raise BoundaryViolation('source XDTO unregistered child')
        if value in selected:continue
        record=_saved_record(records,value)
        selected[value]=record
        if kind is shared._VALUE:continue
        for name,field in record[1]:
            if name=='_owner':
                if field is not None:pending.append(field)
                break
        if kind is _OBJECT:pending.extend(child for _,child in record[3])
        else:pending.extend(record[3])
    return selected


def _check_graph(boundary,target,*related):
    owner,factory,records=_scope(boundary,target)
    types=_validate_records(factory,_graph_records(records,target,*related))
    return owner,factory,types[target._type] if type(target) is _OBJECT else target._prop


def _saved_record(records,value):
    record=records.get(value)
    if type(record) is not tuple or len(record)!=5 or record[0] is not value:
        raise BoundaryViolation('source XDTO value not produced here')
    return record


def _saved_fields(records,value):
    _,saved,container,entries,positions=_saved_record(records,value)
    current=_fields(value)
    if len(current)!=len(saved) or any(current.get(k) is not v for k,v in saved):
        raise BoundaryViolation('source XDTO value fields changed')
    return container,entries,positions


def _object_fields(factory,records,value):
    container,entries,_=_saved_fields(records,value)
    if value._factory is not factory:raise BoundaryViolation('source XDTO object ownership changed')
    values=value._values
    # Check the local mapping before any name lookup, including collisions.
    if type(values) is not dict or values is not container or len(values)!=len(entries) or any(type(k) is not str for k in values):
        raise BoundaryViolation('source XDTO value mapping changed')
    if any(k not in values or values[k] is not v for k,v in entries):
        raise BoundaryViolation('source XDTO properties changed')
    return admit_type(factory,value._type)


def _list_fields(records,value,prop,parent,saved=None):
    container,entries,positions=_saved_fields(records,value) if saved is None else saved
    items=value._items
    if (value._owner is not parent or value._prop is not prop or type(items) is not list
            or items is not container or len(items)!=len(entries) or prop._upper==1):
        raise BoundaryViolation('source XDTO list fields changed')
    live=parent._values.get(prop._name) is value
    if not live and items:raise BoundaryViolation('source XDTO orphan list contains values')
    cap=min(shared.values.MAX_LIST,prop._upper if prop._upper>=0 else shared.values.MAX_LIST)
    if len(items)>cap:raise BoundaryViolation('source XDTO list exceeds bounds')
    return entries,positions


def _object_read(factory,records,value):
    items=_object_fields(factory,records,value)
    trail=value;properties=items;seen={id(trail)}
    while trail._owner is not None:
        parent=trail._owner;prop=trail._owning
        if (type(parent) is not _OBJECT or id(parent) in seen
                or len(seen)>min(shared.values.MAX_DEPTH,shared.io.MAX_DEPTH)):
            raise BoundaryViolation('source XDTO cyclic or excessive ownership')
        seen.add(id(parent))
        properties=_object_fields(factory,records,parent)
        if not any(prop is p for p in properties):raise BoundaryViolation('source XDTO owning property changed')
        slot=parent._values.get(prop._name)
        if prop._upper==1:
            if slot is not trail:raise BoundaryViolation('source XDTO owner backlink changed')
        elif type(slot) is _LIST:
            entries,positions=_list_fields(records,slot,prop,parent)
            index=positions.get(id(trail),-1)
            if type(index) is not int or not 0<=index<len(entries) or entries[index] is not trail or slot._items[index] is not trail:
                raise BoundaryViolation('source XDTO list backlink changed')
        else:raise BoundaryViolation('source XDTO list backlink changed')
        if trail._type is not prop._type:raise BoundaryViolation('source XDTO child type changed')
        trail=parent
    if trail._owning is not None:raise BoundaryViolation('source XDTO detached property changed')
    return items


def _list_read(factory,records,value):
    saved=_saved_fields(records,value)
    parent=value._owner;prop=value._prop
    if type(parent) is not _OBJECT or not any(prop is p for p in _object_read(factory,records,parent)):
        raise BoundaryViolation('source XDTO list ownership changed')
    entries,_=_list_fields(records,value,prop,parent,saved)
    return entries


def _child(factory,records,parent,prop,child):
    # Only the selected forward edge is observed. Its owner has just been
    # proved, so rewalking the same backlink would check the same edge twice.
    if child is None:
        if not prop._nil:raise BoundaryViolation('source XDTO null changed')
    elif type(child) is _OBJECT:
        _object_fields(factory,records,child)
        if child._type is not prop._type or child._owner is not parent or child._owning is not prop:
            raise BoundaryViolation('source XDTO child ownership changed')
    elif type(child) is shared._VALUE:
        _saved_fields(records,child)
        if child._factory is not factory or (child._type is not prop._type
                and not (prop._upper==1 and _derived_scalar(child._type,prop._type))):
            raise BoundaryViolation('source XDTO child type changed')
    else:raise BoundaryViolation('source XDTO unregistered child')


def _select_item(factory,records,value,entries,index):
    child=value._items[index]
    if child is not entries[index]:raise BoundaryViolation('source XDTO list entries changed')
    _child(factory,records,value._owner,value._prop,child)
    return child


def _property_read(factory,records,obj,prop):
    if prop._name not in obj._values:return None
    child=obj._values[prop._name]
    if prop._upper==1:_child(factory,records,obj,prop,child)
    elif type(child) is _LIST:_list_fields(records,child,prop,obj)
    else:raise BoundaryViolation('source XDTO property list changed')
    return child


def _derived_scalar(derived,base):
    return type(derived) is shared._TYPE and type(base) is shared._TYPE and derived._base is base


def _validate_records(factory,records):
    if len(records)>shared.values.MAX_NODES:raise BoundaryViolation('source XDTO value inventory exceeds bounds')
    types={}
    # Check the entire bounded private value inventory before native traversal.
    for value in records:
        container,entries,_=_saved_fields(records,value)
        current=vars(value)
        if type(value) is _OBJECT:
            if set(current)!={'_factory','_type','_owner','_owning','_values'} or value._factory is not factory:
                raise BoundaryViolation('source XDTO object ownership changed')
            if value._type not in types:types[value._type]=admit_type(factory,value._type)
            values=value._values
            if type(values) is not dict or any(type(k) is not str for k in values) or values is not container or len(values)!=len(entries):
                raise BoundaryViolation('source XDTO value mapping changed')
            if any(k not in values or values[k] is not v for k,v in entries):raise BoundaryViolation('source XDTO properties changed')
        elif type(value) is _LIST:
            if set(current)!={'_owner','_prop','_items'} or type(value._items) is not list or value._items is not container:
                raise BoundaryViolation('source XDTO list fields changed')
            if len(value._items)!=len(entries) or any(a is not b for a,b in zip(value._items,entries)):
                raise BoundaryViolation('source XDTO list entries changed')
        elif type(value) is not shared._VALUE:raise BoundaryViolation('source XDTO value inventory changed')
    # Build counts on demand, only after the inventory has proved the exact
    # live list and its entries against the seal. Keep nothing across checks.
    backlinks={}
    for value in records:
        if type(value) is shared._VALUE:continue
        if type(value) is _LIST:
            parent=value._owner;prop=value._prop
            if type(parent) is not _OBJECT or parent not in records or not any(prop is p for p in types[parent._type]) or prop._upper==1:
                raise BoundaryViolation('source XDTO list ownership changed')
            live=parent._values.get(prop._name) is value
            if not live and value._items:raise BoundaryViolation('source XDTO orphan list contains values')
            cap=min(shared.values.MAX_LIST,prop._upper if prop._upper>=0 else shared.values.MAX_LIST)
            if len(value._items)>cap:raise BoundaryViolation('source XDTO list exceeds bounds')
            children=((prop,child) for child in value._items)
        else:
            parent=value
            children=[]
            for name,child in value._values.items():
                prop=_property(types[value._type],name)
                if prop._upper!=1:
                    if type(child) is not _LIST or child not in records or child._owner is not value or child._prop is not prop:
                        raise BoundaryViolation('source XDTO property list changed')
                    continue
                children.append((prop,child))
            trail=value;visited=set();depth=0
            while trail is not None:
                if type(trail) is not _OBJECT or trail not in records or id(trail) in visited or depth>min(shared.values.MAX_DEPTH,shared.io.MAX_DEPTH):
                    raise BoundaryViolation('source XDTO cyclic or excessive ownership')
                visited.add(id(trail));depth+=1
                ancestor=trail._owner
                if ancestor is not None:
                    if type(ancestor) is not _OBJECT or ancestor not in records:raise BoundaryViolation('source XDTO foreign owner')
                    prop=trail._owning
                    if not any(prop is p for p in types[ancestor._type]):raise BoundaryViolation('source XDTO owning property changed')
                    slot=ancestor._values.get(prop._name)
                    if prop._upper==1:
                        if slot is not trail:raise BoundaryViolation('source XDTO owner backlink changed')
                    else:
                        if type(slot) is not _LIST or slot not in records:
                            raise BoundaryViolation('source XDTO list backlink changed')
                        key=id(slot)
                        counts=backlinks.get(key)
                        if counts is None:
                            counts=backlinks[key]={}
                            for child in slot._items:
                                child_key=id(child)
                                counts[child_key]=counts.get(child_key,0)+1
                        if counts.get(id(trail))!=1:
                            raise BoundaryViolation('source XDTO list backlink changed')
                elif trail._owning is not None:raise BoundaryViolation('source XDTO detached property changed')
                trail=ancestor
        for prop,child in children:
            if child is None:
                if not prop._nil:raise BoundaryViolation('source XDTO null changed')
            elif not any(type(child) is cls for cls in (_OBJECT,shared._VALUE)) or child not in records:
                raise BoundaryViolation('source XDTO unregistered child')
            elif child._factory is not factory or (child._type is not prop._type
                    and not (prop._upper==1 and type(child) is shared._VALUE
                             and _derived_scalar(child._type,prop._type))):
                raise BoundaryViolation('source XDTO child type changed')
            elif type(child) is _OBJECT and (child._owner is not parent or child._owning is not prop):
                raise BoundaryViolation('source XDTO child ownership changed')
    return types


def _budget(factory,nodes=0,units=0):
    if (factory._nodes+nodes>min(shared.values.MAX_NODES,shared.io.MAX_NODES)
            or factory._units+units>min(shared.values.MAX_UNITS,shared.io.MAX_UNITS)):
        raise ValueError('source XDTO allocation exceeds resource budget')


def _publish(boundary,owner,factory,*changed):
    shared._SEALS[boundary.app]=shared._seal(owner,boundary.app,factory)
    _record(boundary,*changed)


def create(boundary,kind):
    owner,factory=check_inventory(boundary);admit_type(factory,kind);_budget(factory,1)
    result=shared._CREATE_CALL(factory,kind)
    if type(result) is not _OBJECT:raise BoundaryViolation('source XDTO object constructor changed')
    _publish(boundary,owner,factory,result);_check(boundary,result);return result


def _property(items,name):
    if type(name) is not str:raise TypeError('source XDTO property requires String')
    prop=next((p for p in items if p._name==name),None)
    if prop is None:raise ValueError('XDTO: неизвестное свойство')
    return prop


def _native(value):return value._value if type(value) is shared._VALUE else value


_PROPERTY_FIELDS={
    'name':('_name',str),'имя':('_name',str),'namespaceuri':('_uri',str),'uriпространстваимен':('_uri',str),
    'lowerbound':('_lower',int),'нижняяграница':('_lower',int),'upperbound':('_upper',int),'верхняяграница':('_upper',int),
    'nillable':('_nil',bool),'возможнопустое':('_nil',bool),
}


def get_property(factory,prop,name):
    # The factory/descriptor seal has already been checked. A descriptor
    # must also be an exact member of the current type, not a host copy.
    data=_fields(prop)
    owner=data.get('_owner')
    fields=_fields(owner) if type(owner) is _TYPE else {}
    uri,name_in_registry=fields.get('_uri'),fields.get('_name')
    if (type(uri) is not str or type(name_in_registry) is not str
            or factory._types.get((uri,name_in_registry)) is not owner):
        raise BoundaryViolation('source XDTO property requires a current owning type')
    items=owner._properties
    if (type(items) is not _PROPERTIES or type(items._items) is not tuple
            or not any(prop is candidate for candidate in items._items)):
        raise BoundaryViolation('source XDTO property is not in its owning type')
    key=name.casefold()
    if key in ('qualified','квалифицированное'):
        uri=data.get('_uri')
        if type(uri) is not str:raise BoundaryViolation('source XDTO property namespace changed')
        return bool(uri)
    if key in ('form','форма'):
        flag=data.get('_attribute')
        if type(flag) is not bool:raise BoundaryViolation('source XDTO property form changed')
        return shared.ATTRIBUTE_FORM if flag else shared.ELEMENT_FORM
    field=_PROPERTY_FIELDS.get(key)
    if field is None:raise ValueError('source XDTO property member not integrated')
    attr,kind=field;result=data.get(attr)
    if type(result) is not kind:raise BoundaryViolation('source XDTO property field changed')
    return Decimal(result) if kind is int else result


def _list(boundary,owner,factory,obj,prop):
    if prop._upper==1:raise ValueError('XDTO: свойство не является списком')
    if prop._name not in obj._values:
        _check_graph(boundary,obj)
        _budget(factory,1);result=_GET_LIST(obj,prop)
        _publish(boundary,owner,factory,obj,result);_check_graph(boundary,obj)
    return obj._values[prop._name]


def get(boundary,obj,name):
    owner,factory,records=_scope(boundary,obj)
    if type(obj) is _LIST:
        _list_read(factory,records,obj)
        method,_,returns,_=_method(obj,name)
        return HostFunction(name,method.__get__(obj,_LIST),returns_value=returns)
    prop=_property(_object_read(factory,records,obj),name)
    result=_property_read(factory,records,obj,prop)
    if prop._upper!=1 and result is None:return _list(boundary,owner,factory,obj,prop)
    return _native(result)


def _input(boundary,owner,prop,value,old=None,present=False):
    if present and value is old:return 0,0
    if value is None or value is shared.values._DIRECT_SOURCE_XDTO_NULL:
        if not prop._nil:raise ValueError('XDTO: пустое значение не разрешено')
        return 0,0
    if type(prop._type) is _TYPE:
        if type(value) is not _OBJECT:raise TypeError('source XDTO property requires owned object')
        _check_graph(boundary,value)
        if value._type is not prop._type or value._owner is not None:raise ValueError('source XDTO object type/owner mismatch')
        # Check the prospective complete tree against the tightest alias before
        # native _prepare (which sees only values.MAX_DEPTH) can attach anything.
        depth=0;ancestor=owner
        while ancestor is not None:
            if ancestor is value:raise ValueError('XDTO: цикл владения')
            depth+=1;ancestor=ancestor._owner
        pending=[(value,depth)]
        while pending:
            node,level=pending.pop()
            if level>min(shared.values.MAX_DEPTH,shared.io.MAX_DEPTH):
                raise ValueError('source XDTO ownership depth exceeded')
            for child in node._values.values():
                for item in child._items if type(child) is _LIST else (child,):
                    if type(item) is _OBJECT:pending.append((item,level+1))
        return 0,0
    if type(value) is shared._VALUE and prop._upper==1:
        shared._check_value(owner._factory,value)
        actual,declared=value._type,prop._type
        # The native setter retains a specific wrapper in a base property,
        # but allocates a declaration-typed wrapper in the reverse direction.
        if _derived_scalar(actual,declared):return 0,0
        if _derived_scalar(declared,actual):value=value._value
        else:raise TypeError('XDTO: тип свойства не совпадает')
    if not any(type(value) is cls for cls in (str,bool,Decimal)):
        raise TypeError('source XDTO property requires primitive scalar')
    _,lexical=shared.values.scalar(prop._type,value)
    return 1,len(lexical)


def set_member(boundary,obj,name):
    if type(obj) is not _OBJECT:
        _check_graph(boundary,obj);raise ValueError('source XDTO list properties are read-only')
    _,_,items=_check_graph(boundary,obj);prop=_property(items,name)
    if prop._upper!=1:raise ValueError('XDTO: используйте методы списка')
    def assign(value):
        if type(value) is int:value=Decimal(value)
        owner,factory,current=_check_graph(boundary,obj)
        if _property(current,name) is not prop:raise BoundaryViolation('source XDTO bound property changed')
        old=obj._values.get(name);nodes,units=_input(boundary,obj,prop,value,old,name in obj._values)
        _budget(factory,nodes,units);_SET(obj,name,value)
        new=obj._values[name]
        _publish(boundary,owner,factory,obj,old,new);_check_graph(boundary,obj,old,new)
    return assign


def _method(value,name):
    if type(name) is not str:raise TypeError('source XDTO method requires String')
    if type(value) is _OBJECT:
        key=name.casefold()
        if key in ('unset','сбросить'):return _UNSET,(1,),False,'unset'
        if key in _OBJECT_READS:return _OBJECT_READS[key]
    else:
        key={'__getitem__':'get','__setitem__':'set'}.get(name,name.casefold())
        if key in _METHODS:return _METHODS[key]
    raise ValueError('source XDTO method not integrated')


def resolve(boundary,value,name,*,require_value=False,argument_count=None,allow_references=False,validate=None):
    if name=="__iter__":
        _,factory,records=_scope(boundary,value)
        if type(value) is not _LIST:raise ValueError("source XDTO object is not iterable")
        _list_read(factory,records,value)
        return lambda:iterate(boundary,value)
    # Admit the actual retained receiver, both before evaluation of arguments
    # and again on entry to the bound call (args may perform host effects).
    scope=_scope(boundary,value)
    method,arity,returns,operation=_method(value,name)
    mutation=operation in _MUTATIONS
    def check(count=None,scope=None):
        if scope is None:scope=_scope(boundary,value)
        owner,factory,records=scope
        if mutation or operation=='validate':
            relevant=_graph_records(records,value) if mutation else records
            types=_validate_records(factory,relevant)
            items=types[value._type] if type(value) is _OBJECT else value._prop
        elif type(value) is _OBJECT:items=_object_read(factory,records,value)
        else:items=_list_read(factory,records,value)
        if validate is not None:validate()
        if require_value and not returns:raise ValueError('source XDTO procedure cannot be used as value')
        if count is not None and count not in arity:raise TypeError('source XDTO invalid method arity')
        if mutation and type(value) is _LIST and value._owner._values.get(value._prop._name) is not value:
            raise ValueError('source XDTO orphan list is read-only')
        return owner,factory,records,items
    check(argument_count,scope)
    def call(*args):
        owner,factory,records,items=check(len(args))
        if type(value) is _OBJECT and operation!='unset':
            if operation=='factory':return factory
            if operation in ('is_set','get_list','get_xdto'):
                prop=_property(items,args[0])
                if operation=='get_xdto' and prop._upper!=1:
                    raise ValueError('source XDTO GetXDTO requires a single property')
                result=_property_read(factory,records,value,prop)
                if operation=='get_list':
                    return _list(boundary,owner,factory,value,prop)
                if operation=='get_xdto':return result
                return method(value,prop)
            return method(value)
        if operation in ('get','get_xdto'):
            if not(type(args[0]) is int or type(args[0]) is Decimal):raise ValueError('source XDTO index requires Number')
            index=shared.values.index(args[0],len(items))
            child=_select_item(factory,records,value,items,index)
            return _native(child) if operation=='get' else child
        if operation=='count':
            for index in range(len(items)):_select_item(factory,records,value,items,index)
            return method(value)
        changed=[value];nodes=units=0
        if operation=='unset':
            prop=_property(items,args[0]);old=value._values.get(prop._name)
            if type(old) is _LIST:changed.extend(old._items);changed.append(old)
            else:changed.append(old)
        elif operation in ('add','insert','set'):
            prop=value._prop;parent=value._owner
            if operation=='add':index=len(value._items);incoming=args[0]
            else:
                if not (type(args[0]) is int or type(args[0]) is Decimal):raise ValueError('source XDTO index requires Number')
                index=shared.values.index(args[0],len(value._items),end=operation=='insert');incoming=args[1]
            if type(incoming) is int:
                incoming=Decimal(incoming)
                args=(*args[:-1],incoming)
            old=value._items[index] if operation=='set' else None
            if operation!='set':
                cap=min(shared.values.MAX_LIST,prop._upper if prop._upper>=0 else shared.values.MAX_LIST)
                if len(value._items)>=cap:raise ValueError('XDTO: превышен размер списка')
            nodes,units=_input(boundary,parent,prop,incoming,old,operation=='set')
            if operation!='set':nodes+=1
            changed.extend((old,incoming if type(incoming) is _OBJECT else None))
        elif operation=='delete':
            index=len(value._items)-1 if not args else shared.values.index(args[0],len(value._items))
            if index<0:raise ValueError('XDTO: список пуст')
            changed.append(value._items[index])
        elif operation=='clear':changed.extend(value._items)
        _budget(factory,nodes,units)
        result=method(value,*args)
        if type(result) is shared._VALUE or type(result) is _OBJECT:changed.append(result)
        _publish(boundary,owner,factory,*changed)
        _check_graph(boundary,value,*changed)
        return result
    if allow_references:call.requires_reference=lambda index:False
    return call


def captured(boundary,function,**contract):
    if type(function) is not HostFunction:return None
    from .python_direct_source_xdto_local import _host_hooks
    _host_hooks()
    _fields(function)
    callback=function.function
    if type(callback) is not MethodType or not owns(callback.__self__):return None
    value=callback.__self__
    candidates=((_UNSET,(1,),False,'unset'),) if type(value) is _OBJECT else tuple(_METHODS.values())
    match=next((item for item in candidates if item[0] is callback.__func__),None)
    if match is None:raise BoundaryViolation('source XDTO saved method changed')
    def validate():
        _fields(function)
        if function.function is not callback or function.returns_value is not match[2] or type(function.reference_parameters) is not frozenset or function.reference_parameters:
            raise BoundaryViolation('source XDTO saved method contract changed')
    return resolve(boundary,value,"getxdto" if match[3]=="get_xdto" else match[3],validate=validate,**contract)


def iterate(boundary,value):
    _,factory,records=_scope(boundary,value)
    if type(value) is not _LIST:raise ValueError('source XDTO object is not iterable')
    # Like the original tuple snapshot, this retains the original selected
    # objects across legal list edits, but never retains their admission.
    snapshot=_list_read(factory,records,value)
    for index,child in enumerate(snapshot):
        _,factory,records=_scope(boundary,value)
        current=_list_read(factory,records,value)
        if index<len(current) and value._items[index] is not current[index]:
            raise BoundaryViolation('source XDTO list entries changed')
        if type(child) is _OBJECT:_object_read(factory,records,child)
        else:_child(factory,records,value._owner,value._prop,child)
        yield _native(child)


def check_inventory(boundary):
    owner,factory=shared._owner(boundary);_hooks()
    _validate_records(factory,_RECORDS.get(boundary.app,{}))
    return owner,factory


def stage_xml_result(boundary,factory,result):
    """Private canonical-reader output admission, without publication."""
    records=dict(_RECORDS.get(boundary.app,{}));new=[];pending=[result];seen=set()
    while pending:
        value=pending.pop()
        if value is None:continue
        if id(value) in seen:continue
        seen.add(id(value))
        if len(seen)>min(shared.io.MAX_NODES,shared.values.MAX_NODES):raise BoundaryViolation('source XML output graph limit')
        if not any(type(value) is cls for cls in (_OBJECT,_LIST,shared._VALUE)):
            raise BoundaryViolation('source XML foreign output value')
        fields=_fields(value)
        if value in records:raise BoundaryViolation('source XML output reused existing value')
        if type(value) is _OBJECT:
            if set(fields)!={'_factory','_type','_owner','_owning','_values'} or value._factory is not factory:
                raise BoundaryViolation('source XML object fields changed')
            admit_type(factory,value._type)
            if type(value._values) is not dict or any(type(k) is not str for k in value._values):raise BoundaryViolation('source XML object mapping changed')
            if len(seen)+len(pending)+len(value._values)>min(shared.io.MAX_NODES,shared.values.MAX_NODES):raise BoundaryViolation("source XML output entry limit")
            pending.extend(value._values.values())
        elif type(value) is _LIST:
            if set(fields)!={'_owner','_prop','_items'} or type(value._items) is not list or len(value._items)>shared.values.MAX_LIST:
                raise BoundaryViolation('source XML list fields changed')
            if len(seen)+len(pending)+len(value._items)>min(shared.io.MAX_NODES,shared.values.MAX_NODES):raise BoundaryViolation("source XML output entry limit")
            pending.extend(value._items)
        else:
            if set(fields)!={'_factory','_type','_value','_lexical'} or value._factory is not factory:
                raise BoundaryViolation('source XML scalar fields changed')
            shared._kind(factory,value._type)
            if not any(type(value._value) is cls for cls in (str,bool,Decimal)) or type(value._lexical) is not str:
                raise BoundaryViolation('source XML scalar representation changed')
            native,lexical=shared.values.scalar(value._type,value._value)
            if lexical!=value._lexical:raise BoundaryViolation('source XML scalar lexical mismatch')
        records[value]=_snapshot(value);new.append(value)
    if type(result) is _OBJECT and (result._owner is not None or result._owning is not None):
        raise BoundaryViolation('source XML root has an owner')
    _validate_records(factory,records)
    return records,tuple(new)


def publish_xml_result(boundary,staged):
    records,new=staged
    _RECORDS[boundary.app]=records
    for value in new:
        if type(value) is shared._VALUE:shared._VALUES[value]=tuple(_fields(value).items())
