"""Optional pure algorithms for the isolated naked translator experiment.

No VM dispatch, ownership scan, or per-node guard. Exact supported values only:
host callbacks require an explicit boundary rather than accidental str/equality.
"""
from yadinassi.execution.direct.python_direct_plain_array import _DIRECT_PLAIN_ARRAY_TYPE as _PlainArray
from decimal import Decimal
from yadinassi.text.strings import concatenate as _join
from yadinassi.text.chars import CHARS
from yadinassi.temporal.dates import _DIRECT_EQUALITY_DATE_STATE, _DIRECT_ORDER_DATE_TICKS, UnsupportedDateRange
from yadinassi.types.unique_identifiers import BSLUUID
from yadinassi.types.values import BSLType, NULL, to_string, _DIRECT_TYPE_PRESENTATIONS, _DIRECT_ARRAY_TYPE, _DIRECT_FIXED_ARRAY_TYPE, _DIRECT_FIXED_COLLECTION_TYPE, divide as _divide
from yadinassi.collections.structures import _DIRECT_FIXED_STRUCTURE_SNAPSHOT
from yadinassi.collections.search_directions import BSLSearchDirection
from yadinassi.collections.sort_directions import BSLSortDirection
from yadinassi.numeric.round_modes import BSLRoundMode
from yadinassi.collections.maps import _DIRECT_FIXED_MAP_SNAPSHOT
from .direct_boundaries import BoundaryViolation
from .direct_collections import _NakedMap, _TypedMap
from .direct_structure import _DirectStructure


class TextAddend:
    """Only string-left addition differs from Python's native operation."""
    __slots__ = ('text',)

    def __init__(self, text):
        self.text = text

    def __add__(self, right):
        return concatenate(self.text, right)


class UnsupportedScalarSemantics(BoundaryViolation):
    pass


_COLLECTION_TYPES = (list, dict, _NakedMap, _TypedMap, _DirectStructure)
_SCALAR_TYPES = (bool, Decimal, str, type(None))
_FIND_IDENTITY_TYPES = (_DIRECT_FIXED_ARRAY_TYPE, _DIRECT_FIXED_STRUCTURE_SNAPSHOT[0],
                        _DIRECT_FIXED_MAP_SNAPSHOT[0], BSLSearchDirection, BSLSortDirection,
                        BSLRoundMode, BSLType)


_SCALAR_TYPE_IDS=tuple(map(id,_SCALAR_TYPES))
_COLLECTION_TYPE_IDS=tuple(map(id,_COLLECTION_TYPES))
_SUPPORTED_TYPE_IDS=_SCALAR_TYPE_IDS+_COLLECTION_TYPE_IDS
_FIND_DIRECT_COLLECTION_IDS = frozenset(map(id, (
    _PlainArray, _NakedMap, _TypedMap, _DirectStructure,
)))
_FIND_IDENTITY_TYPE_IDS=frozenset(_COLLECTION_TYPE_IDS+tuple(map(id,_FIND_IDENTITY_TYPES))) | _FIND_DIRECT_COLLECTION_IDS

_TYPE_PRESENTATIONS = {id(member): (member, label, error)
                       for member, label, error in _DIRECT_TYPE_PRESENTATIONS}
# An admitted non-stringable singleton, not a generic call to host __str__.
_TYPE_PRESENTATIONS[id(CHARS)] = (
    CHARS, None, 'Строковое представление пространства Символы пока не поддерживается')

_UUID_TEXT = vars(BSLUUID)['text']
_TYPE_MRO = vars(type)['__mro__']

def _fixed_identity(value):
    # Bypass host metaclass attribute hooks; inspect ancestry, never payloads.
    return any(base is _DIRECT_FIXED_COLLECTION_TYPE
               for base in _TYPE_MRO.__get__(type(value)))


def truth(value):
    kind = type(value)
    if kind is bool:
        return value
    if kind is int or kind is Decimal:
        return value != 0
    raise TypeError('Ожидается булево значение или число')


def _supported(value):
    if id(type(value)) not in _SUPPORTED_TYPE_IDS and value is not NULL:
        raise UnsupportedScalarSemantics('host value requires an explicit scalar boundary')


def find_by_identity(items, needle):
    # Both call sites pass exact list/PlainArray or verified exact tuple storage.
    sequence = tuple.__iter__(items) if type(items) is tuple else list.__iter__(items)
    for index, item in enumerate(sequence):
        if item is needle:
            return Decimal(index)
    return None


def find_date(items, needle):
    """Find an exact Date by BSL ticks without invoking Python equality hooks."""
    ticks = _date_order_ticks(needle)
    sequence = tuple.__iter__(items) if type(items) is tuple else list.__iter__(items)
    for index, item in enumerate(sequence):
        if type(item) is _DATE_TYPE and _date_order_ticks(item) == ticks:
            return Decimal(index)
    return None


