"""Shared direct-AST runtime values and Program container.

No compiler entry point lives here. The historical text generator is isolated
in the test-only differential oracle; production compilation uses direct AST.
"""
import os
from dataclasses import dataclass, field
from decimal import Decimal
from .experimental_naked_boundaries import _HostMemberReference, _HostIndexReference, _MISSING, BoundaryViolation

from yadinassi.types.array_index import array_offset
from yadinassi.types.values import Reference as _CanonicalReference, BSLFixedArray as _CanonicalFixedArray
from yadinassi.collections.maps import _DIRECT_FIXED_MAP_SNAPSHOT
from yadinassi.collections.plain_value_list import _normalize_presentation, _normalize_check
from yadinassi.temporal.dates import _DIRECT_EQUALITY_DATE_STATE, UnsupportedDateRange

_MAP_DATE_TYPE, _MAP_DATE_BOUNDARY = _DIRECT_EQUALITY_DATE_STATE

_FIXED_MAP, _FIXED_MAP_STORAGE, _CANONICAL_VALUE_KEY_TYPES, _SINGLETON_KEY_TYPES = _DIRECT_FIXED_MAP_SNAPSHOT

def _canonical_reference(value):
    reference=_CanonicalReference(value.get,value.set)
    if type(value) is _CanonicalReference:
        lend=getattr(value,'_direct_lent_address',None)
        if lend is not None:reference._direct_lent_address=lend
    return reference

def _host_name_reference(getter,setter,name,storage=None):
    try:getter()
    except NameError:raise ValueError('Переменная или функция не определена: '+name) from None
    from .experimental_naked_live_state import _SlotReference, _ForwardReference
    result=_CanonicalReference(getter,setter)
    result._direct_name_sink=(storage is None or type(storage) in (_Cell,_SlotReference)
        or (type(storage) is _ForwardReference and type(storage.reference) is _CanonicalReference
            and getattr(storage.reference,'_direct_name_sink',False) is True))
    return result

def _host_omission_error():
    raise TypeError('Пропуск аргументов встроенных функций, методов и конструкторов пока не поддерживается')

def _host_omission_values(function, positions, count):
    prepare=getattr(function,'prepare_omissions',None)
    if prepare is None:_host_omission_error()
    return prepare(function,positions,count)

ENV='YADINASSI_UNSAFE_COLLECTION_ABLATION'

def _enabled():
    if os.environ.get(ENV)!='1':
        raise RuntimeError('unsafe collection ablation requires '+ENV+'=1')

class UnsupportedNakedSyntax(Exception):pass

def _native_property_missing(name):
    raise ValueError('Метод или свойство не найдено: '+name)

def _native_property_write_missing(name):
    raise ValueError('Свойство недоступно для записи: '+name)

def _invalid_native_arity(message):
    raise TypeError(message)

def _argument_count_error(name,expected,actual):
    raise TypeError(f"{name} ожидает {expected} аргументов, получено {actual}")

def _procedure_value_error(name):
    raise TypeError("Процедура не возвращает значение: "+name)

def _routine_value_error(name):
    raise TypeError("Процедуру или функцию необходимо вызвать: "+name)

@dataclass(frozen=True)
class _MapEntry:
    """Internal read-only iterator pair, never a generic host-object exemption."""
    key: object
    value: object


# Retain the definition identity before lazy direct service admission.
_DIRECT_MAP_ENTRY_TYPE = _MapEntry
_DIRECT_MAP_ENTRY_STORAGE = vars(_MapEntry)["__dict__"]


_ALIASES={'добавить':'add','вставить':'insert','получить':'get','установить':'set',
          'удалить':'delete','очистить':'clear','количество':'count','найти':'find',
          'вграница':'ubound','свойство':'property'}

# Named, independently selectable repairs. These are experiment variants, NOT a
# restoration of the production admission/runtime pipeline. Each repair has a
# specific reproduced failure; incomplete global contracts remain explicit.
REPAIRS=frozenset(('typed_map_keys','array_index_contract','array_insert_shape','constructor_bounds','byref_routines','error_boundaries','service_boundaries','authority_checkpoints','bsl_truth','bsl_presentation','native_order','uca_string_order','typed_find','structure_fields','method_values','dynamic_host_refs','resource_bounds','live_module_state','execute_fragments','array_identity_equality','structure_identity_equality','map_identity_equality','decimal_division','numeric_boolean_equality'))

class _NakedMap(dict):
    """Map kind only, needed for valid missing-key reference outputs."""

def _reject_opaque_date_key(key):
    if type(key) is not _MAP_DATE_TYPE:
        return
    try:boundary=_MAP_DATE_BOUNDARY.__get__(key,_MAP_DATE_TYPE)
    except AttributeError:
        raise BoundaryViolation('invalid exact date boundary state') from None
    if type(boundary) is not bool:
        raise BoundaryViolation('invalid exact date boundary state')
    if boundary:
        raise UnsupportedDateRange(
            'Дата: после выхода за диапазон известно только скалярное '
            'внутреннее представление; дальнейшая операция пока не поддерживается')

