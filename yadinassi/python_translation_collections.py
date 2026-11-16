"""Value-only direct list/dict operations for fresh closed-region collections.

The emitter owns VM admission, source diagnostics and service boundaries. A
RegionCollections instance owns only fresh canonical wrappers: aliases share the
same backing storage; no existing host collection is silently copied or adopted.
"""
from decimal import Decimal
from weakref import ref
from . import values as V, maps as M, structures as S

class UnsupportedCollection(Exception):
    """Optional region eligibility failure, never an instruction to replay effects."""

# Use captured canonical classes even while deciding that current module aliases
# were replaced. Never hash a host-supplied metaclass during lazy import.
_Array=dict(V._DIRECT_COLLECTION_HELPER_ABI)['BSLArray']
_Map=dict(M._DIRECT_COLLECTION_HELPER_ABI)['BSLMap']
_Structure=dict(S._DIRECT_COLLECTION_HELPER_ABI)['BSLStructure']
_Pair=dict(S._DIRECT_COLLECTION_HELPER_ABI)['BSLKeyAndValue']
_TYPES=(_Array,_Map,_Structure)
_SCALARS=(Decimal,bool,str,type(None))
_CLASS_ABI=tuple(item for module in (V,M,S) for item in module._DIRECT_COLLECTION_CLASS_ABI)
_HELPER_ABI=tuple((module,name,original) for module in (V,M,S)
                  for name,original in module._DIRECT_COLLECTION_HELPER_ABI)
_VALUE_ORIGINALS=dict(V._DIRECT_COLLECTION_HELPER_ABI)
_MAP_ORIGINALS=dict(M._DIRECT_COLLECTION_HELPER_ABI)
_STRUCTURE_ORIGINALS=dict(S._DIRECT_COLLECTION_HELPER_ABI)
# Exact admitted scalar/fresh-graph values need no mutable module dispatch.
# These preserve the bounded semantics of the captured helpers without following
# a subsequently replaced helper global into arbitrary Python callbacks.
def _number(value):
    if type(value) is not Decimal:raise TypeError('Ожидается число')
    return value

def _integer(value):
    value=_number(value)
    if value!=value.to_integral_value():raise ValueError('Ожидается целое число')
    return int(value)

def _equal(left,right):
    if type(left) is not type(right):return False
    if any(type(left) is kind for kind in _SCALARS):return left==right
    return left is right

def _map_key(value):
    if any(type(value) is kind for kind in _SCALARS):return type(value),value
    return object,id(value)

def _structure_key(name):
    if type(name) is not str:raise TypeError('Имя свойства структуры должно быть строкой')
    if (not name or not (name[0].isalpha() or name[0]=='_')
            or not all(char.isalnum() or char=='_' for char in name)):
        raise ValueError(f'Недопустимое имя свойства структуры: {name}')
    return name.casefold()

_TRIM_CHARS=_STRUCTURE_ORIGINALS['_DIRECT_COLLECTION_TRIM_CHARS']
def _trim_all(name):return name.strip(_TRIM_CHARS)

_MAX_INSERT_GROWTH=_VALUE_ORIGINALS['_MAX_INSERT_GROWTH']
_MAX_ARRAY_CONSTRUCTION=_VALUE_ORIGINALS['_MAX_ARRAY_CONSTRUCTION']
_MAX_ARRAY_DIMENSIONS=_VALUE_ORIGINALS['_MAX_ARRAY_DIMENSIONS']
_DICT_DESCRIPTORS={cls:dict(items)['__dict__'] for cls,_,items in _CLASS_ABI if '__dict__' in dict(items)}
# Mutable collection subclasses inherit their instance dictionary descriptor.
_OBJECT_DICT=next(dict(items)['__dict__'] for cls,_,items in _CLASS_ABI
                  if cls.__name__=='BSLObject')

def _storage(value):return _OBJECT_DICT.__get__(value,type(value))

def _new_storage(kind,fields):
    value=object.__new__(kind)
    _OBJECT_DICT.__get__(value,kind).update(fields)
    return value

_CONSTRUCTORS={'array':_Array,'массив':_Array,'map':_Map,
               'соответствие':_Map,'structure':_Structure,'структура':_Structure}
_ALIASES={'добавить':'add','получить':'get','установить':'set','вставить':'insert',
          'удалить':'delete','очистить':'clear','количество':'count','вграница':'ubound',
          'найти':'find','свойство':'property'}
_ARITIES={_Array:{'add':(0,1),'get':(1,1),'set':(2,2),'insert':(1,2),'delete':(1,1),
                       'clear':(0,0),'count':(0,0),'ubound':(0,0),'find':(1,1)},
          _Map:{'get':(1,1),'insert':(1,2),'delete':(1,1),'clear':(0,0),'count':(0,0)},
          _Structure:{'insert':(1,2),'delete':(1,1),'clear':(0,0),'count':(0,0),'property':(1,2)}}

