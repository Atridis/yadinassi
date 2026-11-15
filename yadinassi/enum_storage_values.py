"""Internal declared-enum identity codec; no profile or runtime authority.

This is an explicit host encoding, not native UUID serialization. A domain is
only an immutable projection of declarations already admitted by its owner. It
does not admit source, bind an interpreter family, validate a database snapshot,
or authorize a write. Callers must perform those checks in their current owner
snapshot before using it. Runtime decoding must resolve the returned EnumKey
through that family's canonical enum manager, never manufacture a BSL reference.
"""
from dataclasses import dataclass, field
from uuid import UUID

from .catalog_backend import BackendError
from .configuration_enumerations import EnumDefinition, EnumValueDefinition


MAX_ENUMS = 128
MAX_ENUM_VALUES = 512
MAX_TOTAL_VALUES = 4096
_TAG = 'enum_ref_v1'
_EMPTY = UUID(int=0)


def _uuid(value, *, empty=False):
    if type(value) is not UUID:
        raise BackendError('invalid_input')
    try:
        integer = value.int
    except AttributeError:
        raise BackendError('invalid_input') from None
    if (type(integer) is not int or not 0 <= integer < 2**128
            or (not empty and not integer)):
        raise BackendError('invalid_input')
    return value


@dataclass(frozen=True, slots=True)
class EnumKey:
    """Stored identity, deliberately distinct from a catalog/document key."""
    database_id: UUID
    enum_id: UUID
    value_id: UUID

    def __post_init__(self):
        _uuid(self.database_id)
        _uuid(self.enum_id)
        _uuid(self.value_id, empty=True)


@dataclass(frozen=True, slots=True, init=False)
class EnumValueDomain:
    """Bounded declared identities, not a source grant or a live row proof.

    Names, presentations and generated InternalInfo type/value GUIDs have no
    role in this codec. The canonical source importer owns their validation.
    Empty declaration/value inventories are valid; an unknown target is not.
    """
    database_id: UUID
    declarations: tuple = field(repr=False)

    def __init__(self, database_id, definitions):
        _uuid(database_id)
        if type(definitions) is not tuple or len(definitions) > MAX_ENUMS:
            raise BackendError('invalid_input')
        identities, declarations, total = set(), [], 0
        for definition in definitions:
            if type(definition) is not EnumDefinition:
                raise BackendError('invalid_input')
            try:
                identity, values = definition.identity, definition.values
            except AttributeError:
                raise BackendError('invalid_input') from None
            identity = _uuid(identity)
            if identity in identities:
                raise BackendError('invalid_input')
            identities.add(identity)
            if type(values) is not tuple or len(values) > MAX_ENUM_VALUES:
                raise BackendError('invalid_input')
            total += len(values)
            if total > MAX_TOTAL_VALUES:
                raise BackendError('invalid_input')
            declared = []
            for value in values:
                if type(value) is not EnumValueDefinition:
                    raise BackendError('invalid_input')
                try:
                    value_id = value.identity
                except AttributeError:
                    raise BackendError('invalid_input') from None
                value_id = _uuid(value_id)
                if value_id in identities:
                    raise BackendError('invalid_input')
                identities.add(value_id)
                declared.append(value_id)
            declarations.append((identity, tuple(declared)))
        object.__setattr__(self, 'database_id', database_id)
        object.__setattr__(self, 'declarations', tuple(declarations))

    def _values(self, enum_id):
        _uuid(enum_id)
        for identity, values in self.declarations:
            if identity == enum_id:
                return values
        raise BackendError('invalid_input')

    def empty(self, enum_id):
        self._values(enum_id)
        return EnumKey(self.database_id, enum_id, _EMPTY)

    def require_key(self, key, enum_id):
        """Reject foreign/undeclared identities without conversion or hooks."""
        values = self._values(enum_id)
        if type(key) is not EnumKey:
            raise BackendError('invalid_input')
        # Check exact component types before equality/hash, even for a forged
        # dataclass created without its normal constructor.
        try:
            database, target, value = key.database_id, key.enum_id, key.value_id
        except AttributeError:
            raise BackendError('invalid_input') from None
        _uuid(database)
        _uuid(target)
        _uuid(value, empty=True)
        if (database != self.database_id or target != enum_id
                or (value.int and value not in values)):
            raise BackendError('invalid_input')
        return key

    def encode(self, key, enum_id):
        key = self.require_key(key, enum_id)
        return [_TAG, str(key.enum_id), str(key.value_id)]

    def decode(self, payload, enum_id):
        """Read strictly; malformed/noncanonical persisted data is integrity."""
        try:
            if (type(payload) is not list or len(payload) != 3
                    or any(type(value) is not str for value in payload)
                    or payload[0] != _TAG
                    or len(payload[1]) != 36 or len(payload[2]) != 36):
                raise BackendError('invalid_input')
            key = EnumKey(self.database_id, UUID(payload[1]), UUID(payload[2]))
            self.require_key(key, enum_id)
            if self.encode(key, enum_id) != payload:
                raise BackendError('invalid_input')
            return key
        except (BackendError, ValueError, TypeError, AttributeError):
            raise BackendError('integrity') from None
