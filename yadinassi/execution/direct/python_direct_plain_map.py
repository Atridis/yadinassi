"""Plain Python storage for direct Map construction.

Copy construction is an explicit canonical input boundary, not arbitrary Python
iterable expansion. Keep scalar keys in the native dict; only exact supported
collection keys use opaque identity storage.
"""
from yadinassi.collections.maps import BSLFixedMap
from yadinassi.collections.structures import BSLFixedStructure
from yadinassi.execution.codegen.experimental_naked_structure import _DirectStructure
from .python_direct_plain_array import PlainArray
from yadinassi.collections.search_directions import BSLSearchDirection
from yadinassi.numeric.round_modes import BSLRoundMode
from yadinassi.temporal.dates import BSLDate, MAX_TICKS, _DIRECT_EQUALITY_DATE_STATE
from yadinassi.execution.codegen.experimental_naked_boundaries import BoundaryViolation
from yadinassi.types.values import BSLFixedArray, BSLNull, BSLType
from yadinassi.execution.codegen.experimental_naked_collections import _reject_opaque_date_key
from collections.abc import ItemsView, KeysView
from decimal import Decimal
from reprlib import recursive_repr
from .python_direct_numbers import public_number

_KEY_TYPES=(Decimal,str,int,float,type(None),BSLSearchDirection,BSLRoundMode,BSLNull,BSLType)
_KEY_TYPE_IDS=frozenset(id(kind) for kind in _KEY_TYPES)

_DATE_TICKS = vars(BSLDate)['ticks']
_DATE_BOUNDARY = _DIRECT_EQUALITY_DATE_STATE[1]
_DATE_HASH, _DATE_EQ, _DATE_KNOWN = BSLDate.__hash__, BSLDate.__eq__, BSLDate.require_known


_TRUE_KEY, _FALSE_KEY = object(), object()
_MISSING = object()


def native_map_storage_key(key):
    """Encode a Boolean; all other keys must already have been admitted."""
    return _TRUE_KEY if key is True else _FALSE_KEY if key is False else key


class _IdentityKey:
    """Retain the original object. Dict operations only observe its identity."""
    __slots__ = ("value",)

    def __init__(self, value):
        self.value = value

    def __hash__(self):
        return id(self.value)

    def __eq__(self, other):
        return type(other) is _IdentityKey and self.value is other.value


def native_map_public_key(key):
    if type(key) is _IdentityKey:
        return key.value
    return True if key is _TRUE_KEY else False if key is _FALSE_KEY else key


def native_map_items(storage, has_identity_keys=False):
    pairs = dict.items(storage)
    if (not has_identity_keys and not (type(storage) is PlainMap and storage._identity_keys)
            and not dict.__contains__(storage, _TRUE_KEY) and not dict.__contains__(storage, _FALSE_KEY)):
        return pairs
    return ((native_map_public_key(key), value) for key, value in pairs)


def _admit_extended_key(key):
    if key is True:
        return _TRUE_KEY
    if key is False:
        return _FALSE_KEY
    # Ordinary native keys do not take this path. Only known dates can be
    # hashed by ticks; detect even malformed host state before dict hashing.
    if type(key) is BSLDate:
        _reject_opaque_date_key(key)
        attributes = vars(BSLDate)
        if (attributes.get('__hash__') is not _DATE_HASH or attributes.get('__eq__') is not _DATE_EQ
                or attributes.get('require_known') is not _DATE_KNOWN
                or BSLDate.__getattribute__ is not object.__getattribute__
                or attributes.get('ticks') is not _DATE_TICKS or attributes.get('boundary') is not _DATE_BOUNDARY):
            raise BoundaryViolation('date key hooks changed')
        try:
            ticks = _DATE_TICKS.__get__(key, BSLDate)
        except AttributeError:
            raise BoundaryViolation('invalid exact date key state') from None
        if type(ticks) is not int or not 0 <= ticks <= MAX_TICKS:
            raise BoundaryViolation('invalid exact date key state')
        return key
    if id(type(key)) in _IDENTITY_KEY_TYPE_IDS:
        return _IdentityKey(key)
    raise TypeError("Map key requires a scalar Python value")

class _PlainMapItems(ItemsView):
    def __iter__(self):
        return iter(native_map_items(self._mapping))

    def __contains__(self, item):
        key, value = item
        stored_key = key if id(type(key)) in _KEY_TYPE_IDS else _admit_extended_key(key)
        stored = dict.get(self._mapping, stored_key, _MISSING)
        return stored is not _MISSING and (stored is value or stored == value)