def _bad_arity(receiver,method,args):
    kind=type(receiver)
    if method in ('count','ubound'):
        def no_args():pass
        family=('_ArrayBase.get_member' if kind is _Array else
                '_MapBase.get_method' if kind is _Map else '_StructureBase.get_method')
        no_args.__qualname__=family+'.<locals>.<lambda>'
        return no_args(*args)
    if kind is _Array and method=='clear':return _storage(receiver)['items'].clear(*args)
    for cls,mro,items in _CLASS_ABI:
        if cls is kind:
            for base in mro:
                original=next((dict(fields).get(method) for registered,_,fields in _CLASS_ABI if registered is base),None)
                if original is not None:return original(receiver,*args)
    raise TypeError('Неверное число аргументов метода коллекции')

def trusted(vm=None):
    """Definition-time class/helper proof, called once BEFORE entering a region."""
    for cls,mro,items in _CLASS_ABI:
        current=type.__getattribute__(cls,'__mro__')
        if len(current)!=len(mro) or any(a is not b for a,b in zip(current,mro)):return False
        actual=vars(cls)
        if len(actual)!=len(items) or any(type(key) is not str for key in actual):return False
        if any(actual.get(key) is not value for key,value in items):return False
    if not all(vars(module).get(name) is original for module,name,original in _HELPER_ABI):return False
    if vm is not None:
        registry=vm.types
        if type(registry) is not dict or any(type(key) is not str for key in registry):return False
        for name,constructor in _CONSTRUCTORS.items():
            wrapper=registry.get(name)
            if type(wrapper) is not V.HostFunction:return False
            fields=vars(wrapper)
            if any(type(key) is not str for key in fields):return False
            if (fields.get('function') is not constructor or fields.get('returns_value') is not True
                    or type(fields.get('reference_parameters')) is not frozenset
                    or fields['reference_parameters']):return False
    return True

def method_arity(kind,name):
    name=_ALIASES.get(name.casefold(),name.casefold())
    return _ARITIES.get(kind,{}).get(name)

COLLECTION_TYPES=frozenset(_CONSTRUCTORS)
COLLECTION_METHODS=frozenset((*_ALIASES,*(name for methods in _ARITIES.values() for name in methods)))
admit=trusted

