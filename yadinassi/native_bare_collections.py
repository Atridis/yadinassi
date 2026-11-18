"""Reconstructed minimal native collections; not an exact historical snapshot.

Trusted Python objects, native indexing/equality/errors. No legacy adaptation.
"""
class BareArray:
    __slots__ = ('_data',)
    def __init__(self, size=0, *dimensions):
        if dimensions:
            raise NotImplementedError('Multidimensional bare arrays are not implemented')
        self._data = [] if size == 0 else [None] * size
    def __len__(self): return len(self._data)
    def __iter__(self): return iter(self._data)
    def __getitem__(self, index): return self._data[index]
    def __setitem__(self, index, value): self._data[index] = value
    get = __getitem__
    set = __setitem__
    count = __len__
    def add(self, value=None): self._data.append(value)
    def insert(self, index, value=None): self._data.insert(index, value)
    def delete(self, index): del self._data[index]
    def clear(self): self._data.clear()
    def ubound(self): return len(self._data) - 1
    def find(self, value): return self._data.index(value)


from collections import namedtuple
from itertools import starmap

_ENTRY_FIELDS = {'key': 0, 'ключ': 0, 'value': 1, 'значение': 1}
_ITEM_FIELDS = {'value': 0, 'значение': 0, 'presentation': 1, 'представление': 1,
                'check': 2, 'пометка': 2, 'picture': 3, 'картинка': 3}


class BareMapEntry(namedtuple('_BareMapEntry', 'key value')):
    __slots__ = ()
    def get_member(self, name): return self[_ENTRY_FIELDS[name]]


class BareMap(dict):
    __slots__ = ()
    insert = dict.__setitem__
    set = dict.__setitem__
    def delete(self, key): dict.pop(self, key, None)
    def count(self): return len(self)
    def __iter__(self): return starmap(BareMapEntry, dict.items(self))
    def copy(self): return BareMap(dict.items(self))


class BareStructure(dict):
    """Canonical keys map directly to payloads; no spelling/value tuples."""
    __slots__ = ()
    def __init__(self, keys='', *values):
        dict.__init__(self)
        if isinstance(keys, dict):
            dict.update(self, ((key.casefold(), value) for key, value in dict.items(keys)))
        elif keys:
            for index, name in enumerate(keys.split(',')):
                self[name.strip().casefold()] = values[index] if index < len(values) else None
    # Internal compiler protocol already receives canonical names.
    get_member = dict.__getitem__
    set_member = dict.__setitem__
    def insert(self, name, value=None): self[name.casefold()] = value
    def get(self, name, default=None): return dict.get(self, name.casefold(), default)
    def set(self, name, value): self[name.casefold()] = value
    def delete(self, name): dict.pop(self, name.casefold(), None)
    def count(self): return len(self)
    def property(self, name, output=None):
        if output is not None:
            raise NotImplementedError('Bare Structure.Property output argument is unsupported')
        return name.casefold() in self
    def __iter__(self): return starmap(BareMapEntry, dict.items(self))
    def copy(self): return BareStructure(self)


class BareValueListItem(list):
    __slots__ = ()
    def get_member(self, name): return self[_ITEM_FIELDS[name]]
    def set_member(self, name, value): self[_ITEM_FIELDS[name]] = value
    get = list.__getitem__
    set = list.__setitem__
    def get_id(self):
        raise NotImplementedError('Bare ValueList item identifiers are unsupported')


class BareValueList(list):
    __slots__ = ()
    def add(self, value=None, presentation='', check=False, picture=None):
        item = BareValueListItem((value, presentation, check, picture))
        list.append(self, item)
        return item
    def insert(self, index, value=None, presentation='', check=False, picture=None):
        item = BareValueListItem((value, presentation, check, picture))
        list.insert(self, index, item)
        return item
    get = list.__getitem__
    set = list.__setitem__
    delete = list.__delitem__
    def count(self): return len(self)
    def index_of(self, item): return list.index(self, item)
    def find_by_value(self, value):
        return next((item for item in self if item[0] == value), None)
    def find_by_id(self, identifier):
        raise NotImplementedError('Bare ValueList item identifiers are unsupported')
    def fill_checks(self, check):
        for item in self: item[2] = check
    def unload_values(self):
        # Allocate only the returned storage, not an empty list followed by a copy.
        result = object.__new__(BareArray)
        result._data = [item[0] for item in self]
        return result
    def load_values(self, values):
        self.clear()
        self.extend(BareValueListItem((value, '', False, None)) for value in values)
    def copy(self): return BareValueList(BareValueListItem(item) for item in self)
    def sort_by_value(self, descending=False):
        list.sort(self, key=lambda item: item[0], reverse=descending)
    def sort_by_presentation(self, descending=False):
        list.sort(self, key=lambda item: item[1], reverse=descending)
    def move(self, index, offset):
        item = list.pop(self, index)
        list.insert(self, index + offset, item)
