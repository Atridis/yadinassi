"""Values and execution container shared by the direct BSL generator."""
from dataclasses import dataclass, field
from decimal import Decimal
from .direct_boundaries import BoundaryViolation

from yadinassi.types.values import Reference as _CanonicalReference
from yadinassi.collections.maps import _DIRECT_FIXED_MAP_SNAPSHOT
from yadinassi.collections.plain_value_list import _normalize_presentation, _normalize_check
from yadinassi.temporal.dates import _DIRECT_EQUALITY_DATE_STATE, UnsupportedDateRange

_MAP_DATE_TYPE, _MAP_DATE_BOUNDARY = _DIRECT_EQUALITY_DATE_STATE

_FIXED_MAP, _FIXED_MAP_STORAGE, _CANONICAL_VALUE_KEY_TYPES, _SINGLETON_KEY_TYPES = _DIRECT_FIXED_MAP_SNAPSHOT


def _host_name_reference(getter,setter,name,storage=None):
    try:getter()
    except NameError:raise ValueError('Переменная или функция не определена: '+name) from None
    from .direct_live_state import _SlotReference, _ForwardReference
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

class UnsupportedNakedSyntax(Exception):pass

def _argument_count_error(name,expected,actual):
    raise TypeError(f"{name} ожидает {expected} аргументов, получено {actual}")


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
    def __eq__(self, other):
        return self is other

    def __ne__(self, other):
        return self is not other

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


_OMITTED_REF=object()


@dataclass
class Program:
    _generated_source: str | None
    constants: tuple
    function: object
    last_state: object=None
    source_name: str="<direct>"
    source_text: str=""
    _generated_tree: object=field(default=None, repr=False, compare=False)

    @property
    def generated_source(self):
        tree = self._generated_tree
        if tree is not None:
            import ast
            self._generated_source = ast.unparse(tree)
            self._generated_tree = None
        return '<generated source not retained>' if self._generated_source is None else self._generated_source

    def run(self, initial, *, context):
        from .direct_live_state import validate_state
        from .direct_errors import convert_error

        state = validate_state(initial)
        self.last_state = state
        context.enter()
        try:
            try:
                return self.function(state, self.constants, context)
            finally:
                try:
                    if getattr(context, '_verify_context', True):
                        context._check()
                finally:
                    context.leave()
        except Exception as error:
            converted = convert_error(error, self.source_name, self.source_text, _context=context)
            if converted is error:
                raise
            raise converted from None