class _TypedMap(dict):
    @staticmethod
    def token(key):
        if type(key) is _MAP_DATE_TYPE:_reject_opaque_date_key(key)
        if type(key) is Decimal or type(key) is bool or type(key) is str or key is None:
            return type(key),key
        return object,id(key)
    def __init__(self,*args):
        dict.__init__(self)
        if not args:return
        if len(args)!=1:raise TypeError('Конструктор соответствия ожидает один аргумент')
        source=args[0]
        if type(source) is not _FIXED_MAP:
            raise TypeError('Конструктор соответствия ожидает фиксированное соответствие')
        state=_FIXED_MAP_STORAGE.__get__(source, _FIXED_MAP)
        items=dict.get(state, '_items')
        if type(items) is not dict:raise TypeError('Некорректное фиксированное соответствие')
        for token,entry in dict.items(items):
            if type(token) is not tuple or len(token)!=2 or type(entry) is not tuple or len(entry)!=2:
                raise TypeError('Некорректное фиксированное соответствие')
            key,value=entry;kind=type(key)
            if kind is str or kind is bool or kind is Decimal or kind is type(None):
                if token[0] is not kind or type(token[1]) is not kind or not (token[1] is key or token[1]==key):
                    raise TypeError('Некорректное фиксированное соответствие')
            elif any(kind is cls for cls in _SINGLETON_KEY_TYPES):
                if token[0] is not kind or token[1] is not key:
                    raise TypeError('Некорректное фиксированное соответствие')
                token=(object,id(key))
            elif any(kind is cls for cls in _CANONICAL_VALUE_KEY_TYPES) or token[0] is not object:
                # Date/UUID/descriptors use value equality in canonical maps,
                # unlike current direct identity keys. Never silently change it.
                raise TypeError('direct Map copy: canonical value-key semantics are not integrated')
            elif type(token[1]) is not int or token[1]!=id(key):
                raise TypeError('Некорректное фиксированное соответствие')
            dict.__setitem__(self,token,entry)
    def __setitem__(self,key,value):dict.__setitem__(self,self.token(key),(key,value))
    def __getitem__(self,key):return dict.__getitem__(self,self.token(key))[1]
    def __delitem__(self,key):
        # BSL Map.Delete is idempotent, including absent identity keys.
        dict.pop(self,self.token(key),None)
    def __contains__(self,key):return dict.__contains__(self,self.token(key))
    def get(self,key,default=None):
        entry=dict.get(self,self.token(key));return default if entry is None else entry[1]
    def items(self):return iter(dict.values(self))

_MAP_TYPE_IDS=(id(_NakedMap),id(_TypedMap))

def _checked_array_index(obj,key):
    if type(key) is not Decimal:raise TypeError('Ожидается число')
    if key!=key.to_integral_value():raise ValueError('Ожидается целое число')
    if key<0 or key>=len(obj):raise IndexError(f'Индекс массива вне границ: {key}')
    return int(key)

def _array_set_checked(obj,key,value):
    # Ordinary Python argument binding evaluates value before bounds validation.
    obj[array_offset(obj,key,method=True)]=value

def _array_set_raw(obj,key,value):
    obj[int(key)]=value

def _array_insert_shape(obj,key,value=None):
    if type(key) is not Decimal:raise TypeError('Ожидается число')
    if not key.is_finite() or key!=key.to_integral_value():raise ValueError('Ожидается целое число')
    if key<0:raise IndexError('Индекс массива вне границ')
    index=int(key)
    if index<len(obj):obj.insert(index,value)
    else:obj.extend([None]*(index-len(obj))+[value])

def _array_constructor_bounds(*sizes):
    if len(sizes)==1 and type(sizes[0]) is _CanonicalFixedArray:
        from .experimental_naked_resources import bounded_array
        return bounded_array(sizes[0])
    if not sizes:return []
    for size in sizes:
        if type(size) is not Decimal:raise TypeError('Ожидается число')
        if not size.is_finite() or size!=size.to_integral_value():raise ValueError('Ожидается целое число')
        if size<0:raise ValueError('Размер массива не может быть отрицательным')
    def build(depth):
        return ([None]*int(sizes[depth]) if depth==len(sizes)-1 else
                [build(depth+1) for _ in range(int(sizes[depth]))])
    return build(0)

class _Reference:
    def get(self):return self.value
    def set(self,value):self.value=value

_UNSET_REF=object()

