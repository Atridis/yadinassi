"""Lightweight ValueList storage for the direct backend, not the legacy adapter.

Values are kept in four-position records in a native list. Items share one
small membership record with a weak reference to their list. There is no ID
dictionary, separate mutation revision or recursive admission. Identifier lookup is linear.
Native Python ordering replaces 1C collation. Typed lists/UI/serialization remain
separate capabilities; this module does not grant access to them.
"""
from decimal import Decimal
from types import MappingProxyType
from weakref import ReferenceType, ref

from yadinassi.types.values import NULL, to_string
from yadinassi.temporal.dates import BSLDate, _exact_date_text
from .plain_table_storage import _sort_value
from .sort_directions import _sort_descending


def _normalize_presentation(value):
    kind = type(value)
    if kind is str:
        return value
    if value is None:
        return ""
    if kind is int:
        value = Decimal(value)
    elif kind is not Decimal:
        raise ValueError("Недопустимое представление элемента списка значений")
    return to_string(value)


def _normalize_check(value):
    kind = type(value)
    if kind is bool:
        return value
    if kind is int or (kind is Decimal and value.is_finite()):
        if value == 0:
            return False
        if value == 1:
            return True
    raise ValueError("Недопустимая пометка элемента списка значений")


_ITEM_NORMALIZERS = MappingProxyType({1: _normalize_presentation, 2: _normalize_check})

# Finite BSL call signatures for the native receiver arm. This is consumed
# when compiling a call, not consulted by an item or in a sort loop.
_METHODS = MappingProxyType({
    alias: (method, returns_value)
    for method, russian, returns_value in (
        ('add', 'добавить', True),
        ('get', 'получить', True),
        ('count', 'количество', True),
        ('insert', 'вставить', True),
        ('index_of', 'индекс', True),
        ('find_by_value', 'найтипозначению', True),
        ('find_by_id', 'найтипоидентификатору', True),
        ('unload_values', 'выгрузитьзначения', True),
        ('copy', 'скопировать', True),
        ('delete', 'удалить', False),
        ('clear', 'очистить', False),
        ('fill_checks', 'заполнитьпометки', False),
        ('load_values', 'загрузитьзначения', False),
        ('move', 'сдвинуть', False),
        ('sort_by_value', 'сортироватьпозначению', False),
        ('sort_by_presentation', 'сортироватьпопредставлению', False),
    )
    for alias in (method.replace('_', ''), russian)
})

def _item(item):
    if type(item) is not PlainValueListItem:
        raise TypeError('ValueList contains a foreign item')
    return item


def _scalar_item_sort_key(item):
    # Reuse the scalar ranks, not ValueTable's string collation.
    return _sort_value(list.__getitem__(_item(item), 0), python_string_order=True, unsupported=TypeError)


def _index(index, *, allow_boolean=False):
    kind = type(index)
    if kind is int:
        return index
    if kind is Decimal:
        return int(index)
    if kind is str:
        digits = index[1:] if index.startswith(('+', '-')) else index
        if digits.isascii() and digits.isdecimal():
            return int(index)
    if kind is bool and allow_boolean:
        return int(index)
    raise TypeError('ValueList index requires a number')


def _checked_position(position, stop):
    if not 0 <= position < stop:
        raise IndexError('ValueList index out of bounds')
    return position


def _same(left, right):
    # Arbitrary stored objects may not run host comparison callbacks.
    if left is right:
        return True
    if (type(left) is str or type(left) is int or type(left) is Decimal
            or type(left) is bool or left is None) and type(right) is type(left):
        return left == right
    return False


class _ItemMembership:
    __slots__ = ('owner', 'cleared_before')

    def __init__(self, owner):
        self.owner = ref(owner)
        # IDs are never reused. Clear/LoadValues detach the whole old range.
        self.cleared_before = 0


