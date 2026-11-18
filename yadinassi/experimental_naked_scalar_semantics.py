"""Optional pure algorithms for the isolated naked translator experiment.

No VM dispatch, ownership scan, or per-node guard. Exact supported values only:
host callbacks require an explicit boundary rather than accidental str/equality.
"""
from decimal import Decimal
from .strings import concatenate as _join
from .collation import _DIRECT_STRING_KEY_ABI as _string_key
from .dates import _DIRECT_EQUALITY_DATE_STATE, UnsupportedDateRange
from .values import NULL, to_string, _DIRECT_TYPE_PRESENTATIONS, _DIRECT_ARRAY_TYPE, _DIRECT_FIXED_ARRAY_TYPE, _DIRECT_FIXED_COLLECTION_TYPE, divide as _divide
from .structures import _DIRECT_FIXED_STRUCTURE_SNAPSHOT
from .maps import _DIRECT_FIXED_MAP_SNAPSHOT
from .experimental_naked_boundaries import BoundaryViolation
from .experimental_naked_collections import _NakedMap, _TypedMap
from .experimental_naked_structure import _DirectStructure


class UnsupportedScalarSemantics(BoundaryViolation):
    pass


_COLLECTION_TYPES = (list, dict, _NakedMap, _TypedMap, _DirectStructure)
_SCALAR_TYPES = (bool, Decimal, str, type(None))
_FIND_FIXED_TYPES = (_DIRECT_FIXED_ARRAY_TYPE, _DIRECT_FIXED_STRUCTURE_SNAPSHOT[0],
                     _DIRECT_FIXED_MAP_SNAPSHOT[0])


_SCALAR_TYPE_IDS=tuple(map(id,_SCALAR_TYPES))
_COLLECTION_TYPE_IDS=tuple(map(id,_COLLECTION_TYPES))
_SUPPORTED_TYPE_IDS=_SCALAR_TYPE_IDS+_COLLECTION_TYPE_IDS
_FIND_IDENTITY_TYPE_IDS=_COLLECTION_TYPE_IDS+tuple(map(id,_FIND_FIXED_TYPES))

_TYPE_PRESENTATIONS = {id(member): (member, label, error)
                       for member, label, error in _DIRECT_TYPE_PRESENTATIONS}

_TYPE_MRO = vars(type)['__mro__']

def _fixed_identity(value):
    # Bypass host metaclass attribute hooks; inspect ancestry, never payloads.
    return any(base is _DIRECT_FIXED_COLLECTION_TYPE
               for base in _TYPE_MRO.__get__(type(value)))


def truth(value):
    if type(value) is bool:
        return value
    if type(value) is Decimal:
        return value != 0
    raise TypeError('Ожидается булево значение или число')


def _supported(value):
    if id(type(value)) not in _SUPPORTED_TYPE_IDS and value is not NULL:
        raise UnsupportedScalarSemantics('host value requires an explicit scalar boundary')


def typed_find(array, value):
    if type(array) is not list:
        raise UnsupportedScalarSemantics('typed_find requires a native array')
    value_type = type(value)
    # Fixed collection descendants are opaque identity values, as in values.equal.
    # This grants no fields, methods, equality hooks or payload traversal.
    identity = id(value_type) in _FIND_IDENTITY_TYPE_IDS or _fixed_identity(value)
    if not identity:_supported(value)
    for index, item in enumerate(array):
        # Different exact types cannot compare equal and need no callback.
        if type(item) is value_type:
            if (item is value) if identity else (item == value):
                return Decimal(index)
    return None


def presentation(value):
    entry = _TYPE_PRESENTATIONS.get(id(value))
    if entry is not None and entry[0] is value:
        if entry[2] is not None:raise ValueError(entry[2])
        return entry[1]
    kind = type(value)
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
    return _join(left, presentation(right))


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
    if left_type is not right_type or not (left_type is Decimal or left_type is bool or left_type is str):
        raise TypeError('Значения несовместимы для сравнения')
    if operator == '<': return left < right
    if operator == '<=': return left <= right
    if operator == '>': return left > right
    if operator == '>=': return left >= right
    raise ValueError('ordering operator required')


def uca_order(left, right, operator):
    """Exact string ordering through the existing bounded, pinned UCA kernel."""
    if type(left) is not str or type(right) is not str:
        return order(left, right, operator)
    left_key, right_key = _string_key(left), _string_key(right)
    if operator == '<': return left_key < right_key
    if operator == '<=': return left_key <= right_key
    if operator == '>': return left_key > right_key
    if operator == '>=': return left_key >= right_key
    raise ValueError('ordering operator required')