class PlainMap(dict):
    """Native storage with a separate Boolean key domain.

    Normal mapping iteration/views expose logical keys. Unbound dict methods
    are private storage operations here. Converting to a Python dict cannot
    represent both a Boolean and its equal-in-Python number key.
    """
    __slots__=('_identity_keys',)

    def __init__(self,*arguments,**keywords):
        dict.__init__(self)
        # Monotonic hint; avoid scanning the map after Delete/Clear.
        self._identity_keys=False
        if arguments or keywords:self.update(*arguments,**keywords)

    def update(self,*arguments,**keywords):
        if len(arguments)>1:raise TypeError("Map.update expects at most one mapping")
        if arguments:
            source=arguments[0]
            if type(source) is not dict and type(source) is not PlainMap:
                raise TypeError("Map.update requires native mapping storage")
            pairs = native_map_items(source) if type(source) is PlainMap else dict.items(source)
            for key,value in pairs:self[key]=value
        for key,value in keywords.items():self[key]=value

    def setdefault(self,key,default=None):
        if id(type(key)) not in _KEY_TYPE_IDS:
            key=_admit_extended_key(key)
            if type(key) is _IdentityKey:self._identity_keys=True
        return dict.setdefault(self,key,default)

    def __ior__(self,other):
        self.update(other);return self

    @recursive_repr()
    def __repr__(self):
        if not self._identity_keys and not dict.__contains__(self, _TRUE_KEY) and not dict.__contains__(self, _FALSE_KEY):
            return dict.__repr__(self)
        return '{' + ', '.join(f'{key!r}: {value!r}' for key,value in native_map_items(self)) + '}'

    def __iter__(self):
        return (native_map_public_key(key) for key in dict.__iter__(self))

    def __reversed__(self):
        return (native_map_public_key(key) for key in dict.__reversed__(self))

    def keys(self):
        return KeysView(self)

    def items(self):
        return _PlainMapItems(self)

    def copy(self):
        result=PlainMap()
        dict.update(result,dict.items(self))
        result._identity_keys=self._identity_keys
        return result

    def pop(self,key,*default):
        if id(type(key)) not in _KEY_TYPE_IDS:key=_admit_extended_key(key)
        return dict.pop(self,key,*default)

    def popitem(self):
        key,value=dict.popitem(self)
        return native_map_public_key(key),value

    def __or__(self,other):
        if type(other) is not dict and type(other) is not PlainMap:return NotImplemented
        result=self.copy();result.update(other)
        return result

    def __ror__(self,other):
        if type(other) is not dict and type(other) is not PlainMap:return NotImplemented
        result=PlainMap(other);result.update(self)
        return result

    def __eq__(self,other):return self is other

    def __ne__(self,other):return self is not other

    def __setitem__(self,key,value):
        if id(type(key)) not in _KEY_TYPE_IDS:
            key=_admit_extended_key(key)
            if type(key) is _IdentityKey:self._identity_keys=True
        dict.__setitem__(self,key,value)

    def get(self,key,default=None):
        if id(type(key)) not in _KEY_TYPE_IDS:key=_admit_extended_key(key)
        return public_number(dict.get(self,key,default))

    __getitem__=get

    def __delitem__(self,key):
        if id(type(key)) not in _KEY_TYPE_IDS:key=_admit_extended_key(key)
        dict.pop(self,key,None)

    def __contains__(self,key):
        if id(type(key)) not in _KEY_TYPE_IDS:key=_admit_extended_key(key)
        return dict.__contains__(self,key)


def plain_map(*arguments):
    if not arguments:return PlainMap()
    if len(arguments)!=1:raise TypeError('Конструктор соответствия ожидает один аргумент')
    source=arguments[0]
    if type(source) is PlainFixedMap:
        result=PlainMap()
        dict.update(result,source._items)
        result._identity_keys=source._identity_keys
        return result
    if type(source) is not BSLFixedMap:
        raise TypeError('Конструктор соответствия ожидает фиксированное соответствие')
    items=object.__getattribute__(source,'_items')
    if type(items) is not dict:raise TypeError('Некорректное фиксированное соответствие')
    result=PlainMap()
    for entry in dict.values(items):
        if type(entry) is not tuple or len(entry)!=2:
            raise TypeError('Некорректное фиксированное соответствие')
        key,value=entry
        result[key]=value
    return result


from types import MappingProxyType
from yadinassi.collections.structures import BSLKeyAndValue
from yadinassi.types.values import HostFunction

class PlainFixedMap:
    """Read-only shallow snapshot with the source's direct key semantics."""
    __slots__=('_items','_snapshot','_identity_keys')

    def __init__(self, source):
        if type(source) is not PlainMap:
            raise TypeError('FixedMap requires an exact PlainMap')
        # Exact PlainMap's mutation API enforces supported keys.
        # Raw host mutation of its private storage is not a new admission route.
        # PlainMap decodes logical keys in its mapping protocol. A plain
        # dict copy through that protocol would collapse True and Number(1).
        snapshot = dict(dict.items(source))
        self._items=MappingProxyType(snapshot)
        self._identity_keys=source._identity_keys
        # A codec can read the exact underlying dict with its native slots,
        # without running iteration on a host-provided mapping proxy.
        self._snapshot=snapshot

    def get(self,key):
        if id(type(key)) not in _KEY_TYPE_IDS:key=_admit_extended_key(key)
        return public_number(self._items.get(key))

    def get_index(self,key):
        if id(type(key)) not in _KEY_TYPE_IDS:key=_admit_extended_key(key)
        try:return public_number(self._items[key])
        except KeyError:raise ValueError('Ключ фиксированного соответствия не найден') from None

    def __iter__(self):
        for key,value in native_map_items(self._snapshot, self._identity_keys):yield BSLKeyAndValue(public_number(key),public_number(value))

    def get_member(self,name):raise ValueError('Поле объекта не обнаружено: '+name)

    def get_method(self,name):
        key=name.casefold()
        if key in ('get','получить'):return HostFunction(name,self.get)
        if key in ('count','количество'):return HostFunction(name,lambda:Decimal(len(self._items)))
        raise ValueError('Метод соответствия не найден: '+name)

    def __str__(self):return 'ФиксированноеСоответствие'


_DIRECT_FIXED_MAP_STORAGE = vars(PlainFixedMap)['_snapshot']

# Identity keys confer no new receiver or payload operations.
_IDENTITY_KEY_TYPES = (list, PlainArray, _DirectStructure, PlainMap,
                       BSLFixedArray, BSLFixedStructure, PlainFixedMap)
_IDENTITY_KEY_TYPE_IDS = frozenset(id(kind) for kind in _IDENTITY_KEY_TYPES)