class _Cell(_Reference):
    __slots__=('_value',)
    def __init__(self,value=_UNSET_REF):self._value=value
    @property
    def value(self):
        if self._value is _UNSET_REF:raise NameError('Uninitialized reference')
        return self._value
    @value.setter
    def value(self,value):self._value=value

def _bound_ref(value):
    # Missing actuals fail before entering the callee, without reading index refs.
    if type(value) is _Cell and value._value is _UNSET_REF:
        raise NameError('Uninitialized reference')
    return value

class _IndexRef(_Reference):
    __slots__=('owner','key','checked')
    def __init__(self,owner,key,checked=False):
        self.owner,self.key,self.checked=owner,key,checked
        self.value  # Argument binding validates before callee effects.
    def index(self):
        if isinstance(self.owner,list):
            return _checked_array_index(self.owner,self.key) if self.checked else int(self.key)
        return self.key
    @property
    def value(self):
        if id(type(self.owner)) in _MAP_TYPE_IDS:return self.owner.get(self.key)
        if type(self.owner) is dict and self.key not in self.owner:raise ValueError('Свойство структуры не найдено: '+str(self.key))
        return self.owner[self.index()]
    @value.setter
    def value(self,value):
        if type(self.owner) is dict and self.key not in self.owner:raise ValueError('Свойство структуры не найдено: '+str(self.key))
        self.owner[self.index()]=value

class _ValueListItemReference(_Reference):
    __slots__=('item','field')

    def __init__(self,item,name):
        from yadinassi.collections.plain_value_list import _field
        self.item=item
        try:self.field=_field(name)
        except AttributeError as exc:raise ValueError(str(exc)) from None
        if self.field == 3:
            raise ValueError('Свойство элемента списка недоступно для передачи по ссылке: '+name)
        item._require_live_owner()

    @property
    def value(self):
        self.item._require_live_owner()
        return self.item[self.field]

    @value.setter
    def value(self,value):
        self.item._require_live_owner()
        if self.field == 1:
            value = _normalize_presentation(value)
        elif self.field == 2:
            value = _normalize_check(value)
        self.item[self.field]=value

class _AttributeRef(_Reference):
    __slots__=('owner','name')
    def __init__(self,owner,name):
        self.owner,self.name=owner,name
        self.value
    @property
    def value(self):
        if id(type(self.owner)) in _MAP_TYPE_IDS:return _native_property_missing(self.name)
        if isinstance(self.owner,dict):
            if self.name not in self.owner:raise ValueError('Свойство структуры не найдено: '+self.name)
            return self.owner[self.name]
        return getattr(self.owner,self.name.casefold())
    @value.setter
    def value(self,value):
        if id(type(self.owner)) in _MAP_TYPE_IDS:return _native_property_write_missing(self.name)
        if isinstance(self.owner,dict):
            if self.name not in self.owner:raise ValueError('Свойство структуры не найдено: '+self.name)
            self.owner[self.name]=value
        else:setattr(self.owner,self.name.casefold(),value)

def _as_ref(value):return value if isinstance(value,(_Reference,_HostMemberReference,_HostIndexReference)) else _Cell(value)
_OMITTED_REF=object()

def _property_output(receiver,key,output):
    found=key in receiver
    output.value=receiver[key] if found else None
    return found

@dataclass
class Program:
    _generated_source: str | None
    constants: tuple
    function: object
    symbols: dict
    repairs: frozenset=frozenset()
    last_state: object=None
    output: object=None
    source_name: str="<naked-collection-experiment>"
    source_text: str=""
    required_services: tuple=()
    trusted_entry: bool=False
    _generated_tree: object=field(default=None, repr=False, compare=False)

    @property
    def generated_source(self):
        tree = self._generated_tree
        if tree is not None:
            import ast
            self._generated_source = ast.unparse(tree)
            self._generated_tree = None
        return '<generated source not retained>' if self._generated_source is None else self._generated_source

    def run(self,initial=None,*,context=None):
        if not self.trusted_entry:_enabled()
        if 'live_module_state' in self.repairs:
            from .experimental_naked_live_state import validate_state
            state=validate_state(initial)
        else:state={} if initial is None else {key.casefold():value for key,value in initial.items()}
        self.last_state=state;self.output=[]
        bounded=bool(self.repairs & {'service_boundaries','authority_checkpoints'})
        if bounded:
            if context is None:raise ValueError('explicit BoundaryContext required')
            context.enter()
        try:
            try:
                if bounded:return self.function(state,self.constants,self.output,context)
                return self.function(state,self.constants,self.output)
            finally:
                if bounded:
                    try:
                        if getattr(context,'_verify_context',True):context._check()
                    finally:context.leave()
        except Exception as error:
            if 'error_boundaries' not in self.repairs:raise
            from .experimental_naked_errors import convert_error
            converted=convert_error(error,self.source_name,self.source_text)
            if converted is error:raise
            raise converted from None