_DATE_TYPE, _DATE_BOUNDARY_SLOT = _DIRECT_EQUALITY_DATE_STATE


def _array_date_check(value):
    if type(value) is _DATE_TYPE:
        boundary = _DATE_BOUNDARY_SLOT.__get__(value, _DATE_TYPE)
        if type(boundary) is not bool:
            raise UnsupportedScalarSemantics('invalid exact date boundary state')
        if boundary:
            raise UnsupportedDateRange(
                'Дата: после выхода за диапазон известно только скалярное '
                'внутреннее представление; дальнейшая операция пока не поддерживается')


def array_equal(left, right):
    """Direct Array and fixed-collection identity; no payload traversal.

    Different BSL kinds compare unequal (values.equal's existing type gate).
    Other operands keep their existing direct Python operator, including
    scalar conversion and explicitly supplied host equality behavior.
    """
    if type(left) is list or type(right) is list or _fixed_identity(left) or _fixed_identity(right):
        _array_date_check(left); _array_date_check(right)
        return left is right
    return left == right


def array_not_equal(left, right):
    if type(left) is list or type(right) is list or _fixed_identity(left) or _fixed_identity(right):
        _array_date_check(left); _array_date_check(right)
        return left is not right
    # Do not rewrite arbitrary __ne__ as not __eq__: this slice does not change
    # the pre-existing non-array operator contract.
    return left != right


def structure_equal(left, right):
    if type(left) is _DirectStructure or type(right) is _DirectStructure or _fixed_identity(left) or _fixed_identity(right):
        _array_date_check(left); _array_date_check(right)
        return left is right
    return left == right


def structure_not_equal(left, right):
    if type(left) is _DirectStructure or type(right) is _DirectStructure or _fixed_identity(left) or _fixed_identity(right):
        _array_date_check(left); _array_date_check(right)
        return left is not right
    return left != right


def collection_equal(left, right):
    """Exact direct Array/Structure identity, never recursive payload equality."""
    left_type,right_type=type(left),type(right)
    if (left_type is list or right_type is list or
            left_type is _DirectStructure or right_type is _DirectStructure or
            _fixed_identity(left) or _fixed_identity(right)):
        _array_date_check(left); _array_date_check(right)
        return left is right
    return left == right


def collection_not_equal(left, right):
    left_type,right_type=type(left),type(right)
    if (left_type is list or right_type is list or
            left_type is _DirectStructure or right_type is _DirectStructure or
            _fixed_identity(left) or _fixed_identity(right)):
        _array_date_check(left); _array_date_check(right)
        return left is not right
    return left != right


def map_identity_operators(*, array=False, structure=False):
    """Compile-time selection of exact Map identity, independent of other repairs."""
    def equal(left, right):
        left_type,right_type=type(left),type(right)
        if (left_type is _TypedMap or right_type is _TypedMap or
                (array and (left_type is list or right_type is list)) or
                (structure and (left_type is _DirectStructure or right_type is _DirectStructure)) or
                _fixed_identity(left) or _fixed_identity(right)):
            _array_date_check(left); _array_date_check(right)
            return left is right
        return left == right
    def not_equal(left, right):
        left_type,right_type=type(left),type(right)
        if (left_type is _TypedMap or right_type is _TypedMap or
                (array and (left_type is list or right_type is list)) or
                (structure and (left_type is _DirectStructure or right_type is _DirectStructure)) or
                _fixed_identity(left) or _fixed_identity(right)):
            _array_date_check(left); _array_date_check(right)
            return left is not right
        return left != right
    return equal,not_equal


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


def numeric_boolean_operators(equal=None, not_equal=None):
    """Boolean operator conversion is only for exact canonical Number/Boolean.

    Compose with selected collection repairs; unrelated host operators retain
    their prior eq/ne semantics and are never interchanged.
    """
    if equal is None:equal=lambda left,right:left==right
    if not_equal is None:not_equal=lambda left,right:left!=right
    def outside_boolean_domain(left,right):
        left_type,right_type=type(left),type(right)
        if left_type is bool or right_type is bool:
            _array_date_check(left);_array_date_check(right)
            return not ((left_type is bool or left_type is Decimal)
                        and (right_type is bool or right_type is Decimal))
        return False
    def compare_equal(left,right):
        if outside_boolean_domain(left,right):return False
        return equal(left,right)
    def compare_not_equal(left,right):
        if outside_boolean_domain(left,right):return True
        return not_equal(left,right)
    return compare_equal,compare_not_equal
