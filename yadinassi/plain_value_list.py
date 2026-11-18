"""Lightweight ValueList storage for the direct backend, not the legacy adapter.

Values are references in four-position list records inside a native list. There is no owner
weakref, per-element ID dictionary, mutation revision, render cache or recursive
admission. Identifiers use one extra item slot and a monotonic list counter; lookup is linear.
Native Python ordering replaces 1C collation. Typed lists/UI/serialization remain
separate capabilities; this module does not grant access to them.
"""
from decimal import Decimal

_MAX_ITEMS = 100_000


def _item(item):
    if type(item) is not PlainValueListItem:
        raise TypeError('ValueList contains a foreign item')
    return item


def _index(index):
    if type(index) is not int and type(index) is not Decimal:
        raise TypeError('ValueList index requires a number')
    return int(index)


def _same(left, right):
    # Arbitrary stored objects may not run host comparison callbacks.
    if left is right:
        return True
    if (type(left) is str or type(left) is int or type(left) is Decimal
            or type(left) is bool or left is None) and type(right) is type(left):
        return left == right
    return False


class PlainValueListItem(list):
    """Four fixed native slots: value, presentation, check, picture.

    No per-instance dictionary, owner or field-property descriptors; one ID slot.
    Generated code addresses these slots directly.
    """
    __slots__ = ('_id',)

    def __eq__(self, other):
        return self is other

    def __ne__(self, other):
        return self is not other

    def get_id(self):
        if type(self._id) is not int: raise TypeError('Invalid ValueList item identifier')
        return Decimal(self._id)

    def get_member(self, name):
        return list.__getitem__(self, _field(name))

    def set_member(self, name, value):
        list.__setitem__(self, _field(name), value)


def _field(name):
    if type(name) is not str:
        raise TypeError('ValueList field name requires a string')
    try:
        return _FIELDS[name.casefold()]
    except KeyError:
        raise AttributeError('Unknown ValueList item field: ' + name) from None


_FIELDS = {'value': 0, 'значение': 0,
           'presentation': 1, 'представление': 1,
           'check': 2, 'пометка': 2, 'picture': 3, 'картинка': 3}


class PlainValueList(list):
    __slots__ = ('_next_id',)

    def __init__(self):
        list.__init__(self)
        self._next_id = 0

    @property
    def items(self):
        return self

    def __eq__(self, other):
        return self is other

    def __ne__(self, other):
        return self is not other

    def add(self, value=None, presentation='', check=False, picture=None):
        if len(self) >= _MAX_ITEMS: raise ValueError('ValueList item limit exceeded')
        item = PlainValueListItem((value, presentation, check, picture))
        if type(self._next_id) is not int: raise TypeError('Invalid ValueList identifier counter')
        item._id = self._next_id
        self._next_id += 1
        list.append(self, item)
        return item

    def insert(self, index, value=None, presentation='', check=False, picture=None):
        position = _index(index)
        if len(self) >= _MAX_ITEMS: raise ValueError('ValueList item limit exceeded')
        item = PlainValueListItem((value, presentation, check, picture))
        if type(self._next_id) is not int: raise TypeError('Invalid ValueList identifier counter')
        item._id = self._next_id
        self._next_id += 1
        list.insert(self, position, item)
        return item

    def get(self, index):
        return _item(list.__getitem__(self, _index(index)))

    def count(self):
        return Decimal(list.__len__(self))

    def index_of(self, item):
        for index, existing in enumerate(self):
            if existing is item:
                return Decimal(index)
        return Decimal(-1)

    def _position(self, item_or_index):
        if type(item_or_index) is PlainValueListItem:
            index = int(self.index_of(item_or_index))
            if index < 0:
                raise ValueError('ValueList item does not belong to this list')
            return index
        return _index(item_or_index)

    def delete(self, item_or_index):
        list.__delitem__(self, self._position(item_or_index))

    clear = list.clear

    def move(self, item_or_index, offset):
        position = self._position(item_or_index)
        shift = _index(offset)
        if position < 0:
            position += len(self)
        if not 0 <= position < len(self):
            raise IndexError('ValueList index out of bounds')
        item = list.pop(self, position)
        list.insert(self, max(0, min(position + shift, len(self))), item)

    def find_by_value(self, value):
        for item in self:
            if _same(_item(item)[0], value):
                return item
        return None

    def find_by_id(self, identifier):
        identifier = _index(identifier)
        for item in self:
            item_id = _item(item)._id
            if type(item_id) is not int: raise TypeError('Invalid ValueList item identifier')
            if item_id == identifier:
                return item
        return None

    def fill_checks(self, check):
        for item in self:
            _item(item)[2] = check

    def unload_values(self):
        return [_item(item)[0] for item in self]

    def load_values(self, values):
        # This is an explicit input boundary, not arbitrary iterable execution.
        from .python_direct_plain_array import PlainArray
        if type(values) is not list and type(values) is not PlainArray:
            raise TypeError('ValueList.LoadValues requires native array storage')
        if len(values) > _MAX_ITEMS: raise ValueError('ValueList item limit exceeded')
        self.clear()
        for value in values:
            self.add(value)

    def copy(self):
        result = PlainValueList()
        for item in self:
            _item(item)
            result.add(item[0], item[1], item[2], item[3])
        return result

    def sort_by_value(self, descending=False):
        self._sort(0, descending)

    def sort_by_presentation(self, descending=False):
        self._sort(1, descending)

    def _sort(self, field, descending):
        if type(descending) is not bool:
            raise TypeError('Plain ValueList sort direction requires a boolean')
        # Fail before list.sort can invoke arbitrary stored host hooks.
        for item in self:
            if type(item) is not PlainValueListItem:
                raise TypeError('ValueList contains a foreign item')
            kind = type(list.__getitem__(item, field))
            if kind is not str and kind is not int and kind is not Decimal and kind is not bool:
                raise TypeError('ValueList sorting requires scalar values')
        list.sort(self, key=lambda item: list.__getitem__(item, field), reverse=descending)


BSLValueList = PlainValueList
BSLValueListItem = PlainValueListItem
