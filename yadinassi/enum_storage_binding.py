"""Canonical enum storage binding, without admission or transaction authority."""
from dataclasses import dataclass, fields
from types import MethodType
from uuid import UUID

from .catalog_backend import BackendError
from .configuration_enumerations import EnumDefinition, EnumValueDefinition
from .enum_storage_values import EnumKey, EnumValueDomain, _uuid
from .enumerations import BSLEnumerations, BSLEnumManager, EnumMetadata
from .enum_types import BSLEnumReference, BSLEnumType
from .metadata import _DeclaredMetadataCollection


def _same(left, right):
    if type(left) is not type(right):
        return False
    if type(left) is str:
        return left == right
    if type(left) is UUID:
        _uuid(left, empty=True); _uuid(right, empty=True)
        return left.int == right.int
    if type(left) is tuple:
        return len(left) == len(right) and all(_same(a, b) for a, b in zip(left, right))
    if type(left) in (EnumDefinition, EnumValueDefinition):
        return all(_same(getattr(left, f.name), getattr(right, f.name)) for f in fields(left))
    return False


def _mapping(value):
    if type(value) is not dict or any(type(k) is not str for k in value):
        raise BackendError('invalid_input')
    return value


@dataclass(frozen=True, slots=True, init=False)
class EnumStorageBinding:
    """Owner supplies a bound lifetime guard; every operation invokes it first.

    Definitions must already have passed the owner's canonical source admission.
    This bridge neither imports source nor confers root/context/write authority.
    Only existing namespace-owned references/types can cross its boundary.
    """
    _domain: object
    _namespace: object
    _snapshot: object
    _entries: tuple
    _hook: object
    _hook_owner: object
    _hook_function: object

    def __init__(self, domain, definitions, namespace, *, require_live):
        if type(require_live) is not MethodType:
            raise BackendError('invalid_input')
        require_live()
        if type(domain) is not EnumValueDomain or type(namespace) is not BSLEnumerations:
            raise BackendError('invalid_input')
        rebuilt = EnumValueDomain(domain.database_id, definitions)
        if not _same(rebuilt.declarations, domain.declarations):
            raise BackendError('invalid_input')
        snapshot = namespace.metadata
        if type(snapshot) is not _DeclaredMetadataCollection:
            raise BackendError('invalid_input')
        managers, metadata = _mapping(namespace._managers), _mapping(snapshot._items)
        if len(managers) != len(definitions) or len(metadata) != len(definitions):
            raise BackendError('invalid_input')
        entries = []
        for definition in definitions:
            # Validate full declared payload without dataclass/user equality.
            if not _same(definition, definition) or type(definition.name) is not str:
                raise BackendError('invalid_input')
            name = definition.name.casefold()
            manager, meta = managers.get(name), metadata.get(name)
            if (type(manager) is not BSLEnumManager or type(meta) is not EnumMetadata
                    or manager._metadata is not meta or not _same(definition, meta._definition)
                    or type(manager._values) is not tuple or len(manager._values) != len(definition.values)):
                raise BackendError('invalid_input')
            value_type = manager._value_type
            if (type(value_type) is not BSLEnumType or value_type.snapshot is not snapshot
                    or not _same(definition.identity, value_type.metadata_uuid)
                    or type(value_type.family) is not str or value_type.family != 'ref'
                    or not _same(definition.name, value_type.name)):
                raise BackendError('invalid_input')
            manager_type = manager._manager_type
            if (type(manager_type) is not BSLEnumType or manager_type.snapshot is not snapshot
                    or not _same(definition.identity, manager_type.metadata_uuid)
                    or type(manager_type.family) is not str or manager_type.family != 'manager'
                    or not _same(definition.name, manager_type.name)):
                raise BackendError('invalid_input')
            named = _mapping(manager._named)
            if len(named) != len(definition.values) or any(
                    named.get(v.name.casefold()) is not r for v, r in zip(definition.values, manager._values)):
                raise BackendError('invalid_input')
            references = (manager._empty, *manager._values)
            identities = (UUID(int=0), *(v.identity for v in definition.values))
            expected_presentations = (None, *(None if any(lang.casefold() == 'ru' for lang, _ in v.synonyms)
                                              else v.name for v in definition.values))
            for reference, identity, expected in zip(references, identities, expected_presentations):
                if (type(reference) is not BSLEnumReference or reference.value_type is not value_type
                        or reference.metadata is not meta or not _same(identity, reference.reference_uuid)
                        or not (reference.presentation is None if expected is None else _same(reference.presentation, expected))):
                    raise BackendError('invalid_input')
            entries.append((definition.identity, name, manager, meta, meta._definition,
                            value_type, manager._values, references, identities,
                            tuple(r.presentation for r in references), definition.name, manager_type,
                            tuple(v.name.casefold() for v in definition.values)))
        for name, value in (('_domain', domain), ('_namespace', namespace), ('_snapshot', snapshot),
                            ('_entries', tuple(entries)), ('_hook', require_live),
                            ('_hook_owner', require_live.__self__), ('_hook_function', require_live.__func__)):
            object.__setattr__(self, name, value)

    def _live(self):
        hook = self._hook
        if (type(hook) is not MethodType or hook.__self__ is not self._hook_owner
                or hook.__func__ is not self._hook_function):
            raise BackendError('closed')
        hook()
        self._require_namespace()

    def _require_detached(self):
        """Integrity/owner only; detached report operations acquire no lease."""
        from .inventory_enum_runtime import _EnumScope
        hook = self._hook
        if (type(hook) is not MethodType or type(self._hook_owner) is not _EnumScope
                or hook.__self__ is not self._hook_owner
                or hook.__func__ is not _EnumScope.require_live
                or self._hook_function is not _EnumScope.require_live):
            raise BackendError('closed')
        self._hook_owner._require_owner()
        self._require_namespace()

    def _require_namespace(self):
        namespace = self._namespace
        if namespace.metadata is not self._snapshot:
            raise BackendError('closed')
        managers = _mapping(namespace._managers)
        metadata = _mapping(self._snapshot._items)
        if len(managers) != len(self._entries) or len(metadata) != len(self._entries):
            raise BackendError('closed')
        for enum_id, name, manager, meta, definition, typ, values, refs, ids, presentations, type_name, manager_type, value_names in self._entries:
            if (managers.get(name) is not manager or metadata.get(name) is not meta
                    or manager._metadata is not meta or meta._definition is not definition
                    or manager._value_type is not typ or manager._values is not values
                    or manager._empty is not refs[0] or typ.snapshot is not self._snapshot
                    or not _same(typ.name, type_name) or manager._manager_type is not manager_type
                    or manager_type.snapshot is not self._snapshot
                    or not _same(manager_type.metadata_uuid, enum_id)
                    or not _same(manager_type.name, type_name)
                    or type(manager_type.family) is not str or manager_type.family != 'manager'
                    or not _same(typ.metadata_uuid, enum_id) or type(typ.family) is not str or typ.family != 'ref'):
                raise BackendError('closed')
            named = _mapping(manager._named)
            if len(named) != len(value_names) or any(named.get(n) is not r for n, r in zip(value_names, refs[1:])):
                raise BackendError('closed')
            for ref, identity, presentation in zip(refs, ids, presentations):
                if (ref.value_type is not typ or ref.metadata is not meta
                        or not _same(ref.reference_uuid, identity) or ref.presentation is not presentation):
                    raise BackendError('closed')

    def _entry(self, enum_id):
        _uuid(enum_id)
        for entry in self._entries:
            if entry[0] == enum_id:
                return entry
        raise BackendError('invalid_input')

    def key(self, value, enum_id):
        self._live()
        entry = self._entry(enum_id)
        if type(value) is not BSLEnumReference:
            raise BackendError('invalid_input')
        for reference, identity in zip(entry[7], entry[8]):
            if value is reference:
                return self._domain.require_key(EnumKey(self._domain.database_id, enum_id, identity), enum_id)
        raise BackendError('invalid_input')

    def owned_key(self, value):
        """Strict query parameter admission; never adjust a different enum."""
        self._live()
        if type(value) is not BSLEnumReference:raise BackendError('invalid_input')
        for entry in self._entries:
            for reference,identity in zip(entry[7],entry[8]):
                if value is reference:
                    return EnumKey(self._domain.database_id,entry[0],identity)
        raise BackendError('invalid_input')

    def assigned(self, value, enum_id):
        """Measured format16 assignment adjustment, never a storage decoder.

        Foreign/fabricated enum objects are rejected before coercion. Only
        canonical owned other-enum values and measured ordinary scalar kinds
        adjust to the target's canonical typed empty.
        """
        from decimal import Decimal
        from .catalog_qualifiers import bound_number
        self._live()
        target=self._entry(enum_id)
        if type(value) is BSLEnumReference:
            # Membership scan avoids trusting even a fabricated type/UUID.
            for entry in self._entries:
                if any(value is reference for reference in entry[7]):
                    return value if entry[0] == enum_id else target[7][0]
            raise BackendError('invalid_input')
        if value is None:return target[7][0]
        if type(value) is str:
            if len(value)>4096:raise BackendError('invalid_input')
            return target[7][0]
        if type(value) is Decimal:
            try:bound_number(value)
            except (ValueError,TypeError):raise BackendError('invalid_input') from None
            return target[7][0]
        raise BackendError('invalid_input')

    def value(self, key, enum_id):
        self._live()
        entry = self._entry(enum_id)
        key = self._domain.require_key(key, enum_id)
        for reference, identity in zip(entry[7], entry[8]):
            if key.value_id == identity:
                return reference
        raise BackendError('invalid_input')

    def value_type(self, enum_id):
        self._live()
        return self._entry(enum_id)[5]
