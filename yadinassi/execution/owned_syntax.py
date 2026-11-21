"""Experimental immutable syntax ownership; not a Python sandbox.

Literal payloads retain their identity. Original objects are provenance handles,
not fields read during owned execution. Normal mutation of owned syntax rejects;
unrestricted Python can bypass object protocols and is outside this contract.
"""
from dataclasses import fields
import weakref
import os
from yadinassi.syntax import ast


def _immutable(*args, **kwargs):
    raise TypeError('owned compiled syntax is immutable')


class OwnedList(list):
    __slots__ = ('__weakref__', '_owned_provenance')
    __init__ = _immutable
    __setattr__ = __delattr__ = _immutable
    __setitem__ = __delitem__ = append = extend = insert = clear = pop = remove = sort = reverse = _immutable
    __iadd__ = __imul__ = _immutable

    def __copy__(self):
        return self

    def __deepcopy__(self, memo):
        memo[id(self)] = self
        return self


def _copy_owned(self):
    return self


def _deepcopy_owned(self, memo):
    # Syntax is immutable; Literal payloads deliberately retain host identity.
    memo[id(self)] = self
    return self


_CLASSES = {}
_PRIVATE_KINDS = {}
for _kind in vars(ast).values():
    if isinstance(_kind, type) and _kind is not ast.Node and issubclass(_kind, ast.Node):
        _private = type(_kind.__name__, (_kind,), {
            '__module__': __name__, '__slots__': ('_owned_provenance',),
            '__setattr__': _immutable, '__delattr__': _immutable,
            '__copy__': _copy_owned, '__deepcopy__': _deepcopy_owned,
        })
        _CLASSES[_kind] = _private
        _PRIVATE_KINDS[id(_private)] = (_private, _kind)
del _kind, _private


_EXPERIMENT_PID = None


def enable_isolated_process_experiment():
    """Explicit developer-only capability; never a CLI/backend default.

    The launcher must create a disposable isolated subprocess and set this
    acknowledgement there. This API cannot prove OS process isolation itself.
    It records the PID so a fork cannot silently inherit the capability.
    """
    global _EXPERIMENT_PID
    if os.environ.get('YADINASSI_OWNED_IR_EXPERIMENT') != 'isolated-process-v1':
        raise RuntimeError('owned IR experiment requires an explicitly isolated subprocess')
    _EXPERIMENT_PID = os.getpid()


def require_experiment():
    if _EXPERIMENT_PID != os.getpid():
        raise RuntimeError('owned IR experiment is not enabled for this isolated process')


def install_seal():
    """Compatibility no-op; private node classes require no process-wide seal."""
    return None


# A closed registry prevents an arbitrary object claiming an origin attribute.
# Weak ownership avoids retaining completed units through this provenance map.
_ORIGINS = {}


def _record(value, origin, fingerprint_kind, fingerprint):
    identity = id(value)
    def forgotten(reference):
        entry = _ORIGINS.get(identity)
        if entry is not None and entry is reference:
            del _ORIGINS[identity]
    # Keep authority on the collectable view graph, never on a global root.
    # Literal payloads may themselves point back to this view.
    object.__setattr__(value, '_owned_provenance', (origin, fingerprint_kind, fingerprint))
    _ORIGINS[identity] = weakref.ref(value, forgotten)


def syntax_kind(value):
    kind = type(value)
    entry = _PRIVATE_KINDS.get(id(kind))
    if entry is not None and entry[0] is kind:
        # The exact private kind is already checked above. Still verify the live
        # weak registration; unrecorded/fabricated private instances stay foreign.
        origin = _ORIGINS.get(id(value))
        if origin is not None and origin() is value:
            return entry[1]
    return kind


def is_owned(value):
    kind = type(value)
    private = _PRIVATE_KINDS.get(id(kind))
    if kind is not OwnedList and (private is None or private[0] is not kind):
        return False
    entry = _ORIGINS.get(id(value))
    return entry is not None and entry() is value


def owned_provenance(value):
    """Return provenance after one current owned-identity check, never cache it."""
    if not is_owned(value):
        return None
    return object.__getattribute__(value, '_owned_provenance')


