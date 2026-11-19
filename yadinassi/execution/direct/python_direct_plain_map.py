"""Plain Python storage for direct Map construction.

Copy construction is an explicit canonical input boundary, not arbitrary Python
iterable expansion. Normal empty construction uses a dict subclass with native key/value storage.
"""
from yadinassi.collections.maps import BSLFixedMap
from decimal import Decimal
from .python_direct_numbers import public_number

_KEY_TYPES=(Decimal,str,bool,int,float,type(None))
_KEY_TYPE_IDS=frozenset(id(kind) for kind in _KEY_TYPES)

class PlainMap(dict):
    """Native storage, scalar keys; no type-tag tuples or wrapped values."""
    __slots__=()

    def __init__(self,*arguments,**keywords):
        dict.__init__(self)
        if arguments or keywords:self.update(*arguments,**keywords)

    def update(self,*arguments,**keywords):
        if len(arguments)>1:raise TypeError("Map.update expects at most one mapping")
        if arguments:
            source=arguments[0]
            if type(source) is not dict and type(source) is not PlainMap:
                raise TypeError("Map.update requires native mapping storage")
            for key,value in dict.items(source):self[key]=value
        for key,value in keywords.items():self[key]=value

    def setdefault(self,key,default=None):
        if id(type(key)) not in _KEY_TYPE_IDS:raise TypeError("Map key requires a scalar Python value")
        return dict.setdefault(self,key,default)

    def __ior__(self,other):
        self.update(other);return self

    def __eq__(self,other):return self is other

    def __ne__(self,other):return self is not other

    def __setitem__(self,key,value):
        if id(type(key)) not in _KEY_TYPE_IDS:raise TypeError("Map key requires a scalar Python value")
        dict.__setitem__(self,key,value)

    def get(self,key,default=None):
        if id(type(key)) not in _KEY_TYPE_IDS:raise TypeError("Map key requires a scalar Python value")
        return public_number(dict.get(self,key,default))

    __getitem__=get

    def __delitem__(self,key):
        if id(type(key)) not in _KEY_TYPE_IDS:raise TypeError("Map key requires a scalar Python value")
        dict.pop(self,key,None)

    def __contains__(self,key):
        if id(type(key)) not in _KEY_TYPE_IDS:raise TypeError("Map key requires a scalar Python value")
        return dict.__contains__(self,key)


def plain_map(*arguments):
    if not arguments:return PlainMap()
    if len(arguments)!=1:raise TypeError('Конструктор соответствия ожидает один аргумент')
    source=arguments[0]
    if type(source) is PlainFixedMap:
        result=PlainMap()
        dict.update(result,source._items)
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
    """Read-only shallow snapshot with the source's native Python key semantics."""
    __slots__=('_items',)

    def __init__(self, source):
        if type(source) is not PlainMap:
            raise TypeError('FixedMap requires an exact PlainMap')
        # Exact PlainMap's supported mutation API already enforces scalar keys.
        # Raw host mutation of its private storage is not a new admission route.
        self._items=MappingProxyType(dict.copy(source))

    def get(self,key):
        if id(type(key)) not in _KEY_TYPE_IDS:raise TypeError('Map key requires a scalar Python value')
        return public_number(self._items.get(key))

    def get_index(self,key):
        if id(type(key)) not in _KEY_TYPE_IDS:raise TypeError('Map key requires a scalar Python value')
        try:return public_number(self._items[key])
        except KeyError:raise ValueError('Ключ фиксированного соответствия не найден') from None

    def __iter__(self):
        for key,value in self._items.items():yield BSLKeyAndValue(public_number(key),public_number(value))

    def get_member(self,name):raise ValueError('Поле объекта не обнаружено: '+name)

    def get_method(self,name):
        key=name.casefold()
        if key in ('get','получить'):return HostFunction(name,self.get)
        if key in ('count','количество'):return HostFunction(name,lambda:Decimal(len(self._items)))
        raise ValueError('Метод соответствия не найден: '+name)

    def __str__(self):return 'ФиксированноеСоответствие'
