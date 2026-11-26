"""A live address for an element of the compiler's native list."""
from yadinassi.types.array_index import array_offset
from .direct_collections import _Reference


class ArrayElementAddress(_Reference):
    __slots__ = ('array', 'offset')

    def __init__(self, array, key):
        self.array = array
        self.offset = array_offset(array, key)

    @property
    def value(self):
        try:
            return self.array[self.offset]
        except IndexError:
            raise IndexError(f'Индекс массива вне границ: {self.offset}') from None

    @value.setter
    def value(self, value):
        try:
            self.array[self.offset] = value
        except IndexError:
            raise IndexError(f'Индекс массива вне границ: {self.offset}') from None
