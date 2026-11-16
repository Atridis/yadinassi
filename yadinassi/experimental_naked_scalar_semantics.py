"""Optional pure algorithms for the isolated naked translator experiment.

No VM dispatch, ownership scan, or per-node guard. Exact supported values only:
host callbacks require an explicit boundary rather than accidental str/equality.
"""
from decimal import Decimal
from .strings import concatenate as _join
from .values import NULL, to_string
from .experimental_naked_boundaries import BoundaryViolation
from .experimental_naked_collections import _NakedMap, _TypedMap
from .experimental_naked_structure import _DirectStructure


class UnsupportedScalarSemantics(BoundaryViolation):
    pass


_COLLECTION_TYPES = (list, dict, _NakedMap, _TypedMap, _DirectStructure)
_SCALAR_TYPES = (bool, Decimal, str, type(None))


_SCALAR_TYPE_IDS=tuple(map(id,_SCALAR_TYPES))
_COLLECTION_TYPE_IDS=tuple(map(id,_COLLECTION_TYPES))
_SUPPORTED_TYPE_IDS=_SCALAR_TYPE_IDS+_COLLECTION_TYPE_IDS

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
    _supported(value)
    value_type = type(value)
    identity = id(value_type) in _COLLECTION_TYPE_IDS
    for index, item in enumerate(array):
        # Different exact types cannot compare equal and need no callback.
        if type(item) is value_type:
            if (item is value) if identity else (item == value):
                return Decimal(index)
    return None


def presentation(value):
    kind = type(value)
    if kind is list:
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