def origin_node(value):
    if not is_owned(value):
        return value
    return object.__getattribute__(value, '_owned_provenance')[0]


def creation_fingerprint(value):
    if not is_owned(value):
        return None
    entry = object.__getattribute__(value, '_owned_provenance')
    return entry[1], entry[2]


class AdmissionMap:
    """Per-admission write journal; base mappings stay untouched until commit.

    Nested journals commit into their parent's journal, so outer rejection also
    discards successful nested writes. Keys are internal integer identities.
    """
    _DELETED = object()

    def __init__(self, base):
        self.base = base
        self.changes = {}
        self.cleared = False
        self._size = len(base)

    def get(self, key, default=None):
        if key in self.changes:
            value = self.changes[key]
            return default if value is self._DELETED else value
        return default if self.cleared else self.base.get(key, default)

    def __getitem__(self, key):
        value = self.get(key, self._DELETED)
        if value is self._DELETED: raise KeyError(key)
        return value

    def __setitem__(self, key, value):
        if key not in self: self._size += 1
        self.changes[key] = value

    def __contains__(self, key):
        return self.get(key, self._DELETED) is not self._DELETED

    def pop(self, key, default=None):
        value = self.get(key, self._DELETED)
        if value is self._DELETED: return default
        self.changes[key] = self._DELETED
        self._size -= 1
        return value

    def clear(self):
        self.changes.clear()
        self.cleared = True
        self._size = 0

    def __iter__(self):
        if not self.cleared:
            for key in self.base:
                if key not in self.changes: yield key
        for key, value in self.changes.items():
            if value is not self._DELETED: yield key

    def __len__(self):
        return self._size

    def update(self, values):
        for key, value in values.items(): self[key] = value

    def values(self):
        return (self[key] for key in self)

    def items(self):
        return ((key, self[key]) for key in self)

    def commit(self):
        if self.cleared: self.base.clear()
        for key, value in self.changes.items():
            if value is self._DELETED: self.base.pop(key, None)
            else: self.base[key] = value


class OwnedStore:
    def __init__(self, node_signature, block_signature):
        self.memo = {}
        self.versions = {}
        self.node_signature = node_signature
        self.block_signature = block_signature

    def clear(self):
        self.memo.clear()
        self.versions.clear()

    def existing(self, value):
        if is_owned(value):
            return value
        entry = self.memo.get(id(value))
        return entry[1] if entry is not None and entry[0] is value else None

    def freeze(self, value):
        existing = self.existing(value)
        if existing is not None:
            if is_owned(value):
                original = origin_node(value)
                self.versions[id(value)] = (original, value)
                if id(original) not in self.memo:
                    self.memo[id(original)] = (original, value)
                    if isinstance(value, ast.Node):
                        for field in fields(value):
                            if field.name != 'token' and not (syntax_kind(value) is ast.Literal and field.name == 'value'):
                                self.freeze(getattr(value, field.name))
                    else:
                        for item in value: self.freeze(item)
            return existing
        kind = type(value)
        if kind in _CLASSES or kind is list:
            install_seal()
        if kind in _CLASSES:
            result = object.__new__(_CLASSES[kind])
            self.memo[id(value)] = (value, result)
            self.versions[id(result)] = (value, result)
            _record(result, value, 'node', self.node_signature(value))
            for field in fields(value):
                original = getattr(value, field.name)
                # Token is already frozen; Literal payload is deliberately opaque.
                frozen = original if field.name == 'token' or (kind is ast.Literal and field.name == 'value') else self.freeze(original)
                object.__setattr__(result, field.name, frozen)
            return result
        if kind is list:
            result = list.__new__(OwnedList)
            self.memo[id(value)] = (value, result)
            self.versions[id(result)] = (value, result)
            _record(result, value, 'block', self.block_signature(value))
            list.extend(result, (self.freeze(item) for item in value))
            return result
        if kind is tuple:
            result = tuple(self.freeze(item) for item in value)
            self.memo[id(value)] = (value, result)
            return result
        return value