def typed_find(array, value):
    if type(array) is not list and type(array) is not _PlainArray:
        raise UnsupportedScalarSemantics('typed_find requires a native array')
    value_type = type(value)
    if value_type is _DATE_TYPE:
        return find_date(array, value)
    if value_type is BSLUUID:
        # The UUID is a value, unlike a collection. Read only its exact slot;
        # never invoke comparison on a malformed or foreign host value.
        needle = _UUID_TEXT.__get__(value, BSLUUID)
        if type(needle) is not str:
            raise UnsupportedScalarSemantics('invalid UUID text')
        for index, item in enumerate(list.__iter__(array)):
            if type(item) is BSLUUID:
                text = _UUID_TEXT.__get__(item, BSLUUID)
                if type(text) is not str:
                    raise UnsupportedScalarSemantics('invalid UUID text')
                if text == needle:
                    return Decimal(index)
        return None
    # Fixed descendants and the admitted enum singletons use identity.
    # This grants no fields, methods, equality hooks or payload traversal.
    if id(value_type) in _FIND_IDENTITY_TYPE_IDS or _fixed_identity(value):
        return find_by_identity(array,value)
    if id(value_type) not in _SUPPORTED_TYPE_IDS and value is not NULL:
        # PlainMap imports numeric helpers from this module. Resolve its
        # definition-time identities only on the non-scalar needle path.
        from yadinassi.execution.direct.python_direct_plain_map import _DIRECT_PLAIN_MAP_FIND_TYPES
        mutable, fixed = _DIRECT_PLAIN_MAP_FIND_TYPES
        if value_type is mutable or value_type is fixed:
            return find_by_identity(array,value)
        _supported(value)
    for index, item in enumerate(list.__iter__(array)):
        # Different exact types cannot compare equal and need no callback.
        if type(item) is value_type and item == value:
            return Decimal(index)
    return None


def presentation(value):
    entry = _TYPE_PRESENTATIONS.get(id(value))
    if entry is not None and entry[0] is value:
        if entry[2] is not None:raise ValueError(entry[2])
        return entry[1]
    kind = type(value)
    if kind is int:
        return to_string(Decimal(value))
    if kind is list or any(base is _DIRECT_ARRAY_TYPE for base in _TYPE_MRO.__get__(kind)):
        return 'Массив'
    if (kind is _NakedMap or kind is _TypedMap):
        return 'Соответствие'
    if (kind is dict or kind is _DirectStructure):
        return 'Структура'
    if id(kind) in _SCALAR_TYPE_IDS or value is NULL:
        return to_string(value)
    raise UnsupportedScalarSemantics('host presentation requires an explicit service boundary')


def concatenate(left, right):
    if type(left) is not str:
        raise TypeError('Ожидается строка')
    return _join(left, right if type(right) is str else presentation(right))


def order(left, right, operator):
    """Native Python string ordering by explicit experiment policy, not UCA.

    Retain scalar type admission: unknown host comparison callbacks are not
    implicitly invoked. Equality, Map keys and typed Find remain independent.
    """
    left_type, right_type = type(left), type(right)
    if left_type is bool and right_type is Decimal:
        left = Decimal(int(left)); left_type = Decimal
    elif left_type is Decimal and right_type is bool:
        right = Decimal(int(right)); right_type = Decimal
    if left_type is not right_type:
        raise TypeError('Значения несовместимы для сравнения')
    if not (left_type is Decimal or left_type is bool or left_type is str):
        if left_type is not _DATE_TYPE:
            raise TypeError('Значения несовместимы для сравнения')
        left, right = _date_order_ticks(left), _date_order_ticks(right)
    if operator == '<': return left < right
    if operator == '<=': return left <= right
    if operator == '>': return left > right
    if operator == '>=': return left >= right
    raise ValueError('ordering operator required')


_DATE_TYPE, _DATE_BOUNDARY_SLOT = _DIRECT_EQUALITY_DATE_STATE
_DATE_TICKS_SLOT, _DATE_MAX_TICKS = _DIRECT_ORDER_DATE_TICKS


def _date_order_ticks(value):
    # Exact Date operands only. Read the canonical integer slots, not the
    # Python comparison methods or replaceable class-level properties.
    try:
        ticks = _DATE_TICKS_SLOT.__get__(value, _DATE_TYPE)
        boundary = _DATE_BOUNDARY_SLOT.__get__(value, _DATE_TYPE)
    except AttributeError:
        raise UnsupportedScalarSemantics('invalid exact date ordering state') from None
    if (type(ticks) is not int or not 0 <= ticks <= _DATE_MAX_TICKS
            or type(boundary) is not bool or (boundary and ticks not in (0, _DATE_MAX_TICKS))):
        raise UnsupportedScalarSemantics('invalid exact date ordering state')
    if boundary:
        _raise_unproven_date_range()
    return ticks


def _raise_unproven_date_range():
    raise UnsupportedDateRange(
        'Дата: после выхода за диапазон известно только скалярное '
        'внутреннее представление; дальнейшая операция пока не поддерживается')


def decimal_divide(left, right):
    """Pure bounded native-observed division, never host arithmetic dispatch."""
    if type(left) is not Decimal or type(right) is not Decimal:
        raise TypeError('Ожидается число')
    return _divide(left, right)


def decimal_sign(value, operator):
    """A sign changes no precision; Decimal unary +/- would use host context."""
    if type(value) is not Decimal:
        raise TypeError('Ожидается число')
    return value.copy_negate() if operator == '-' else value
