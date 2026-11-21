"""Direct Structure storage for the isolated translator, not a VM wrapper.

Only spelling/value and composition version are retained. Static dot access can
use already-folded keys; dynamic key operations validate only their own key.
"""
from yadinassi.text.strings import _WHITESPACE
from yadinassi.collections.structures import _DIRECT_FIXED_STRUCTURE_SNAPSHOT

_FIXED_STRUCTURE, _FIXED_STORAGE = _DIRECT_FIXED_STRUCTURE_SNAPSHOT

class _DirectStructure(dict):
    __slots__ = ('_version',)
    def __init__(self):
        dict.__init__(self)
        self._version = 0
    def __getitem__(self,name):return structure_get(self,name)
    def __setitem__(self,name,value):return structure_set(self,name,value)
    def __delitem__(self,name):return structure_delete(self,name)
    def __contains__(self,name):return dict.__contains__(self,structure_key(name))
    def get(self,name,default=None):
        key=structure_key(name)
        return dict.__getitem__(self,key)[1] if dict.__contains__(self,key) else default
    def items(self):return structure_items(self)
    def insert(self,name,value=None):return structure_insert(self,name,value)
    def clear(self):return structure_clear(self)
    def property(self,name,output=None):return structure_property(self,name,output)


def structure_key(name):
    if type(name) is not str:
        raise TypeError('Имя свойства структуры должно быть строкой')
    if (not name or not (name[0].isalpha() or name[0]=='_')
            or not all(char.isalnum() or char=='_' for char in name)):
        raise ValueError('Недопустимое имя свойства структуры: '+name)
    return name.casefold()


def new_structure(keys='', *values):
    if type(keys) is _FIXED_STRUCTURE:
        if values:raise TypeError('Копирование структуры ожидает один аргумент')
        # Read only exact canonical storage without invoking receiver hooks.
        # Validate names/container shape, never the shared payload values.
        state=_FIXED_STORAGE.__get__(keys, _FIXED_STRUCTURE)
        items=dict.get(state, '_items')
        if type(items) is not dict:raise TypeError('Некорректная фиксированная структура')
        for key,entry in dict.items(items):
            if (type(key) is not str or type(entry) is not tuple or len(entry)!=2
                    or type(entry[0]) is not str or structure_key(entry[0])!=key):
                raise TypeError('Некорректная фиксированная структура')
        result=_DirectStructure()
        dict.update(result,items)
        return result
    if type(keys) is not str:
        raise TypeError('Список свойств структуры должен быть строкой')
    result=_DirectStructure()
    names=[part.strip(_WHITESPACE) for part in keys.split(',') if part.strip(_WHITESPACE)]
    for index,name in enumerate(names):
        structure_insert(result,name,values[index] if index<len(values) else None)
    return result


def prepare_structure_schema(keys):
    """Compile literal field metadata; invalid literals keep runtime diagnostics."""
    fields={}
    names=[part.strip(_WHITESPACE) for part in keys.split(',') if part.strip(_WHITESPACE)]
    for index,name in enumerate(names):
        fields[structure_key(name)]=(name,index)
    return tuple((key,name,index) for key,(name,index) in fields.items())


def structure_from_schema(schema,*values):
    """Construct fresh storage from private compiler data, without key parsing."""
    result=_DirectStructure()
    dict.update(result,((key,(name,values[index] if index<len(values) else None))
                        for key,name,index in schema))
    result._version=len(schema)
    return result


def structure_get_known(value, key, spelling):
    if not dict.__contains__(value,key):raise ValueError('Свойство структуры не найдено: '+spelling)
    return dict.__getitem__(value,key)[1]


def structure_get(value,name):
    return structure_get_known(value,structure_key(name),name)


def structure_set_known(value,key,spelling,new_value):
    if not dict.__contains__(value,key):raise ValueError('Свойство структуры не найдено: '+spelling)
    old_name=dict.__getitem__(value,key)[0]
    dict.__setitem__(value,key,(old_name,new_value))


def structure_set(value,name,new_value):
    structure_set_known(value,structure_key(name),name,new_value)


def structure_insert(value,name,new_value=None):
    key=structure_key(name)
    if not dict.__contains__(value,key):value._version+=1
    dict.__setitem__(value,key,(name,new_value))


def structure_delete(value,name):
    key=structure_key(name)
    if dict.__contains__(value,key):
        dict.__delitem__(value,key);value._version+=1


def structure_clear(value):
    if value:dict.clear(value);value._version+=1


def structure_property(value,name,output=None):
    key=structure_key(name.strip(' ') if type(name) is str else name)
    found=dict.__contains__(value,key)
    if output is not None:output.set(dict.__getitem__(value,key)[1] if found else None)
    return found


def structure_items(value):
    """Yield original spelling/live values; reject composition changes only."""
    version=value._version;keys=iter(dict.keys(value))
    while True:
        if value._version!=version:
            raise ValueError('Изменение состава структуры во время обхода пока не поддерживается')
        try:key=next(keys)
        except StopIteration:return
        yield dict.__getitem__(value,key)