class PlainValueListItem(list):
    """Four fixed native slots: value, presentation, check, picture.

    No per-instance dictionary or field-property descriptors.
    Generated code addresses these slots directly.
    """
    __slots__ = ('_id', '_membership')

    def __str__(self):
        label = list.__getitem__(self, 1)
        if type(label) is not str:
            raise ValueError('Недопустимое представление элемента списка значений')
        if label:
            return label
        value = list.__getitem__(self, 0)
        if value is None or value is NULL:
            return '<Пустое значение>'
        kind = type(value)
        if kind is str:
            return value
        if kind is int:
            return to_string(Decimal(value))
        if kind is BSLDate:
            return _exact_date_text(value)
        if kind is Decimal or kind is bool:
            return to_string(value)
        # No object fallback: some values can invoke embedded Python formatters.
        raise ValueError('Строковое представление этого типа значения элемента пока не поддерживается')

    def __eq__(self, other):
        return self is other

    def __ne__(self, other):
        return self is not other

    def get_id(self):
        identifier = self._id
        if type(identifier) is not int: raise TypeError('Invalid ValueList item identifier')
        state = self._membership
        if type(state) is not _ItemMembership or type(state.cleared_before) is not int:
            raise TypeError('Invalid ValueList item membership')
        if identifier < state.cleared_before:
            return Decimal(-1)
        self._require_live_owner()
        return Decimal(identifier)

    def _require_live_owner(self):
        state = self._membership
        if type(state) is not _ItemMembership or type(state.owner) is not ReferenceType:
            raise TypeError('Invalid ValueList item membership')
        if state.owner() is None:
            raise ValueError('Список значений элемента освобождён')

    def get_member(self, name):
        return list.__getitem__(self, _field(name))

    def set_member(self, name, value):
        field = _field(name)
        normalizer = _ITEM_NORMALIZERS.get(field)
        list.__setitem__(self, field, value if normalizer is None else normalizer(value))


def _field(name):
    if type(name) is not str:
        raise TypeError('ValueList field name requires a string')
    try:
        return _FIELDS[name.casefold()]
    except KeyError:
        raise AttributeError('Unknown ValueList item field: ' + name) from None


_FIELDS = MappingProxyType({'value': 0, 'значение': 0,
           'presentation': 1, 'представление': 1,
           'check': 2, 'пометка': 2, 'picture': 3, 'картинка': 3})

_ITEM_TEXT = PlainValueListItem.__str__


