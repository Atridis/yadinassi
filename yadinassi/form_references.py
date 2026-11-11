"""Explicit form-only catalog identities. No generic invocation/native codec grant.

Bindings and descriptors are trusted Python infrastructure, never BSL constructors.
Client replicas have presentation/empty/equality only, not UUIDs or object readers.
"""
from dataclasses import dataclass, field
from secrets import token_hex
import re

from .catalog_types import BSLCatalogReference, BSLCatalogType
from .values import BSLObject, HostFunction

_MAX_TEXT = 1024
_MAX_IDENTITIES = 4096
_MISSING = object()


def _text(value):
    if type(value) is not str or len(value) > _MAX_TEXT or '\x00' in value:
        raise ValueError('bounded reference presentation required')
    return value


@dataclass(frozen=True)
class FormReferenceBinding:
    value_type: BSLCatalogType
    empty: BSLCatalogReference
    validate: object
    presentation: object

    def __post_init__(self):
        if (type(self.value_type) is not BSLCatalogType or self.value_type.family != 'ref'
                or type(self.empty) is not BSLCatalogReference or self.empty.value_type != self.value_type
                or not self.empty.is_empty() or not callable(self.validate) or not callable(self.presentation)):
            raise TypeError('host-owned catalog binding required')


@dataclass(frozen=True, eq=False)
class FormCatalogReference(BSLObject):
    _scope: object = field(repr=False)
    target: int
    key: str | None
    presentation: str

    def __eq__(self, other):
        return (type(other) is FormCatalogReference and self._scope is other._scope
                and self.target == other.target and self.key == other.key)

    def __hash__(self):
        return hash((id(self._scope), self.target, self.key))

    def __str__(self):
        return self.presentation

    def is_empty(self):
        return self.key is None

    def get_member(self, name):
        if name.casefold() in ("isempty", "пустая"):
            return HostFunction(name, self.is_empty)
        # No inherited reader, UUID, metadata snapshot or GetObject capability.
        raise ValueError('client form reference has no object or UUID access')


@dataclass(frozen=True)
class FormReferenceDescriptor:
    scope: object = field(repr=False)
    target: int

    def __post_init__(self):
        if type(self.scope) is not FormReferenceScope or self.target not in self.scope.targets:
            raise ValueError('registered form reference target required')

    def adjust_value(self, value=_MISSING):
        return self.scope.adjust(self.target, value)


class FormReferenceScope:
    def __init__(self, *, bindings=None, targets=None):
        self.server = bindings is not None
        source = bindings if self.server else targets
        if type(source) is not dict or not 1 <= len(source) <= 128:
            raise ValueError('bounded explicit reference inventory required')
        if any(type(k) is not int or not 1 <= k <= 128 for k in source):
            raise ValueError('numeric reference target required')
        if self.server and any(type(v) is not FormReferenceBinding for v in source.values()):
            raise TypeError('host reference bindings required')
        if not self.server:
            for value in source.values(): _text(value)
        self.targets = dict(source)
        self.identity = token_hex(16) if self.server else None
        self._issued = {}; self._keys = {}; self._client = {}; self._client_values = {}
        self._owner = None

    def attach(self, owner):
        if self._owner is not None and self._owner is not owner:
            raise ValueError('reference scope already belongs to another form')
        self._owner = owner

    def descriptor(self, target):
        return FormReferenceDescriptor(self, target)

    def adjust(self, target, value=_MISSING):
        if target not in self.targets: raise ValueError('unknown reference target')
        if self.server:
            binding = self.targets[target]
            if value is _MISSING: value = binding.empty
            if type(value) is not BSLCatalogReference:
                raise ValueError('foreign reference type/snapshot')
            canonical = binding.validate(value)
            if (type(canonical) is not BSLCatalogReference or canonical.value_type != binding.value_type
                    or canonical.reference_uuid != value.reference_uuid):
                raise ValueError('reference ownership validation failed')
            return canonical
        if value is _MISSING:
            value = self._client.get((target, None))
        if (type(value) is not FormCatalogReference or value._scope is not self
                or value.target != target or self._client_values.get(id(value)) is not value):
            raise ValueError('unissued client reference')
        return value

    def encode(self, target, value):
        value = self.adjust(target, value)
        if self.server:
            identity = (target, value.reference_uuid)
            if value.is_empty(): key = None
            elif identity in self._keys: key = self._keys[identity]
            else:
                if len(self._keys) >= _MAX_IDENTITIES: raise ValueError('reference identity limit')
                key = token_hex(16); self._keys[identity] = key
            presentation = _text(self.targets[target].presentation(value))
            if key is None and presentation != '':
                raise ValueError('empty reference presentation must be empty')
            self._issued[(target, key)] = value
        else: key, presentation = value.key, value.presentation
        return {'type':'FormCatalogRef','scope':self.identity,'target':target,'key':key,'text':presentation}

    def decode(self, target, packet):
        if (type(packet) is not dict or set(packet) != {'type','scope','target','key','text'}
                or packet['type'] != 'FormCatalogRef' or type(packet['target']) is not int
                or packet['target'] != target or target not in self.targets
                or type(packet['scope']) is not str or not re.fullmatch('[0-9a-f]{32}', packet['scope'])
                or packet['key'] is not None and (type(packet['key']) is not str or not re.fullmatch('[0-9a-f]{32}', packet['key']))):
            raise ValueError('invalid scoped reference packet')
        presentation = _text(packet['text'])
        if packet['key'] is None and presentation != '':
            raise ValueError('empty reference presentation must be empty')
        if self.identity is not None and packet['scope'] != self.identity:
            raise ValueError('foreign reference scope')
        if self.server:
            value = self._issued.get((target,packet['key']))
            if value is None or self.encode(target,value) != packet:
                raise ValueError('unissued or modified reference')
            return value
        self.identity = packet['scope']
        key = (target,packet['key'])
        old = self._client.get(key)
        if old is not None and old.presentation == presentation: return old
        if old is None and len(self._client) >= _MAX_IDENTITIES + len(self.targets):
            raise ValueError('reference identity limit')
        value = FormCatalogReference(self,target,packet['key'],presentation)
        if len(self._client_values) >= _MAX_IDENTITIES * 2:
            raise ValueError("reference presentation allocation limit")
        self._client[key] = value
        self._client_values[id(value)] = value
        return value


def is_reference(kind):
    return type(kind) is FormReferenceDescriptor


def adjust(kind, value=_MISSING):
    if is_reference(kind): return kind.adjust_value(value)
    from .form_model import scalar
    return scalar(kind.adjust_value()) if value is _MISSING else scalar(kind.adjust_value(scalar(value)))


def encode(kind, value, scalar_encoder):
    return kind.scope.encode(kind.target,value) if is_reference(kind) else scalar_encoder(value)


def decode(kind, packet, scalar_decoder):
    return kind.scope.decode(kind.target,packet) if is_reference(kind) else scalar_decoder(packet)


def require_scope(kind, session):
    if is_reference(kind) and kind.scope is not session.reference_scope:
        raise ValueError('descriptor belongs to another form reference scope')
