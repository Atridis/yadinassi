"""Live absolute positions for exact detached arrays at known local calls."""
from decimal import Decimal

from yadinassi.types.values import _DIRECT_ARRAY_TYPE as ARRAY
from yadinassi.types.values import _DIRECT_ARRAY_ADDRESS_ABI, _DIRECT_COLLECTION_CLASS_ABI
from yadinassi.execution.codegen.experimental_naked_boundaries import BoundaryViolation
from yadinassi.execution.codegen.experimental_naked_collections import _Reference, _checked_array_index
from .python_direct_cells import check_local_reference


_BASE, _ARRAY_BASE, _ARRAY = _DIRECT_COLLECTION_CLASS_ABI[:3]
_INSTANCE_DICT = dict(_BASE[2])['__dict__']
def _hooks(abi):
    cls, mro, fields = abi
    known = dict(fields)
    return cls, mro, tuple((name, known.get(name)) for name in ('items', '__getattribute__', '__getattr__'))


_HOOKS = tuple(map(_hooks, (_BASE, _ARRAY_BASE, _ARRAY)))


def _invalid():
    raise BoundaryViolation('canonical array address storage or hooks changed')


def _items(array, *, writing=False):
    if type(array) is not ARRAY:
        _invalid()
    for cls, mro, hooks in _HOOKS:
        current = vars(cls)
        if cls.__mro__ is not mro:
            _invalid()
        for name, expected in hooks:
            if current.get(name) is not expected:
                _invalid()
    # Inspect raw descriptors; never invoke a replacement class method.
    for cls, name, method, code, defaults in _DIRECT_ARRAY_ADDRESS_ABI:
        if name in (('get', 'get_index') if writing else ('set', 'set_index')):
            continue
        if (vars(cls).get(name) is not method or method.__code__ is not code
                or method.__defaults__ is not defaults or cls is not ARRAY and name in vars(ARRAY)):
            _invalid()
        keywords = method.__kwdefaults__
        if name == 'checked_index':
            if type(keywords) is not dict or len(keywords) != 1:
                _invalid()
            key, value = next(iter(keywords.items()))
            if type(key) is not str or key != 'inserting' or value is not False:
                _invalid()
        elif keywords is not None:
            _invalid()
    fields = _INSTANCE_DICT.__get__(array, ARRAY)
    # One legitimate field; inspect key type before any dict lookup.
    if type(fields) is not dict or len(fields) != 1:
        _invalid()
    name, items = next(iter(fields.items()))
    if type(name) is not str or name != 'items' or type(items) is not list:
        _invalid()
    return items


class _ArrayAddress(_Reference):
    __slots__ = ('context', 'vm', 'generation', 'array', 'items', 'offset')

    def __init__(self, context, array, key):
        self.context, self.vm = context, context.vm
        self.generation = self.vm._family_generation
        self._live()
        self.array, self.items = array, _items(array)
        # The accepted numeric position is immutable. Its contents and live
        # bounds may change, but the address is never retargeted to a new list.
        if type(key) is Decimal and key.is_infinite():
            int(key)  # Preserve the canonical BSLArray overflow diagnostic.
        self.offset = _checked_array_index(self.items, key)

    def _live(self):
        check_local_reference(self.context,self.vm,self.generation)

    def _check(self, *, writing=False):
        self._live()
        if _items(self.array, writing=writing) is not self.items:
            _invalid()
        if self.offset >= len(self.items):
            raise IndexError(f'Индекс массива вне границ: {self.offset}')

    @property
    def value(self):
        self._check()
        return list.__getitem__(self.items, self.offset)

    @value.setter
    def value(self, value):
        self._check(writing=True)
        try:
            list.__setitem__(self.items, self.offset, value)
        finally:
            # Replacing an opaque item can run a Python finalizer.
            self._live()
            if _items(self.array, writing=True) is not self.items:
                _invalid()


class _GuardedArrayAddress(_ArrayAddress):
    __slots__ = ()

    def _live(self):
        self.context._check_effect()
        super()._live()


def local_index(context, array, key):
    if context.policy is not None:
        return context.reference_index(array, key)
    if context._verify_context:
        # A known local BSL routine can borrow the same canonical boxed array
        # slot in a guarded interpreter. Arbitrary host ByRef stays unchanged.
        return _GuardedArrayAddress(context, array, key)
    return _ArrayAddress(context, array, key)