class PlainValueList(list):
    __slots__ = ('_next_id', '_membership', '_text_cache', '__weakref__')

    def __init__(self):
        list.__init__(self)
        self._next_id = 0
        self._membership = None
        self._text_cache = None

    def __str__(self):
        # Native String retains even an empty warm result across item field
        # changes. Add/Insert already advance the identity counter, so those
        # hot paths need no cache invalidation or extra revision writes.
        serial, cached = self._next_id, self._text_cache
        if type(serial) is not int:
            raise TypeError('Invalid ValueList identifier counter')
        if (type(cached) is tuple and len(cached) == 2
                and type(cached[0]) is int and cached[0] == serial
                and type(cached[1]) is str):
            return cached[1]
        text = '; '.join(_ITEM_TEXT(_item(item)) for item in list.__iter__(self))
        self._text_cache = (serial, text)
        return text

    def _start_membership(self):
        state = self._membership = _ItemMembership(self)
        return state

    @property
    def items(self):
        return self

    def __eq__(self, other):
        return self is other

    def __ne__(self, other):
        return self is not other

    def add(self, value=None, presentation='', check=False, picture=None):
        item = PlainValueListItem((
            value,
            presentation if type(presentation) is str else _normalize_presentation(presentation),
            check if type(check) is bool else _normalize_check(check),
            picture,
        ))
        if type(self._next_id) is not int: raise TypeError('Invalid ValueList identifier counter')
        item._membership = self._membership or self._start_membership()
        item._id = self._next_id
        self._next_id += 1
        list.append(self, item)
        return item

    def insert(self, index, value=None, presentation='', check=False, picture=None):
        position = _checked_position(_index(index, allow_boolean=True), list.__len__(self) + 1)
        item = PlainValueListItem((
            value,
            presentation if type(presentation) is str else _normalize_presentation(presentation),
            check if type(check) is bool else _normalize_check(check),
            picture,
        ))
        if type(self._next_id) is not int: raise TypeError('Invalid ValueList identifier counter')
        item._membership = self._membership or self._start_membership()
        item._id = self._next_id
        self._next_id += 1
        list.insert(self, position, item)
        return item

    def get(self, index):
        position = _index(index)
        if position < 0:
            raise IndexError('ValueList index out of bounds')
        return _item(list.__getitem__(self, position))

    def get_index(self, index):
        kind = type(index)
        if kind is Decimal:
            if not index.is_finite() or index != index.to_integral_value():
                raise TypeError('ValueList bracket index requires an integer')
            index = int(index)
        elif kind is not int:
            raise TypeError('ValueList bracket index requires an integer')
        if index < 0:
            raise IndexError('ValueList index out of bounds')
        return _item(list.__getitem__(self, index))

    def count(self):
        return Decimal(list.__len__(self))

    def _index_of(self, item):
        for index, existing in enumerate(self):
            if existing is item:
                return index
        return -1

    def index_of(self, item):
        return Decimal(self._index_of(item))

    def _position(self, item_or_index):
        if type(item_or_index) is PlainValueListItem:
            index = self._index_of(item_or_index)
            if index < 0:
                raise ValueError('ValueList item does not belong to this list')
            return index
        return _index(item_or_index)

    def delete(self, item_or_index):
        position = _checked_position(self._position(item_or_index), list.__len__(self))
        item = _item(list.__getitem__(self, position))
        list.__delitem__(self, position)
        item._id = -1
        self._text_cache = None

    def clear(self):
        state = self._membership
        if state is not None:
            state.cleared_before = self._next_id
        self._text_cache = None
        list.clear(self)

    def move(self, item_or_index, offset):
        count = list.__len__(self)
        position = _checked_position(self._position(item_or_index), count)
        shift = _index(offset)
        destination = _checked_position(position + shift, count)
        if destination == position:
            return
        item = list.pop(self, position)
        list.insert(self, destination, item)
        self._text_cache = None

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
        check = _normalize_check(check)
        for item in self:
            _item(item)[2] = check

    def unload_values(self):
        return [_item(item)[0] for item in self]

    def load_values(self, values):
        # This is an explicit input boundary, not arbitrary iterable execution.
        from yadinassi.execution.direct.python_direct_plain_array import PlainArray
        if type(values) is not list and type(values) is not PlainArray:
            raise TypeError('ValueList.LoadValues requires native array storage')
        self.clear()
        for value in values:
            self.add(value)

    def copy(self):
        result = PlainValueList()
        for item in self:
            _item(item)
            result.add(item[0], item[1], item[2], item[3])
        return result

    def sort_by_value(self, direction=None):
        self._sort(0, direction)

    def sort_by_presentation(self, direction=None):
        self._sort(1, direction)

    def _sort(self, field, direction):
        descending = _sort_descending(direction)
        # Fail before list.sort can invoke arbitrary stored host hooks.
        prior = None
        for item in self:
            if type(item) is not PlainValueListItem:
                raise TypeError('ValueList contains a foreign item')
            kind = type(list.__getitem__(item, field))
            if kind is prior:
                continue
            simple = kind is str or kind is int or kind is Decimal or kind is bool
            if field == 0 and (not simple or (prior is not None and not
                    ((prior is int or prior is Decimal) and (kind is int or kind is Decimal)))):
                # Validate and sort detached item references before changing
                # the owner. Python's stable sort then preserves ties and IDs.
                ordered = sorted(list.__iter__(self), key=_scalar_item_sort_key, reverse=descending)
                list.__setitem__(self, slice(None), ordered)
                if len(ordered) > 1:
                    self._text_cache = None
                return
            if not simple:
                raise TypeError('ValueList sorting requires scalar values')
            prior = kind
        list.sort(self, key=lambda item: list.__getitem__(item, field), reverse=descending)
        # Both native singleton sorts preserve already warmed presentation.
        if list.__len__(self) > 1:
            self._text_cache = None


_DIRECT_PLAIN_METHODS = (PlainValueList.add, PlainValueList.insert, PlainValueList.get, PlainValueList.count)

BSLValueList = PlainValueList
BSLValueListItem = PlainValueListItem