class CollectionRegion:
    def __init__(self,lease=None):
        # Weak ownership avoids retaining discarded fresh objects until exit.
        self._owned={};self.lease=lease
    def binary(self,operator,left,right,scalar_binary):
        # Never pass a fresh graph into mutable generic value dispatch.
        if self.owns(left) or self.owns(right):
            if operator == '=':return left is right
            if operator == '<>':return left is not right
            if operator in ('<','<=','>','>='):raise TypeError('Значения несовместимы для сравнения')
            if operator == '+' and type(left) is str:
                labels={_Array:'Массив',_Map:'Соответствие',_Structure:'Структура',_Pair:'КлючИЗначение'}
                return scalar_binary(operator,left,labels[type(right)])
            raise TypeError('Ожидается число')
        return scalar_binary(operator,left,right)
    def owns(self,value):
        entry=self._owned.get(id(value))
        return entry is not None and entry() is value
    def safe_value(self,value):
        return (any(type(value) is kind for kind in _SCALARS)
                or (any(type(value) is kind for kind in (*_TYPES,_Pair)) and self.owns(value)))
    def _value(self,value):
        if not self.safe_value(value):raise UnsupportedCollection('non-scalar or foreign collection payload')
        return value
    def _receiver(self,value):
        if not any(type(value) is kind for kind in _TYPES) or not self.owns(value):
            raise UnsupportedCollection('receiver is not a fresh region collection')
        return type(value)
    def _adopt_new(self,value):
        self._owned[id(value)]=ref(value)
        if self.lease is not None:self.lease.owned_values.append(ref(value))
        if type(value) is _Array:
            for item in _storage(value)['items']:
                if type(item) is _Array and not self.owns(item):self._adopt_new(item)
        return value
    def new(self,type_name,args=()):
        if type(type_name) is not str:raise UnsupportedCollection('dynamic constructor name')
        constructor=_CONSTRUCTORS.get(type_name.casefold())
        if constructor is None:raise UnsupportedCollection('unsupported collection constructor')
        if self.lease is not None:self.lease.check()
        for value in args:self._value(value)
        if constructor is _Map:
            if args:
                if len(args)>1:
                    # Argument binding fails before captured code can run.
                    original=dict(next(items for cls,_,items in _CLASS_ABI if cls is _Map))['__init__']
                    original(object.__new__(_Map),*args)
                raise TypeError('Конструктор соответствия ожидает фиксированное соответствие')
            value=_new_storage(_Map,{'_items':{},'_version':0})
        elif constructor is _Structure:
            keys=args[0] if args else ''
            if type(keys) is not str:raise TypeError('Список свойств структуры должен быть строкой')
            names=[name for part in keys.split(',') if (name:=_trim_all(part))]
            items={};version=0
            for index,name in enumerate(names):
                key=_structure_key(name)
                if key not in items:version+=1
                items[key]=(name,args[index+1] if index+1<len(args) else None)
            value=_new_storage(_Structure,{'_items':items,'_version':version})
        else:
            sizes=tuple(args) if args else (Decimal(0),)
            if len(sizes)>_MAX_ARRAY_DIMENSIONS:
                raise ValueError('Массив: превышен предел измерений Yadinassi (64)')
            for size in sizes:
                size=_number(size)
                if not size.is_finite() or size!=size.to_integral_value():raise ValueError('Ожидается целое число')
                if size<0:raise ValueError('Размер массива не может быть отрицательным')
                if len(sizes)>1 and size==0:raise ValueError('Размеры многомерного массива должны быть положительными')
            widths=[];parents=1;cost=0
            for depth,size in enumerate(sizes):
                if depth:cost+=parents
                remaining=_MAX_ARRAY_CONSTRUCTION-cost
                if parents and (remaining<0 or size>remaining//parents):
                    raise ValueError('Массив: превышен предел ресурсов Yadinassi (1000000 элементов и вложенных массивов)')
                width=int(size) if parents else 0
                widths.append(width);parents*=width;cost+=parents
            def create(depth):
                items=([None]*widths[depth] if depth==len(widths)-1 else
                       [create(depth+1) for _ in range(widths[depth])])
                return _new_storage(_Array,{'items':items})
            value=create(0)
        return self._adopt_new(value)
    def _index(self,array,index):
        position=_integer(index)
        if not 0<=position<len(_storage(array)['items']):raise IndexError(f'Индекс массива вне границ: {position}')
        return position
    def prepare_index(self,receiver,write=False):
        if not any(type(receiver) is kind for kind in _TYPES):
            raise TypeError('Индексирование поддерживается только для коллекций')
        self._receiver(receiver)
        return receiver
    def prepare_attribute(self,receiver,name,write=False):
        if not any(type(receiver) is kind for kind in (*_TYPES,_Pair)):
            raise TypeError('Значение не имеет методов или свойств')
        if not self.owns(receiver):raise UnsupportedCollection('foreign attribute receiver')
        return receiver
    def bind(self,receiver,name):
        if type(receiver) is _Pair and self.owns(receiver):
            if name.casefold() in ('key','value','ключ','значение'):raise TypeError('Значение не является функцией')
            raise ValueError(f'Метод или свойство не найдено: {name}')
        if not any(type(receiver) is kind for kind in _TYPES):
            raise TypeError('Значение не имеет методов или свойств')
        kind=self._receiver(receiver);method=_ALIASES.get(name.casefold(),name.casefold())
        if method not in _ARITIES[kind]:
            if kind is _Map:raise ValueError(f'Метод соответствия не найден: {name}')
            if kind is _Structure:raise ValueError(f'Метод структуры не найден: {name}')
            raise ValueError(f'Метод или свойство не найдено: {name}')
        return receiver,name
    def invoke(self,bound,args=()):
        return self.call(bound[0],bound[1],args)
    def read_index(self,receiver,index):
        self.prepare_index(receiver)
        kind=self._receiver(receiver);self._value(index)
        if kind is _Array:return _storage(receiver)['items'][self._index(receiver,index)]
        if kind is _Map:
            item=_storage(receiver)['_items'].get(_map_key(index));return None if item is None else item[1]
        key=_structure_key(index)
        if key not in _storage(receiver)['_items']:raise ValueError(f'Свойство структуры не найдено: {index}')
        return _storage(receiver)['_items'][key][1]
    def write_index(self,receiver,index,value):
        self.prepare_index(receiver,write=True)
        kind=self._receiver(receiver);self._value(index);self._value(value)
        if kind is _Array:_storage(receiver)['items'][self._index(receiver,index)]=value
        elif kind is _Map:self._insert(receiver,index,value)
        else:
            key=_structure_key(index)
            if key not in _storage(receiver)['_items']:raise ValueError(f'Свойство структуры не найдено: {index}')
            _storage(receiver)['_items'][key]=_storage(receiver)['_items'][key][0],value
    def read_attribute(self,receiver,name):
        self.prepare_attribute(receiver,name)
        if type(receiver) is _Pair and self.owns(receiver):
            if name.casefold() in ('key','ключ'):return _storage(receiver)['key']
            if name.casefold() in ('value','значение'):return _storage(receiver)['value']
            raise ValueError(f'Метод или свойство не найдено: {name}')
        if self._receiver(receiver) is not _Structure:
            # The emitter excludes first-class method extraction. Missing
            # properties still need the ordinary catchable BSL diagnostic.
            raise ValueError(f'Метод или свойство не найдено: {name}')
        return self.read_index(receiver,name)
    def write_attribute(self,receiver,name,value):
        self.prepare_attribute(receiver,name,write=True)
        if type(receiver) is not _Structure:
            raise ValueError(f'Свойство недоступно для записи: {name}')
        self.write_index(receiver,name,value)
    def _insert(self,receiver,key,value):
        token=_map_key(key) if type(receiver) is _Map else _structure_key(key)
        if token not in _storage(receiver)['_items']:_storage(receiver)['_version']+=1
        _storage(receiver)['_items'][token]=key,value
    def property(self,receiver,name):
        if self._receiver(receiver) is not _Structure:raise UnsupportedCollection('non-structure property')
        self._value(name);key=_structure_key(name.strip(' ') if isinstance(name,str) else name)
        item=_storage(receiver)['_items'].get(key)
        return (False,None) if item is None else (True,item[1])
    def call(self,receiver,name,args=()):
        self.bind(receiver,name)
        kind=self._receiver(receiver)
        method=_ALIASES.get(name.casefold(),name.casefold())
        limits=_ARITIES[kind].get(method)
        # Preserve ordinary method/arity diagnostics on exceptional paths only.
        if limits is None or not limits[0]<=len(args)<=limits[1]:
            return _bad_arity(receiver,method,args)
        for value in args:self._value(value)
        if method=='count':return Decimal(len(_storage(receiver)['items'] if kind is _Array else _storage(receiver)['_items']))
        if method=='ubound':return Decimal(len(_storage(receiver)['items'])-1)
        if method=='get':return self.read_index(receiver,args[0])
        if method=='set':self.write_index(receiver,*args);return None
        if method=='clear':
            if kind is _Array:_storage(receiver)['items'].clear()
            elif _storage(receiver)['_items']:_storage(receiver)['_items'].clear();_storage(receiver)['_version']+=1
            return None
        if method=='property':
            if len(args)>1:raise UnsupportedCollection('Property output requires explicit reference-slot lowering')
            return self.property(receiver,args[0])[0]
        if kind is not _Array:
            if method=='insert':self._insert(receiver,args[0],args[1] if len(args)>1 else None)
            else:
                token=_map_key(args[0]) if kind is _Map else _structure_key(args[0])
                if token in _storage(receiver)['_items']:del _storage(receiver)['_items'][token];_storage(receiver)['_version']+=1
            return None
        items=_storage(receiver)['items']
        if method=='add':items.append(args[0] if args else None);return None
        if method=='find':
            for index,value in enumerate(items):
                if _equal(value,args[0]):return Decimal(index)
            return None
        position=_number(args[0])
        if not position.is_finite() or position!=position.to_integral_value():raise ValueError('Ожидается целое число')
        if position<0:raise IndexError('Индекс массива вне границ')
        if method=='delete':
            if position>=len(items):raise IndexError('Индекс массива вне границ')
            del items[int(position)];return None
        if position>=len(items)+_MAX_INSERT_GROWTH:
            raise ValueError('Вставить: превышен предел роста массива Yadinassi (1000000 элементов)')
        index=int(position);value=args[1] if len(args)>1 else None
        if index<len(items):items.insert(index,value)
        else:items.extend([None]*(index-len(items))+[value])
        return None
    def iterate(self,receiver):
        if not any(type(receiver) is kind for kind in _TYPES):
            raise TypeError('Для Каждого ожидает массив, структуру, соответствие или поддержанное пространство системного перечисления')
        kind=self._receiver(receiver)
        if kind is _Array:return iter(_storage(receiver)['items'])
        return self._iterate_pairs(receiver,kind)
    def _iterate_pairs(self,receiver,kind):
        version=_storage(receiver)['_version'];keys=iter(_storage(receiver)['_items'])
        while True:
            if version!=_storage(receiver)['_version']:
                noun='соответствия' if kind is _Map else 'структуры'
                raise ValueError(f'Изменение состава {noun} во время обхода пока не поддерживается')
            try:key=next(keys)
            except StopIteration:return
            pair=_new_storage(_Pair,dict(zip(('key','value'),_storage(receiver)['_items'][key])));self._owned[id(pair)]=ref(pair)
            if self.lease is not None:self.lease.owned_values.append(ref(pair))
            yield pair

RegionCollections=CollectionRegion
