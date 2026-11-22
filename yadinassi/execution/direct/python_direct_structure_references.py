"""Selected property addresses on restored canonical mutable Structures."""
from yadinassi.collections.structures import (
    _DIRECT_COLLECTION_CLASS_ABI, _DIRECT_FIXED_STRUCTURE_SNAPSHOT, _DIRECT_STRUCTURE_ADDRESS_ABI,
)
from yadinassi.execution.codegen.experimental_naked_boundaries import BoundaryViolation
from yadinassi.execution.codegen.experimental_naked_collections import _Reference
from yadinassi.execution.codegen.experimental_naked_structure import structure_key
from yadinassi.types.values import _DIRECT_COLLECTION_CLASS_ABI as _VALUE_ABI
from .python_direct_cells import check_local_reference


_BASE, _STRUCTURE = _DIRECT_COLLECTION_CLASS_ABI[:2]
STRUCTURE = _STRUCTURE[0]
_, _INSTANCE_DICT = _DIRECT_FIXED_STRUCTURE_SNAPSHOT
_READ = frozenset(('get', 'get_member'))
_WRITE = frozenset(('set', 'set_member'))


def _hooks(abi):
    cls, mro, fields = abi
    known = dict(fields)
    return cls, mro, tuple((name, known.get(name)) for name in (
        '_items', '_version', '__getattribute__', '__getattr__'))


_HOOKS = tuple(map(_hooks, (_VALUE_ABI[0], _BASE, _STRUCTURE)))


def _invalid():
    raise BoundaryViolation('canonical structure address storage or hooks changed')


def _storage(value, *, writing=False):
    if type(value) is not STRUCTURE:
        _invalid()
    for cls, mro, hooks in _HOOKS:
        current = vars(cls)
        if cls.__mro__ is not mro:
            _invalid()
        for name, expected in hooks:
            if current.get(name) is not expected:
                _invalid()
    for cls, name, method, code, defaults in _DIRECT_STRUCTURE_ADDRESS_ABI:
        if name not in (_WRITE if writing else _READ):
            continue
        if (vars(cls).get(name) is not method or method.__code__ is not code
                or method.__defaults__ is not defaults or method.__kwdefaults__ is not None
                or cls is not STRUCTURE and name in vars(STRUCTURE)):
            _invalid()
    state = _INSTANCE_DICT.__get__(value, STRUCTURE)
    if type(state) is not dict or len(state) != 2:
        _invalid()
    for name in state:
        if type(name) is not str:
            _invalid()
    items, version = state.get('_items'), state.get('_version')
    if type(items) is not dict or type(version) is not int or version < 0:
        _invalid()
    return items, version


class _StructureAddress(_Reference):
    __slots__ = ('context', 'vm', 'generation', 'owner', 'items', 'version', 'name', 'key')

    def __init__(self, context, owner, name):
        self.context, self.vm = context, context.vm
        self.generation = self.vm._family_generation
        check_local_reference(context,self.vm,self.generation)
        self.name, self.key, self.owner = name, structure_key(name), owner
        self.items, self.version = _storage(owner)
        self._selected()  # An absent field must fail before evaluating later actuals.

    def _live_storage(self, *, writing=False):
        check_local_reference(self.context,self.vm,self.generation)
        items, version = _storage(self.owner,writing=writing)
        if items is not self.items or version < self.version:
            _invalid()
        self.version = version

    def _selected(self):
        items = self.items
        # Composition is live: delete invalidates this name, insertion can
        # restore it. Before lookup reject non-string raw keys without hashing.
        for key in items:
            if type(key) is not str:
                _invalid()
        entry = items.get(self.key)
        if entry is None and self.key not in items:
            raise ValueError('Свойство структуры не найдено: '+self.name)
        if type(entry) is not tuple or len(entry) != 2 or type(entry[0]) is not str or entry[0].casefold() != self.key:
            _invalid()
        return entry

    @property
    def value(self):
        self._live_storage()
        return self._selected()[1]

    @value.setter
    def value(self, value):
        self._live_storage(writing=True)
        entry = self._selected()
        try:
            # Existing field replacement preserves its spelling/version.
            self.items[self.key] = (entry[0], value)
        finally:
            del entry  # Do not defer a replaced payload's finalizer past the lease check.
            self._live_storage(writing=True)


def local_member(context, owner, name):
    if context._verify_context or context.policy is not None:
        return context.reference_member(owner, name)
    return _StructureAddress(context, owner, name)
