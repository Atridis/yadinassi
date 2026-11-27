"""Direct methods on canonical boxed Array storage."""
from decimal import Decimal

from yadinassi.execution.codegen.direct_boundaries import BoundaryViolation
from yadinassi.types.direct_method_names import DirectMethodNames
from yadinassi.types.values import BSLObject, BSLArray, BSLFixedArray


_STATE = vars(BSLObject)['__dict__']


class BoxedArrayMethods(DirectMethodNames):
    __slots__ = ('items',)

    def __init__(self, value, kind, storage_type):
        state = _STATE.__get__(value, kind)
        if type(state) is not dict or len(state) != 1:
            raise BoundaryViolation('boxed array method storage changed')
        key, = state
        if type(key) is not str or key != 'items' or type(state[key]) is not storage_type:
            raise BoundaryViolation('boxed array method storage changed')
        self.items = state[key]

    def _bsl_value_count(self):
        return Decimal(len(self.items))

    def _bsl_value_ubound(self):
        return Decimal(len(self.items) - 1)

    _bsl_proc_count = _bsl_value_count
    _bsl_proc_ubound = _bsl_value_ubound


class FixedArrayMethods(BoxedArrayMethods):
    __slots__ = ()

    def __init__(self, value):
        super().__init__(value, BSLFixedArray, tuple)

    def _bsl_value_get(self, index):
        kind = type(index)
        if kind is Decimal:
            if not index.is_finite() or index != index.to_integral_value():
                raise ValueError('Ожидается целое число')
        elif kind is not int:
            raise TypeError('Ожидается число')
        if not 0 <= index < len(self.items):
            raise IndexError('Индекс массива вне границ')
        return self.items[int(index)]

    _bsl_proc_get = _bsl_value_get


class ArrayMethods(BoxedArrayMethods):
    __slots__ = ()

    def __init__(self, value):
        super().__init__(value, BSLArray, list)
